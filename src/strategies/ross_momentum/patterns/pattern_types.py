"""Pattern contracts for Ross Momentum detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class PatternFamily(str, Enum):
    GAP_OPEN = "GAP/OPEN"
    BREAKOUT = "BREAKOUT"
    PULLBACK = "PULLBACK"
    REVERSAL = "REVERSAL"
    RANGE = "RANGE"
    VOL_EVENT = "VOL_EVENT"
    CANDLE = "CANDLE"


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


@dataclass(frozen=True)
class PatternResult:
    symbol: str
    setup_id: str
    detected: bool
    direction: Direction
    confidence: float
    rationale_text: str
    entry_zone: Optional[str] = None
    stop_suggestion: Optional[str] = None
    target_suggestion: Optional[str] = None
    setup_quality_tags: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    data_quality_flags: List[str] = field(default_factory=list)
    rejection_reason: Optional[str] = None
    pattern_name: Optional[str] = None
    pattern_family: Optional[PatternFamily] = None

    @property
    def tags(self) -> List[str]:
        return list(self.setup_quality_tags)
