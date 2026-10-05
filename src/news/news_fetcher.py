from __future__ import annotations

import calendar
import importlib
import importlib.util
import logging
import re
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from math import ceil
from typing import Any, Dict, Iterable, List, Mapping
from urllib.parse import urlparse

from src.news.rss_lifecycle import RssFetchLifecycle, capture_source_timing, current_source_timing

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
    summary: str = ""
    source_tier: str = "fast"
    match_type: str = "ticker_token"
    matched_field: str = "title"


@dataclass(frozen=True)
class RssFailureSummary:
    total_sources: int
    failure_count: int
    failures_by_domain: Dict[str, Dict[str, int]]
    reason: str | None
    tier_source_counts: Dict[str, int] = field(default_factory=dict)
    tier_match_counts: Dict[str, int] = field(default_factory=dict)
    ticker_token_match_count: int = 0
    company_name_match_count: int = 0
    description_summary_match_count: int = 0
    max_entries_per_symbol: int = 0
    total_news_budget_seconds: float = 0.0
    news_elapsed_seconds: float = 0.0
    news_budget_exhausted: bool = False
    sources_attempted_count: int = 0
    sources_skipped_due_to_budget_count: int = 0
    tier_sources_attempted_counts: Dict[str, int] = field(default_factory=dict)
    tier_budget_seconds: float = 0.0
    tier_elapsed_seconds: float = 0.0
    tier_budget_exhausted: bool = False
    tier_budget_seconds_by_tier: Dict[str, float] = field(default_factory=dict)
    tier_elapsed_seconds_by_tier: Dict[str, float] = field(default_factory=dict)
    tier_budget_exhausted_by_tier: Dict[str, bool] = field(default_factory=dict)
    source_diagnostics: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    unique_source_urls_scheduled_count: int = 0
    unique_source_urls_attempted_count: int = 0
    duplicate_source_fetches_avoided_count: int = 0


DEFAULT_RSS_FETCH_WORKERS = 4
MIN_SOURCE_TIMEOUT_SECONDS = 0.05
SOURCE_WAIT_POLL_SECONDS = 0.05


_METADATA_KEYS = (
    "company_name",
    "companyName",
    "issuer_name",
    "issuerName",
    "security_name",
    "securityName",
    "long_name",
    "longName",
    "short_name",
    "shortName",
    "contract_description",
    "contractDescription",
    "description",
    "name",
)
_LEGAL_SUFFIXES = {
    "INC",
    "INCORPORATED",
    "CORP",
    "CORPORATION",
    "CO",
    "COMPANY",
    "LTD",
    "LIMITED",
    "PLC",
    "SA",
    "SAS",
    "NV",
    "AG",
    "SE",
    "LP",
    "LLC",
    "HOLDING",
    "HOLDINGS",
    "GROUP",
}
_TAG_RE = re.compile(r"<[^>]+>")
_WORD_RE = re.compile(r"[A-Z0-9]+")


def _compile_symbol_patterns(
    symbols: Iterable[str], *, allow_bare: bool = True
) -> Dict[str, re.Pattern[str]]:
    patterns: Dict[str, re.Pattern[str]] = {}
    for symbol in symbols:
        normalized = str(symbol or "").strip().upper()
        if not normalized:
            continue
        escaped = re.escape(normalized)
        # Summary prose can contain ordinary words or another company's brand
        # (egg, hour, Link, CNET). Only explicit security notation establishes a
        # ticker there. Preserve exact uppercase ticker titles and issuer aliases.
        explicit = (
            rf"(?<![A-Z0-9$])\${escaped}(?![A-Z0-9])"
            rf"|\({escaped}\)"
            rf"|(?<![A-Z0-9])(?:NASDAQ|NYSE(?:\s+AMERICAN|\s+ARCA)?|AMEX|OTCQX|OTCQB|OTC)"
            rf"\s*:\s*{escaped}(?![A-Z0-9])"
        )
        pattern = rf"(?i:{explicit})"
        if allow_bare:
            pattern += rf"|(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])"
        patterns[normalized] = re.compile(pattern)
    return patterns


def _clean_text(value: Any) -> str:
    text = str(value or "")
    text = _TAG_RE.sub(" ", text)
    return " ".join(text.split())


def _normalized_words(value: Any) -> list[str]:
    return _WORD_RE.findall(_clean_text(value).upper())


def _company_alias_from_words(words: list[str], symbol: str) -> str | None:
    while words and words[-1] in _LEGAL_SUFFIXES:
        words = words[:-1]
    if len(words) < 2:
        return None
    alias = " ".join(words)
    if alias == symbol.upper():
        return None
    return alias if len(alias) >= 6 else None


def _metadata_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        values: list[Any] = []
        for key in _METADATA_KEYS:
            values.extend(_metadata_values(value.get(key)))
        aliases = value.get("aliases") or value.get("company_aliases") or value.get("issuer_aliases")
        values.extend(_metadata_values(aliases))
        return values
    if isinstance(value, (list, tuple, set)):
        values = []
        for item in value:
            values.extend(_metadata_values(item))
        return values
    return [value]


