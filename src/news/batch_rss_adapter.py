from __future__ import annotations

import hashlib
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from src.config.config_resolver import get_config
from src.news.news_fetcher import (
    Headline,
    RssFailureSummary,
    fetch_fast_headlines_for_symbols,
    fetch_headlines_for_symbols,
)
from src.news.evidence_store import enrich_evidence_metrics
from src.news.news_intelligence_contract import (
    NewsBatchResult,
    NewsCandidate,
    NewsEvidence,
    NewsEvidenceSummary,
    NewsIntelligenceProvider,
    NewsRequest,
    RetrievalDiagnostics,
    RetrievalPolicy,
    SourceDiagnostic,
)
from src.news.rss_batch_runtime import (
    dedupe_bounded_headlines,
    extended_tier_reserve_fraction,
    fast_tier_budget_seconds,
    merge_rss_failure_summaries,
    news_provider_status,
    stage_elapsed_seconds,
    stage_remaining_seconds,
)
from src.news.source_groups import SourceGroupId, get_source_group_urls


DEFAULT_SOURCE_GROUPS: tuple[str, ...] = ("FAST_TRADING", "PREP_EXTENDED")
ADAPTED_SOURCE_GROUPS: tuple[str, ...] = ("FAST_TRADING", "PREP_EXTENDED")
UNRESOLVED_SYMBOL_METADATA_KEYS: tuple[str, ...] = (
    "unresolved_symbols",
    "extended_unresolved_symbols",
    "symbols_for_extended_fallback",
)


