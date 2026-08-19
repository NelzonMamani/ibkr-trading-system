from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import importlib
import importlib.util
import json
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from src.config.config_resolver import get_config
from src.news.news_fetcher import symbol_relevance_match
from src.news.rss_registry import RSS_FAST_TRADING

if importlib.util.find_spec("requests"):
    requests = importlib.import_module("requests")  # type: ignore
else:
    requests = None

if importlib.util.find_spec("feedparser"):
    feedparser = importlib.import_module("feedparser")  # type: ignore
else:
    feedparser = None

CATALYST_PATTERNS: dict[str, tuple[str, ...]] = {
    "earnings": ("earnings", "eps", "guidance"),
    "offering": ("offering", "registered direct", "atm", "dilution", "s-1"),
    "fda_clinical": ("fda", "clinical", "trial", "phase 1", "phase 2", "phase 3"),
    "contract_order": ("contract", "order", "award"),
    "partnership": ("partnership", "collaboration", "joint venture"),
    "acquisition_merger": ("acquisition", "merger", "buyout"),
    "guidance": ("guidance", "outlook", "forecast"),
    "upgrade_analyst": ("upgrade", "downgrade", "analyst"),
    "sector_sympathy": ("sector", "sympathy", "theme", "thematic"),
}

@dataclass
class NewsItem:
    title: str
    source: str
    published_at: str
    url: str
    age_hours: float
    freshness: str
    catalyst_tag: str

@dataclass
class NewsResult:
    symbol: str
    fetched_at: str
    source_mode: str
    diagnostics: dict[str, Any] = field(default_factory=dict)
    news_context: list[dict[str, Any]] = field(default_factory=list)

class NewsProvider:
    def __init__(self) -> None:
        self.cache_file = Path(str(get_config("NEWS_CACHE_FILE")))
        self.max_age_hours = float(get_config("NEWS_MAX_AGE_HOURS"))
        self.timeout_s = float(get_config("NEWS_REQUEST_TIMEOUT_S"))
        self.cache = self._load_cache()

    def get_news(self, symbol: str) -> NewsResult:
        symbol = symbol.upper().strip()
        now = datetime.now(timezone.utc)
        if not symbol:
            return NewsResult(symbol="", fetched_at=now.isoformat(), source_mode="invalid")
        cached = (self.cache.get("symbols") or {}).get(symbol)
        if isinstance(cached, dict):
            fetched_at = _parse_iso(cached.get("fetched_at"))
            if fetched_at and (now - fetched_at) <= timedelta(seconds=int(get_config("NEWS_REFRESH_SECONDS_PREP"))):
                print(f"[NEWS][CACHE_HIT] symbol={symbol}")
                return NewsResult(**cached)

        result = self._fetch_symbol(symbol, now)
        self.cache.setdefault("symbols", {})[symbol] = asdict(result)
        self.cache["updated_at"] = now.isoformat()
        self._write_cache()
        print(f"[NEWS][CACHE_WRITE] symbol={symbol} count={len(result.news_context)}")
        return result

    def get_news_batch(self, symbols: list[str]) -> dict[str, NewsResult]:
        return {s.upper(): self.get_news(s) for s in symbols if s}

    def _fetch_symbol(self, symbol: str, now: datetime) -> NewsResult:
        entries: list[dict[str, Any]] = []
        diagnostics = {"rss_sources": len(RSS_FAST_TRADING), "errors": []}
        source_mode = "feedparser" if feedparser is not None else "xml_fallback"
        for url in RSS_FAST_TRADING:
            try:
                for item in self._fetch_entries(url):
                    title = str(item.get("title") or "").strip()
                    if not title or not _title_mentions_symbol(title, symbol):
                        continue
                    published = _parse_iso(str(item.get("published_at") or "")) or now
                    age_hours = round(max((now - published).total_seconds(), 0.0) / 3600.0, 3)
                    freshness = "fresh" if age_hours <= self.max_age_hours else "stale"
                    entries.append(asdict(NewsItem(
                        title=title,
                        source=str(item.get("source") or url),
                        published_at=published.isoformat(),
                        url=str(item.get("url") or ""),
                        age_hours=age_hours,
                        freshness=freshness,
                        catalyst_tag=_classify_catalyst(title),
                    )))
            except Exception as exc:
                diagnostics["errors"].append(f"{url}:{type(exc).__name__}")
        entries.sort(key=lambda r: r.get("published_at", ""), reverse=True)
        entries = entries[: int(get_config("NEWS_MAX_ENTRIES_PER_SYMBOL"))]
        print(f"[NEWS][DISCOVERY] symbol={symbol} headlines={len(entries)} source_mode={source_mode}")
        return NewsResult(symbol=symbol, fetched_at=now.isoformat(), source_mode=source_mode, diagnostics=diagnostics, news_context=entries)

    def _fetch_entries(self, url: str) -> list[dict[str, Any]]:
        if requests is None:
            return []
        response = requests.get(url, timeout=self.timeout_s)
        response.raise_for_status()
        body = response.text
        if feedparser is not None:
            parsed = feedparser.parse(body)
            source = (parsed.feed.get("title") or url) if getattr(parsed, "feed", None) else url
            return [{
                "title": getattr(entry, "title", ""),
                "url": getattr(entry, "link", ""),
                "published_at": _normalize_pub_date(getattr(entry, "published", "") or getattr(entry, "updated", "") or ""),
                "source": source,
            } for entry in (getattr(parsed, "entries", []) or [])]
        root = ET.fromstring(body)
        return [{
            "title": (item.findtext("title") or "").strip(),
            "url": (item.findtext("link") or "").strip(),
            "published_at": _normalize_pub_date(item.findtext("pubDate") or ""),
            "source": url,
        } for item in root.findall('.//item')]

    def _load_cache(self) -> dict[str, Any]:
        if not self.cache_file.exists():
            return {"symbols": {}, "updated_at": None}
        try:
            return json.loads(self.cache_file.read_text(encoding="utf-8"))
        except Exception:
            return {"symbols": {}, "updated_at": None}

    def _write_cache(self) -> None:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(json.dumps(self.cache, indent=2), encoding="utf-8")

def _classify_catalyst(title: str) -> str:
    lower = title.lower()
    for tag, terms in CATALYST_PATTERNS.items():
        if any(term in lower for term in terms):
            return tag
    return "generic"

def _title_mentions_symbol(title: str, symbol: str) -> bool:
    return symbol_relevance_match(symbol, title=title) is not None

def _normalize_pub_date(raw: str) -> str:
    dt = _parse_iso(raw)
    if dt:
        return dt.isoformat()
    try:
        from email.utils import parsedate_to_datetime
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()

def _parse_iso(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None
