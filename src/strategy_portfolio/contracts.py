"""Interface contracts for strategy portfolio governance."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Protocol


class AllowState(str, Enum):
    ALLOW = "ALLOW"
    DISALLOW = "DISALLOW"


class SignalIntent(str, Enum):
    ENTER_LONG = "ENTER_LONG"
    ENTER_SHORT = "ENTER_SHORT"
    HOLD = "HOLD"
    EXIT_ONLY = "EXIT_ONLY"
    NO_TRADE = "NO_TRADE"


class OrderConstraint(str, Enum):
    LIMIT = "LIMIT"
    MARKETABLE_LIMIT = "MARKETABLE_LIMIT"
    MARKET = "MARKET"


class ExecutionMode(str, Enum):
    SIM = "SIM"
    PAPER = "PAPER"
    LIVE = "LIVE"
    READ_ONLY = "READ_ONLY"


@dataclass(frozen=True)
class StrategyIdentity:
    strategy_id: str
    strategy_version: str
    strategy_family: str | None = None


class StrategyPolicyContract(Protocol):
    """Minimal policy contract for strategies.

    This is intentionally lightweight to avoid coupling to existing strategy
    implementations.
    """

    identity: StrategyIdentity

    def policy_snapshot(self) -> Mapping[str, object] | None:
        ...


@dataclass(frozen=True)
class DecisionIntent:
    allow_state: AllowState = AllowState.DISALLOW
    signal_intent: SignalIntent = SignalIntent.NO_TRADE
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyContextSnapshot:
    """Placeholder context snapshot for normaliser inputs."""

    payload: Mapping[str, object] = field(default_factory=dict)
