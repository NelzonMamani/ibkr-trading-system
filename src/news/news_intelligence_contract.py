from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Mapping, Protocol, Sequence, runtime_checkable


RetrievalStatus = Literal[
    "not_requested",
    "available",
    "partial",
    "unavailable",
    "unknown",
    "timeout",
    "budget_exhausted",
    "provider_error",
    "cache_hit",
]

CacheState = Literal[
    "not_checked",
    "hit",
    "miss",
    "stale",
    "write_pending",
    "write_skipped",
]

RefreshMode = Literal[
    "cache_only",
    "incremental",
    "bounded_refresh",
    "force_refresh",
    "disabled",
]

FallbackMode = Literal[
    "none",
    "unresolved_only",
    "tiered",
]

TimeoutPolicy = Literal[
    "provider_default",
    "fixed",
    "clamp_to_remaining_budget",
]


@dataclass(frozen=True)
class NewsCandidate:
    """Security or issuer identity supplied by an upstream strategy/scanner."""

    symbol: str
    company_name: str | None = None
    aliases: tuple[str, ...] = ()
    exchange: str | None = None
    market: str | None = None
    region: str | None = None
    priority_rank: int | None = None
    session: str | None = None
    price: float | None = None
    gap_pct: float | None = None
    percentage_move: float | None = None
    float_shares: int | None = None
    absolute_share_volume: int | None = None
    relative_volume_rvol: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def normalized_symbol(self) -> str:
        return str(self.symbol or "").strip().upper()


@dataclass(frozen=True)
class NewsRequest:
    """WHAT evidence a consumer wants, without strategy-specific decisions."""

    strategy_id: str | None = None
    event_classes: tuple[str, ...] = ()
    lookback_seconds: float | None = None
    freshness_seconds: float | None = None
    include_generic_news: bool = False
    need_heat: bool = False
    need_velocity: bool = False
    need_reliability: bool = False
    max_evidence_per_symbol: int | None = None
    session_phase: str | None = None
    audit_reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalPolicy:
    """WHERE and HOW evidence may be retrieved for a batch request."""

    source_groups: tuple[str, ...] = ()
    provider_groups: tuple[str, ...] = ()
    allow_cache_read: bool = True
    allow_cache_write: bool = True
    refresh_mode: RefreshMode = "incremental"
    network_allowed: bool = True
    total_budget_seconds: float | None = None
    tier_budgets: Mapping[str, float] = field(default_factory=dict)
    extended_reserve_fraction: float | None = None
    max_sources: int | None = None
    max_items_per_source: int | None = None
    request_timeout_seconds: float | None = None
    timeout_policy: TimeoutPolicy = "clamp_to_remaining_budget"
    fallback_mode: FallbackMode = "unresolved_only"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def budget_for_tier(self, tier: str) -> float | None:
        value = self.tier_budgets.get(str(tier or ""))
        return float(value) if value is not None else None


@dataclass(frozen=True)
class SourceDiagnostic:
    """Per-source/provider retrieval facts for audit and performance review."""

    source_id: str
    provider: str | None = None
    source_group: str | None = None
    source_tier: str | None = None
    retrieval_status: RetrievalStatus = "unknown"
    attempted: bool = False
    matched_count: int = 0
    failure_reason: str | None = None
    elapsed_seconds: float | None = None
    timed_out: bool = False
    budget_exhausted: bool = False


@dataclass(frozen=True)
class RetrievalDiagnostics:
    """Batch-level retrieval, provider, cache, timing, and budget evidence."""

    retrieval_status: RetrievalStatus = "unknown"
    provider_status: str | None = None
    provider_available: bool | None = None
    cache_state: CacheState = "not_checked"
    source_groups_queried: tuple[str, ...] = ()
    provider_groups_queried: tuple[str, ...] = ()
    sources_queried: tuple[str, ...] = ()
    source_diagnostics: tuple[SourceDiagnostic, ...] = ()
    source_failures: Mapping[str, str] = field(default_factory=dict)
    sources_attempted_count: int = 0
    sources_skipped_due_to_budget_count: int = 0
    elapsed_seconds: float | None = None
    total_budget_seconds: float | None = None
    budget_exhausted: bool = False
    timeout_count: int = 0
    unresolved_symbols: tuple[str, ...] = ()
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    @property
    def unavailable(self) -> bool:
        return (
            self.provider_available is False
            or self.budget_exhausted
            or self.retrieval_status in {"unavailable", "timeout", "budget_exhausted", "provider_error"}
        )


