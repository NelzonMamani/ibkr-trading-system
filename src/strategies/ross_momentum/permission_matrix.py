"""Ross Momentum trade permission matrix."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


class PermissionState(str, Enum):
    ALLOW = "ALLOW"
    PAUSE = "PAUSE"
    HALT = "HALT"


@dataclass(frozen=True)
class PermissionContext:
    topping_wick_ratio: float
    consecutive_losses: int


def evaluate_permission_state(
    policy: RossMomentumPolicy,
    context: PermissionContext,
) -> PermissionState:
    if context.consecutive_losses >= policy.risk.max_consecutive_losses:
        return PermissionState.HALT
    if context.topping_wick_ratio >= policy.topping_risk.topping_wick_ratio_halt:
        return PermissionState.HALT
    if context.topping_wick_ratio >= policy.topping_risk.topping_wick_ratio_pause:
        return PermissionState.PAUSE
    return PermissionState.ALLOW
