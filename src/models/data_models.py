"""
Phase 3 skeleton data models for the teaching-first trading system.

No business logic is present here; the classes are shape-only placeholders
to illustrate how information might flow between system stages.
"""

from dataclasses import asdict, dataclass, field
from typing import List, Optional

from src.domain.performance_snapshot import PerformanceSnapshot
from src.domain.trade_outcome import TradeOutcome


@dataclass
class ScannerCandidate:
    """Phase 4 teaching-first representation of a scanner output candidate."""

    symbol: str  # Ticker symbol under review; purely illustrative, not fetched from markets.
    price: Optional[float]  # Reference price snapshot for teaching math on position sizing.
    gap_percent: Optional[float]  # Pre-market or open gap magnitude to highlight momentum potential.
    rvol: Optional[float]  # Relative volume to show how unusual the current activity is versus baseline.
    float_millions: Optional[float]  # Share float in millions to discuss supply dynamics and volatility.
    rationale: str  # Plain-language teaching note that explains why the symbol is interesting.
    session: Optional[str] = None  # Session label, e.g. PRE/REGULAR/AFTER for session-aware rules.
    premarket_high: Optional[float] = None
    early_session_high: Optional[float] = None
    opening_range_high: Optional[float] = None
    opening_range_low: Optional[float] = None
    opening_range_minutes: Optional[int] = None
    momentum_move_pct: Optional[float] = None
    pullback_pct: Optional[float] = None
    pullback_high: Optional[float] = None
    pullback_volume_ratio: Optional[float] = None
    higher_low: Optional[bool] = None
    vwap: Optional[float] = None
    vwap_hold_minutes: Optional[int] = None
    hod: Optional[float] = None
    consolidation_range_pct: Optional[float] = None
    breakout_volume_ratio: Optional[float] = None
    breakout_hold_minutes: Optional[int] = None
    breakout_reject: Optional[bool] = None
    extension_pct: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread: Optional[float] = None
    volume: Optional[float] = None
    data_quality_flags: List[str] = field(default_factory=list)


@dataclass
class ScannerResult:
    """Represents a single symbol’s market snapshot and explainability context."""

    symbol: Optional[str] = None
    timestamp: Optional[str] = None
    session: Optional[str] = None
    price: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread: Optional[float] = None
    gap_percent: Optional[float] = None
    relative_volume: Optional[float] = None
    volume_spike_flag: Optional[bool] = None
    float_shares: Optional[float] = None
    scanner_score: Optional[float] = None
    rank: Optional[int] = None
    rank_change_vs_previous_cycle: Optional[int] = None
    news_present_flag: Optional[bool] = None
    news_velocity_10m: Optional[float] = None
    news_sentiment: Optional[float] = None
    news_regions: List[str] = field(default_factory=list)
    news_credibility_flag: Optional[bool] = None
    rationale_text: Optional[str] = None
    data_quality_flags: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        print(f"[INFO] ScannerResult instantiated for symbol={self.symbol} — skeleton container only")


@dataclass
class PatternResult:
    """Teaching-first record of a detected pattern for one symbol."""

    symbol: str  # Symbol under review; keeps the pattern explanation tied to one ticker.
    pattern_name: str  # Human-readable, classroom-friendly label of the pattern being taught.
    confidence: float  # Simple confidence number to illustrate certainty without real modeling.
    rationale: str  # Plain-language teaching note describing why this pattern label was chosen.
    gap_percent: Optional[float] = None
    rvol: Optional[float] = None
    float_millions: Optional[float] = None
    data_quality_flags: List[str] = field(default_factory=list)


@dataclass
class TradeIntent:
    """
    Teaching-first intent to express a directional idea; **not** a broker order.

    The intent keeps the conversation in the classroom by describing direction and confidence
    without containing any execution details. The trader_type routes the intent to different
    teaching execution paths (scalper vs. momentum vs. quant vs. manual) while we remain
    single-threaded on purpose so students can trace the flow without concurrency complexity.
    """

    symbol: str  # Ticker symbol for the intent being discussed.
    direction: str  # "LONG", "SHORT", or "NEUTRAL" — directional learning cue only.
    strategy_name: str  # Name of the teaching strategy that produced this intent.
    confidence: float  # Confidence score carried for discussion; not a trading signal.
    rationale: str  # Plain-language explanation of why this intent exists.
    trader_type: str = "UNKNOWN"  # "SCALPER", "MOMENTUM", "QUANT", or "MANUAL" for routing the teaching flow.
    stop_loss_price: Optional[float] = None  # Optional price-based protection configured at entry time.
    take_profit_price: Optional[float] = None  # Optional profit target configured at entry time.
    decision_id: Optional[str] = None
    pattern_name: Optional[str] = None
    invalidation_level: Optional[float] = None
    gap_percent: Optional[float] = None
    rvol: Optional[float] = None
    float_millions: Optional[float] = None
    tick: Optional[int] = None
    data_quality_flags: List[str] = field(default_factory=list)
    regime_label: Optional[str] = None
    regime_confidence: Optional[float] = None
    regime_policy_applied: Optional[bool] = None
    regime_notes: List[str] = field(default_factory=list)
    synthetic: bool = False


