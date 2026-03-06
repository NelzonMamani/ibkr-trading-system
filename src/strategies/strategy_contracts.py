"""Canonical strategy contracts for Epoch 2 decision intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from src.strategies.common import foundation


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


class ExecutionMode(str, Enum):
    SIM = "SIM"
    PAPER = "PAPER"
    LIVE = "LIVE"
    READ_ONLY = "READ_ONLY"


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
    session_label: str = "PRE"
    float: Optional[float] = None
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


@dataclass(frozen=True)
class StrategyFoundationComponents:
    setup_families: List[str] = field(default_factory=list)
    execution_triggers: List[str] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)
    confirmations: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class StrategyExecutionProfile:
    supported_modes: List[ExecutionMode] = field(
        default_factory=lambda: [ExecutionMode.SIM]
    )
    allow_long: bool = True
    allow_short: bool = True
    no_trade_contexts: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class StrategyContract:
    strategy_id: str
    strategy_name: str
    version: str
    foundation_version: str
    foundation_components: StrategyFoundationComponents
    execution_profile: StrategyExecutionProfile
    description: Optional[str] = None


def validate_strategy_contract(contract: StrategyContract) -> List[str]:
    problems: List[str] = []
    problems.extend(
        foundation.validate_foundation_components(
            contract.foundation_components.setup_families, foundation.SETUP_FAMILIES
        )
    )
    problems.extend(
        foundation.validate_foundation_components(
            contract.foundation_components.execution_triggers,
            foundation.EXECUTION_TRIGGERS,
        )
    )
    problems.extend(
        foundation.validate_foundation_components(
            contract.foundation_components.conditions, foundation.CONDITIONS
        )
    )
    problems.extend(
        foundation.validate_foundation_components(
            contract.foundation_components.confirmations, foundation.CONFIRMATIONS
        )
    )
    if not foundation.is_foundation_compatible(contract.foundation_version):
        problems.append("foundation_version_incompatible")
    return sorted(set(problems))
