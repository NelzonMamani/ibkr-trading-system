from __future__ import annotations

import importlib
import importlib.util
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping
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


def _compile_symbol_patterns(symbols: Iterable[str]) -> Dict[str, re.Pattern[str]]:
    patterns: Dict[str, re.Pattern[str]] = {}
    for symbol in symbols:
        normalized = str(symbol or "").strip().upper()
        if not normalized:
            continue
        escaped = re.escape(normalized)
        pattern = rf"(?<![A-Z0-9]){escaped}(?![A-Z0-9])|\${escaped}|\({escaped}\)"
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
    title_upper = _clean_text(title).upper()
    summary_upper = _clean_text(summary).upper()
    ticker_pattern = _compile_symbol_patterns([normalized_symbol]).get(normalized_symbol)
    if ticker_pattern and ticker_pattern.search(title_upper):
        return "ticker_token", "title"
    if ticker_pattern and summary_upper and ticker_pattern.search(summary_upper):
        return "ticker_token", "summary"
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


def _entry_timestamp(entry: Any) -> float:
    published = getattr(entry, "published_parsed", None)
    updated = getattr(entry, "updated_parsed", None)
    if isinstance(entry, Mapping):
        published = entry.get("published_parsed", published)
        updated = entry.get("updated_parsed", updated)
    for ts_struct in (published, updated):
        if ts_struct:
            return time.mktime(ts_struct)
    return time.time()


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


def _empty_headlines(symbols: List[str]) -> Dict[str, List[Headline]]:
    return {str(symbol).upper(): [] for symbol in symbols}


def _summary_for_unavailable(
    *,
    sources: List[str],
    source_tier: str,
    failures_by_domain: Dict[str, Dict[str, int]],
    reason: str,
    max_entries_per_symbol: int,
) -> RssFailureSummary:
    return RssFailureSummary(
        len(sources),
        len(sources) if reason == "feedparser_missing" else 0,
        failures_by_domain,
        reason,
        tier_source_counts={source_tier: len(sources)} if sources else {},
        max_entries_per_symbol=max_entries_per_symbol,
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
) -> tuple[Dict[str, List[Headline]], RssFailureSummary]:
    normalized_symbols = [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]
    headlines: Dict[str, List[Headline]] = _empty_headlines(normalized_symbols)
    failures_by_domain: Dict[str, Dict[str, int]] = {}
    max_entries = max(1, int(max_entries_per_symbol or 1))
    if not normalized_symbols:
        return headlines, RssFailureSummary(0, 0, failures_by_domain, "no_symbols", max_entries_per_symbol=max_entries)
    if not sources:
        return headlines, RssFailureSummary(0, 0, failures_by_domain, "no_sources", max_entries_per_symbol=max_entries)
    if feedparser is None:
        for url in sources:
            _record_failure(failures_by_domain, _domain_for_url(url), "DEPENDENCY_MISSING")
        summary = _summary_for_unavailable(
            sources=sources,
            source_tier=source_tier,
            failures_by_domain=failures_by_domain,
            reason="feedparser_missing",
            max_entries_per_symbol=max_entries,
        )
        _summarize_failures(summary)
        return headlines, summary

    now = time.time()
    min_ts = now - (lookback_hours * 3600)
    symbol_patterns = _compile_symbol_patterns(normalized_symbols)
    company_patterns = _compile_company_patterns(normalized_symbols, symbol_metadata)
    seen_by_symbol: Dict[str, set[tuple[str, str]]] = {symbol: set() for symbol in normalized_symbols}
    failures = 0
    ticker_token_matches = 0
    company_name_matches = 0
    description_summary_matches = 0
    tier_matches = 0

    for url in sources:
        if all(len(items) >= max_entries for items in headlines.values()):
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
            if all(len(items) >= max_entries for items in headlines.values()):
                break
            title = _clean_text(_entry_value(entry, "title"))
            link = _clean_text(_entry_value(entry, "link"))
            if not title:
                continue
            ts = _entry_timestamp(entry)
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
                if pattern and pattern.search(title_upper):
                    match_type = "ticker_token"
                    matched_field = "title"
                elif pattern and summary_upper and pattern.search(summary_upper):
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
) -> tuple[Dict[str, List[Headline]], RssFailureSummary]:
    return _fetch_headlines_from_sources(
        symbols,
        sources,
        lookback_hours=lookback_hours,
        request_timeout_s=request_timeout_s,
        symbol_metadata=symbol_metadata,
        max_entries_per_symbol=max_entries_per_symbol,
        source_tier=source_tier,
    )


def fetch_fast_headlines_for_symbols(
    symbols: List[str],
    sources: List[str],
    lookback_hours: float = 24.0,
    request_timeout_s: float = 5.0,
    *,
    symbol_metadata: Mapping[str, Any] | None = None,
    max_entries_per_symbol: int = 5,
) -> tuple[Dict[str, List[Headline]], RssFailureSummary]:
    return _fetch_headlines_from_sources(
        symbols,
        sources,
        lookback_hours=lookback_hours,
        request_timeout_s=request_timeout_s,
        symbol_metadata=symbol_metadata,
        max_entries_per_symbol=max_entries_per_symbol,
        source_tier="fast",
    )