@dataclass(frozen=True)
class NewsEvidence:
    """Normalized objective news fact with identity, time, provenance, and audit data."""

    symbol: str
    evidence_id: str | None = None
    company_name: str | None = None
    aliases: tuple[str, ...] = ()
    match_type: str | None = None
    match_confidence: float | None = None
    matched_field: str | None = None
    headline: str | None = None
    summary: str | None = None
    url: str | None = None
    reference_id: str | None = None
    event_class: str | None = None
    catalyst_classification: str | None = None
    classifier_version: str | None = None
    is_generic: bool | None = None
    is_qualifying_event_class: bool | None = None
    dilution_or_offering: bool | None = None
    published_at: datetime | None = None
    fetched_at: datetime | None = None
    first_seen_at: datetime | None = None
    age_seconds: float | None = None
    freshness_bucket: str | None = None
    stale: bool | None = None
    decay_score: float | None = None
    original_source: str | None = None
    observed_source: str | None = None
    source_domain: str | None = None
    provider: str | None = None
    source_group: str | None = None
    source_tier: str | None = None
    verified_source: bool | None = None
    source_credibility_score: float | None = None
    source_reliability_score: float | None = None
    region: str | None = None
    duplicate_cluster_id: str | None = None
    publication_count: int | None = None
    independent_source_count: int | None = None
    velocity_5m: int | None = None
    velocity_10m: int | None = None
    velocity_30m: int | None = None
    velocity_60m: int | None = None
    heat_score: float | None = None
    hotness_score: float | None = None
    spike_indicator: bool | None = None
    cache_state: CacheState = "not_checked"
    retrieval_status: RetrievalStatus = "unknown"
    failures: tuple[str, ...] = ()
    timed_out: bool = False
    budget_exhausted: bool = False
    raw: Mapping[str, Any] = field(default_factory=dict)
    audit: Mapping[str, Any] = field(default_factory=dict)

    @property
    def normalized_symbol(self) -> str:
        return str(self.symbol or "").strip().upper()


@dataclass(frozen=True)
class NewsEvidenceSummary:
    """Latency-friendly per-symbol summary of objective news evidence."""

    symbol: str
    evidence_count: int = 0
    fresh_evidence_count: int = 0
    qualifying_event_class_count: int = 0
    generic_evidence_count: int = 0
    freshest_evidence_age_seconds: float | None = None
    highest_reliability_score: float | None = None
    average_reliability_score: float | None = None
    heat_score: float | None = None
    velocity_5m: int | None = None
    velocity_10m: int | None = None
    velocity_30m: int | None = None
    velocity_60m: int | None = None
    independent_source_count: int = 0
    event_class_counts: Mapping[str, int] = field(default_factory=dict)
    retrieval_status: RetrievalStatus = "unknown"
    provider_status: str | None = None
    provider_available: bool | None = None
    cache_state: CacheState = "not_checked"
    budget_exhausted: bool = False
    evidence_ids: tuple[str, ...] = ()
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    @property
    def normalized_symbol(self) -> str:
        return str(self.symbol or "").strip().upper()

    @property
    def retrieval_unavailable(self) -> bool:
        return (
            self.provider_available is False
            or self.budget_exhausted
            or self.retrieval_status in {"unavailable", "timeout", "budget_exhausted", "provider_error"}
        )


@dataclass(frozen=True)
class NewsBatchResult:
    """Batch-first result for one or many symbols."""

    candidates: tuple[NewsCandidate, ...] = ()
    evidence_by_symbol: Mapping[str, tuple[NewsEvidence, ...]] = field(default_factory=dict)
    summaries_by_symbol: Mapping[str, NewsEvidenceSummary] = field(default_factory=dict)
    diagnostics: RetrievalDiagnostics = field(default_factory=RetrievalDiagnostics)
    request: NewsRequest | None = None
    retrieval_policy: RetrievalPolicy | None = None
    cache_state: CacheState = "not_checked"
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def symbols(self) -> tuple[str, ...]:
        if self.summaries_by_symbol:
            return tuple(str(symbol).upper() for symbol in self.summaries_by_symbol.keys())
        return tuple(candidate.normalized_symbol for candidate in self.candidates)

    def evidence_for_symbol(self, symbol: str) -> tuple[NewsEvidence, ...]:
        return tuple(self.evidence_by_symbol.get(str(symbol or "").strip().upper(), ()))

    def summary_for_symbol(self, symbol: str) -> NewsEvidenceSummary | None:
        return self.summaries_by_symbol.get(str(symbol or "").strip().upper())


@runtime_checkable
class NewsIntelligenceProvider(Protocol):
    """Future service boundary for strategy-neutral batch news retrieval."""

    def get_news(
        self,
        candidates: Sequence[NewsCandidate],
        request: NewsRequest,
        retrieval_policy: RetrievalPolicy,
    ) -> NewsBatchResult:
        ...


__all__ = [
    "CacheState",
    "FallbackMode",
    "NewsBatchResult",
    "NewsCandidate",
    "NewsEvidence",
    "NewsEvidenceSummary",
    "NewsIntelligenceProvider",
    "NewsRequest",
    "RetrievalDiagnostics",
    "RetrievalPolicy",
    "RetrievalStatus",
    "SourceDiagnostic",
    "TimeoutPolicy",
]
