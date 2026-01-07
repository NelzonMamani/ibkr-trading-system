"""Signal contracts and validation helpers."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional, Tuple


class SignalType(str, Enum):
    HOD_BREAK = "HOD_BREAK"
    PREMARKET_HIGH_BREAK = "PREMARKET_HIGH_BREAK"
    MICRO_PULLBACK = "MICRO_PULLBACK"
    BULL_FLAG = "BULL_FLAG"
    ORB_1M = "ORB_1M"


class SignalDecision(str, Enum):
    NO_SIGNAL = "NO_SIGNAL"
    SIGNAL = "SIGNAL"
    INVALID = "INVALID"


@dataclass(frozen=True)
class SignalContext:
    symbol: str
    tick: int
    run_mode: str
    session: str


@dataclass(frozen=True)
class Level:
    name: str
    price: Decimal


@dataclass(frozen=True)
class SignalEvent:
    signal_type: SignalType
    symbol: str
    tick: int
    decision: SignalDecision
    confidence: float
    rationale: str
    entry_level: Optional[Decimal]
    stop_level: Optional[Decimal]
    target_level: Optional[Decimal]
    invalidation_level: Optional[Decimal]
    source: str
    metadata: dict = field(default_factory=dict)


def validate_signal_event(event: SignalEvent) -> Tuple[bool, str]:
    if not 0.0 <= event.confidence <= 1.0:
        return False, "confidence must be between 0 and 1"

    if event.decision == SignalDecision.SIGNAL:
        if event.entry_level is None:
            return False, "entry_level is required when decision is SIGNAL"
        if event.stop_level is None:
            return False, "stop_level is required when decision is SIGNAL"
        if event.invalidation_level is None:
            return False, "invalidation_level is required when decision is SIGNAL"

    return True, "ok"
