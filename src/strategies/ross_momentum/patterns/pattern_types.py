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
    setup_id: str
    pattern_name: str
    pattern_family: PatternFamily
    detected: bool
    direction: Direction
    confidence: float
    setup_quality_tags: List[str]
    tags: List[str] = field(default_factory=list)
    entry_zone: Optional[str] = None
    stop_suggestion: Optional[str] = None
    target_suggestion: Optional[str] = None
    rationale_text: str = ""
    risk_flags: List[str] = field(default_factory=list)
    data_quality_flags: List[str] = field(default_factory=list)
    rejection_reason: Optional[str] = None
