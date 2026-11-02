"""Bounded, content-free news retrieval facts for captured runtime output."""
from __future__ import annotations

import json
import math
import re
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit
from datetime import datetime, timezone
from itertools import islice

from src.news.rss_exclusion_evidence import REASONS

from src.news.news_intelligence_contract import NewsBatchResult

_PREFIX = "[NEWS][RETRIEVAL_DIAGNOSTICS] "
_LABEL = re.compile(r"[A-Za-z0-9_.:-]{1,100}\Z")
_ACCOUNT = re.compile(r"(?:DU|U|DF|F)[0-9]{5,}\Z")
_FAILURES = {
    "FEED_EMPTY", "UNKNOWN", "HTTPERROR", "TIMEOUT", "READTIMEOUT", "CONNECTTIMEOUT",
    "CONNECTIONERROR", "SSLError", "SSLERROR", "REQUESTEXCEPTION", "VALUEERROR",
    "deadline_exhausted", "deadline_exhausted_before_attempt", "cancelled_after_max_entries",
    "feedparser_missing", "no_sources", "no_symbols", "news_budget_exhausted",
}


def _label(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value)
    return value if _LABEL.fullmatch(value) and not _ACCOUNT.fullmatch(value) else "REDACTED"


def _source(value: Any) -> str:
    """Drop URL authentication, query values and fragments, including signed tokens."""
    value = str(value or "")
    try:
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https"} and parsed.hostname:
            return urlunsplit((parsed.scheme, parsed.hostname, parsed.path, "", ""))
    except ValueError:
        pass
    return _label(value) or "unknown"


def _failure(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value)
    if value in _FAILURES or re.fullmatch(r"HTTP_[0-9]{3}", value):
        return value
    return "REDACTED"


def _number(value: Any) -> int | float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return value
    return None


def _symbols(values: Any) -> list[str]:
    return [_label(str(value).strip().upper()) or "unknown" for value in (values or ())]



def _identity_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return "REDACTED"
    text = str(value)
    if len(text) > 240 or any(ord(char) < 32 for char in text) or "://" in text:
        return "REDACTED"
    return "REDACTED" if _ACCOUNT.fullmatch(text) else text


def _candidate_identity(candidate: Any) -> Mapping[str, Any]:
    # Use exactly the RSS adapter's metadata precedence and matching normalizer.
    from src.news.batch_rss_adapter import _metadata_by_symbol
    from src.news.news_fetcher import company_aliases_for_symbol

    metadata = candidate.metadata or {}
    effective = _metadata_by_symbol((candidate,))[candidate.normalized_symbol]
    return {
        "symbol": _identity_text(candidate.symbol),
        "company_name": _identity_text(candidate.company_name),
        "aliases": [_identity_text(value) for value in candidate.aliases],
        "exchange": _identity_text(candidate.exchange),
        "market": _identity_text(candidate.market),
        "region": _identity_text(candidate.region),
        "issuer_identifiers": {
            key: _identity_text(metadata[key])
            for key in ("cik", "lei")
            if key in metadata
        },
        "security_identifiers": {
            key: metadata[key] if key in {"con_id", "conId"} else _identity_text(metadata[key])
            for key in ("con_id", "conId", "isin", "figi", "primary_exchange", "primaryExchange",
                        "local_symbol", "localSymbol", "trading_class", "tradingClass", "currency", "instrument_type", "secType")
            if key in metadata and (
                key not in {"con_id", "conId"}
                or (isinstance(metadata[key], int) and not isinstance(metadata[key], bool) and metadata[key] > 0)
            )
        },
        "effective_rss_matching_identity": {
            "symbol": _label(candidate.normalized_symbol),
            "company_aliases": [_identity_text(value) for value in
                                company_aliases_for_symbol(candidate.normalized_symbol, effective)],
        },
    }


# These limits bound only the additive count projection, not the pre-existing event.
_ENTRY_ROWS = 24
_ENTRY_BYTES = 8192
_DATE_COUNTS = ('usable_dates', 'within_window', 'missing_invalid_dates', 'stale_entries',
                'future_entries', 'missing_titles', 'published_time_used', 'updated_time_used')
_DATE_FACTS = ('evaluation_time_utc', 'window_start_utc',
               'observed_publication_min_utc', 'observed_publication_max_utc')


