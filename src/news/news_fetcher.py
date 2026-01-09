from __future__ import annotations

import importlib
import importlib.util
import logging
import re
import time
from collections import Counter
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


def _domain_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        host = host.split("@")[-1]
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


_RETRYABLE_STATUS = {"408", "429", "500", "502", "503", "504"}


def _fetch_feed(url: str, timeout_s: float) -> object | None:
    if feedparser is None:
        return None
    if requests is None:
        return feedparser.parse(url)
    headers = {
        "User-Agent": "IBKRScanner/1.0 (+https://github.com/NelzonMamani/ibkr-trading-system)",
        "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    }
    response = requests.get(url, timeout=timeout_s, headers=headers)
    response.raise_for_status()
    return feedparser.parse(response.text)


def _fetch_feed_with_retry(url: str, timeout_s: float, max_attempts: int = 2) -> object | None:
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return _fetch_feed(url, timeout_s)
        except Exception as exc:
            last_exc = exc
            status = str(getattr(getattr(exc, "response", None), "status_code", "error"))
            if status not in _RETRYABLE_STATUS or attempt + 1 >= max_attempts:
                break
            time.sleep(0.3)
    if last_exc:
        raise last_exc
    return None


def _sleep_for_throttle(domain: str, last_request: Dict[str, float], min_delay_s: float) -> None:
    if not domain:
        return
    last_ts = last_request.get(domain)
    if last_ts is None:
        return
    elapsed = time.time() - last_ts
    if elapsed < min_delay_s:
        time.sleep(max(0.0, min_delay_s - elapsed))


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
    successes = 0
    throttled_domains: Dict[str, float] = {}
    failure_domains: Counter[str] = Counter()
    failure_codes: Counter[str] = Counter()
    logged_domains = set()
    min_delay_s = 0.4
    for url in sources:
        domain = _domain_from_url(url)
        _sleep_for_throttle(domain, throttled_domains, min_delay_s)
        throttled_domains[domain] = time.time()
        try:
            feed = _fetch_feed_with_retry(url, request_timeout_s)
        except Exception as exc:
            failures += 1
            failure_domains[domain or url] += 1
            code = getattr(getattr(exc, "response", None), "status_code", None)
            failure_codes[str(code or "error")] += 1
            if revealing := (domain or url):
                if revealing not in logged_domains:
                    logging.warning("[NEWS] RSS fetch failed for %s: %s", revealing, exc)
                    logged_domains.add(revealing)
            continue
        if feed is None:
            failures += 1
            failure_domains[domain or url] += 1
            failure_codes["parse_error"] += 1
            continue
        successes += 1
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
    top_domains = ", ".join(
        f"{domain}={count}" for domain, count in failure_domains.most_common(5)
    )
    top_codes = ", ".join(
        f"{code}={count}" for code, count in failure_codes.most_common(5)
    )
    logging.info(
        "[NEWS] RSS summary total=%d successes=%d failures=%d top_domains=[%s] top_codes=[%s]",
        len(sources),
        successes,
        failures,
        top_domains,
        top_codes,
    )
    return headlines