def company_aliases_for_symbol(symbol: str, metadata: Any = None) -> tuple[str, ...]:
    normalized_symbol = str(symbol or "").strip().upper()
    aliases: list[str] = []
    for value in _metadata_values(metadata):
        words = _normalized_words(value)
        alias = _company_alias_from_words(words, normalized_symbol)
        if alias and alias not in aliases:
            aliases.append(alias)
    return tuple(aliases)


def _compile_company_patterns(symbols: Iterable[str], symbol_metadata: Mapping[str, Any] | None) -> Dict[str, list[re.Pattern[str]]]:
    metadata = symbol_metadata or {}
    patterns: Dict[str, list[re.Pattern[str]]] = {}
    for symbol in symbols:
        normalized_symbol = str(symbol or "").strip().upper()
        aliases = company_aliases_for_symbol(normalized_symbol, metadata.get(normalized_symbol) or metadata.get(symbol))
        symbol_patterns: list[re.Pattern[str]] = []
        for alias in aliases:
            tokens = _normalized_words(alias)
            if len(tokens) < 2:
                continue
            phrase = r"[^A-Z0-9]+".join(re.escape(token) for token in tokens)
            symbol_patterns.append(re.compile(rf"(?<![A-Z0-9]){phrase}(?![A-Z0-9])"))
        patterns[normalized_symbol] = symbol_patterns
    return patterns


def symbol_relevance_match(
    symbol: str,
    *,
    title: str,
    summary: str = "",
    metadata: Any = None,
) -> tuple[str, str] | None:
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_symbol:
        return None
    title_text = _clean_text(title)
    summary_text = _clean_text(summary)
    ticker_pattern = _compile_symbol_patterns([normalized_symbol]).get(normalized_symbol)
    summary_pattern = _compile_symbol_patterns([normalized_symbol], allow_bare=False).get(normalized_symbol)
    if ticker_pattern and ticker_pattern.search(title_text):
        return "ticker_token", "title"
    if summary_pattern and summary_text and summary_pattern.search(summary_text):
        return "ticker_token", "summary"
    title_upper = title_text.upper()
    summary_upper = summary_text.upper()
    for alias in company_aliases_for_symbol(normalized_symbol, metadata):
        tokens = _normalized_words(alias)
        if len(tokens) < 2:
            continue
        phrase = r"[^A-Z0-9]+".join(re.escape(token) for token in tokens)
        pattern = re.compile(rf"(?<![A-Z0-9]){phrase}(?![A-Z0-9])")
        if pattern.search(title_upper):
            return "company_name", "title"
        if summary_upper and pattern.search(summary_upper):
            return "company_name", "summary"
    return None


def _entry_timestamp(entry: Any) -> float | None:
    published = getattr(entry, "published_parsed", None)
    updated = getattr(entry, "updated_parsed", None)
    if isinstance(entry, Mapping):
        published = entry.get("published_parsed", published)
        updated = entry.get("updated_parsed", updated)
    for ts_struct in (published, updated):
        if ts_struct:
            try:
                return float(calendar.timegm(ts_struct))
            except (TypeError, ValueError, OverflowError):
                continue
    return None


def _entry_value(entry: Any, key: str) -> Any:
    if isinstance(entry, Mapping):
        return entry.get(key)
    return getattr(entry, key, None)


def _entry_summary(entry: Any) -> str:
    parts: list[str] = []
    for key in ("summary", "description", "subtitle"):
        value = _entry_value(entry, key)
        if value:
            parts.append(_clean_text(value))
    content = _entry_value(entry, "content")
    if isinstance(content, (list, tuple)):
        for item in content:
            if isinstance(item, Mapping):
                parts.append(_clean_text(item.get("value") or item.get("content") or ""))
            else:
                parts.append(_clean_text(getattr(item, "value", "") or item))
    elif content:
        parts.append(_clean_text(content))
    return " ".join(part for part in parts if part)


def _fetch_feed(url: str, timeout_s: float) -> object | None:
    if feedparser is None:
        return None
    if requests is None:
        return feedparser.parse(url)
    timing = current_source_timing()
    if timing is None:
        response = requests.get(url, timeout=timeout_s)
        response.raise_for_status()
        return feedparser.parse(response.text)
    response = None
    try:
        requested_at_s = time.monotonic()
        try:
            response = requests.get(url, timeout=timeout_s)
        finally:
            timing["request_elapsed_seconds"] = max(0.0, time.monotonic() - requested_at_s)
        timing["http_status"] = getattr(response, "status_code", None)
        response.raise_for_status()
        text = response.text
        parse_started_at_s = time.monotonic()
        try:
            feed = feedparser.parse(text)
        finally:
            completed_at_s = time.monotonic()
            timing["_completed_at_s"] = completed_at_s
            timing["parse_elapsed_seconds"] = max(0.0, completed_at_s - parse_started_at_s)
        # Capture the retrieval completion before optional reporting/cleanup.
        entries = getattr(feed, "entries", None)
        if entries is not None and hasattr(entries, "__len__"):
            timing["feed_item_count"] = len(entries)
        return feed
    except Exception:
        timing.setdefault("_completed_at_s", time.monotonic())
        raise
    finally:
        # The owned worker closes this response after publishing its Future.
        # Slow cleanup must not hide an already completed in-budget parse.
        timing["_response"] = response


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


