from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from src.news.batch_rss_adapter import (
    BatchRssNewsIntelligenceProvider, _extended_tier_reserve_fraction, _lookback_hours,
    _max_entries_per_symbol, _request_timeout_seconds, _source_groups_for_policy,
    _total_budget_seconds,
)
from src.news.retrieval_diagnostics import emit_retrieval_diagnostics
from src.news.evidence_store import (
    CanonicalNewsEvidenceStore,
    dedupe_evidence,
    evidence_max_entries,
    evidence_freshness_seconds,
    normalize_symbol,
    summarize_news_evidence,
)
from src.news.source_groups import get_source_group_urls
from src.news.news_intelligence_contract import (
    CacheState,
    NewsBatchResult,
    NewsCandidate,
    NewsEvidence,
    NewsEvidenceSummary,
    NewsIntelligenceProvider,
    NewsRequest,
    RetrievalDiagnostics,
    RetrievalPolicy,
)


REFRESH_SYMBOL_METADATA_KEYS = (
    "refresh_symbols",
    "unresolved_symbols",
    "extended_unresolved_symbols",
    "symbols_for_extended_fallback",
)


def _json_value(value: Any) -> Any:
    """Stable JSON values for the opt-in diagnostic acquisition record."""
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_json_value(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _acquisition_profile(candidate: NewsCandidate, request: NewsRequest, policy: RetrievalPolicy) -> dict[str, Any]:
    groups = _source_groups_for_policy(policy)
    profile = _json_value({
        "schema": "news.acquisition_profile.v1",
        "request": {
            "lookback_seconds": _lookback_hours(request) * 3600,
            "freshness_seconds": evidence_freshness_seconds(request),
            "max_evidence_per_symbol": _max_entries_per_symbol(request),
            "event_classes": request.event_classes,
            "include_generic_news": request.include_generic_news,
            "need_heat": request.need_heat, "need_velocity": request.need_velocity,
            "need_reliability": request.need_reliability,
        },
        "retrieval": {
            "source_groups": groups,
            "source_urls_by_group": {group: get_source_group_urls(group) for group in groups},
            "provider_groups": policy.provider_groups,
            "total_budget_seconds": _total_budget_seconds(policy),
            "tier_budgets": policy.tier_budgets,
            "extended_reserve_fraction": _extended_tier_reserve_fraction(policy),
            "request_timeout_seconds": _request_timeout_seconds(policy),
            "timeout_policy": policy.timeout_policy,
            "max_sources": policy.max_sources, "max_items_per_source": policy.max_items_per_source,
            "fallback_mode": policy.fallback_mode,
        },
        "issuer": {
            "symbol": candidate.normalized_symbol, "company_name": candidate.company_name,
            "aliases": candidate.aliases, "exchange": candidate.exchange,
            "market": candidate.market, "region": candidate.region, "metadata": candidate.metadata,
        },
    })
    profile["fingerprint"] = hashlib.sha256(json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return profile


class CanonicalNewsIntelligenceService(NewsIntelligenceProvider):
    """Cache/prep-first News Intelligence provider with bounded refresh."""

    provider_id = "canonical_news_intelligence"

    def __init__(
        self,
        *,
        evidence_store: CanonicalNewsEvidenceStore | None = None,
        retrieval_provider: NewsIntelligenceProvider | None = None,
    ) -> None:
        self.evidence_store = evidence_store or CanonicalNewsEvidenceStore()
        self.retrieval_provider = retrieval_provider or BatchRssNewsIntelligenceProvider()

    def get_news(
        self,
        candidates: Sequence[NewsCandidate],
        request: NewsRequest,
        retrieval_policy: RetrievalPolicy,
    ) -> NewsBatchResult:
        started_at = datetime.now(timezone.utc)
        ordered_candidates = _dedupe_candidates(candidates)
        symbols = [candidate.normalized_symbol for candidate in ordered_candidates]
        if not symbols:
            result = NewsBatchResult(
                candidates=ordered_candidates,
                evidence_by_symbol={},
                summaries_by_symbol={},
                diagnostics=RetrievalDiagnostics(
                    retrieval_status="not_requested",
                    provider_status="no_symbols",
                    provider_available=True,
                    diagnostics={"provider_id": self.provider_id, "failure_reason": "no_symbols"},
                ),
                request=request,
                retrieval_policy=retrieval_policy,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )
            emit_retrieval_diagnostics(result, provider_invoked=False)
            return result

        cache_read = (
            self.evidence_store.read(ordered_candidates, request)
            if retrieval_policy.allow_cache_read
            else None
        )
        cached_evidence = cache_read.evidence_by_symbol if cache_read else {symbol: tuple() for symbol in symbols}
        cache_diagnostics = cache_read.diagnostics if cache_read else {
            "cache_hit_symbols": [],
            "cache_miss_symbols": list(symbols),
            "stale_cache_miss_symbols": [],
            "prep_reuse_symbols": [],
            "cache_read_skipped": True,
        }
        require_compatible = bool(retrieval_policy.metadata.get("require_compatible_acquisition"))
        profiles = ({candidate.normalized_symbol: _acquisition_profile(candidate, request, retrieval_policy)
                     for candidate in ordered_candidates} if require_compatible else {})
        previous_retrievals = cache_diagnostics.get("last_retrieval_by_symbol", {})
        compatible = {symbol: previous_retrievals.get(symbol, {}).get("acquisition_profile") == profile
                      for symbol, profile in profiles.items()}
        mismatches = [symbol for symbol in symbols if require_compatible and not compatible[symbol]]
        explicit_refresh_symbols = _explicit_refresh_symbols(symbols, retrieval_policy.metadata)
        if explicit_refresh_symbols is None and retrieval_policy.refresh_mode == "force_refresh":
            refresh_symbols = list(symbols)
        elif explicit_refresh_symbols is None and retrieval_policy.refresh_interval_seconds is not None:
            refresh_symbols = _symbols_due_refresh(
                symbols, cache_diagnostics, retrieval_policy.refresh_interval_seconds, now=started_at,
            )
        elif explicit_refresh_symbols is None:
            refresh_symbols = _symbols_without_fresh_evidence(symbols, cached_evidence)
        else:
            refresh_symbols = explicit_refresh_symbols
        if require_compatible:
            if explicit_refresh_symbols is None:
                refresh_symbols = [symbol for symbol in symbols if symbol in refresh_symbols or symbol in mismatches]
            cache_diagnostics["cadence_cache_hit_symbols"] = [
                symbol for symbol in cache_diagnostics.get("cadence_cache_hit_symbols", []) if symbol not in mismatches
            ]
        refresh_allowed = (
            retrieval_policy.network_allowed
            and retrieval_policy.refresh_mode not in {"cache_only", "disabled"}
            and bool(refresh_symbols)
        )

        refresh_result: NewsBatchResult | None = None
        retrieval_by_symbol: dict[str, dict[str, Any]] = {}
        write_diagnostics: dict[str, Any] = {
            "cache_write_skipped": True,
            "cache_write_symbols": [],
            "cache_write_failed": False,
            "cache_write_error": None,
        }
        if refresh_allowed:
            refresh_candidates = [candidate for candidate in ordered_candidates if candidate.normalized_symbol in set(refresh_symbols)]
            refresh_metadata = {
                **dict(retrieval_policy.metadata or {}),
                "unresolved_symbols": tuple(refresh_symbols),
                "refresh_symbols": tuple(refresh_symbols),
            }
            refresh_policy = replace(
                retrieval_policy,
                allow_cache_read=False,
                metadata=refresh_metadata,
            )
            refresh_result = self.retrieval_provider.get_news(refresh_candidates, request, refresh_policy)
            if retrieval_policy.allow_cache_write or require_compatible:
                completed_at = refresh_result.completed_at or datetime.now(timezone.utc)
                coverage = _json_value(asdict(refresh_result.diagnostics)) if require_compatible else None
                for symbol in refresh_symbols:
                    outcome = _refresh_symbol_outcome(symbol, refresh_result)
                    retrieval_by_symbol[symbol] = {
                        "completed_at": completed_at.isoformat(),
                        "retrieval_status": outcome.retrieval_status,
                        "provider_status": outcome.provider_status,
                        "provider_available": outcome.provider_available,
                        "budget_exhausted": outcome.budget_exhausted,
                    }
                    if require_compatible:
                        retrieval_by_symbol[symbol].update(acquisition_profile=profiles[symbol], coverage=coverage)
            if retrieval_policy.allow_cache_write:
                # Persist acquisition outcomes even when the provider returns no articles.
                retrieved = {symbol: tuple(refresh_result.evidence_by_symbol.get(symbol, ()))
                             for symbol in refresh_symbols}
                write_with_metadata = getattr(self.evidence_store, "write_with_retrieval_metadata", None)
                if callable(write_with_metadata):
                    write_diagnostics = write_with_metadata(
                        retrieved, request, retrieval_by_symbol=retrieval_by_symbol,
                    )
                else:
                    # Existing injected stores retain their two-argument contract.
                    # Without acquisition persistence they refresh conservatively.
                    write_diagnostics = self.evidence_store.write(retrieved, request)
                write_diagnostics["cache_write_skipped"] = False

        coverage_unknown = [symbol for symbol in mismatches if symbol not in retrieval_by_symbol]
        if require_compatible:
            cache_diagnostics["acquisition_cache_hit_symbols"] = [
                symbol for symbol in symbols if compatible[symbol] and symbol not in retrieval_by_symbol
            ]
        combined_evidence: dict[str, tuple[NewsEvidence, ...]] = {}
        summaries: dict[str, NewsEvidenceSummary] = {}
        for symbol in symbols:
            items = list(cached_evidence.get(symbol, ()))
            if refresh_result is not None:
                items.extend(refresh_result.evidence_by_symbol.get(symbol, ()))
            merged = tuple(dedupe_evidence(items, max_items=evidence_max_entries(request)))
            combined_evidence[symbol] = merged
            cached_retrieval = (cache_diagnostics.get("last_retrieval_by_symbol", {}).get(symbol, {})
                                if symbol in cache_diagnostics.get("cadence_cache_hit_symbols", []) else {})
            if require_compatible:
                cached_retrieval = retrieval_by_symbol.get(symbol, previous_retrievals.get(symbol, {}) if compatible[symbol] else {})
            symbol_refresh = refresh_result if refresh_result is not None and (not require_compatible or symbol in refresh_symbols) else None
            refreshed_outcome = _refresh_symbol_outcome(symbol, symbol_refresh) if symbol_refresh is not None else None
            provider_status = (refreshed_outcome.provider_status if refreshed_outcome is not None
                               else _provider_status(refresh_result, cache_diagnostics))
            provider_available = (refreshed_outcome.provider_available if refreshed_outcome is not None
                                  else _provider_available(refresh_result, cache_diagnostics))
            budget_exhausted = cached_retrieval.get("budget_exhausted", _symbol_budget_exhausted(symbol, refresh_result))
            summaries[symbol] = summarize_news_evidence(
                symbol,
                merged,
                request=request,
                retrieval_status=cached_retrieval.get("retrieval_status") or _symbol_retrieval_status(symbol, refresh_result, merged, cache_diagnostics),
                provider_status=cached_retrieval.get("provider_status") or provider_status,
                provider_available=cached_retrieval.get("provider_available", provider_available),
                cache_state=_symbol_cache_state(symbol, merged, cache_diagnostics),
                budget_exhausted=budget_exhausted,
                diagnostics={
                    "provider_id": self.provider_id,
                    "cache_hit": symbol in set(cache_diagnostics.get("cache_hit_symbols", [])),
                    "cache_stale": symbol in set(cache_diagnostics.get("stale_cache_miss_symbols", [])),
                    "prep_reused": symbol in set(cache_diagnostics.get("prep_reuse_symbols", [])),
                    "refresh_requested": symbol in set(refresh_symbols),
                    "last_retrieval": dict(cached_retrieval),
                    "objective_news_status": _objective_status(symbol, merged, refresh_result, budget_exhausted=budget_exhausted),
                    "classification_authority": "strategy_adapter_not_common_provider",
                },
            )
            if symbol in coverage_unknown:
                summaries[symbol] = replace(summaries[symbol], retrieval_status="unknown", provider_status="coverage_unknown",
                    provider_available=None, budget_exhausted=False, diagnostics={
                        **summaries[symbol].diagnostics, "objective_news_status": "coverage_unknown",
                        "last_retrieval": dict(previous_retrievals.get(symbol, {})),
                    })

        diagnostics = _combined_diagnostics(
            symbols=symbols,
            retrieval_policy=retrieval_policy,
            cache_diagnostics=cache_diagnostics,
            write_diagnostics=write_diagnostics,
            refresh_symbols=refresh_symbols,
            refresh_allowed=refresh_allowed,
            refresh_result=refresh_result,
            combined_evidence=combined_evidence,
            summaries=summaries,
        )
        if require_compatible:
            diagnostics = replace(diagnostics, diagnostics={
                **diagnostics.diagnostics,
                "acquisition_profile_compatible_by_symbol": compatible,
                "acquisition_profile_mismatch_symbols": mismatches,
                "acquisition_coverage_unknown_symbols": coverage_unknown,
                "acquisition_cache_hit_symbols": cache_diagnostics["acquisition_cache_hit_symbols"],
                "retrieved_evidence_ids_by_symbol": {
                    symbol: list(dict.fromkeys(item.evidence_id for item in refresh_result.evidence_for_symbol(symbol)
                                              if item.evidence_id is not None)) if refresh_result is not None else []
                    for symbol in symbols
                },
                "last_retrieval_by_symbol": {
                    symbol: dict(summaries[symbol].diagnostics["last_retrieval"]) for symbol in symbols
                },
            })
            if coverage_unknown:
                all_unknown = len(coverage_unknown) == len(symbols)
                diagnostics = replace(diagnostics, retrieval_status="unknown" if all_unknown else "partial",
                    provider_status="coverage_unknown" if all_unknown else "mixed",
                    provider_available=None if diagnostics.provider_available is not False else False,
                    unresolved_symbols=tuple(dict.fromkeys((*diagnostics.unresolved_symbols, *coverage_unknown))))
        result = NewsBatchResult(
            candidates=ordered_candidates,
            evidence_by_symbol=combined_evidence,
            summaries_by_symbol=summaries,
            diagnostics=diagnostics,
            request=request,
            retrieval_policy=retrieval_policy,
            cache_state=diagnostics.cache_state,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
        )
        emit_retrieval_diagnostics(
            result, provider_invoked=refresh_result is not None, cache_diagnostics=cache_diagnostics
        )
        return result


def _dedupe_candidates(candidates: Sequence[NewsCandidate]) -> tuple[NewsCandidate, ...]:
    seen: set[str] = set()
    ordered: list[NewsCandidate] = []
    for candidate in candidates:
        symbol = candidate.normalized_symbol
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        ordered.append(candidate)
    return tuple(ordered)


def _explicit_refresh_symbols(symbols: Sequence[str], metadata: Mapping[str, Any]) -> list[str] | None:
    raw: Any = None
    found = False
    for key in REFRESH_SYMBOL_METADATA_KEYS:
        if key in metadata:
            raw = metadata.get(key)
            found = True
            break
    if not found:
        return None
    if raw is None:
        return []
    if isinstance(raw, str):
        requested = {normalize_symbol(raw)}
    else:
        try:
            requested = {normalize_symbol(item) for item in raw}
        except TypeError:
            requested = set()
    requested.discard("")
    return [symbol for symbol in symbols if symbol in requested]


def _symbols_due_refresh(symbols, diagnostics, interval_seconds, *, now):
    """Use canonical acquisition timestamps, including empty outcomes, for cadence."""
    try:
        interval = float(interval_seconds)
    except (TypeError, ValueError):
        interval = 0.0
    if not math.isfinite(interval) or interval < 0:
        interval = 0.0
    metadata = diagnostics.get("last_retrieval_by_symbol", {})
    rejected = diagnostics.get("issuer_relevance_rejected_by_symbol", {})
    due = []
    hits = []
    for symbol in symbols:
        raw = metadata.get(symbol, {}).get("completed_at")
        try:
            acquired = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            age = (now - acquired).total_seconds() if acquired.tzinfo is not None else -1
        except (ValueError, TypeError):
            age = -1
        if symbol in rejected or not (0 <= age < interval):
            due.append(symbol)
        else:
            hits.append(symbol)
    diagnostics["cadence_cache_hit_symbols"] = hits
    diagnostics["refresh_interval_seconds"] = interval
    return due


def _symbols_without_fresh_evidence(
    symbols: Sequence[str],
    evidence_by_symbol: Mapping[str, Sequence[NewsEvidence]],
) -> list[str]:
    refresh: list[str] = []
    for symbol in symbols:
        evidence = evidence_by_symbol.get(symbol, ())
        if not any(item.stale is False for item in evidence):
            refresh.append(symbol)
    return refresh


def _refresh_symbol_outcome(symbol: str, result: NewsBatchResult) -> NewsEvidenceSummary | RetrievalDiagnostics:
    """Use the same per-symbol outcome for persistence, summaries and aggregation."""
    summary = result.summary_for_symbol(symbol)
    if summary is not None and summary.retrieval_status == "budget_exhausted" and not summary.budget_exhausted:
        summary = replace(summary, budget_exhausted=True)
    if summary is not None and summary.provider_status in {"provider_unavailable", "provider_request_failure"}:
        status = summary.retrieval_status
        if status not in {"unavailable", "timeout", "budget_exhausted", "provider_error"}:
            status = "provider_error" if summary.provider_status == "provider_request_failure" else "unavailable"
        return replace(summary, provider_available=False, retrieval_status=status)
    if summary is not None and (
        (summary.provider_available is False
         and summary.provider_status not in {None, "", "unknown", "not_requested", "available"})
        or summary.budget_exhausted
        or summary.retrieval_status not in {"unknown", "not_requested"}
    ):
        return summary
    # A reachable provider does not prove completed per-symbol retrieval.
    diagnostics = result.diagnostics
    if diagnostics.retrieval_status == "budget_exhausted" and not diagnostics.budget_exhausted:
        diagnostics = replace(diagnostics, budget_exhausted=True)
    if diagnostics.unresolved_symbols:
        unresolved = symbol in diagnostics.unresolved_symbols
        exhausted = unresolved and diagnostics.budget_exhausted
        diagnostics = replace(
            diagnostics,
            retrieval_status=("budget_exhausted" if exhausted else "unavailable") if unresolved else "available",
            # Preserve the provider's reason/reachability for unresolved symbols;
            # successful peers must not inherit a failed batch provider label.
            provider_status=diagnostics.provider_status if unresolved else "available",
            provider_available=not unresolved,
            budget_exhausted=exhausted,
            unresolved_symbols=(symbol,) if unresolved else (),
        )
    if summary is not None and summary.provider_available is False:
        # Negative availability alone does not supply the missing failure reason
        # or budget outcome. Only enrich it from a failure scoped to this symbol;
        # a healthy batch or another symbol's failure cannot clear that negative.
        # Persist it as unavailable so later mixed cache diagnostics cannot
        # reinterpret an unknown outcome as another symbol's budget failure.
        if not (diagnostics.unavailable or diagnostics.provider_status in {"provider_unavailable", "provider_request_failure"}):
            return replace(summary, retrieval_status="unavailable")
        diagnostics = replace(diagnostics, provider_available=False)
    if diagnostics.provider_available is False and diagnostics.retrieval_status in {"unknown", "not_requested"}:
        diagnostics = replace(diagnostics, retrieval_status="budget_exhausted" if diagnostics.budget_exhausted else "unavailable")
    if summary is None:
        return diagnostics
    # Providers may supply article metrics while leaving outcome fields unknown.
    # Persist the explicit retrieval outcome so a cadence hit or service restart
    # cannot turn a known failure into an apparently successful empty response.
    return replace(summary, retrieval_status=diagnostics.retrieval_status,
                   provider_status=diagnostics.provider_status,
                   provider_available=diagnostics.provider_available,
                   budget_exhausted=diagnostics.budget_exhausted)


def _symbol_retrieval_status(
    symbol: str,
    refresh_result: NewsBatchResult | None,
    evidence: Sequence[NewsEvidence],
    cache_diagnostics: Mapping[str, Any],
) -> str:
    if refresh_result is not None:
        return _refresh_symbol_outcome(symbol, refresh_result).retrieval_status
    if any(item.stale is False for item in evidence):
        return "cache_hit"
    if symbol in set(cache_diagnostics.get("stale_cache_miss_symbols", [])):
        return "available"
    return "not_requested"


def _provider_status(refresh_result: NewsBatchResult | None, cache_diagnostics: Mapping[str, Any]) -> str:
    if refresh_result is not None:
        return refresh_result.diagnostics.provider_status or "unknown"
    if cache_diagnostics.get("cache_read_failed"):
        return "cache_read_error"
    if cache_diagnostics.get("cache_hit_symbols") or cache_diagnostics.get("prep_reuse_symbols"):
        return "cache"
    return "cache_miss"


def _provider_available(refresh_result: NewsBatchResult | None, cache_diagnostics: Mapping[str, Any]) -> bool:
    if refresh_result is not None and refresh_result.diagnostics.provider_available is not None:
        return bool(refresh_result.diagnostics.provider_available)
    return not bool(cache_diagnostics.get("cache_read_failed"))


def _symbol_cache_state(
    symbol: str,
    evidence: Sequence[NewsEvidence],
    cache_diagnostics: Mapping[str, Any],
) -> CacheState:
    if symbol in cache_diagnostics.get("acquisition_cache_hit_symbols", ()):
        return "hit"
    if symbol in set(cache_diagnostics.get("cadence_cache_hit_symbols", [])) or symbol in set(cache_diagnostics.get("cache_hit_symbols", [])) or any(item.cache_state == "hit" for item in evidence):
        return "hit"
    if symbol in set(cache_diagnostics.get("stale_cache_miss_symbols", [])):
        return "stale"
    return "miss"


def _symbol_budget_exhausted(symbol: str, refresh_result: NewsBatchResult | None) -> bool:
    if refresh_result is None:
        return False
    return bool(_refresh_symbol_outcome(symbol, refresh_result).budget_exhausted)


def _objective_status(
    symbol: str,
    evidence: Sequence[NewsEvidence],
    refresh_result: NewsBatchResult | None,
    *,
    budget_exhausted: bool | None = None,
) -> str:
    if budget_exhausted is None:
        budget_exhausted = _symbol_budget_exhausted(symbol, refresh_result)
    if budget_exhausted:
        return "budget_exhausted"
    if any(item.stale is False for item in evidence):
        return "news_present_unclassified"
    if evidence:
        return "stale_news"
    return "no_recent_news"


def _combined_diagnostics(
    *,
    symbols: Sequence[str],
    retrieval_policy: RetrievalPolicy,
    cache_diagnostics: Mapping[str, Any],
    write_diagnostics: Mapping[str, Any],
    refresh_symbols: Sequence[str],
    refresh_allowed: bool,
    refresh_result: NewsBatchResult | None,
    combined_evidence: Mapping[str, Sequence[NewsEvidence]],
    summaries: Mapping[str, NewsEvidenceSummary],
) -> RetrievalDiagnostics:
    refresh_diag = refresh_result.diagnostics if refresh_result is not None else None
    cache_hit_symbols = tuple(sorted(set(cache_diagnostics.get("cache_hit_symbols", []))))
    stale_symbols = tuple(sorted(set(cache_diagnostics.get("stale_cache_miss_symbols", []))))
    miss_symbols = tuple(sorted(set(cache_diagnostics.get("cache_miss_symbols", []))))
    prep_symbols = tuple(sorted(set(cache_diagnostics.get("prep_reuse_symbols", []))))
    cadence_hits = tuple(cache_diagnostics.get("cadence_cache_hit_symbols", ()))
    acquisition_hits = tuple(cache_diagnostics.get("acquisition_cache_hit_symbols", ()))
    if cache_hit_symbols or cadence_hits or acquisition_hits:
        cache_state: CacheState = "hit"
    elif stale_symbols:
        cache_state = "stale"
    elif retrieval_policy.allow_cache_read:
        cache_state = "miss"
    else:
        cache_state = "not_checked"
    retrieval_status = (
        refresh_diag.retrieval_status
        if refresh_diag is not None
        else ("cache_hit" if cache_hit_symbols else "not_requested")
    )
    diagnostics_payload = {
        "provider_id": CanonicalNewsIntelligenceService.provider_id,
        "cache_first": True,
        "cache_file": cache_diagnostics.get("cache_file"),
        "cache_namespace": cache_diagnostics.get("cache_namespace"),
        "cache_hits_by_symbol": dict(cache_diagnostics.get("cache_hits_by_symbol", {}) or {}),
        "cache_hit_symbols": list(cache_hit_symbols),
        "cadence_cache_hit_symbols": list(cache_diagnostics.get("cadence_cache_hit_symbols", [])),
        "last_retrieval_by_symbol": dict(cache_diagnostics.get("last_retrieval_by_symbol", {})),
        "refresh_interval_seconds": retrieval_policy.refresh_interval_seconds,
        "stale_cache_miss_symbols": list(stale_symbols),
        "cache_miss_symbols": list(miss_symbols),
        "prep_reuse_symbols": list(prep_symbols),
        "prep_stale_symbols": list(cache_diagnostics.get("prep_stale_symbols", []) or []),
        "legacy_news_cache_symbols": list(cache_diagnostics.get("legacy_news_cache_symbols", []) or []),
        "refresh_requested_count": len(refresh_symbols),
        "refresh_symbols": list(refresh_symbols),
        "refresh_allowed": bool(refresh_allowed),
        "cache_read_failed": bool(cache_diagnostics.get("cache_read_failed", False)),
        "cache_read_error": cache_diagnostics.get("cache_read_error"),
        "cache_write_failed": bool(write_diagnostics.get("cache_write_failed", False)),
        "cache_write_error": write_diagnostics.get("cache_write_error"),
        "cache_write_symbols": list(write_diagnostics.get("cache_write_symbols", []) or []),
        "evidence_count_by_symbol": {symbol: len(combined_evidence.get(symbol, ())) for symbol in symbols},
        "freshest_evidence_age_seconds_by_symbol": {
            symbol: min(
                (item.age_seconds for item in combined_evidence.get(symbol, ()) if item.age_seconds is not None),
                default=None,
            )
            for symbol in symbols
        },
        "source_provenance_by_symbol": {
            symbol: [
                {
                    "source": item.observed_source or item.original_source,
                    "domain": item.source_domain,
                    "url": item.url,
                    "published_at": item.published_at.isoformat() if item.published_at else None,
                    "source_group": item.source_group,
                    "source_tier": item.source_tier,
                    "cache_state": item.cache_state,
                    "retrieval_status": item.retrieval_status,
                }
                for item in combined_evidence.get(symbol, ())
            ]
            for symbol in symbols
        },
        "match_types_by_symbol": {
            symbol: sorted({str(item.match_type) for item in combined_evidence.get(symbol, ()) if item.match_type})
            for symbol in symbols
        },
        "reliability_by_symbol": {
            symbol: max(
                (
                    value
                    for item in combined_evidence.get(symbol, ())
                    for value in (item.source_reliability_score, item.source_credibility_score)
                    if value is not None
                ),
                default=None,
            )
            for symbol in symbols
        },
        "heat_by_symbol": {
            symbol: max((item.heat_score for item in combined_evidence.get(symbol, ()) if item.heat_score is not None), default=None)
            for symbol in symbols
        },
        "velocity_by_symbol": {
            symbol: {
                "velocity_5m": max((item.velocity_5m for item in combined_evidence.get(symbol, ()) if item.velocity_5m is not None), default=None),
                "velocity_10m": max((item.velocity_10m for item in combined_evidence.get(symbol, ()) if item.velocity_10m is not None), default=None),
                "velocity_30m": max((item.velocity_30m for item in combined_evidence.get(symbol, ()) if item.velocity_30m is not None), default=None),
                "velocity_60m": max((item.velocity_60m for item in combined_evidence.get(symbol, ()) if item.velocity_60m is not None), default=None),
            }
            for symbol in symbols
        },
        "refresh_diagnostics": dict(refresh_diag.diagnostics or {}) if refresh_diag is not None else {},
        "classification_authority": "strategy_adapter_not_common_provider",
    }
    provider_status = _provider_status(refresh_result, cache_diagnostics)
    provider_available = _provider_available(refresh_result, cache_diagnostics)
    known_budget_symbols = tuple(symbol for symbol in symbols if summaries[symbol].budget_exhausted)
    budget_exhausted = bool(known_budget_symbols) or bool(
        refresh_diag is not None
        and (refresh_diag.budget_exhausted or refresh_diag.retrieval_status == "budget_exhausted")
    )
    unresolved_symbols = refresh_diag.unresolved_symbols if refresh_diag is not None else ()
    unresolved_symbols = tuple(dict.fromkeys((*unresolved_symbols, *known_budget_symbols)))
    if cadence_hits or acquisition_hits:
        # Batch facts must agree with the effective per-symbol acquisition outcomes,
        # including negative cache hits and batches mixing cached and fresh retrievals.
        outcomes = [summaries[symbol] for symbol in symbols]
        statuses = {item.retrieval_status for item in outcomes}
        providers = {item.provider_status for item in outcomes}
        availability = {item.provider_available for item in outcomes}
        retrieval_status = next(iter(statuses)) if len(statuses) == 1 else "partial"
        provider_status = next(iter(providers)) if len(providers) == 1 else "mixed"
        provider_available = False if False in availability else (None if None in availability else True)
        budget_exhausted = any(item.budget_exhausted for item in outcomes)
        unresolved_symbols = tuple(item.symbol for item in outcomes if item.retrieval_unavailable or item.budget_exhausted)
    return RetrievalDiagnostics(
        retrieval_status=retrieval_status,
        provider_status=provider_status,
        provider_available=provider_available,
        cache_state=cache_state,
        source_groups_queried=refresh_diag.source_groups_queried if refresh_diag is not None else (),
        provider_groups_queried=("canonical_news_intelligence",) + (refresh_diag.provider_groups_queried if refresh_diag is not None else ()),
        sources_queried=refresh_diag.sources_queried if refresh_diag is not None else (),
        source_diagnostics=refresh_diag.source_diagnostics if refresh_diag is not None else (),
        source_failures=refresh_diag.source_failures if refresh_diag is not None else {},
        sources_attempted_count=refresh_diag.sources_attempted_count if refresh_diag is not None else 0,
        sources_skipped_due_to_budget_count=refresh_diag.sources_skipped_due_to_budget_count if refresh_diag is not None else 0,
        elapsed_seconds=refresh_diag.elapsed_seconds if refresh_diag is not None else 0.0,
        total_budget_seconds=refresh_diag.total_budget_seconds if refresh_diag is not None else retrieval_policy.total_budget_seconds,
        budget_exhausted=budget_exhausted,
        timeout_count=refresh_diag.timeout_count if refresh_diag is not None else 0,
        unresolved_symbols=unresolved_symbols,
        diagnostics=diagnostics_payload,
    )


__all__ = ["CanonicalNewsIntelligenceService", "REFRESH_SYMBOL_METADATA_KEYS"]
