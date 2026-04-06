from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class CandidateMetrics:
    symbol: str
    con_id: Optional[int]
    exchange: Optional[str]
    session_label: Optional[str]
    session_phase: Optional[str]
    last_price: Optional[float]
    prev_close: Optional[float]
    ref_close_rth: Optional[float]
    reference_price: Optional[float]
    reference_label: Optional[str]
    reference_source: Optional[str]
    reference_quality_tier: Optional[str]
    reference_resolved: Optional[bool]
    gap_pct: Optional[float]
    pct_change: Optional[float]
    pct_change_resolved: Optional[float]
    pct_change_qualification_usable: Optional[bool]
    pct_change_execution_usable: Optional[bool]
    pct_change_source_quality: Optional[str]
    pct_change_degraded: Optional[bool]
    pct_change_synthetic: Optional[bool]
    pct_change_failure_reason: Optional[str]
    gap_pct_resolved: Optional[float]
    gap_source: Optional[str]
    context_status: Optional[str]
    execution_ready: Optional[bool]
    prep_only: Optional[bool]
    live_rvol_deferred: Optional[bool]
    prep_seeded: Optional[bool]
    live_confirmation_pending: Optional[bool]
    watchlist_source: Optional[str]
    promotion_reason: Optional[str]
    ibkr_change_pct: Optional[float]
    pct_source: Optional[str]
    open_relative_pct_change: Optional[float]
    hod_pct: Optional[float]
    rvol: Optional[float]
    rvol_discovery: Optional[float]
    rvol_phase: Optional[float]
    phase_volume_ratio: Optional[float]
    relative_volume: Optional[float]
    avg_volume_20d: Optional[int]
    adv20_resolved: Optional[bool]
    degraded_adv20: Optional[bool]
    adv20_source: Optional[str]
    rvol_status: Optional[str]
    rvol_failure_reason: Optional[str]
    rvol_degraded: Optional[bool]
    rvol_qualification_usable: Optional[bool]
    rvol_execution_usable: Optional[bool]
    degraded_rvol_gate_bypass: Optional[bool]
    float_shares: Optional[int]
    float_source: Optional[str]
    float_asof: Optional[str]
    float_cache_hit: Optional[bool]
    float_millions: Optional[float]
    volume: Optional[int]
    premarket_volume: Optional[int]
    dollar_volume: Optional[float]
    bid: Optional[float]
    ask: Optional[float]
    spread: Optional[float]
    spread_pct: Optional[float]
    halted: Optional[bool]
    ssr: Optional[bool]
    catalyst_present: Optional[bool]
    catalyst_summary: Optional[str]
    news_count: Optional[int]
    fresh_news_count: Optional[int]
    stale_news_count: Optional[int]
    top_news_title: Optional[str]
    top_news_age_hours: Optional[float]
    top_news_catalyst_tag: Optional[str]
    news_source_mode: Optional[str]
    news_asof: Optional[str]
    data_quality_ok: bool
    quote_integrity_state: Optional[str] = None
    quote_usability_state: Optional[str] = None
    data_integrity_flags: list[str] = field(default_factory=list)
    degraded_data_profile: Optional[str] = None
    degraded_reference: Optional[bool] = None
    degraded_pct_change: Optional[bool] = None
    degraded_rvol: Optional[bool] = None
    reference_synthetic: Optional[bool] = None
    degraded_focus_eligibility: Optional[bool] = None
    degraded_execution_eligibility: Optional[bool] = None
    watchlist_eligible: Optional[bool] = None
    focus_eligible: Optional[bool] = None
    execution_eligible: Optional[bool] = None
    eligibility_reason_codes: list[str] = field(default_factory=list)
    data_quality_flags: list[str] = field(default_factory=list)
    drop_reasons: list[str] = field(default_factory=list)
    rank_score: Optional[float] = None
    rank_components: Optional[dict[str, float]] = None
    timestamp_utc: str = ""
    gate_checks: dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class ScannerResult:
    top_n_symbols: list[str]
    candidates: list[CandidateMetrics]
    watchlist_k: list[CandidateMetrics]
    focus_m: list[CandidateMetrics]
    drops_by_reason: dict[str, int]
    new_symbols: list[str]
    continuing_symbols: list[str]
    dropped_symbols: list[str]
