"""Ross exit and trade-management policy section."""

from __future__ import annotations

from dataclasses import dataclass

from src.strategies.ross_momentum.strategy_policy import (
    POLICY_V2,
    IndicatorGates,
    RiskAndPermissions,
    RossMomentumPolicy,
    ToppingRiskSpec,
)


@dataclass(frozen=True)
class ExitPolicy:
    topping_risk: ToppingRiskSpec
    indicator_gates: IndicatorGates
    risk_permissions: RiskAndPermissions
    exit_model: object
    trailing_model: object

    @classmethod
    def from_policy(cls, policy: RossMomentumPolicy) -> "ExitPolicy":
        return cls(
            topping_risk=policy.topping_risk,
            indicator_gates=policy.indicator_gates,
            risk_permissions=policy.risk,
            exit_model=POLICY_V2.exit_model,
            trailing_model=POLICY_V2.trailing_model,
        )
