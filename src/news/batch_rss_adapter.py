from __future__ import annotations

import hashlib
import time
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from src.config.config_resolver import get_config
from src.news.news_fetcher import (
    Headline,
    RssFailureSummary,
    fetch_fast_headlines_for_symbols,
    fetch_headlines_for_symbols,
)
from src.news.news_intelligence_contract import (
    NewsBatchResult,
    NewsCandidate,
    NewsEvidence,
    NewsEvidenceSummary,
    NewsIntelligenceProvider,
    NewsRequest,
    RetrievalDiagnostics,
    RetrievalPolicy,
)
from src.news.source_groups import SourceGroupId, get_source_group_urls


NEWS_AGE_MAX_MINUTES = 360
DEFAULT_SOURCE_GROUPS: tuple[str, ...] = ("FAST_TRADING", "PREP_EXTENDED")
ADAPTED_SOURCE_GROUPS: tuple[str, ...] = ("FAST_TRADING", "PREP_EXTENDED")

CATALYST_KEYWORDS = {
    "earnings": "EARNINGS",
    "guidance": "EARNINGS",
    "fda": "FDA",
    "approval": "FDA",
    "contract": "CONTRACT",
    "partnership": "CONTRACT",
    "upgrade": "ANALYST_ACTION",
    "downgrade": "ANALYST_ACTION",
    "initiates": "ANALYST_ACTION",
    "press release": "PRESS_RELEASE",
    "ai": "TECH_CATALYST",
    "artificial intelligence": "TECH_CATALYST",
    "crypto": "CRYPTO_CATALYST",
    "bitcoin": "CRYPTO_CATALYST",
    "ev": "EV_CATALYST",
    "electric vehicle": "EV_CATALYST",
    "battery": "EV_CATALYST",
    "defense": "DEFENSE_CATALYST",
    "military": "DEFENSE_CATALYST",
    "quantum": "TECH_CATALYST",
    "semiconductor": "TECH_CATALYST",
    "gpu": "TECH_CATALYST",
}
DILUTION_KEYWORDS = {"offering", "dilution", "s-1", "s1", "atm", "registered direct"}