def _normalize_budget_seconds(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        budget = float(value)
    except (TypeError, ValueError):
        return None
    if budget < 0:
        return 0.0
    return budget


def _budget_remaining_seconds(deadline_s: float | None) -> float | None:
    if deadline_s is None:
        return None
    return max(0.0, float(deadline_s) - time.monotonic())


def _budget_elapsed_seconds(started_at_s: float) -> float:
    return max(0.0, time.monotonic() - float(started_at_s))


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


def _empty_headlines(symbols: List[str]) -> Dict[str, List[Headline]]:
    return {str(symbol).upper(): [] for symbol in symbols}


def _budget_summary_kwargs(
    *,
    total_news_budget_seconds: float | None,
    stage_started_at_s: float,
    stage_deadline_s: float | None,
    news_budget_exhausted: bool | None = None,
) -> Dict[str, Any]:
    remaining = _budget_remaining_seconds(stage_deadline_s)
    # Explicit coordinator outcomes describe unfinished work, not reporting lag.
    exhausted = (
        bool(remaining is not None and remaining <= 0.0)
        if news_budget_exhausted is None else bool(news_budget_exhausted)
    )
    return {
        "total_news_budget_seconds": float(total_news_budget_seconds or 0.0),
        "news_elapsed_seconds": _budget_elapsed_seconds(stage_started_at_s),
        "news_budget_exhausted": exhausted,
    }


def _tier_budget_summary_kwargs(
    *,
    source_tier: str,
    tier_budget_seconds: float | None,
    tier_started_at_s: float | None,
    tier_deadline_s: float | None,
    tier_budget_exhausted: bool | None = None,
) -> Dict[str, Any]:
    normalized_budget = _normalize_budget_seconds(tier_budget_seconds)
    started_at_s = float(tier_started_at_s) if tier_started_at_s is not None else None
    deadline_s = float(tier_deadline_s) if tier_deadline_s is not None else None
    if deadline_s is None and normalized_budget is not None and started_at_s is not None:
        deadline_s = started_at_s + normalized_budget
    if normalized_budget is None and deadline_s is not None and started_at_s is not None:
        normalized_budget = max(0.0, deadline_s - started_at_s)
    remaining = _budget_remaining_seconds(deadline_s)
    exhausted = (
        bool(remaining is not None and remaining <= 0.0)
        if tier_budget_exhausted is None else bool(tier_budget_exhausted)
    )
    elapsed = _budget_elapsed_seconds(started_at_s) if started_at_s is not None else 0.0
    budget_value = float(normalized_budget or 0.0)
    tier = str(source_tier or "unknown")
    return {
        "tier_budget_seconds": budget_value,
        "tier_elapsed_seconds": elapsed,
        "tier_budget_exhausted": exhausted,
        "tier_budget_seconds_by_tier": {tier: budget_value} if tier else {},
        "tier_elapsed_seconds_by_tier": {tier: elapsed} if tier else {},
        "tier_budget_exhausted_by_tier": {tier: exhausted} if tier else {},
    }


def _summary_for_unavailable(
    *,
    sources: List[str],
    source_tier: str,
    failures_by_domain: Dict[str, Dict[str, int]],
    reason: str,
    max_entries_per_symbol: int,
    total_news_budget_seconds: float | None,
    stage_started_at_s: float,
    stage_deadline_s: float | None,
    tier_budget_seconds: float | None = None,
    tier_started_at_s: float | None = None,
    tier_deadline_s: float | None = None,
) -> RssFailureSummary:
    return RssFailureSummary(
        len(sources),
        len(sources) if reason == "feedparser_missing" else 0,
        failures_by_domain,
        reason,
        tier_source_counts={source_tier: len(sources)} if sources else {},
        max_entries_per_symbol=max_entries_per_symbol,
        sources_attempted_count=0,
        sources_skipped_due_to_budget_count=0,
        tier_sources_attempted_counts={source_tier: 0} if sources else {},
        **_budget_summary_kwargs(
            total_news_budget_seconds=total_news_budget_seconds,
            stage_started_at_s=stage_started_at_s,
            stage_deadline_s=stage_deadline_s,
        ),
        **_tier_budget_summary_kwargs(
            source_tier=source_tier,
            tier_budget_seconds=tier_budget_seconds,
            tier_started_at_s=tier_started_at_s,
            tier_deadline_s=tier_deadline_s,
        ),
    )


def _fetch_headlines_from_sources(
    symbols: List[str],
    sources: List[str],
    *,
    lookback_hours: float,
    request_timeout_s: float,
    symbol_metadata: Mapping[str, Any] | None,
    max_entries_per_symbol: int,
    source_tier: str,
    total_news_budget_seconds: float | None = None,
    stage_started_at_s: float | None = None,
    stage_deadline_s: float | None = None,
    tier_budget_seconds: float | None = None,
    tier_started_at_s: float | None = None,
    tier_deadline_s: float | None = None,
    lifecycle: RssFetchLifecycle | None = None,
) -> tuple[Dict[str, List[Headline]], RssFailureSummary]:
    budget_seconds = _normalize_budget_seconds(total_news_budget_seconds)
    started_at_s = time.monotonic() if stage_started_at_s is None else float(stage_started_at_s)
    deadline_s = float(stage_deadline_s) if stage_deadline_s is not None else None
    if deadline_s is None and budget_seconds is not None:
        deadline_s = started_at_s + budget_seconds
    if budget_seconds is None and deadline_s is not None:
        budget_seconds = max(0.0, deadline_s - started_at_s)
    normalized_tier_budget = _normalize_budget_seconds(tier_budget_seconds)
    tier_started_s = started_at_s if tier_started_at_s is None else float(tier_started_at_s)
    tier_deadline = float(tier_deadline_s) if tier_deadline_s is not None else None
    if tier_deadline is None and normalized_tier_budget is not None:
        tier_deadline = tier_started_s + normalized_tier_budget
    if normalized_tier_budget is None and tier_deadline is not None:
        normalized_tier_budget = max(0.0, tier_deadline - tier_started_s)

    normalized_symbols = [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]
    headlines: Dict[str, List[Headline]] = _empty_headlines(normalized_symbols)
    failures_by_domain: Dict[str, Dict[str, int]] = {}
    max_entries = max(1, int(max_entries_per_symbol or 1))

    def budget_kwargs(exhausted: bool = False) -> Dict[str, Any]:
        return _budget_summary_kwargs(
            total_news_budget_seconds=budget_seconds,
            stage_started_at_s=started_at_s,
            stage_deadline_s=deadline_s,
            news_budget_exhausted=exhausted,
        )

    def tier_budget_kwargs(exhausted: bool = False) -> Dict[str, Any]:
        return _tier_budget_summary_kwargs(
            source_tier=source_tier,
            tier_budget_seconds=normalized_tier_budget,
            tier_started_at_s=tier_started_s,
            tier_deadline_s=tier_deadline,
            tier_budget_exhausted=exhausted,
        )

    if not normalized_symbols:
        return headlines, RssFailureSummary(0, 0, failures_by_domain, "no_symbols", max_entries_per_symbol=max_entries, **budget_kwargs(), **tier_budget_kwargs())
    if not sources:
        return headlines, RssFailureSummary(0, 0, failures_by_domain, "no_sources", max_entries_per_symbol=max_entries, **budget_kwargs(), **tier_budget_kwargs())
    if feedparser is None:
        for url in sources:
            _record_failure(failures_by_domain, _domain_for_url(url), "DEPENDENCY_MISSING")
        summary = _summary_for_unavailable(
            sources=sources,
            source_tier=source_tier,
            failures_by_domain=failures_by_domain,
            reason="feedparser_missing",
            max_entries_per_symbol=max_entries,
            total_news_budget_seconds=budget_seconds,
            stage_started_at_s=started_at_s,
            stage_deadline_s=deadline_s,
            tier_budget_seconds=normalized_tier_budget,
            tier_started_at_s=tier_started_s,
            tier_deadline_s=tier_deadline,
        )
        _summarize_failures(summary)
        return headlines, summary


    now = time.time()
    min_ts = now - (lookback_hours * 3600)
    symbol_patterns = _compile_symbol_patterns(normalized_symbols)
    summary_symbol_patterns = _compile_symbol_patterns(normalized_symbols, allow_bare=False)
    company_patterns = _compile_company_patterns(normalized_symbols, symbol_metadata)
    seen_by_symbol: Dict[str, set[tuple[str, str]]] = {symbol: set() for symbol in normalized_symbols}
    failures = 0
    ticker_token_matches = 0
    company_name_matches = 0
    description_summary_matches = 0
    tier_matches = 0
    sources_attempted = 0
    sources_skipped_due_to_budget = 0
    news_budget_exhausted = False
    tier_budget_exhausted = False
    configured_timeout_s = max(0.001, float(request_timeout_s or 0.001))
    source_diagnostics: list[Mapping[str, Any]] = []

    unique_sources: list[str] = []
    seen_sources: set[str] = set()
    duplicate_source_fetches_avoided = 0
    for raw_url in sources:
        url = str(raw_url or "").strip()
        if not url:
            continue
        if url in seen_sources:
            duplicate_source_fetches_avoided += 1
            continue
        seen_sources.add(url)
        unique_sources.append(url)

    def source_diag(
        url: str,
        *,
        retrieval_status: str,
        attempted: bool,
        matched_count: int = 0,
        failure_reason: str | None = None,
        elapsed_seconds: float | None = None,
        timeout_seconds: float | None = None,
        timed_out: bool = False,
        budget_exhausted: bool = False,
        request_elapsed_seconds: float | None = None,
        parse_elapsed_seconds: float | None = None,
        http_status: int | None = None,
        response_closed: bool | None = None,
        feed_item_count: int | None = None,
        elapsed_kind: str | None = None,
        worker_completed: bool | None = None,
    ) -> Mapping[str, Any]:
        row = {
            "source_id": url,
            "source_url": url,
            "source_domain": _domain_for_url(url),
            "provider": "rss_batch",
            "source_group": "PREP_EXTENDED" if source_tier == "extended" else "FAST_TRADING",
            "source_tier": source_tier,
            "retrieval_status": retrieval_status,
            "attempted": bool(attempted),
            "matched_count": int(matched_count),
            "failure_reason": failure_reason,
            "elapsed_seconds": elapsed_seconds,
            "timeout_seconds": timeout_seconds,
            "timed_out": bool(timed_out),
            "budget_exhausted": bool(budget_exhausted),
        }
        row.update(
            request_elapsed_seconds=request_elapsed_seconds,
            parse_elapsed_seconds=parse_elapsed_seconds,
            http_status=http_status, response_closed=response_closed,
            feed_item_count=feed_item_count, elapsed_kind=elapsed_kind,
            worker_completed=worker_completed,
        )
        return row

    def per_source_timeout_seconds(remaining_source_count: int) -> float:
        timeout_s = configured_timeout_s
        remaining_budget_s = _budget_remaining_seconds(deadline_s)
        remaining_tier_s = _budget_remaining_seconds(tier_deadline)
        if remaining_budget_s is not None:
            timeout_s = min(timeout_s, remaining_budget_s)
        if remaining_tier_s is not None:
            timeout_s = min(timeout_s, remaining_tier_s)
        worker_count = max(1, min(DEFAULT_RSS_FETCH_WORKERS, len(unique_sources) or 1))
        waves_remaining = max(1, ceil(max(1, remaining_source_count) / worker_count))
        if remaining_budget_s is not None:
            timeout_s = min(timeout_s, max(MIN_SOURCE_TIMEOUT_SECONDS, remaining_budget_s / waves_remaining))
        if remaining_tier_s is not None:
            timeout_s = min(timeout_s, max(MIN_SOURCE_TIMEOUT_SECONDS, remaining_tier_s / waves_remaining))
        return max(0.001, timeout_s)

    def fetch_one(url: str, timeout_s: float, attempt_id: int | None, callback_ready: threading.Event | None) -> Mapping[str, Any]:
        source_started_s = time.monotonic()
        if lifecycle is not None:
            lifecycle.source_started(attempt_id, source_started_s)
        with capture_source_timing(lifecycle is not None) as timing:
            error = None
            feed = None
            try:
                feed = _fetch_feed(url, timeout_s)
            except Exception as exc:  # exercised through synthetic transport failures
                error = exc
            completed_at_s = timing.get("_completed_at_s")
            if completed_at_s is None:
                completed_at_s = time.monotonic()
            # Count the parsed feed, independently of publication/relevance filtering.
            # Ordinary retrieval has no lifecycle timing collector; unknown stays None.
            entries = getattr(feed, "entries", None)
            if entries is not None and hasattr(entries, "__len__"):
                timing.setdefault("feed_item_count", len(entries))
            result = {
                "url": url, "feed": feed, "error": error,
                "elapsed_seconds": max(0.0, completed_at_s - source_started_s),
                "completed_at_s": completed_at_s, "timeout_seconds": timeout_s,
                "_response": timing.get("_response"),
                **{key: timing.get(key) for key in (
                    "request_elapsed_seconds", "parse_elapsed_seconds", "http_status",
                    "response_closed", "feed_item_count", "cleanup_error",
                )},
            }
        if lifecycle is not None:
            observation = {key: value for key, value in result.items() if key not in {"feed", "error", "url", "_response"}}
            observation["failure_reason"] = _failure_code(error) if error is not None else None
            lifecycle.source_completed(attempt_id, observation)
            if result["_response"] is not None:
                # Registration happens immediately after submit. Holding the
                # worker here ensures close runs in its done callback, never as
                # a late-registered synchronous callback on the coordinator.
                callback_ready.wait()
        return result

    def close_source_response(future: Any, attempt_id: int) -> None:
        if future.cancelled():
            return
        result = future.result()
        close = getattr(result.pop("_response", None), "close", None)
        updates: dict[str, Any] = {}
        if callable(close):
            try:
                close()
                updates["response_closed"] = True
            except Exception as exc:
                updates.update(response_closed=False, cleanup_error=type(exc).__name__)
        result.update(updates)
        lifecycle.source_cleanup_completed(attempt_id, updates)

    def process_feed(url: str, feed: Any) -> int:
        nonlocal ticker_token_matches, company_name_matches, description_summary_matches, tier_matches
        source_name = ""
        try:
            source_name = (feed.feed.get("title") or "").strip()
        except Exception:
            source_name = ""
        source_matches = 0
        for entry in getattr(feed, "entries", []) or []:
            if all(len(items) >= max_entries for items in headlines.values()):
                break
            title = _clean_text(_entry_value(entry, "title"))
            link = _clean_text(_entry_value(entry, "link"))
            if not title:
                continue
            ts = _entry_timestamp(entry)
            if ts is None or ts > now:
                logging.info("[NEWS][TIME_REJECT] source=%s reason=missing_or_future_publication_time", url)
                continue
            if ts < min_ts:
                continue
            summary_text = _entry_summary(entry)
            title_upper = title.upper()
            summary_upper = summary_text.upper()
            for symbol in normalized_symbols:
                if len(headlines[symbol]) >= max_entries:
                    continue
                match_type = ""
                matched_field = ""
                pattern = symbol_patterns.get(symbol)
                summary_pattern = summary_symbol_patterns.get(symbol)
                if pattern and pattern.search(title):
                    match_type = "ticker_token"
                    matched_field = "title"
                elif summary_pattern and summary_text and summary_pattern.search(summary_text):
                    match_type = "ticker_token"
                    matched_field = "summary"
                else:
                    for company_pattern in company_patterns.get(symbol, []):
                        if company_pattern.search(title_upper):
                            match_type = "company_name"
                            matched_field = "title"
                            break
                        if summary_upper and company_pattern.search(summary_upper):
                            match_type = "company_name"
                            matched_field = "summary"
                            break
                if not match_type:
                    continue
                key = (title.lower(), source_name.lower() or url.lower())
                if key in seen_by_symbol[symbol]:
                    continue
                seen_by_symbol[symbol].add(key)
                if match_type == "ticker_token":
                    ticker_token_matches += 1
                if match_type == "company_name":
                    company_name_matches += 1
                if matched_field == "summary":
                    description_summary_matches += 1
                tier_matches += 1
                source_matches += 1
                headlines[symbol].append(
                    Headline(
                        title=title,
                        source=source_name or url,
                        published_ts=ts,
                        url=link,
                        summary=summary_text,
                        source_tier=source_tier,
                        match_type=match_type,
                        matched_field=matched_field,
                    )
                )
        return source_matches

    if unique_sources:
        worker_count = max(1, min(DEFAULT_RSS_FETCH_WORKERS, len(unique_sources)))
        executor = ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="news-rss")
        if lifecycle is not None:
            lifecycle.register_executor(executor)
        pending: dict[Any, tuple[str, float, float, int | None]] = {}
        next_source_index = 0
        skipped_sources_recorded = False

        def record_budget_skipped_sources() -> None:
            nonlocal sources_skipped_due_to_budget, skipped_sources_recorded
            if skipped_sources_recorded:
                return
            skipped = max(0, len(unique_sources) - next_source_index)
            sources_skipped_due_to_budget += skipped
            for url in unique_sources[next_source_index:]:
                source_diagnostics.append(
                    source_diag(
                        url,
                        retrieval_status="budget_exhausted",
                        attempted=False,
                        failure_reason="deadline_exhausted_before_attempt",
                        elapsed_seconds=0.0,
                        timeout_seconds=0.0,
                        budget_exhausted=True,
                    )
                )
            skipped_sources_recorded = True

        try:
            while pending or next_source_index < len(unique_sources):
                wave_timeout_s: float | None = None
                while (
                    next_source_index < len(unique_sources) and len(pending) < worker_count
                    and not news_budget_exhausted and not tier_budget_exhausted
                ):
                    if all(len(items) >= max_entries for items in headlines.values()):
                        break
                    remaining_budget_s = _budget_remaining_seconds(deadline_s)
                    remaining_tier_s = _budget_remaining_seconds(tier_deadline)
                    if remaining_budget_s is not None and remaining_budget_s <= 0.0:
                        news_budget_exhausted = True
                        tier_budget_exhausted = tier_budget_exhausted or (remaining_tier_s is not None and remaining_tier_s <= 0.0)
                        record_budget_skipped_sources()
                        break
                    if remaining_tier_s is not None and remaining_tier_s <= 0.0:
                        tier_budget_exhausted = True
                        record_budget_skipped_sources()
                        break
                    remaining_sources = len(unique_sources) - next_source_index
                    if wave_timeout_s is None:
                        wave_timeout_s = per_source_timeout_seconds(remaining_sources)
                    timeout_s = wave_timeout_s
                    url = unique_sources[next_source_index]
                    next_source_index += 1
                    sources_attempted += 1
                    submitted_s = time.monotonic()
                    attempt_id = lifecycle.source_submitted(url, source_tier, submitted_s) if lifecycle is not None else None
                    callback_ready = threading.Event() if lifecycle is not None else None
                    future = executor.submit(fetch_one, url, timeout_s, attempt_id, callback_ready)
                    if lifecycle is not None:
                        try:
                            lifecycle.register_future(attempt_id, future)
                            future.add_done_callback(lambda done, index=attempt_id: close_source_response(done, index))
                        finally:
                            callback_ready.set()
                    pending[future] = (url, timeout_s, submitted_s, attempt_id)
                if not pending:
                    break
                # Drain completed work without waiting, including completions that
                # FIRST_COMPLETED omitted or that arrived while processing a peer.
                done = {future for future in pending if future.done()}
                if not done:
                    remaining_budget_s = _budget_remaining_seconds(deadline_s)
                    remaining_tier_s = _budget_remaining_seconds(tier_deadline)
                    if remaining_budget_s is not None and remaining_budget_s <= 0.0:
                        news_budget_exhausted = True
                        tier_budget_exhausted = tier_budget_exhausted or (remaining_tier_s is not None and remaining_tier_s <= 0.0)
                        record_budget_skipped_sources()
                        break
                    if remaining_tier_s is not None and remaining_tier_s <= 0.0:
                        tier_budget_exhausted = True
                        record_budget_skipped_sources()
                        break
                    if news_budget_exhausted or tier_budget_exhausted:
                        break
                    wait_timeout = SOURCE_WAIT_POLL_SECONDS
                    if remaining_budget_s is not None:
                        wait_timeout = min(wait_timeout, remaining_budget_s)
                    if remaining_tier_s is not None:
                        wait_timeout = min(wait_timeout, remaining_tier_s)
                    done, _ = wait(tuple(pending.keys()), timeout=max(0.001, wait_timeout), return_when=FIRST_COMPLETED)
                    done.update(future for future in pending if future.done())
                if not done:
                    continue
                for future in done:
                    result = future.result()
                    # A bounded wait may resume after its deadline. Use the worker's
                    # completion instant so in-time results survive coordinator lag.
                    completed_at_s = float(result.get("completed_at_s", time.monotonic()))
                    stage_expired = deadline_s is not None and completed_at_s >= deadline_s
                    tier_expired = tier_deadline is not None and completed_at_s >= tier_deadline
                    if stage_expired or tier_expired:
                        news_budget_exhausted = news_budget_exhausted or stage_expired
                        tier_budget_exhausted = tier_budget_exhausted or tier_expired
                        record_budget_skipped_sources()
                    url, timeout_s, submitted_s, _ = pending.pop(future)
                    measured_elapsed = result.get("elapsed_seconds")
                    elapsed = float(measured_elapsed) if measured_elapsed is not None else _budget_elapsed_seconds(submitted_s)
                    measurements = {key: result.get(key) for key in (
                        "request_elapsed_seconds", "parse_elapsed_seconds", "http_status",
                        "response_closed", "feed_item_count",
                    )}
                    measurements.update(elapsed_kind="worker_fetch_parse", worker_completed=True)
                    error = result.get("error")
                    # Late evidence is discarded, but an observed transport error
                    # remains a fact alongside the exhausted local budget.
                    if (stage_expired or tier_expired) and error is None:
                        source_diagnostics.append(
                            source_diag(
                                url, retrieval_status="budget_exhausted", attempted=True,
                                failure_reason="deadline_exhausted", elapsed_seconds=elapsed,
                                timeout_seconds=timeout_s, budget_exhausted=True,
                                **measurements,
                            )
                        )
                        continue
                    if error is not None:
                        code = _failure_code(error if isinstance(error, Exception) else None)
                        failures += 1
                        _record_failure(failures_by_domain, _domain_for_url(url), code)
                        source_diagnostics.append(
                            source_diag(
                                url,
                                retrieval_status="budget_exhausted" if stage_expired or tier_expired else "provider_error",
                                attempted=True,
                                failure_reason=code,
                                elapsed_seconds=elapsed,
                                timeout_seconds=timeout_s,
                                timed_out="TIMEOUT" in code or code.endswith("TIMEOUT"),
                                budget_exhausted=stage_expired or tier_expired,
                                **measurements,
                            )
                        )
                        continue
                    feed = result.get("feed")
                    if feed is None:
                        failures += 1
                        code = _failure_code(None, feed_missing=True)
                        _record_failure(failures_by_domain, _domain_for_url(url), code)
                        source_diagnostics.append(
                            source_diag(
                                url,
                                retrieval_status="unavailable",
                                attempted=True,
                                failure_reason=code,
                                elapsed_seconds=elapsed,
                                timeout_seconds=timeout_s,
                                **measurements,
                            )
                        )
                        continue
                    matched_count = process_feed(url, feed)
                    source_diagnostics.append(
                        source_diag(
                            url,
                            retrieval_status="available",
                            attempted=True,
                            matched_count=matched_count,
                            elapsed_seconds=elapsed,
                            timeout_seconds=timeout_s,
                            **measurements,
                        )
                    )
                if all(len(items) >= max_entries for items in headlines.values()):
                    break
        finally:
            if lifecycle is not None and not skipped_sources_recorded and all(len(items) >= max_entries for items in headlines.values()):
                for url in unique_sources[next_source_index:]:
                    source_diagnostics.append(source_diag(
                        url, retrieval_status="not_requested", attempted=False,
                        failure_reason="result_limit_reached", elapsed_seconds=0.0,
                        timeout_seconds=0.0,
                    ))
            pending_cancelled_for_budget = bool(news_budget_exhausted or tier_budget_exhausted)
            for future, (url, timeout_s, submitted_s, attempt_id) in list(pending.items()):
                cancelled = future.cancel()
                if lifecycle is not None:
                    lifecycle.cancellation_requested(attempt_id, cancelled)
                elapsed = _budget_elapsed_seconds(submitted_s)
                source_diagnostics.append(
                    source_diag(
                        url,
                        retrieval_status="budget_exhausted" if pending_cancelled_for_budget else "partial",
                        attempted=True,
                        failure_reason="deadline_exhausted" if pending_cancelled_for_budget else "cancelled_after_max_entries",
                        elapsed_seconds=elapsed,
                        timeout_seconds=timeout_s,
                        # The coordinator stopped waiting; no HTTP timeout was observed.
                        # Running requests can still complete after this local deadline.
                        timed_out=False,
                        budget_exhausted=pending_cancelled_for_budget,
                        elapsed_kind="since_submission",
                        worker_completed=bool(future.done() and not future.cancelled()),
                    )
                )
            executor.shutdown(wait=False, cancel_futures=True)
    else:
        duplicate_source_fetches_avoided = len(sources)
    summary = RssFailureSummary(
        len(sources),
        failures,
        failures_by_domain,
        None,
        tier_source_counts={source_tier: len(sources)},
        tier_match_counts={source_tier: tier_matches},
        ticker_token_match_count=ticker_token_matches,
        company_name_match_count=company_name_matches,
        description_summary_match_count=description_summary_matches,
        max_entries_per_symbol=max_entries,
        sources_attempted_count=sources_attempted,
        sources_skipped_due_to_budget_count=sources_skipped_due_to_budget,
        tier_sources_attempted_counts={source_tier: sources_attempted},
        source_diagnostics=tuple(source_diagnostics),
        unique_source_urls_scheduled_count=len(unique_sources),
        unique_source_urls_attempted_count=sources_attempted,
        duplicate_source_fetches_avoided_count=duplicate_source_fetches_avoided,
        **budget_kwargs(news_budget_exhausted),
        **tier_budget_kwargs(tier_budget_exhausted),
    )
    _summarize_failures(summary)
    return headlines, summary


