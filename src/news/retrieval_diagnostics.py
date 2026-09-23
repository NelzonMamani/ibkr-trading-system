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
                for key in ("cache_hit_symbols", "cache_miss_symbols", "stale_cache_miss_symbols", "prep_reuse_symbols", "prep_stale_symbols")
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
                "http_status": int(str(item.failure_reason)[5:])
                if re.fullmatch(r"HTTP_[0-9]{3}", str(item.failure_reason)) else None,
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
