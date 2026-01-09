from __future__ import annotations

import importlib
import importlib.util
import logging
import re
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List

if importlib.util.find_spec("feedparser"):
    feedparser = importlib.import_module("feedparser")  # type: ignore
else:  # pragma: no cover - optional dependency
    feedparser = None

if importlib.util.find_spec("requests"):
    requests = importlib.import_module("requests")  # type: ignore
else:  # pragma: no cover - optional dependency
    requests = None


@dataclass(frozen=True)
class Headline:
    title: str
    source: str
    published_ts: float
    url: str


def _compile_symbol_patterns(symbols: Iterable[str]) -> Dict[str, re.Pattern[str]]:
    patterns: Dict[str, re.Pattern[str]] = {}
    for symbol in symbols:
        escaped = re.escape(symbol.upper())
        pattern = rf"(?<![A-Z0-9]){escaped}(?![A-Z0-9])|\${escaped}|\({escaped}\)"
        patterns[symbol] = re.compile(pattern)
    return patterns


def _entry_timestamp(entry) -> float:
    published = getattr(entry, "published_parsed", None)
    updated = getattr(entry, "updated_parsed", None)
    for ts_struct in (published, updated):
        if ts_struct:
            return time.mktime(ts_struct)
    return time.time()


def _fetch_feed(url: str, timeout_s: float) -> object | None:
    if feedparser is None:
        return None
    if requests is None:
        return feedparser.parse(url)
    response = requests.get(url, timeout=timeout_s)
    response.raise_for_status()
    return feedparser.parse(response.text)


def fetch_headlines_for_symbols(
    symbols: List[str],
    sources: List[str],
    lookback_hours: float = 24.0,
    request_timeout_s: float = 5.0,
) -> Dict[str, List[Headline]]:
    headlines: Dict[str, List[Headline]] = {symbol: [] for symbol in symbols}
    if not symbols or not sources or feedparser is None:
        return headlines

    now = time.time()
    min_ts = now - (lookback_hours * 3600)
    patterns = _compile_symbol_patterns(symbols)
    failures = 0
    for url in sources:
        try:
            feed = _fetch_feed(url, request_timeout_s)
        except Exception as exc:
            failures += 1
            logging.warning("[NEWS] RSS fetch failed for %s: %s", url, exc)
            continue
        if feed is None:
            failures += 1
            continue
        source_name = ""
        try:
            source_name = (feed.feed.get("title") or "").strip()
        except Exception:
            source_name = ""
        for entry in getattr(feed, "entries", []) or []:
            title = (getattr(entry, "title", "") or "").strip()
            link = (getattr(entry, "link", "") or "").strip()
            if not title:
                continue
            ts = _entry_timestamp(entry)
            if ts < min_ts:
                continue
            for symbol, pattern in patterns.items():
                if pattern.search(title.upper()):
                    headlines[symbol].append(
                        Headline(
                            title=title,
                            source=source_name or url,
                            published_ts=ts,
                            url=link,
                        )
                    )
    if failures:
        logging.info("[NEWS] RSS failures=%d sources=%d", failures, len(sources))
    return headlines
