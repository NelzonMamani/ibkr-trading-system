"""Ross execution timing policy section."""

from __future__ import annotations

from dataclasses import dataclass

from src.strategies.ross_momentum.strategy_policy import (
    MicroPullbackSpec,
    RossMomentumPolicy,
    TimeframePlan,
)


@dataclass(frozen=True)
class ExecutionTimingPolicy:
    opening: TimeframePlan
    midday: TimeframePlan
    late_day: TimeframePlan
    micro_pullback: MicroPullbackSpec

    @classmethod
    def from_policy(cls, policy: RossMomentumPolicy) -> "ExecutionTimingPolicy":
        return cls(
            opening=policy.timeframe_opening,
            midday=policy.timeframe_midday,
            late_day=policy.timeframe_late_day,
            micro_pullback=policy.micro_pullback,
        )