def _count(value):
    # Reject booleans, hostile objects and oversized integers, never stringify them.
    return value if type(value) is int and 0 <= value <= 2**63 - 1 else None


def _flag(value):
    return value if type(value) is bool else None


def _utc_fact(value):
    if type(value) is not str or len(value) > 40:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.astimezone(timezone.utc).isoformat() if parsed.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def _entry_row(item, index, symbols):
    raw = getattr(item, 'entry_diagnostics', None)
    raw = raw if type(raw) is dict else {}
    parsed = _count(item.feed_item_count)
    examined = _count(getattr(item, 'entries_examined_count', None))
    truncated = _flag(getattr(item, 'processing_truncated', None))
    complete = (item.worker_completed is True and item.retrieval_status == 'available'
                and parsed is not None and examined == parsed and truncated is False)
    prefix = (examined is not None and (truncated is True or item.worker_completed is False
              or item.retrieval_status in {'partial', 'timeout', 'budget_exhausted'}
              or (truncated is False and item.worker_completed is True
                  and parsed is not None and examined < parsed)))
    traversal = 'all_parser_entries' if complete else 'examined_prefix' if prefix else 'unknown'
    dates = {key: _count(raw.get(key)) for key in _DATE_COUNTS}
    relevance = raw.get('relevance_rejections_by_symbol')
    relevance = relevance if type(relevance) is dict else {}
    # Do not iterate arbitrary input keys, or emit ticker/query/account strings.
    issuer_counts = [{'symbol_index': i, 'count': _count(relevance.get(symbol))}
                     for i, symbol in enumerate(islice(symbols, 50))]
    exclusions = raw.get('exclusion_evidence')
    exclusions = exclusions if type(exclusions) is dict else {}
    reasons = exclusions.get('counts')
    reasons = reasons if (exclusions.get('schema') == 'news.rss_exclusions.v1'
                          and item.source_group == 'ROSS_ISSUER_QUERY'
                          and type(reasons) is dict) else {}
    reason_counts = {key: _count(reasons.get(key)) for key in sorted(REASONS)}
    reason_measured = any(value is not None for value in reason_counts.values())
    issuer_measured = any(row['count'] is not None for row in issuer_counts)
    utc_facts = {key: _utc_fact(raw.get(key)) for key in _DATE_FACTS}
    return {
        'source_index': index,
        'parser_entries': parsed, 'entries_examined': examined,
        'processing_truncated': truncated, 'traversal_scope': traversal,
        'date_counts': dates if any(v is not None for v in dates.values()) else None,
        'date_counts_scope': traversal if (examined is not None and
            all(v is not None and v <= examined for v in dates.values())) else 'unknown',
        'utc_facts': {key: value for key, value in utc_facts.items() if value is not None} or None,
        'issuer_rejections': issuer_counts if issuer_measured else None,
        'issuer_rejections_scope': 'compared_time_valid_entries' if issuer_measured else 'unknown',
        'issuer_rejections_traversal_scope': traversal if issuer_measured else 'unknown',
        'reason_counts': reason_counts if reason_measured else None,
        'reason_counts_scope': 'instrumented_first_rejections' if reason_measured else 'unknown',
        'reason_counts_traversal_scope': traversal if reason_measured else 'unknown',
        'matched_count': _count(item.matched_count) if examined is not None else None,
        'matched_count_scope': 'existing_source_match_semantics_not_pre_dedup',
        'duplicate_exclusions': None, 'pre_dedup_issuer_matches': None,
        'classification_exclusions': None, 'unmeasured_counts_scope': 'not_collected_by_this_projection',
        'transport_cache_hit': _flag(raw.get('transport_cache_hit')),
        # Never promote the fetcher's missing/default false into proof of no send.
        'http_request_attempted': _flag(raw.get('http_request_attempted'))
            if type(raw.get('transport_cache_hit')) is bool else None,
    }