def fetch_headlines_for_symbols(
    symbols: List[str],
    sources: List[str],
    lookback_hours: float = 24.0,
    request_timeout_s: float = 5.0,
    *,
    symbol_metadata: Mapping[str, Any] | None = None,
    max_entries_per_symbol: int = 5,
    source_tier: str = "custom",
    total_news_budget_seconds: float | None = None,
    stage_started_at_s: float | None = None,
    stage_deadline_s: float | None = None,
    tier_budget_seconds: float | None = None,
    tier_started_at_s: float | None = None,
    tier_deadline_s: float | None = None,
    lifecycle: RssFetchLifecycle | None = None,
) -> tuple[Dict[str, List[Headline]], RssFailureSummary]:
    return _fetch_headlines_from_sources(
        symbols,
        sources,
        lookback_hours=lookback_hours,
        request_timeout_s=request_timeout_s,
        symbol_metadata=symbol_metadata,
        max_entries_per_symbol=max_entries_per_symbol,
        source_tier=source_tier,
        total_news_budget_seconds=total_news_budget_seconds,
        stage_started_at_s=stage_started_at_s,
        stage_deadline_s=stage_deadline_s,
        tier_budget_seconds=tier_budget_seconds,
        tier_started_at_s=tier_started_at_s,
        tier_deadline_s=tier_deadline_s,
        lifecycle=lifecycle,
    )


