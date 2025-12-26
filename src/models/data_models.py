"""
Phase 3 skeleton data models for the teaching-first trading system.

No business logic is present here; the classes are shape-only placeholders
to illustrate how information might flow between system stages.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ScannerCandidate:
    """Phase 4 teaching-first representation of a scanner output candidate."""

    symbol: str
    price: float
    gap_percent: float
    rvol: float
    float_millions: float
    rationale: str

    def __post_init__(self) -> None:
        print(
            f"[SCAN] ScannerCandidate created for {self.symbol} — static placeholder, "
            "no live data or validation"
        )


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
    """Represents evaluation of a specific pattern on one symbol."""

    symbol: Optional[str] = None
    pattern_name: Optional[str] = None
    pattern_family: Optional[str] = None
    detected: Optional[bool] = None
    direction: Optional[str] = None
    confidence_score: Optional[float] = None
    quality_tags: List[str] = field(default_factory=list)
    entry_zone: Optional[str] = None
    stop_suggestion: Optional[str] = None
    target_suggestion: Optional[str] = None
    rationale_text: Optional[str] = None
    risk_flags: List[str] = field(default_factory=list)
    data_quality_flags: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        print(f"[INFO] PatternResult instantiated for symbol={self.symbol} — skeleton container only")


@dataclass
class TradeIntent:
    """Represents a deliberate decision to attempt a trade if risk permits."""

    trade_id: Optional[str] = None
    strategy_id: Optional[str] = None
    symbol: Optional[str] = None
    direction: Optional[str] = None
    timestamp_created: Optional[str] = None
    session: Optional[str] = None
    setup_name: Optional[str] = None
    signal_rationale_text: Optional[str] = None
    supporting_patterns: List[PatternResult] = field(default_factory=list)
    intended_entry_type: Optional[str] = None
    intended_entry_price: Optional[float] = None
    initial_stop_price: Optional[float] = None
    profit_targets: List[float] = field(default_factory=list)
    time_stop_minutes: Optional[int] = None

    def __post_init__(self) -> None:
        print(f"[STRATEGY] TradeIntent instantiated (trade_id={self.trade_id}) — skeleton container only")


@dataclass
class RiskDecision:
    """Represents permission or denial to execute a TradeIntent."""

    trade_id: Optional[str] = None
    risk_decision: Optional[str] = None
    max_position_size_allowed: Optional[float] = None
    risk_budget_percent: Optional[float] = None
    constraints: List[str] = field(default_factory=list)
    risk_rationale_text: Optional[str] = None
    risk_flags: List[str] = field(default_factory=list)
    circuit_breaker_triggered_flag: Optional[bool] = None

    def __post_init__(self) -> None:
        print(f"[RISK] RiskDecision instantiated (trade_id={self.trade_id}) — skeleton container only")


@dataclass
class ExecutionResult:
    """Represents broker execution outcomes for a trade attempt."""

    trade_id: Optional[str] = None
    order_id: Optional[str] = None
    order_status: Optional[str] = None
    filled_quantity: Optional[float] = None
    average_fill_price: Optional[float] = None
    timestamp_execution: Optional[str] = None
    slippage: Optional[float] = None
    commission_fees: Optional[float] = None
    execution_rationale_text: Optional[str] = None
    broker_error_codes: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        print(f"[EXECUTION] ExecutionResult instantiated (trade_id={self.trade_id}) — skeleton container only")


@dataclass
class TradeRecord:
    """Minimal teaching-first record of one trade attempt's stage outputs."""

    scanner_output: Optional[str] = None
    pattern_output: Optional[str] = None
    strategy_output: Optional[str] = None
    risk_output: Optional[str] = None
    execution_output: Optional[str] = None

    def __post_init__(self) -> None:
        print("[STORAGE] TradeRecord instantiated — skeleton container only (shape, no logic)")