class BatchRssNewsIntelligenceProvider(NewsIntelligenceProvider):
    """Strategy-neutral adapter over the existing batch RSS fetcher."""

    provider_id = "rss_batch"

    def __init__(self, *, fast_fetcher=None, extended_fetcher=None) -> None:
        self._fast_fetcher = fast_fetcher or fetch_fast_headlines_for_symbols
        self._extended_fetcher = extended_fetcher or fetch_headlines_for_symbols

    def get_news(
        self,
        candidates: Sequence[NewsCandidate],
        request: NewsRequest,
        retrieval_policy: RetrievalPolicy,
    ) -> NewsBatchResult:
        started_at = datetime.now(timezone.utc)
        request = request or NewsRequest()
        retrieval_policy = retrieval_policy or RetrievalPolicy()
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

        source_groups = _source_groups_for_policy(retrieval_policy)
        fast_sources = _sources_for_group(source_groups, "FAST_TRADING")
        extended_sources = _sources_for_group(source_groups, "PREP_EXTENDED")
        fast_source_set = set(fast_sources)
        cross_tier_duplicate_sources = [url for url in extended_sources if url in fast_source_set]
        if cross_tier_duplicate_sources:
            extended_sources = [url for url in extended_sources if url not in fast_source_set]
        unresolved_for_extended = _explicit_unresolved_symbols(symbols, retrieval_policy)
        max_entries_per_symbol = _max_entries_per_symbol(request)
        lookback_hours = _lookback_hours(request)
        request_timeout_s = _request_timeout_seconds(retrieval_policy)
        total_news_budget_seconds = _total_budget_seconds(retrieval_policy)
        stage_started_at_s = time.monotonic()
        stage_deadline_s = stage_started_at_s + total_news_budget_seconds
        fast_budget_seconds = _fast_tier_budget_seconds(
            total_news_budget_seconds,
            retrieval_policy,
            extended_sources_available=bool(extended_sources),
        )
        extended_budget_reserved_seconds = max(0.0, total_news_budget_seconds - fast_budget_seconds)
        fast_deadline_s = min(stage_deadline_s, stage_started_at_s + fast_budget_seconds)
        symbol_metadata = _metadata_by_symbol(ordered_candidates)

        fast_fetched = bool(fast_sources)
        extended_fetched = False
        if fast_sources:
            headlines_by_symbol, fast_summary_raw = self._fast_fetcher(
                symbols,
                fast_sources,
                lookback_hours=lookback_hours,
                request_timeout_s=request_timeout_s,
                symbol_metadata=symbol_metadata,
                max_entries_per_symbol=max_entries_per_symbol,
                total_news_budget_seconds=total_news_budget_seconds,
                stage_started_at_s=stage_started_at_s,
                stage_deadline_s=stage_deadline_s,
                tier_budget_seconds=fast_budget_seconds,
                tier_started_at_s=stage_started_at_s,
                tier_deadline_s=fast_deadline_s,
            )
        else:
            headlines_by_symbol = {symbol: [] for symbol in symbols}
            fast_summary_raw = RssFailureSummary(
                total_sources=0,
                failure_count=0,
                failures_by_domain={},
                reason=("no_sources" if not extended_sources else None),
                max_entries_per_symbol=max_entries_per_symbol,
                total_news_budget_seconds=total_news_budget_seconds,
                news_elapsed_seconds=stage_elapsed_seconds(stage_started_at_s),
            )

        fast_summary = merge_rss_failure_summaries(fast_summary_raw)
        summary: RssFailureSummary = fast_summary
        fast_provider_status = news_provider_status(fast_summary)
        provider_failed = fast_provider_status in {"provider_unavailable", "provider_request_failure"}
        extended_fallback_requested = False
        extended_fallback_symbol_count = 0
        budget_skipped_sources = 0
        budget_skipped_source_diagnostics: tuple[Mapping[str, Any], ...] = ()
        extended_budget_seconds = 0.0
        fast_budget_exhausted = bool(getattr(fast_summary, "tier_budget_exhausted", False))
        extended_budget_exhausted = False

        if (
            not provider_failed
            and retrieval_policy.fallback_mode != "none"
            and unresolved_for_extended
            and extended_sources
        ):
            budget_remaining_s = stage_remaining_seconds(stage_deadline_s)
            budget_exhausted_before_extended = bool(
                getattr(fast_summary, "news_budget_exhausted", False)
            ) or budget_remaining_s <= 0.0
            if not budget_exhausted_before_extended:
                extended_fallback_requested = True
                extended_fallback_symbol_count = len(unresolved_for_extended)
                extended_started_at_s = time.monotonic()
                extended_budget_seconds = stage_remaining_seconds(stage_deadline_s)
                explicit_extended_budget_seconds = retrieval_policy.budget_for_tier("extended")
                if explicit_extended_budget_seconds is not None:
                    extended_budget_seconds = min(extended_budget_seconds, max(0.0, explicit_extended_budget_seconds))
                extended_metadata = {
                    symbol: symbol_metadata.get(symbol, {})
                    for symbol in unresolved_for_extended
                    if symbol_metadata.get(symbol)
                }
                extended_headlines_by_symbol, extended_summary = self._extended_fetcher(
                    unresolved_for_extended,
                    extended_sources,
                    lookback_hours=lookback_hours,
                    request_timeout_s=request_timeout_s,
                    symbol_metadata=extended_metadata,
                    max_entries_per_symbol=max_entries_per_symbol,
                    source_tier="extended",
                    total_news_budget_seconds=total_news_budget_seconds,
                    stage_started_at_s=stage_started_at_s,
                    stage_deadline_s=stage_deadline_s,
                    tier_budget_seconds=extended_budget_seconds,
                    tier_started_at_s=extended_started_at_s,
                    tier_deadline_s=stage_deadline_s,
                )
                extended_fetched = True
                extended_budget_exhausted = bool(
                    getattr(extended_summary, "tier_budget_exhausted", False)
                    or getattr(extended_summary, "news_budget_exhausted", False)
                )
                for symbol, extended_headlines in extended_headlines_by_symbol.items():
                    combined = list(headlines_by_symbol.get(symbol, [])) + list(extended_headlines)
                    headlines_by_symbol[symbol] = dedupe_bounded_headlines(combined, max_entries_per_symbol)
                summary = merge_rss_failure_summaries(fast_summary, extended_summary)
            else:
                extended_budget_exhausted = True
                budget_skipped_source_diagnostics = _budget_skipped_source_diagnostics(
                    extended_sources,
                    source_tier="extended",
                )
                budget_skipped_sources += len(budget_skipped_source_diagnostics)

        summary_elapsed = max(
            float(getattr(summary, "news_elapsed_seconds", 0.0) or 0.0),
            stage_elapsed_seconds(stage_started_at_s),
        )
        budget_exhausted = bool(getattr(summary, "news_budget_exhausted", False)) or budget_skipped_sources > 0
        if budget_skipped_sources or summary_elapsed or budget_exhausted or total_news_budget_seconds:
            summary_updates: dict[str, Any] = {
                "total_news_budget_seconds": total_news_budget_seconds,
                "news_elapsed_seconds": summary_elapsed,
                "news_budget_exhausted": budget_exhausted,
                "sources_skipped_due_to_budget_count": int(
                    getattr(summary, "sources_skipped_due_to_budget_count", 0) or 0
                )
                + budget_skipped_sources,
            }
            if budget_skipped_source_diagnostics:
                tier_source_counts = dict(getattr(summary, "tier_source_counts", {}) or {})
                tier_source_counts["extended"] = tier_source_counts.get("extended", 0) + len(
                    budget_skipped_source_diagnostics
                )
                tier_attempt_counts = dict(getattr(summary, "tier_sources_attempted_counts", {}) or {})
                tier_attempt_counts.setdefault("extended", 0)
                tier_budget_seconds_by_tier = dict(getattr(summary, "tier_budget_seconds_by_tier", {}) or {})
                tier_budget_seconds_by_tier.setdefault("extended", float(extended_budget_seconds))
                tier_elapsed_seconds_by_tier = dict(getattr(summary, "tier_elapsed_seconds_by_tier", {}) or {})
                tier_elapsed_seconds_by_tier.setdefault("extended", 0.0)
                tier_budget_exhausted_by_tier = dict(getattr(summary, "tier_budget_exhausted_by_tier", {}) or {})
                tier_budget_exhausted_by_tier["extended"] = True
                summary_updates.update(
                    source_diagnostics=tuple(getattr(summary, "source_diagnostics", ()) or ())
                    + budget_skipped_source_diagnostics,
                    tier_source_counts=tier_source_counts,
                    tier_sources_attempted_counts=tier_attempt_counts,
                    tier_budget_seconds_by_tier=tier_budget_seconds_by_tier,
                    tier_elapsed_seconds_by_tier=tier_elapsed_seconds_by_tier,
                    tier_budget_exhausted_by_tier=tier_budget_exhausted_by_tier,
                    unique_source_urls_scheduled_count=int(
                        getattr(summary, "unique_source_urls_scheduled_count", 0) or 0
                    )
                    + len(budget_skipped_source_diagnostics),
                )
            summary = replace(summary, **summary_updates)

        provider_status = news_provider_status(summary)
        retrieval_status = _retrieval_status(summary, provider_status)
        budget_unresolved_symbols = _budget_unresolved_symbols(
            symbols,
            unresolved_for_extended,
            news_budget_exhausted=bool(getattr(summary, "news_budget_exhausted", False)),
        )
        evidence_by_symbol: dict[str, tuple[NewsEvidence, ...]] = {}
        summaries_by_symbol: dict[str, NewsEvidenceSummary] = {}
        status_counts: dict[str, int] = {}
        symbols_by_status: dict[str, list[str]] = {}
        now_ts = time.time()

        for candidate in ordered_candidates:
            symbol = candidate.normalized_symbol
            unique_headlines = dedupe_bounded_headlines(headlines_by_symbol.get(symbol, []), max_entries_per_symbol)
            symbol_budget_exhausted = symbol in budget_unresolved_symbols
            evidences = enrich_evidence_metrics(
                tuple(
                    _evidence_from_headline(
                        candidate,
                        headline,
                        request=request,
                        retrieval_status=("budget_exhausted" if symbol_budget_exhausted else retrieval_status),
                        provider_status=provider_status,
                        budget_exhausted=symbol_budget_exhausted,
                        fetched_at=started_at,
                        now_ts=now_ts,
                    )
                    for headline in unique_headlines
                ),
                now_ts=now_ts,
            )
            objective_status = _objective_status_for_symbol(
                symbol,
                unique_headlines,
                budget_unresolved_symbols,
                provider_status,
            )
            status_counts[objective_status] = status_counts.get(objective_status, 0) + 1
            symbols_by_status.setdefault(objective_status, []).append(symbol)
            evidence_by_symbol[symbol] = evidences
            summaries_by_symbol[symbol] = _summary_for_symbol(
                symbol=symbol,
                evidence=evidences,
                retrieval_status=("budget_exhausted" if symbol_budget_exhausted else retrieval_status),
                provider_status=provider_status,
                provider_available=_provider_available(provider_status),
                budget_exhausted=symbol_budget_exhausted,
                objective_status=objective_status,
            )

        tier_attempt_counts = dict(getattr(summary, "tier_sources_attempted_counts", {}) or {})
        source_diag_objects = _source_diagnostics_from_summary(summary)
        source_diag_payload = [dict(getattr(item, "__dict__", {})) for item in source_diag_objects]
        tier_elapsed_by_tier = dict(getattr(summary, "tier_elapsed_seconds_by_tier", {}) or {})
        tier_budget_by_tier = dict(getattr(summary, "tier_budget_seconds_by_tier", {}) or {})
        tier_exhausted_by_tier = dict(getattr(summary, "tier_budget_exhausted_by_tier", {}) or {})
        duplicate_fetches_avoided = int(getattr(summary, "duplicate_source_fetches_avoided_count", 0) or 0) + len(cross_tier_duplicate_sources)
        diagnostics_payload = {
            "provider_id": self.provider_id,
            "legacy_batch_fetcher": "src.news.news_fetcher",
            "classification_authority": "strategy_adapter_not_common_provider",
            "extended_fallback_unresolved_symbol_source": "retrieval_policy.metadata",
            "failure_reason": getattr(summary, "reason", None),
            "rss_sources": int(getattr(summary, "total_sources", 0) or 0),
            "rss_failures": int(getattr(summary, "failure_count", 0) or 0),
            "rss_failure_summary": dict(getattr(summary, "failures_by_domain", {}) or {}),
            "provider_status": provider_status,
            "result_status_counts": dict(status_counts),
            "symbols_by_status": {key: sorted(value) for key, value in symbols_by_status.items()},
            "tier_source_counts": dict(getattr(summary, "tier_source_counts", {}) or {}),
            "tier_match_counts": dict(getattr(summary, "tier_match_counts", {}) or {}),
            "extended_fallback_requested": extended_fallback_requested,
            "extended_fallback_symbol_count": extended_fallback_symbol_count,
            "explicit_unresolved_symbol_count": len(unresolved_for_extended),
            "ticker_token_match_count": int(getattr(summary, "ticker_token_match_count", 0) or 0),
            "company_name_match_count": int(getattr(summary, "company_name_match_count", 0) or 0),
            "description_summary_match_count": int(getattr(summary, "description_summary_match_count", 0) or 0),
            "headline_count": sum(len(items) for items in evidence_by_symbol.values()),
            "max_entries_per_symbol": max_entries_per_symbol,
            "total_news_budget_seconds": float(getattr(summary, "total_news_budget_seconds", 0.0) or 0.0),
            "news_elapsed_seconds": float(getattr(summary, "news_elapsed_seconds", 0.0) or 0.0),
            "news_budget_exhausted": bool(getattr(summary, "news_budget_exhausted", False)),
            "fast_budget_seconds": float(fast_budget_seconds),
            "extended_budget_seconds": float(extended_budget_seconds),
            "extended_budget_reserved_seconds": float(extended_budget_reserved_seconds),
            "fast_budget_exhausted": bool(fast_budget_exhausted),
            "extended_budget_exhausted": bool(extended_budget_exhausted),
            "fast_sources_attempted_count": int(tier_attempt_counts.get("fast", 0) or 0),
            "extended_sources_attempted_count": int(tier_attempt_counts.get("extended", 0) or 0),
            "sources_skipped_due_to_budget_count": int(
                getattr(summary, "sources_skipped_due_to_budget_count", 0) or 0
            ),
            "unique_source_urls_scheduled_count": int(getattr(summary, "unique_source_urls_scheduled_count", 0) or 0),
            "unique_source_urls_attempted_count": int(getattr(summary, "unique_source_urls_attempted_count", 0) or 0),
            "duplicate_source_fetches_avoided_count": duplicate_fetches_avoided,
            "cross_tier_duplicate_source_urls_avoided": tuple(cross_tier_duplicate_sources),
            "source_diagnostics": source_diag_payload,
            "per_source_elapsed_seconds": {item.source_id: item.elapsed_seconds for item in source_diag_objects},
            "tier_elapsed_seconds_by_tier": tier_elapsed_by_tier,
            "tier_budget_seconds_by_tier": tier_budget_by_tier,
            "tier_budget_exhausted_by_tier": tier_exhausted_by_tier,
            "fast_tier_elapsed_seconds": float(tier_elapsed_by_tier.get("fast", 0.0) or 0.0),
            "extended_tier_elapsed_seconds": float(tier_elapsed_by_tier.get("extended", 0.0) or 0.0),
            "symbols_unresolved_at_budget_exhaustion": sorted(budget_unresolved_symbols),
            "diagnostics_mapping_gaps": (),
            "diagnostics_authority_notes": (
                "event_and_catalyst_classification_remain_strategy_adapter_authority",
            ),
        }
        diagnostics = RetrievalDiagnostics(
            retrieval_status=retrieval_status,
            provider_status=provider_status,
            provider_available=_provider_available(provider_status),
            cache_state="not_checked",
            source_groups_queried=_queried_source_groups(fast_fetched, extended_fetched),
            provider_groups_queried=("rss_batch",),
            sources_queried=tuple((fast_sources if fast_fetched else []) + (extended_sources if extended_fetched else [])),
            source_diagnostics=source_diag_objects,
            source_failures=_flatten_failures(getattr(summary, "failures_by_domain", {}) or {}),
            sources_attempted_count=int(getattr(summary, "sources_attempted_count", 0) or 0),
            sources_skipped_due_to_budget_count=int(
                getattr(summary, "sources_skipped_due_to_budget_count", 0) or 0
            ),
            elapsed_seconds=summary_elapsed,
            total_budget_seconds=total_news_budget_seconds,
            budget_exhausted=bool(getattr(summary, "news_budget_exhausted", False)),
            timeout_count=_timeout_count(getattr(summary, "failures_by_domain", {}) or {}),
            unresolved_symbols=tuple(sorted(budget_unresolved_symbols)),
            diagnostics=diagnostics_payload,
        )
        return NewsBatchResult(
            candidates=ordered_candidates,
            evidence_by_symbol=evidence_by_symbol,
            summaries_by_symbol=summaries_by_symbol,
            diagnostics=diagnostics,
            request=request,
            retrieval_policy=retrieval_policy,
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


def _metadata_by_symbol(candidates: Sequence[NewsCandidate]) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        symbol = candidate.normalized_symbol
        values: dict[str, Any] = dict(candidate.metadata or {})
        if candidate.company_name:
            values.setdefault("company_name", candidate.company_name)
        if candidate.aliases:
            values.setdefault("aliases", tuple(candidate.aliases))
        metadata[symbol] = values
    return metadata


def _source_groups_for_policy(retrieval_policy: RetrievalPolicy) -> tuple[str, ...]:
    requested = tuple(str(group or "").strip().upper() for group in retrieval_policy.source_groups)
    groups = requested or DEFAULT_SOURCE_GROUPS
    return tuple(group for group in groups if group in ADAPTED_SOURCE_GROUPS)


def _sources_for_group(source_groups: Sequence[str], group_id: SourceGroupId) -> list[str]:
    if group_id not in set(source_groups):
        return []
    return list(get_source_group_urls(group_id))


def _budget_skipped_source_diagnostics(
    sources: Sequence[str],
    *,
    source_tier: str,
) -> tuple[Mapping[str, Any], ...]:
    source_group = "PREP_EXTENDED" if source_tier == "extended" else "FAST_TRADING"
    rows: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for raw_url in sources:
        url = str(raw_url or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        rows.append(
            {
                "source_id": url,
                "source_url": url,
                "source_domain": (urlparse(url).netloc or url).lower(),
                "provider": "rss_batch",
                "source_group": source_group,
                "source_tier": source_tier,
                "retrieval_status": "budget_exhausted",
                "attempted": False,
                "matched_count": 0,
                "failure_reason": "deadline_exhausted_before_attempt",
                "elapsed_seconds": 0.0,
                "timeout_seconds": 0.0,
                "timed_out": False,
                "budget_exhausted": True,
            }
        )
    return tuple(rows)

def _source_diagnostics_from_summary(summary: RssFailureSummary) -> tuple[SourceDiagnostic, ...]:
    rows: list[SourceDiagnostic] = []
    for item in tuple(getattr(summary, "source_diagnostics", ()) or ()):
        if not isinstance(item, Mapping):
            continue
        source_id = str(item.get("source_id") or item.get("source_url") or "").strip()
        if not source_id:
            continue
        rows.append(
            SourceDiagnostic(
                source_id=source_id,
                provider=str(item.get("provider") or "rss_batch"),
                source_group=str(item.get("source_group") or ""),
                source_tier=str(item.get("source_tier") or ""),
                retrieval_status=str(item.get("retrieval_status") or "unknown"),
                attempted=bool(item.get("attempted", False)),
                matched_count=int(item.get("matched_count") or 0),
                failure_reason=item.get("failure_reason"),
                elapsed_seconds=item.get("elapsed_seconds"),
                timeout_seconds=item.get("timeout_seconds"),
                timed_out=bool(item.get("timed_out", False)),
                budget_exhausted=bool(item.get("budget_exhausted", False)),
            )
        )
    return tuple(rows)


def _explicit_unresolved_symbols(symbols: Sequence[str], retrieval_policy: RetrievalPolicy) -> list[str]:
    metadata = dict(retrieval_policy.metadata or {})
    raw: Any = None
    for key in UNRESOLVED_SYMBOL_METADATA_KEYS:
        if key in metadata:
            raw = metadata.get(key)
            break
    if raw is None:
        return []
    if isinstance(raw, str):
        requested = {raw.strip().upper()}
    else:
        try:
            requested = {str(symbol or "").strip().upper() for symbol in raw}
        except TypeError:
            requested = set()
    requested.discard("")
    return [symbol for symbol in symbols if symbol in requested]


def _max_entries_per_symbol(request: NewsRequest) -> int:
    value = request.max_evidence_per_symbol if request.max_evidence_per_symbol is not None else get_config("NEWS_MAX_ENTRIES_PER_SYMBOL")
    try:
        return max(1, int(value or 5))
    except Exception:
        return 5


def _lookback_hours(request: NewsRequest) -> float:
    if request.lookback_seconds is not None:
        try:
            return max(0.0, float(request.lookback_seconds) / 3600.0)
        except Exception:
            return 0.0
    try:
        return float(get_config("NEWS_LOOKBACK_HOURS"))
    except Exception:
        return 24.0


def _request_timeout_seconds(retrieval_policy: RetrievalPolicy) -> float:
    value = (
        retrieval_policy.request_timeout_seconds
        if retrieval_policy.request_timeout_seconds is not None
        else get_config("NEWS_REQUEST_TIMEOUT_S")
    )
    try:
        return max(0.0, float(value or 0.0))
    except Exception:
        return 5.0


def _total_budget_seconds(retrieval_policy: RetrievalPolicy) -> float:
    value = (
        retrieval_policy.total_budget_seconds
        if retrieval_policy.total_budget_seconds is not None
        else get_config("NEWS_TOTAL_BUDGET_S")
    )
    try:
        return max(0.0, float(value or 0.0))
    except Exception:
        return 0.0


def _extended_tier_reserve_fraction(retrieval_policy: RetrievalPolicy) -> float:
    value = (
        retrieval_policy.extended_reserve_fraction
        if retrieval_policy.extended_reserve_fraction is not None
        else get_config("NEWS_EXTENDED_TIER_RESERVE_FRACTION")
    )
    return extended_tier_reserve_fraction(value)


def _fast_tier_budget_seconds(
    total_budget_seconds: float,
    retrieval_policy: RetrievalPolicy,
    *,
    extended_sources_available: bool,
) -> float:
    explicit = retrieval_policy.budget_for_tier("fast")
    if explicit is not None:
        return max(0.0, explicit)
    return fast_tier_budget_seconds(
        total_budget_seconds,
        extended_sources_available=extended_sources_available,
        extended_reserve_fraction=_extended_tier_reserve_fraction(retrieval_policy),
    )


def _retrieval_status(summary: RssFailureSummary, provider_status: str) -> str:
    if provider_status == "provider_unavailable":
        return "unavailable"
    if provider_status == "provider_request_failure":
        return "provider_error"
    if bool(getattr(summary, "news_budget_exhausted", False)):
        return "budget_exhausted"
    if provider_status == "partial_request_failure":
        return "partial"
    return "available"


def _provider_available(provider_status: str) -> bool:
    return provider_status not in {"provider_unavailable", "provider_request_failure"}


def _budget_unresolved_symbols(
    symbols: Sequence[str],
    explicit_unresolved_symbols: Sequence[str],
    *,
    news_budget_exhausted: bool,
) -> set[str]:
    if not news_budget_exhausted:
        return set()
    explicit = {str(symbol or "").strip().upper() for symbol in explicit_unresolved_symbols}
    explicit.discard("")
    return explicit or {str(symbol or "").strip().upper() for symbol in symbols if str(symbol or "").strip()}


def _evidence_from_headline(
    candidate: NewsCandidate,
    headline: Headline,
    *,
    request: NewsRequest,
    retrieval_status: str,
    provider_status: str,
    budget_exhausted: bool,
    fetched_at: datetime,
    now_ts: float,
) -> NewsEvidence:
    age_seconds = max(0.0, now_ts - float(headline.published_ts))
    stale = _is_stale(age_seconds, request)
    evidence_id = _evidence_id(candidate.normalized_symbol, headline)
    return NewsEvidence(
        symbol=candidate.normalized_symbol,
        evidence_id=evidence_id,
        company_name=candidate.company_name,
        aliases=tuple(candidate.aliases or ()),
        match_type=headline.match_type,
        match_confidence=1.0,
        matched_field=headline.matched_field,
        headline=str(headline.title or ""),
        summary=headline.summary,
        url=headline.url,
        reference_id=headline.url or None,
        event_class=None,
        catalyst_classification=None,
        classifier_version=None,
        is_generic=None,
        is_qualifying_event_class=False,
        dilution_or_offering=None,
        published_at=datetime.fromtimestamp(float(headline.published_ts), tz=timezone.utc),
        fetched_at=fetched_at,
        first_seen_at=datetime.fromtimestamp(float(headline.published_ts), tz=timezone.utc),
        age_seconds=age_seconds,
        freshness_bucket=_freshness_bucket(age_seconds),
        stale=stale,
        original_source=headline.source,
        observed_source=headline.source,
        source_domain=_source_domain(headline.url),
        provider="rss_batch",
        source_group=("PREP_EXTENDED" if headline.source_tier == "extended" else "FAST_TRADING"),
        source_tier=headline.source_tier,
        verified_source=True,
        cache_state="not_checked",
        retrieval_status=retrieval_status,
        budget_exhausted=budget_exhausted,
        raw={
            "source": headline.source,
            "source_tier": headline.source_tier,
            "match_type": headline.match_type,
            "matched_field": headline.matched_field,
        },
        audit={
            "provider_status": provider_status,
            "request_strategy_id": request.strategy_id,
            "request_audit_reason": request.audit_reason,
            "classification_authority": "strategy_adapter_not_common_provider",
        },
    )


def _evidence_id(symbol: str, headline: Headline) -> str:
    digest = hashlib.sha1(
        "|".join(
            (
                symbol,
                str(headline.title or "").strip().lower(),
                str(headline.source or "").strip().lower(),
                str(headline.url or "").strip().lower(),
            )
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"rss-batch:{symbol}:{digest}"


def _is_stale(age_seconds: float, request: NewsRequest) -> bool | None:
    if request.freshness_seconds is None:
        return None
    try:
        return age_seconds > max(0.0, float(request.freshness_seconds))
    except Exception:
        return None


def _freshness_bucket(age_seconds: float) -> str:
    if age_seconds <= 5 * 60:
        return "0_5m"
    if age_seconds <= 30 * 60:
        return "5_30m"
    if age_seconds <= 6 * 60 * 60:
        return "30m_6h"
    return "older_than_6h"


def _source_domain(url: str) -> str | None:
    try:
        parsed = urlparse(str(url or ""))
    except Exception:
        return None
    return parsed.netloc or None


def _objective_status_for_symbol(
    symbol: str,
    headlines: Sequence[Headline],
    budget_unresolved_symbols: set[str],
    provider_status: str,
) -> str:
    if provider_status in {"provider_unavailable", "provider_request_failure"} and not headlines:
        return provider_status
    if symbol in budget_unresolved_symbols:
        return "budget_exhausted"
    if headlines:
        return "news_present_unclassified"
    return "no_recent_news"


def _summary_for_symbol(
    *,
    symbol: str,
    evidence: Sequence[NewsEvidence],
    retrieval_status: str,
    provider_status: str,
    provider_available: bool,
    budget_exhausted: bool,
    objective_status: str,
) -> NewsEvidenceSummary:
    fresh_evidence = [item for item in evidence if item.stale is False]
    source_count = len({item.observed_source for item in evidence if item.observed_source})
    freshest_age = min((item.age_seconds for item in evidence if item.age_seconds is not None), default=None)
    reliability_values = [
        float(value)
        for item in evidence
        for value in (item.source_reliability_score, item.source_credibility_score)
        if value is not None
    ]
    return NewsEvidenceSummary(
        symbol=symbol,
        evidence_count=len(evidence),
        fresh_evidence_count=len(fresh_evidence),
        qualifying_event_class_count=0,
        generic_evidence_count=0,
        freshest_evidence_age_seconds=freshest_age,
        highest_reliability_score=max(reliability_values) if reliability_values else None,
        average_reliability_score=(sum(reliability_values) / len(reliability_values)) if reliability_values else None,
        heat_score=max((item.heat_score for item in evidence if item.heat_score is not None), default=None),
        velocity_5m=max((item.velocity_5m for item in evidence if item.velocity_5m is not None), default=None),
        velocity_10m=max((item.velocity_10m for item in evidence if item.velocity_10m is not None), default=None),
        velocity_30m=max((item.velocity_30m for item in evidence if item.velocity_30m is not None), default=None),
        velocity_60m=max((item.velocity_60m for item in evidence if item.velocity_60m is not None), default=None),
        independent_source_count=source_count,
        event_class_counts={},
        retrieval_status=retrieval_status,
        provider_status=provider_status,
        provider_available=provider_available,
        cache_state="not_checked",
        budget_exhausted=budget_exhausted,
        evidence_ids=tuple(item.evidence_id for item in evidence if item.evidence_id),
        diagnostics={
            "objective_news_status": objective_status,
            "classification_authority": "strategy_adapter_not_common_provider",
        },
    )


def _flatten_failures(failures_by_domain: Mapping[str, Mapping[str, int]]) -> dict[str, str]:
    flattened: dict[str, str] = {}
    for domain, failures in failures_by_domain.items():
        parts = [f"{code}:{count}" for code, count in sorted(dict(failures or {}).items())]
        flattened[str(domain)] = ",".join(parts)
    return flattened


def _timeout_count(failures_by_domain: Mapping[str, Mapping[str, int]]) -> int:
    total = 0
    for failures in failures_by_domain.values():
        for code, count in dict(failures or {}).items():
            if "TIMEOUT" in str(code).upper():
                total += int(count or 0)
    return total


def _queried_source_groups(fast_fetched: bool, extended_fetched: bool) -> tuple[str, ...]:
    queried: list[str] = []
    if fast_fetched:
        queried.append("FAST_TRADING")
    if extended_fetched:
        queried.append("PREP_EXTENDED")
    return tuple(queried)


__all__ = ["BatchRssNewsIntelligenceProvider"]
