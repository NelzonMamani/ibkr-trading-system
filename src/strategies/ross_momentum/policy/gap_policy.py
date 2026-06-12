"""Ross gap and percent-change policy section."""

from __future__ import annotations

from dataclasses import dataclass

from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


@dataclass(frozen=True)
class GapPolicy:
    min_pct: float
    premarket_min_pct: float
    max_pct: float | None

    @classmethod
    def from_policy(cls, policy: RossMomentumPolicy) -> "GapPolicy":
        return cls(
            min_pct=float(policy.stock_selection.gap_min_pct),
            premarket_min_pct=5.0,
            max_pct=policy.stock_selection.gap_max_pct,
        )
