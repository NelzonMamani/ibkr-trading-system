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
    setup_family_id: str
    pattern_name: str
    pattern_family: PatternFamily
    detected: bool
    session_valid: bool
    direction: Direction
    confidence: float
    setup_quality_tags: List[str]
    trigger_type: Optional[str] = None
    trigger_level: Optional[float] = None
    entry_reference: Optional[str] = None
    stop_reference: Optional[str] = None
    invalidation_reference: Optional[str] = None
    required_confirmations: List[str] = field(default_factory=list)
    structural_notes: List[str] = field(default_factory=list)
    non_entry_classification: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    entry_zone: Optional[str] = None
    stop_suggestion: Optional[str] = None
    target_suggestion: Optional[str] = None
    rationale_text: str = ""
    risk_flags: List[str] = field(default_factory=list)
    data_quality_flags: List[str] = field(default_factory=list)
    rejection_reason: Optional[str] = None
    reason_if_false: Optional[str] = None
