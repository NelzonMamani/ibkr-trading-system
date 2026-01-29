from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class CandidateMetrics:
    symbol: str
    con_id: Optional[int]
    exchange: Optional[str]
    session_label: Optional[str]
    last_price: Optional[float]
    prev_close: Optional[float]
    ref_close_rth: Optional[float]
    gap_pct: Optional[float]
    pct_change: Optional[float]
    ibkr_change_pct: Optional[float]
    pct_source: Optional[str]
    rvol: Optional[float]
    relative_volume: Optional[float]
    avg_volume_20d: Optional[int]
    float_shares: Optional[int]
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
    data_quality_ok: bool
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
