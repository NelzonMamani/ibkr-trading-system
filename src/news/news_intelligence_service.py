from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from src.news.batch_rss_adapter import BatchRssNewsIntelligenceProvider
from src.news.evidence_store import (
    CanonicalNewsEvidenceStore,
    dedupe_evidence,
    evidence_max_entries,
    normalize_symbol,
    summarize_news_evidence,
)
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
            return NewsBatchResult(
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
        explicit_refresh_symbols = _explicit_refresh_symbols(symbols, retrieval_policy.metadata)
        if explicit_refresh_symbols is None:
            refresh_symbols = _symbols_without_fresh_evidence(symbols, cached_evidence)
        else:
            refresh_symbols = explicit_refresh_symbols
        refresh_allowed = (
            retrieval_policy.network_allowed
            and retrieval_policy.refresh_mode not in {"cache_only", "disabled"}
            and bool(refresh_symbols)
        )

        refresh_result: NewsBatchResult | None = None
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
            if retrieval_policy.allow_cache_write:
                write_diagnostics = self.evidence_store.write(refresh_result.evidence_by_symbol, request)
                write_diagnostics["cache_write_skipped"] = False

        combined_evidence: dict[str, tuple[NewsEvidence, ...]] = {}
        summaries: dict[str, NewsEvidenceSummary] = {}
        for symbol in symbols:
            items = list(cached_evidence.get(symbol, ()))
            if refresh_result is not None:
                items.extend(refresh_result.evidence_by_symbol.get(symbol, ()))
            merged = tuple(dedupe_evidence(items, max_items=evidence_max_entries(request)))
            combined_evidence[symbol] = merged
            summaries[symbol] = summarize_news_evidence(
                symbol,
                merged,
                request=request,
                retrieval_status=_symbol_retrieval_status(symbol, refresh_result, merged, cache_diagnostics),
                provider_status=_provider_status(refresh_result, cache_diagnostics),
                provider_available=_provider_available(refresh_result, cache_diagnostics),
                cache_state=_symbol_cache_state(symbol, merged, cache_diagnostics),
                budget_exhausted=_symbol_budget_exhausted(symbol, refresh_result),
                diagnostics={
                    "provider_id": self.provider_id,
                    "cache_hit": symbol in set(cache_diagnostics.get("cache_hit_symbols", [])),
                    "cache_stale": symbol in set(cache_diagnostics.get("stale_cache_miss_symbols", [])),
                    "prep_reused": symbol in set(cache_diagnostics.get("prep_reuse_symbols", [])),
                    "refresh_requested": symbol in set(refresh_symbols),
                    "objective_news_status": _objective_status(symbol, merged, refresh_result),
                    "classification_authority": "strategy_adapter_not_common_provider",
                },
            )

        diagnostics = _combined_diagnostics(
            symbols=symbols,
            retrieval_policy=retrieval_policy,
            cache_diagnostics=cache_diagnostics,
            write_diagnostics=write_diagnostics,
            refresh_symbols=refresh_symbols,
            refresh_allowed=refresh_allowed,
            refresh_result=refresh_result,
            combined_evidence=combined_evidence,
        )
        return NewsBatchResult(
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


def _symbol_retrieval_status(
    symbol: str,
    refresh_result: NewsBatchResult | None,
    evidence: Sequence[NewsEvidence],
    cache_diagnostics: Mapping[str, Any],
) -> str:
    if refresh_result is not None:
        summary = refresh_result.summary_for_symbol(symbol)
        if summary is not None:
            return summary.retrieval_status
        return refresh_result.diagnostics.retrieval_status
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
    if symbol in set(cache_diagnostics.get("cache_hit_symbols", [])) or any(item.cache_state == "hit" for item in evidence):
        return "hit"
    if symbol in set(cache_diagnostics.get("stale_cache_miss_symbols", [])):
        return "stale"
    return "miss"


def _symbol_budget_exhausted(symbol: str, refresh_result: NewsBatchResult | None) -> bool:
    if refresh_result is None:
        return False
    summary = refresh_result.summary_for_symbol(symbol)
    if summary is not None:
        return bool(summary.budget_exhausted)
    return symbol in set(refresh_result.diagnostics.unresolved_symbols) and bool(refresh_result.diagnostics.budget_exhausted)


def _objective_status(
    symbol: str,
    evidence: Sequence[NewsEvidence],
    refresh_result: NewsBatchResult | None,
) -> str:
    if _symbol_budget_exhausted(symbol, refresh_result):
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
) -> RetrievalDiagnostics:
    refresh_diag = refresh_result.diagnostics if refresh_result is not None else None
    cache_hit_symbols = tuple(sorted(set(cache_diagnostics.get("cache_hit_symbols", []))))
    stale_symbols = tuple(sorted(set(cache_diagnostics.get("stale_cache_miss_symbols", []))))
    miss_symbols = tuple(sorted(set(cache_diagnostics.get("cache_miss_symbols", []))))
    prep_symbols = tuple(sorted(set(cache_diagnostics.get("prep_reuse_symbols", []))))
    if cache_hit_symbols:
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
    return RetrievalDiagnostics(
        retrieval_status=retrieval_status,
        provider_status=_provider_status(refresh_result, cache_diagnostics),
        provider_available=_provider_available(refresh_result, cache_diagnostics),
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
        budget_exhausted=bool(refresh_diag.budget_exhausted) if refresh_diag is not None else False,
        timeout_count=refresh_diag.timeout_count if refresh_diag is not None else 0,
        unresolved_symbols=refresh_diag.unresolved_symbols if refresh_diag is not None else (),
        diagnostics=diagnostics_payload,
    )


__all__ = ["CanonicalNewsIntelligenceService", "REFRESH_SYMBOL_METADATA_KEYS"]
