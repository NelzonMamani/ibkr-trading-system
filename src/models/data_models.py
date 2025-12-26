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

    symbol: str  # Ticker symbol under review; purely illustrative, not fetched from markets.
    price: float  # Reference price snapshot for teaching math on position sizing.
    gap_percent: float  # Pre-market or open gap magnitude to highlight momentum potential.
    rvol: float  # Relative volume to show how unusual the current activity is versus baseline.
    float_millions: float  # Share float in millions to discuss supply dynamics and volatility.
    rationale: str  # Plain-language teaching note that explains why the symbol is interesting.


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


@dataclass
class TradeIntent:
    """
    Teaching-first intent to express a directional idea; **not** a broker order.

    The intent keeps the conversation in the classroom by describing direction and confidence
    without containing any execution details.
    """

    symbol: str  # Ticker symbol for the intent being discussed.
    direction: str  # "LONG", "SHORT", or "NONE" — directional learning cue only.
    strategy_name: str  # Name of the teaching strategy that produced this intent.
    confidence: float  # Confidence score carried for discussion; not a trading signal.
    rationale: str  # Plain-language explanation of why this intent exists.


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
