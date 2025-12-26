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


@dataclass
class TradeRecord:
    """Minimal teaching-first record of one trade attempt's stage outputs."""

    scanner_output: List = field(default_factory=list)
    pattern_output: List = field(default_factory=list)
    strategy_output: List[TradeIntent] = field(default_factory=list)
    risk_output: List[RiskDecision] = field(default_factory=list)
    execution_output: List[ExecutionResult] = field(default_factory=list)

    def __post_init__(self) -> None:
        print(
            "[STORAGE] TradeRecord instantiated — capturing lists for each stage with "
            f"{len(self.scanner_output)} scanner, {len(self.pattern_output)} patterns, "
            f"{len(self.strategy_output)} intents, {len(self.risk_output)} risk decisions, "
            f"{len(self.execution_output)} execution results."
        )
