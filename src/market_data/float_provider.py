"""Float provider with ordered fallbacks and daily caching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class FloatRecord:
    symbol: str
    raw: Optional[int]
    formatted: str
    source: str
    fetched_at: Optional[str]
    cache_hit: bool


class FloatProvider:
    def __init__(self, cache_path: str = "data/cache/float_cache.json") -> None:
        self.cache_path = Path(cache_path)

    def get_float(self, symbol: str, session_date: str) -> FloatRecord:
        symbol = symbol.upper()
        cache = self._load_cache()
        cached = cache.get(session_date, {}).get(symbol)
        if cached:
            return FloatRecord(
                symbol=symbol,
                raw=int(cached.get("raw") or 0) or None,
                formatted=str(cached.get("formatted") or "NA"),
                source=str(cached.get("source") or "cache"),
                fetched_at=str(cached.get("fetched_at") or ""),
                cache_hit=True,
            )

        fetched_at = datetime.now(timezone.utc).isoformat()
        for source_name, fetcher in [
            ("YAHOO", self._fetch_yahoo),
            ("FINVIZ", self._fetch_finviz),
            ("NASDAQ", self._fetch_nasdaq),
            ("IB", self._fetch_ib_cache),
        ]:
            raw = fetcher(symbol)
            if raw:
                formatted = _format_float(raw)
                self._write_cache(cache, session_date, symbol, raw, formatted, source_name, fetched_at)
                return FloatRecord(
                    symbol=symbol,
                    raw=raw,
                    formatted=formatted,
                    source=source_name,
                    fetched_at=fetched_at,
                    cache_hit=False,
                )

        return FloatRecord(
            symbol=symbol,
            raw=None,
            formatted="NA",
            source="unavailable",
            fetched_at=fetched_at,
            cache_hit=False,
        )

    def _load_cache(self) -> Dict[str, Any]:
        if not self.cache_path.exists():
            return {}
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_cache(
        self,
        cache: Dict[str, Any],
        session_date: str,
        symbol: str,
        raw: int,
        formatted: str,
        source: str,
        fetched_at: str,
    ) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache.setdefault("_meta", {"version": 1})
        cache.setdefault(session_date, {})[symbol] = {
            "raw": raw,
            "formatted": formatted,
            "source": source,
            "fetched_at": fetched_at,
        }
        self.cache_path.write_text(json.dumps(cache, sort_keys=True, indent=2), encoding="utf-8")

    @staticmethod
    def _fetch_yahoo(symbol: str) -> Optional[int]:
        try:
            url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}"
            payload = _read_json(url)
            result = payload.get("quoteResponse", {}).get("result", [])
            if not result:
                return None
            shares = result[0].get("sharesOutstanding")
            return int(shares) if shares else None
        except Exception:
            return None

    @staticmethod
    def _fetch_finviz(symbol: str) -> Optional[int]:
        try:
            url = f"https://finviz.com/quote.ashx?t={symbol}"
            html = _read_text(url, user_agent="Mozilla/5.0")
            match = re.search(r"Float\s*<\/td>\s*<td[^>]*>\s*([\d\.]+)([MBK]?)", html)
            if not match:
                return None
            value = float(match.group(1))
            suffix = match.group(2)
            multiplier = {"B": 1_000_000_000, "M": 1_000_000, "K": 1_000}.get(suffix, 1)
            return int(value * multiplier)
        except Exception:
            return None

    @staticmethod
    def _fetch_nasdaq(symbol: str) -> Optional[int]:
        try:
            url = f"https://api.nasdaq.com/api/quote/{symbol}/summary?assetclass=stocks"
            payload = _read_json(url, user_agent="Mozilla/5.0")
            value = (
                payload.get("data", {})
                .get("summaryData", {})
                .get("SharesOutstanding", {})
                .get("value")
            )
            if not value:
                return None
            cleaned = value.replace(",", "").strip()
            if cleaned.endswith("B"):
                return int(float(cleaned[:-1]) * 1_000_000_000)
            if cleaned.endswith("M"):
                return int(float(cleaned[:-1]) * 1_000_000)
            if cleaned.endswith("K"):
                return int(float(cleaned[:-1]) * 1_000)
            return int(float(cleaned))
        except Exception:
            return None

    @staticmethod
    def _fetch_ib_cache(symbol: str) -> Optional[int]:
        cache_path = Path("src/scanner/float_cache.json")
        if not cache_path.exists():
            return None
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            value = payload.get(symbol)
            return int(value) if value else None
        except Exception:
            return None


def _format_float(value: int) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.2f}K"
    return str(value)


def _read_text(url: str, user_agent: str | None = None) -> str:
    headers = {"User-Agent": user_agent or "Mozilla/5.0"}
    request = Request(url, headers=headers)
    with urlopen(request, timeout=10) as response:
        return response.read().decode("utf-8", errors="ignore")


def _read_json(url: str, user_agent: str | None = None) -> Dict[str, Any]:
    return json.loads(_read_text(url, user_agent=user_agent))