def _entry_projection_bytes(projection):
    # Count the key/wrapper too; this conservatively bounds the actual event delta.
    return len(json.dumps({'entry_counts': projection}, sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode('utf-8'))


def _entry_counts_projection(result, provider_invoked):
    sources = result.diagnostics.source_diagnostics
    total = len(sources) if type(sources) in (tuple, list) else None
    projection = {'authority': 'diagnostic_only_not_canonical',
                  'qualification_evaluated': False,
                  'max_source_rows': _ENTRY_ROWS, 'max_added_bytes': _ENTRY_BYTES,
                  'sources_total': total, 'sources_emitted': 0, 'sources_omitted': total,
                  'symbol_counts_omitted': max(0, len(result.symbols) - 50),
                  'omitted_bytes': None, 'truncated': False,
                  'status': 'not_collected_this_result',
                  'omissions': {'row_limit': 0, 'byte_limit': 0, 'projection_error': 0, 'not_collected': total},
                  'rows': []}
    # Historical/cache-only facts are not a fresh parsing result. Existing source
    # status fields remain in the original event unchanged.
    if not provider_invoked or total is None:
        if total is None:
            projection['status'] = 'unknown_source_schema'
            projection['truncated'] = None
        return projection
    projection['status'] = 'projected'
    projection['omissions']['not_collected'] = 0
    projection['omissions']['row_limit'] = max(0, total - _ENTRY_ROWS)
    # Reserve report capacity for issuer exclusions without changing source/request
    # order. Inspect and sort only the same bounded24 candidate rows.
    selected = list(enumerate(islice(sources, _ENTRY_ROWS)))
    selected.sort(key=lambda pair: (getattr(pair[1], 'source_group', None) != 'ROSS_ISSUER_QUERY', pair[0]))
    for index, item in selected:
        try:
            row = _entry_row(item, index, result.symbols)
            projection['rows'].append(row)
            if _entry_projection_bytes(projection) > _ENTRY_BYTES:
                projection['rows'].pop()
                projection['omissions']['byte_limit'] += 1
        except Exception:
            # No exception text, object repr or additional I/O in a diagnostic.
            if len(projection['rows']) and projection['rows'][-1].get('source_index') == index:
                projection['rows'].pop()
            projection['omissions']['projection_error'] += 1
    # Final metadata growth (e.g. omission counters) must also fit the budget.
    while True:
        projection['sources_emitted'] = len(projection['rows'])
        projection['sources_omitted'] = total - len(projection['rows'])
        projection['truncated'] = bool(projection['sources_omitted'] or projection['symbol_counts_omitted'])
        projection['status'] = 'partial_projection' if projection['truncated'] else 'projected'
        if _entry_projection_bytes(projection) <= _ENTRY_BYTES:
            return projection
        projection['rows'].pop()
        projection['omissions']['byte_limit'] += 1


def emit_retrieval_diagnostics(
    result: NewsBatchResult,
    *,
    provider_invoked: bool,
    cache_diagnostics: Mapping[str, Any] | None = None,
) -> None:
    """Emit facts only; never serialize headlines, raw payloads or policy metadata."""
    diagnostics = result.diagnostics
    details = diagnostics.diagnostics
    cache = cache_diagnostics or details
    policy = result.retrieval_policy
    refresh = details.get("refresh_diagnostics", {})
    refresh = refresh if isinstance(refresh, Mapping) else {}
    payload = {
        "schema": "news.retrieval_diagnostics.v1",
        "started_at_utc": result.started_at.isoformat() if result.started_at else None,
        "completed_at_utc": result.completed_at.isoformat() if result.completed_at else None,
        "symbols": _symbols(result.symbols),
        "candidate_identities": [_candidate_identity(candidate) for candidate in result.candidates],
        "provider_invoked": provider_invoked,
        "provider_failure_reason": _failure(refresh.get("failure_reason", details.get("failure_reason"))),
        "refresh_allowed": bool(details.get("refresh_allowed", False)),
        "refresh_symbols": _symbols(details.get("refresh_symbols", ())),
        "request_mode": _label(policy.refresh_mode) if policy else None,
        "network_allowed": bool(policy.network_allowed) if policy else False,
        "retrieval_status": _label(diagnostics.retrieval_status),
        "provider_status": _label(diagnostics.provider_status),
        "provider_available": diagnostics.provider_available,
        "source_groups": [_label(value) for value in diagnostics.source_groups_queried],
        "sources_attempted": diagnostics.sources_attempted_count,
        "sources_skipped_due_to_budget": diagnostics.sources_skipped_due_to_budget_count,
        "elapsed_seconds": _number(diagnostics.elapsed_seconds),
        "total_budget_seconds": _number(diagnostics.total_budget_seconds),
        "budget_exhausted": diagnostics.budget_exhausted,
        "unresolved_symbols": _symbols(diagnostics.unresolved_symbols),
        "tier_budget_seconds": {
            key: _number(refresh.get(key))
            for key in ("fast_budget_seconds", "extended_budget_seconds", "extended_budget_reserved_seconds")
        },
        "cache": {
            "state": _label(diagnostics.cache_state),
            "read_attempted": bool(policy.allow_cache_read) if policy else False,
            "read_skipped": bool(cache.get("cache_read_skipped", False)),
            "write_attempted": provider_invoked and bool(policy.allow_cache_write) if policy else False,
            **{
                key: _symbols(cache.get(key, ()))
                for key in ("cache_hit_symbols", "cadence_cache_hit_symbols", "cache_miss_symbols", "stale_cache_miss_symbols", "prep_reuse_symbols", "prep_stale_symbols")
            },
            **{
                key: bool(cache.get(key, False))
                for key in ("cache_read_failed", "prep_read_failed")
            },
            "cache_write_failed": bool(details.get("cache_write_failed", False)),
            "cache_read_error": _label(cache.get("cache_read_error")),
            "prep_read_error": _label(cache.get("prep_read_error")),
            "cache_write_error": _label(details.get("cache_write_error")),
        },
        "sources": [
            {
                "source": _source(item.source_id),
                "provider": _label(item.provider),
                "source_group": _label(item.source_group),
                "source_tier": _label(item.source_tier),
                "status": _label(item.retrieval_status),
                "attempted": item.attempted,
                "matched_count": item.matched_count,
                "failure_code": _failure(item.failure_reason),
                "http_status": item.http_status if item.http_status is not None else (
                    int(str(item.failure_reason)[5:])
                    if re.fullmatch(r"HTTP_[0-9]{3}", str(item.failure_reason)) else None),
                "feed_item_count": _number(item.feed_item_count),
                "worker_completed": item.worker_completed,
                "request_elapsed_seconds": _number(item.request_elapsed_seconds),
                "parse_elapsed_seconds": _number(item.parse_elapsed_seconds),
                "response_closed": item.response_closed,
                "elapsed_kind": _label(item.elapsed_kind),
                "elapsed_seconds": _number(item.elapsed_seconds),
                "timeout_seconds": _number(item.timeout_seconds),
                "timed_out": item.timed_out,
                "budget_exhausted": item.budget_exhausted,
            }
            for item in diagnostics.source_diagnostics
        ],
        "summaries": {
            _label(symbol) or "unknown": {
                "evidence_count": len(result.evidence_by_symbol.get(symbol, ())),
                "retrieval_status": _label(summary.retrieval_status),
                "provider_status": _label(summary.provider_status),
                "provider_available": summary.provider_available,
                "cache_state": _label(summary.cache_state),
                "budget_exhausted": summary.budget_exhausted,
                "retrieval_unavailable": summary.retrieval_unavailable,
                "objective_news_status": _label(summary.diagnostics.get("objective_news_status")),
                "fresh_evidence_count": sum(item.stale is False for item in result.evidence_by_symbol.get(symbol, ())),
                "stale_evidence_count": sum(item.stale is True for item in result.evidence_by_symbol.get(symbol, ())),
                "unavailability_reasons": [
                    reason for condition, reason in (
                        (summary.provider_available is False, "provider_unavailable"),
                        (summary.budget_exhausted, "budget_exhausted"),
                        (summary.retrieval_status in {"unavailable", "timeout", "budget_exhausted", "provider_error"},
                         "retrieval_" + str(summary.retrieval_status)),
                    ) if condition
                ],
            }
            for symbol, summary in result.summaries_by_symbol.items()
        },
    }
    try:
        payload['entry_counts'] = _entry_counts_projection(result, provider_invoked)
    except Exception:
        # Projection failure is visible, but cannot turn a completed acquisition
        # into a different result. Original event/log failure behavior is unchanged.
        payload['entry_counts'] = {'authority': 'diagnostic_only_not_canonical',
            'qualification_evaluated': False, 'status': 'projection_error',
            'sources_total': None, 'sources_emitted': 0, 'sources_omitted': None,
            'omitted_bytes': None, 'truncated': True, 'rows': []}
    print(_PREFIX + json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False), flush=True)