@dataclass(frozen=True)
class DecisionArtifact:
    """Canonical decision artifact capturing explicit intents and trace metadata."""

    decision_id: str
    strategy_name: str
    run_mode: str
    session_phase: str
    source: str
    created_at: str
    intents: List[TradeIntent] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class IntentRiskDecision:
    """Per-intent risk decision with explicit reason tags."""

    intent_id: str
    symbol: str
    allowed: bool
    max_position_size: int
    reason_tags: List[str] = field(default_factory=list)
    rationale: Optional[str] = None


@dataclass
class RiskDecision:
    """
    Teaching-first risk output that intentionally stops short of being an order.

    A RiskDecision represents permission and limits only; it does not include any order
    ticket details or broker-specific instructions. It carries trader_type so execution can
    route deterministically in a single-threaded teaching flow.
    """

    symbol: str
    allowed: bool
    max_position_size: int
    risk_level: str
    rationale: str
    trader_type: str = "MANUAL"
    strategy_name: str = "UNKNOWN"
    direction: str = "UNKNOWN"
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    pattern_name: Optional[str] = None
    invalidation_level: Optional[float] = None
    reason_code: Optional[str] = None
    intent_id: Optional[str] = None
    decision_id: Optional[str] = None
    created_tick: Optional[int] = None
    idempotency_key: Optional[str] = None
    overall_action: str = "ALLOW"
    decision_code: str = "APPROVE"
    run_mode: Optional[str] = None
    evaluated_limits: dict = field(default_factory=dict)
    timestamp: Optional[str] = None
    per_intent: List[IntentRiskDecision] = field(default_factory=list)
    risk_reasons: List[str] = field(default_factory=list)
    sizing: dict = field(default_factory=dict)
    circuit_breaker_tripped: bool = False
    execution_blocked: bool = False


@dataclass
class ExecutionResult:
    """
    Phase 4 teaching-only execution result for deterministic, broker-free flows.

    This dataclass explicitly avoids any broker details and only records the routing path,
    status, and rationale for the simulated attempt.
    """

    symbol: str
    trader_type: str
    attempted: bool
    status: str  # "SKIPPED" or "SIMULATED" to reinforce safety.
    rationale: str
    direction: str = "UNKNOWN"
    quantity: int = 1
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    raw_price: Optional[float] = None
    slippage_applied: float = 0.0
    entry_tick: Optional[int] = None
    exit_tick: Optional[int] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    gross_realised_pnl: float = 0.0
    commission: float = 0.0
    net_realised_pnl: float = 0.0
    requested_quantity: int = 0
    filled_quantity: int = 0
    remaining_quantity: int = 0
    fill_status: str = "UNKNOWN"  # "FULL" | "PARTIAL" | "NONE"
    average_fill_price: Optional[float] = None
    note: Optional[str] = None
    gateway_decision: Optional[str] = None
    attempt_number: int = 0
    client_order_id: Optional[str] = None
    retry_scheduled: bool = False
    next_retry_tick: Optional[int] = None
    rejection_reason: Optional[str] = None
    broker_error_code: Optional[str] = None
    broker_error_message: Optional[str] = None
    broker_warning_code: Optional[str] = None
    broker_warning_message: Optional[str] = None


@dataclass
class TradeRecord:
    """Minimal teaching-first record of one trade attempt's stage outputs."""

    SCHEMA_FIELDS = (
        "scanner_output",
        "pattern_output",
        "strategy_output",
        "decision_output",
        "risk_output",
        "execution_output",
        "trade_outcomes",
        "performance_snapshot",
        "regime_snapshot",
        "regime_policy_decision",
    )

    scanner_output: List = field(default_factory=list)
    pattern_output: List = field(default_factory=list)
    strategy_output: List[TradeIntent] = field(default_factory=list)
    decision_output: List[DecisionArtifact] = field(default_factory=list)
    risk_output: List[RiskDecision] = field(default_factory=list)
    execution_output: List[ExecutionResult] = field(default_factory=list)
    trade_outcomes: List[TradeOutcome] = field(default_factory=list)
    performance_snapshot: Optional[PerformanceSnapshot] = None
    regime_snapshot: Optional[dict] = None
    regime_policy_decision: Optional[dict] = None

    def __post_init__(self) -> None:
        print(
            "[STORAGE] TradeRecord instantiated — capturing lists for each stage with "
            f"{len(self.scanner_output)} scanner, {len(self.pattern_output)} patterns, "
            f"{len(self.strategy_output)} intents, {len(self.decision_output)} decisions, "
            f"{len(self.risk_output)} risk decisions, "
            f"{len(self.execution_output)} execution results, "
            f"{len(self.trade_outcomes)} trade outcomes, "
            f"performance_snapshot={'present' if self.performance_snapshot else 'absent'}, "
            f"regime_snapshot={'present' if self.regime_snapshot else 'absent'}, "
            f"regime_policy_decision={'present' if self.regime_policy_decision else 'absent'}."
        )

    @classmethod
    def schema_fields(cls) -> tuple[str, ...]:
        return cls.SCHEMA_FIELDS

    def to_serializable_dict(self) -> dict:
        return asdict(self)
