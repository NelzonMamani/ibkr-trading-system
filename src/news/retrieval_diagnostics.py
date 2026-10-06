"""Bounded, content-free news retrieval facts for captured runtime output."""
from __future__ import annotations

import json
import math
import re
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

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
            key: (metadata[key] if isinstance(metadata[key], int) and not isinstance(metadata[key], bool) else None)
                  if key in {"con_id", "conId"} else _identity_text(metadata[key])
            for key in ("con_id", "conId", "isin", "figi", "primary_exchange", "primaryExchange",
                        "local_symbol", "localSymbol", "trading_class", "tradingClass", "currency", "instrument_type", "secType")
            if key in metadata
        },
        "effective_rss_matching_identity": {
            "symbol": _label(candidate.normalized_symbol),
            "company_aliases": [_identity_text(value) for value in
                                company_aliases_for_symbol(candidate.normalized_symbol, effective)],
        },
    }


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
    print(_PREFIX + json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False), flush=True)