class BatchRssNewsIntelligenceProvider(NewsIntelligenceProvider):
    """Strategy-neutral adapter over the existing batch RSS fetcher."""

    provider_id = "rss_batch"

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
            completed_at = datetime.now(timezone.utc)
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
                completed_at=completed_at,
            )

        source_groups = _source_groups_for_policy(retrieval_policy)
        fast_sources = _sources_for_group(source_groups, "FAST_TRADING")
        extended_sources = _sources_for_group(source_groups, "PREP_EXTENDED")
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
            headlines_by_symbol, fast_summary_raw = fetch_fast_headlines_for_symbols(
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
                news_elapsed_seconds=_stage_elapsed_seconds(stage_started_at_s),
            )

        fast_summary = _merge_rss_failure_summaries(fast_summary_raw)
        summary: RssFailureSummary = fast_summary
        fast_provider_status = _news_provider_status(fast_summary)
        provider_failed = fast_provider_status in {"provider_unavailable", "provider_request_failure"}
        extended_fallback_requested = False
        extended_fallback_symbol_count = 0
        scanner_budget_skipped_sources = 0
        extended_budget_seconds = 0.0
        fast_budget_exhausted = bool(getattr(fast_summary, "tier_budget_exhausted", False))
        extended_budget_exhausted = False

        now_ts = time.time()
        unresolved_symbols = [
            symbol
            for symbol in symbols
            if not _headlines_have_confirmed_catalyst(headlines_by_symbol.get(symbol, []), now_ts)
        ]
        if not provider_failed and retrieval_policy.fallback_mode != "none" and unresolved_symbols:
            budget_remaining_s = _stage_remaining_seconds(stage_deadline_s)
            budget_exhausted_before_extended = bool(
                getattr(fast_summary, "news_budget_exhausted", False)
            ) or budget_remaining_s <= 0.0
            if extended_sources and not budget_exhausted_before_extended:
                extended_fallback_requested = True
                extended_fallback_symbol_count = len(unresolved_symbols)
                extended_started_at_s = time.monotonic()
                extended_budget_seconds = _stage_remaining_seconds(stage_deadline_s)
                extended_metadata = {
                    symbol: symbol_metadata.get(symbol, {})
                    for symbol in unresolved_symbols
                    if symbol_metadata.get(symbol)
                }
                extended_headlines_by_symbol, extended_summary = fetch_headlines_for_symbols(
                    unresolved_symbols,
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
                    headlines_by_symbol[symbol] = _dedupe_bounded_headlines(combined, max_entries_per_symbol)
                summary = _merge_rss_failure_summaries(fast_summary, extended_summary)
            elif extended_sources and budget_exhausted_before_extended:
                extended_budget_exhausted = True
                scanner_budget_skipped_sources += len(extended_sources)

        summary_elapsed = max(
            float(getattr(summary, "news_elapsed_seconds", 0.0) or 0.0),
            _stage_elapsed_seconds(stage_started_at_s),
        )
        budget_exhausted = bool(getattr(summary, "news_budget_exhausted", False)) or scanner_budget_skipped_sources > 0
        if scanner_budget_skipped_sources or summary_elapsed or budget_exhausted or total_news_budget_seconds:
            summary = replace(
                summary,
                total_news_budget_seconds=total_news_budget_seconds,
                news_elapsed_seconds=summary_elapsed,
                news_budget_exhausted=budget_exhausted,
                sources_skipped_due_to_budget_count=int(
                    getattr(summary, "sources_skipped_due_to_budget_count", 0) or 0
                )
                + scanner_budget_skipped_sources,
            )

        now_ts = time.time()
        unresolved_at_budget_exhaustion = []
        if bool(getattr(summary, "news_budget_exhausted", False)):
            unresolved_at_budget_exhaustion = [
                symbol
                for symbol in symbols
                if not _headlines_have_confirmed_catalyst(headlines_by_symbol.get(symbol, []), now_ts)
            ]
        budget_unresolved_symbols = set(unresolved_at_budget_exhaustion)
        provider_status = _news_provider_status(summary)
        retrieval_status = _retrieval_status(summary, provider_status)
        evidence_by_symbol: dict[str, tuple[NewsEvidence, ...]] = {}
        summaries_by_symbol: dict[str, NewsEvidenceSummary] = {}
        status_index: Counter[str] = Counter()
        symbols_by_status: dict[str, list[str]] = {}

        for candidate in ordered_candidates:
            symbol = candidate.normalized_symbol
            unique_headlines = _dedupe_bounded_headlines(headlines_by_symbol.get(symbol, []), max_entries_per_symbol)
            evidences = tuple(
                _evidence_from_headline(
                    candidate,
                    headline,
                    request=request,
                    retrieval_status=retrieval_status,
                    provider_status=provider_status,
                    budget_exhausted=symbol in budget_unresolved_symbols,
                    fetched_at=started_at,
                    now_ts=now_ts,
                )
                for headline in unique_headlines
            )
            legacy_status = _legacy_status_for_symbol(symbol, unique_headlines, budget_unresolved_symbols, provider_status, now_ts)
            status_index[legacy_status] += 1
            symbols_by_status.setdefault(legacy_status, []).append(symbol)
            evidence_by_symbol[symbol] = evidences
            summaries_by_symbol[symbol] = _summary_for_symbol(
                symbol=symbol,
                evidence=evidences,
                retrieval_status=("budget_exhausted" if symbol in budget_unresolved_symbols else retrieval_status),
                provider_status=provider_status,
                provider_available=_provider_available(provider_status),
                budget_exhausted=symbol in budget_unresolved_symbols,
                legacy_status=legacy_status,
            )

        qualifying_count, non_qualifying_count = _headline_quality_counts(headlines_by_symbol, now_ts)
        tier_attempt_counts = dict(getattr(summary, "tier_sources_attempted_counts", {}) or {})
        diagnostics_payload = {
            "provider_id": self.provider_id,
            "legacy_batch_fetcher": "src.news.news_fetcher",
            "failure_reason": getattr(summary, "reason", None),
            "rss_sources": int(getattr(summary, "total_sources", 0) or 0),
            "rss_failures": int(getattr(summary, "failure_count", 0) or 0),
            "rss_failure_summary": dict(getattr(summary, "failures_by_domain", {}) or {}),
            "provider_status": provider_status,
            "result_status_counts": dict(status_index),
            "symbols_by_status": {key: sorted(value) for key, value in symbols_by_status.items()},
            "tier_source_counts": dict(getattr(summary, "tier_source_counts", {}) or {}),
            "tier_match_counts": dict(getattr(summary, "tier_match_counts", {}) or {}),
            "extended_fallback_requested": extended_fallback_requested,
            "extended_fallback_symbol_count": extended_fallback_symbol_count,
            "ticker_token_match_count": int(getattr(summary, "ticker_token_match_count", 0) or 0),
            "company_name_match_count": int(getattr(summary, "company_name_match_count", 0) or 0),
            "description_summary_match_count": int(getattr(summary, "description_summary_match_count", 0) or 0),
            "qualifying_headline_count": qualifying_count,
            "non_qualifying_headline_count": non_qualifying_count,
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
            "symbols_unresolved_at_budget_exhaustion": sorted(unresolved_at_budget_exhaustion),
            "unmigrated_runtime": "src.scanner.scanner_runner",
            "diagnostics_mapping_gaps": (
                "per_source_elapsed_seconds_not_available_from_RssFailureSummary",
                "scanner_catalyst_keyword_table_is_duplicated_until_runtime_migration",
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
            source_failures=_flatten_failures(getattr(summary, "failures_by_domain", {}) or {}),
            sources_attempted_count=int(getattr(summary, "sources_attempted_count", 0) or 0),
            sources_skipped_due_to_budget_count=int(
                getattr(summary, "sources_skipped_due_to_budget_count", 0) or 0
            ),
            elapsed_seconds=summary_elapsed,
            total_budget_seconds=total_news_budget_seconds,
            budget_exhausted=bool(getattr(summary, "news_budget_exhausted", False)),
            timeout_count=_timeout_count(getattr(summary, "failures_by_domain", {}) or {}),
            unresolved_symbols=tuple(sorted(unresolved_at_budget_exhaustion)),
            diagnostics=diagnostics_payload,
        )
        completed_at = datetime.now(timezone.utc)
        return NewsBatchResult(
            candidates=ordered_candidates,
            evidence_by_symbol=evidence_by_symbol,
            summaries_by_symbol=summaries_by_symbol,
            diagnostics=diagnostics,
            request=request,
            retrieval_policy=retrieval_policy,
            started_at=started_at,
            completed_at=completed_at,
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
    try:
        raw = float(value or 0.0)
    except Exception:
        return 0.0
    return min(max(raw, 0.0), 0.9)


def _fast_tier_budget_seconds(
    total_budget_seconds: float,
    retrieval_policy: RetrievalPolicy,
    *,
    extended_sources_available: bool,
) -> float:
    explicit = retrieval_policy.budget_for_tier("fast")
    if explicit is not None:
        return max(0.0, explicit)
    total = max(0.0, float(total_budget_seconds or 0.0))
    if total <= 0.0 or not extended_sources_available:
        return total
    reserve = total * _extended_tier_reserve_fraction(retrieval_policy)
    if reserve <= 0.0:
        return total
    return max(0.001, total - reserve)


def _stage_remaining_seconds(stage_deadline_s: float) -> float:
    return max(0.0, float(stage_deadline_s) - time.monotonic())


def _stage_elapsed_seconds(stage_started_at_s: float) -> float:
    return max(0.0, time.monotonic() - float(stage_started_at_s))


def _merge_rss_failure_summaries(*summaries: Any) -> RssFailureSummary:
    total_sources = 0
    failure_count = 0
    failures_by_domain: dict[str, dict[str, int]] = {}
    reason: str | None = None
    tier_source_counts: Counter[str] = Counter()
    tier_match_counts: Counter[str] = Counter()
    tier_sources_attempted_counts: Counter[str] = Counter()
    ticker_token_match_count = 0
    company_name_match_count = 0
    description_summary_match_count = 0
    max_entries_per_symbol = 0
    total_news_budget_seconds = 0.0
    news_elapsed_seconds = 0.0
    news_budget_exhausted = False
    sources_attempted_count = 0
    sources_skipped_due_to_budget_count = 0
    tier_budget_seconds = 0.0
    tier_elapsed_seconds = 0.0
    tier_budget_exhausted = False
    tier_budget_seconds_by_tier: dict[str, float] = {}
    tier_elapsed_seconds_by_tier: dict[str, float] = {}
    tier_budget_exhausted_by_tier: dict[str, bool] = {}
    for summary in summaries:
        if summary is None:
            continue
        total_sources += int(getattr(summary, "total_sources", 0) or 0)
        failure_count += int(getattr(summary, "failure_count", 0) or 0)
        if reason is None:
            raw_reason = getattr(summary, "reason", None)
            reason = str(raw_reason) if raw_reason else None
        for domain, codes in dict(getattr(summary, "failures_by_domain", {}) or {}).items():
            bucket = failures_by_domain.setdefault(str(domain), {})
            if isinstance(codes, dict):
                for code, count in codes.items():
                    bucket[str(code)] = bucket.get(str(code), 0) + int(count or 0)
        tier_source_counts.update(dict(getattr(summary, "tier_source_counts", {}) or {}))
        tier_match_counts.update(dict(getattr(summary, "tier_match_counts", {}) or {}))
        tier_sources_attempted_counts.update(dict(getattr(summary, "tier_sources_attempted_counts", {}) or {}))
        ticker_token_match_count += int(getattr(summary, "ticker_token_match_count", 0) or 0)
        company_name_match_count += int(getattr(summary, "company_name_match_count", 0) or 0)
        description_summary_match_count += int(getattr(summary, "description_summary_match_count", 0) or 0)
        max_entries_per_symbol = max(max_entries_per_symbol, int(getattr(summary, "max_entries_per_symbol", 0) or 0))
        total_news_budget_seconds = max(
            total_news_budget_seconds,
            float(getattr(summary, "total_news_budget_seconds", 0.0) or 0.0),
        )
        news_elapsed_seconds = max(news_elapsed_seconds, float(getattr(summary, "news_elapsed_seconds", 0.0) or 0.0))
        news_budget_exhausted = news_budget_exhausted or bool(getattr(summary, "news_budget_exhausted", False))
        sources_attempted_count += int(getattr(summary, "sources_attempted_count", 0) or 0)
        sources_skipped_due_to_budget_count += int(getattr(summary, "sources_skipped_due_to_budget_count", 0) or 0)
        tier_budget_seconds = max(tier_budget_seconds, float(getattr(summary, "tier_budget_seconds", 0.0) or 0.0))
        tier_elapsed_seconds = max(tier_elapsed_seconds, float(getattr(summary, "tier_elapsed_seconds", 0.0) or 0.0))
        tier_budget_exhausted = tier_budget_exhausted or bool(getattr(summary, "tier_budget_exhausted", False))
        for tier, value in dict(getattr(summary, "tier_budget_seconds_by_tier", {}) or {}).items():
            key = str(tier)
            tier_budget_seconds_by_tier[key] = max(tier_budget_seconds_by_tier.get(key, 0.0), float(value or 0.0))
        for tier, value in dict(getattr(summary, "tier_elapsed_seconds_by_tier", {}) or {}).items():
            key = str(tier)
            tier_elapsed_seconds_by_tier[key] = max(tier_elapsed_seconds_by_tier.get(key, 0.0), float(value or 0.0))
        for tier, value in dict(getattr(summary, "tier_budget_exhausted_by_tier", {}) or {}).items():
            key = str(tier)
            tier_budget_exhausted_by_tier[key] = bool(tier_budget_exhausted_by_tier.get(key, False) or value)
    return RssFailureSummary(
        total_sources=total_sources,
        failure_count=failure_count,
        failures_by_domain=failures_by_domain,
        reason=reason,
        tier_source_counts=dict(tier_source_counts),
        tier_match_counts=dict(tier_match_counts),
        ticker_token_match_count=ticker_token_match_count,
        company_name_match_count=company_name_match_count,
        description_summary_match_count=description_summary_match_count,
        max_entries_per_symbol=max_entries_per_symbol,
        total_news_budget_seconds=total_news_budget_seconds,
        news_elapsed_seconds=news_elapsed_seconds,
        news_budget_exhausted=news_budget_exhausted,
        sources_attempted_count=sources_attempted_count,
        sources_skipped_due_to_budget_count=sources_skipped_due_to_budget_count,
        tier_sources_attempted_counts=dict(tier_sources_attempted_counts),
        tier_budget_seconds=tier_budget_seconds,
        tier_elapsed_seconds=tier_elapsed_seconds,
        tier_budget_exhausted=tier_budget_exhausted,
        tier_budget_seconds_by_tier=tier_budget_seconds_by_tier,
        tier_elapsed_seconds_by_tier=tier_elapsed_seconds_by_tier,
        tier_budget_exhausted_by_tier=tier_budget_exhausted_by_tier,
    )


def _news_provider_status(summary: Any) -> str:
    reason = str(getattr(summary, "reason", "") or "")
    total_sources = int(getattr(summary, "total_sources", 0) or 0)
    failure_count = int(getattr(summary, "failure_count", 0) or 0)
    if reason == "no_symbols":
        return "no_symbols"
    if reason in {"no_sources", "feedparser_missing"}:
        return "provider_unavailable"
    if total_sources > 0 and failure_count >= total_sources:
        return "provider_request_failure"
    if failure_count > 0:
        return "partial_request_failure"
    return "available"


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


def _dedupe_bounded_headlines(headlines: Iterable[Headline], max_entries_per_symbol: int) -> list[Headline]:
    seen = set()
    deduped: list[Headline] = []
    for headline in headlines:
        key = (headline.title.strip().lower(), headline.source.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(headline)
        if len(deduped) >= max_entries_per_symbol:
            break
    return deduped


def _headline_is_fresh(headline: Headline, now_ts: float) -> bool:
    age_minutes = max(0.0, (now_ts - float(headline.published_ts)) / 60.0)
    return age_minutes <= NEWS_AGE_MAX_MINUTES


def _detect_catalyst_type(titles: Iterable[str]) -> str | None:
    for title in titles:
        lowered = str(title or "").lower()
        for keyword, label in CATALYST_KEYWORDS.items():
            if keyword in lowered:
                return label
    return None


def _detect_dilution(titles: Iterable[str]) -> bool:
    for title in titles:
        lowered = str(title or "").lower()
        if any(keyword in lowered for keyword in DILUTION_KEYWORDS):
            return True
    return False


def _headlines_have_confirmed_catalyst(headlines: Iterable[Headline], now_ts: float | None = None) -> bool:
    items = list(headlines or [])
    if not items:
        return False
    timestamp = time.time() if now_ts is None else float(now_ts)
    catalyst_type = _detect_catalyst_type(headline.title for headline in items)
    dilution_flag = _detect_dilution(headline.title for headline in items)
    news_is_fresh = any(_headline_is_fresh(headline, timestamp) for headline in items)
    return bool(catalyst_type and not dilution_flag and news_is_fresh)


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
    title = str(headline.title or "")
    event_class = _detect_catalyst_type((title,))
    dilution_flag = _detect_dilution((title,))
    age_seconds = max(0.0, now_ts - float(headline.published_ts))
    stale = age_seconds > NEWS_AGE_MAX_MINUTES * 60
    is_qualifying = bool(event_class and not dilution_flag and not stale)
    evidence_id = _evidence_id(candidate.normalized_symbol, headline)
    return NewsEvidence(
        symbol=candidate.normalized_symbol,
        evidence_id=evidence_id,
        company_name=candidate.company_name,
        aliases=tuple(candidate.aliases or ()),
        match_type=headline.match_type,
        match_confidence=1.0,
        matched_field=headline.matched_field,
        headline=title,
        summary=headline.summary,
        url=headline.url,
        reference_id=headline.url or None,
        event_class=event_class,
        catalyst_classification=event_class,
        classifier_version="scanner_runner_keyword_parity",
        is_generic=not bool(event_class),
        is_qualifying_event_class=is_qualifying,
        dilution_or_offering=dilution_flag,
        published_at=datetime.fromtimestamp(float(headline.published_ts), tz=timezone.utc),
        fetched_at=fetched_at,
        first_seen_at=datetime.fromtimestamp(float(headline.published_ts), tz=timezone.utc),
        age_seconds=age_seconds,
        freshness_bucket=_freshness_bucket(age_seconds),
        stale=stale,
        original_source=headline.source,
        observed_source=headline.source,
        provider="rss_batch",
        source_group=("PREP_EXTENDED" if headline.source_tier == "extended" else "FAST_TRADING"),
        source_tier=headline.source_tier,
        verified_source=True,
        cache_state="not_checked",
        retrieval_status=("budget_exhausted" if budget_exhausted else retrieval_status),
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


def _freshness_bucket(age_seconds: float) -> str:
    if age_seconds <= 5 * 60:
        return "0_5m"
    if age_seconds <= 30 * 60:
        return "5_30m"
    if age_seconds <= NEWS_AGE_MAX_MINUTES * 60:
        return "30m_6h"
    return "stale"


def _legacy_status_for_symbol(
    symbol: str,
    headlines: Sequence[Headline],
    budget_unresolved_symbols: set[str],
    provider_status: str,
    now_ts: float,
) -> str:
    if not headlines:
        if provider_status in {"provider_unavailable", "provider_request_failure"}:
            return provider_status
        if symbol in budget_unresolved_symbols:
            return "budget_exhausted"
        return "no_recent_news"
    titles = [headline.title for headline in headlines]
    catalyst_type = _detect_catalyst_type(titles)
    dilution_flag = _detect_dilution(titles)
    news_is_fresh = any(_headline_is_fresh(headline, now_ts) for headline in headlines)
    if catalyst_type and not dilution_flag and news_is_fresh:
        return "catalyst_confirmed"
    if symbol in budget_unresolved_symbols:
        return "budget_exhausted"
    if not news_is_fresh:
        return "stale_news"
    return "news_present_non_qualifying"


def _summary_for_symbol(
    *,
    symbol: str,
    evidence: Sequence[NewsEvidence],
    retrieval_status: str,
    provider_status: str,
    provider_available: bool,
    budget_exhausted: bool,
    legacy_status: str,
) -> NewsEvidenceSummary:
    fresh_evidence = [item for item in evidence if not item.stale]
    qualifying = [item for item in evidence if item.is_qualifying_event_class]
    generic = [item for item in evidence if item.is_generic]
    event_counts: Counter[str] = Counter(item.event_class for item in evidence if item.event_class)
    source_count = len({item.observed_source for item in evidence if item.observed_source})
    freshest_age = min((item.age_seconds for item in evidence if item.age_seconds is not None), default=None)
    return NewsEvidenceSummary(
        symbol=symbol,
        evidence_count=len(evidence),
        fresh_evidence_count=len(fresh_evidence),
        qualifying_event_class_count=len(qualifying),
        generic_evidence_count=len(generic),
        freshest_evidence_age_seconds=freshest_age,
        independent_source_count=source_count,
        event_class_counts=dict(event_counts),
        retrieval_status=retrieval_status,
        provider_status=provider_status,
        provider_available=provider_available,
        cache_state="not_checked",
        budget_exhausted=budget_exhausted,
        evidence_ids=tuple(item.evidence_id for item in evidence if item.evidence_id),
        diagnostics={"legacy_news_diagnostic_status": legacy_status},
    )


def _headline_quality_counts(headlines_by_symbol: Mapping[str, Sequence[Headline]], now_ts: float) -> tuple[int, int]:
    qualifying = 0
    non_qualifying = 0
    for headlines in headlines_by_symbol.values():
        unique_headlines = _dedupe_bounded_headlines(headlines, max_entries_per_symbol=999_999)
        for headline in unique_headlines:
            catalyst_type = _detect_catalyst_type((headline.title,))
            dilution_flag = _detect_dilution((headline.title,))
            news_is_fresh = _headline_is_fresh(headline, now_ts)
            if catalyst_type and not dilution_flag and news_is_fresh:
                qualifying += 1
            else:
                non_qualifying += 1
    return qualifying, non_qualifying


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
