"""Canonical strategy contracts for Epoch 2 decision intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SessionContext(str, Enum):
    PRE = "PRE"
    REGULAR = "REGULAR"
    AFTER = "AFTER"


class DecisionType(str, Enum):
    NO_ACTION = "NO_ACTION"
    WATCH = "WATCH"
    CONSIDER = "CONSIDER"
    EMIT_INTENT = "EMIT_INTENT"


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class TimeInForcePolicy(str, Enum):
    DAY = "DAY"
    IOC = "IOC"
    GTC = "GTC"


@dataclass(frozen=True)
class ScannerContext:
    score: float
    rank: int
    drop_reasons: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class MarketContext:
    price: float
    spread: float
    volume: float
    rvol: float
    key_levels: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyInput:
    symbol: str
    session_context: SessionContext
    scanner_context: ScannerContext
    market_context: MarketContext
    news_context: Optional[Dict[str, Any]] = None
    data_quality_flags: List[str] = field(default_factory=list)
    pattern_inputs: Optional[List[Any]] = None
    pattern_results: Optional[List[Any]] = None


@dataclass(frozen=True)
class TradeIntent:
    intent_id: str
    symbol: str
    direction: Direction
    entry_model: str
    stop_model: str
    target_model: Optional[str]
    time_in_force_policy: TimeInForcePolicy
    invalidations: List[str]
    rationale_text: str
    risk_flags: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class StrategyDecision:
    symbol: str
    strategy_id: str
    decision_type: DecisionType
    confidence: float
    rationale_text: str
    risk_flags: List[str] = field(default_factory=list)
    intents: List[TradeIntent] = field(default_factory=list)


@dataclass(frozen=True)
class StrategyRiskPayload:
    strategy_id: str
    symbol: str
    intents: List[TradeIntent]
    decision_type: DecisionType
    confidence: float
    rationale_text: str
    risk_flags: List[str] = field(default_factory=list)
