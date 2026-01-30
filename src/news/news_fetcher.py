from __future__ import annotations

import importlib
import importlib.util
import logging
import re
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List
from urllib.parse import urlparse

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


@dataclass(frozen=True)
class RssFailureSummary:
    total_sources: int
    failure_count: int
    failures_by_domain: Dict[str, Dict[str, int]]
    reason: str | None


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


def _domain_for_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or "unknown"


def _failure_code(exc: Exception | None, feed_missing: bool = False) -> str:
    if feed_missing:
        return "FEED_EMPTY"
    if exc is None:
        return "UNKNOWN"
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if status_code:
        return f"HTTP_{status_code}"
    return type(exc).__name__.upper()


def _record_failure(
    failures_by_domain: Dict[str, Dict[str, int]],
    domain: str,
    code: str,
) -> None:
    bucket = failures_by_domain.setdefault(domain, {})
    bucket[code] = bucket.get(code, 0) + 1


def _summarize_failures(summary: RssFailureSummary) -> None:
    if summary.failure_count <= 0:
        return
    parts = []
    for domain, codes in summary.failures_by_domain.items():
        code_str = ",".join(f"{code}:{count}" for code, count in sorted(codes.items()))
        parts.append(f"{domain}({code_str})")
    logging.info(
        "[NEWS] RSS failure summary: failures=%d/%d domains=%s",
        summary.failure_count,
        summary.total_sources,
        "; ".join(parts),
    )


def fetch_headlines_for_symbols(
    symbols: List[str],
    sources: List[str],
    lookback_hours: float = 24.0,
    request_timeout_s: float = 5.0,
) -> tuple[Dict[str, List[Headline]], RssFailureSummary]:
    headlines: Dict[str, List[Headline]] = {symbol: [] for symbol in symbols}
    failures_by_domain: Dict[str, Dict[str, int]] = {}
    if not symbols:
        return headlines, RssFailureSummary(0, 0, failures_by_domain, "no_symbols")
    if not sources:
        return headlines, RssFailureSummary(0, 0, failures_by_domain, "no_sources")
    if feedparser is None:
        for url in sources:
            _record_failure(failures_by_domain, _domain_for_url(url), "DEPENDENCY_MISSING")
        summary = RssFailureSummary(len(sources), len(sources), failures_by_domain, "feedparser_missing")
        _summarize_failures(summary)
        return headlines, summary

    now = time.time()
    min_ts = now - (lookback_hours * 3600)
    patterns = _compile_symbol_patterns(symbols)
    failures = 0
    for url in sources:
        try:
            feed = _fetch_feed(url, request_timeout_s)
        except Exception as exc:
            failures += 1
            _record_failure(failures_by_domain, _domain_for_url(url), _failure_code(exc))
            continue
        if feed is None:
            failures += 1
            _record_failure(failures_by_domain, _domain_for_url(url), _failure_code(None, feed_missing=True))
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
    summary = RssFailureSummary(len(sources), failures, failures_by_domain, None)
    _summarize_failures(summary)
    return headlines, summary


def fetch_fast_headlines_for_symbols(
    symbols: List[str],
    sources: List[str],
    lookback_hours: float = 24.0,
    request_timeout_s: float = 5.0,
) -> tuple[Dict[str, List[Headline]], RssFailureSummary]:
    headlines: Dict[str, List[Headline]] = {symbol: [] for symbol in symbols}
    failures_by_domain: Dict[str, Dict[str, int]] = {}
    if not symbols:
        return headlines, RssFailureSummary(0, 0, failures_by_domain, "no_symbols")
    if not sources:
        return headlines, RssFailureSummary(0, 0, failures_by_domain, "no_sources")
    if feedparser is None:
        for url in sources:
            _record_failure(failures_by_domain, _domain_for_url(url), "DEPENDENCY_MISSING")
        summary = RssFailureSummary(len(sources), len(sources), failures_by_domain, "feedparser_missing")
        _summarize_failures(summary)
        return headlines, summary

    now = time.time()
    min_ts = now - (lookback_hours * 3600)
    patterns = _compile_symbol_patterns(symbols)
    remaining = set(symbols)
    failures = 0
    for url in sources:
        if not remaining:
            break
        try:
            feed = _fetch_feed(url, request_timeout_s)
        except Exception as exc:
            failures += 1
            _record_failure(failures_by_domain, _domain_for_url(url), _failure_code(exc))
            continue
        if feed is None:
            failures += 1
            _record_failure(failures_by_domain, _domain_for_url(url), _failure_code(None, feed_missing=True))
            continue
        source_name = ""
        try:
            source_name = (feed.feed.get("title") or "").strip()
        except Exception:
            source_name = ""
        for entry in getattr(feed, "entries", []) or []:
            if not remaining:
                break
            title = (getattr(entry, "title", "") or "").strip()
            link = (getattr(entry, "link", "") or "").strip()
            if not title:
                continue
            ts = _entry_timestamp(entry)
            if ts < min_ts:
                continue
            for symbol in list(remaining):
                pattern = patterns.get(symbol)
                if pattern and pattern.search(title.upper()):
                    headlines[symbol].append(
                        Headline(
                            title=title,
                            source=source_name or url,
                            published_ts=ts,
                            url=link,
                        )
                    )
                    remaining.discard(symbol)
    summary = RssFailureSummary(len(sources), failures, failures_by_domain, None)
    _summarize_failures(summary)
    return headlines, summary