def fetch_fast_headlines_for_symbols(
    symbols: List[str],
    sources: List[str],
    lookback_hours: float = 24.0,
    request_timeout_s: float = 5.0,
    *,
    symbol_metadata: Mapping[str, Any] | None = None,
    max_entries_per_symbol: int = 5,
    total_news_budget_seconds: float | None = None,
    stage_started_at_s: float | None = None,
    stage_deadline_s: float | None = None,
    tier_budget_seconds: float | None = None,
    tier_started_at_s: float | None = None,
    tier_deadline_s: float | None = None,
    lifecycle: RssFetchLifecycle | None = None,
) -> tuple[Dict[str, List[Headline]], RssFailureSummary]:
    return _fetch_headlines_from_sources(
        symbols,
        sources,
        lookback_hours=lookback_hours,
        request_timeout_s=request_timeout_s,
        symbol_metadata=symbol_metadata,
        max_entries_per_symbol=max_entries_per_symbol,
        source_tier="fast",
        total_news_budget_seconds=total_news_budget_seconds,
        stage_started_at_s=stage_started_at_s,
        stage_deadline_s=stage_deadline_s,
        tier_budget_seconds=tier_budget_seconds,
        tier_started_at_s=tier_started_at_s,
        tier_deadline_s=tier_deadline_s,
        lifecycle=lifecycle,
    )
