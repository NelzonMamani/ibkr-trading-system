"""Pattern contracts for Ross Momentum detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional


class PatternFamily(str, Enum):
    GAP_OPEN = "GAP/OPEN"
    BREAKOUT = "BREAKOUT"
    PULLBACK = "PULLBACK"
    REVERSAL = "REVERSAL"
    RANGE = "RANGE"
    VOL_EVENT = "VOL_EVENT"
    CANDLE = "CANDLE"
    EXHAUSTION = "EXHAUSTION"


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


@dataclass(frozen=True)
class PatternResult:
    setup_id: str
    pattern_name: str
    pattern_family: PatternFamily
    detected: bool
    direction: Direction
    confidence: float
    setup_quality_tags: List[str]
    setup_family_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    entry_zone: Optional[str] = None
    stop_suggestion: Optional[str] = None
    target_suggestion: Optional[str] = None
    rationale_text: str = ""
    risk_flags: List[str] = field(default_factory=list)
    data_quality_flags: List[str] = field(default_factory=list)
    rejection_reason: Optional[str] = None
    session_valid: bool = True
    trigger_type: Optional[str] = None
    trigger_level: Optional[float] = None
    stop_level: Optional[float] = None
    invalidation_level: Optional[float] = None
    non_entry_signal: bool = False
    signal_class: Optional[str] = None
    trigger_mode: Optional[str] = None
    anchor_a_price: Optional[float] = None
    anchor_b_price: Optional[float] = None
    anchor_c_price: Optional[float] = None
    anchor_a_index: Optional[int] = None
    anchor_b_index: Optional[int] = None
    anchor_c_index: Optional[int] = None
    ab_length: Optional[float] = None
    retracement_pct: Optional[float] = None
    d_projection: Optional[float] = None
    risk_reference_level: Optional[float] = None
    setup_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.setup_family_id is None:
            object.__setattr__(self, "setup_family_id", self.setup_id)
