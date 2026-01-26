from src.strategies.ross_momentum.permission_matrix import (
    PermissionContext,
    PermissionState,
    evaluate_permission_state,
)
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


def test_permission_pause_on_topping_tail() -> None:
    policy = RossMomentumPolicy()
    context = PermissionContext(
        topping_wick_ratio=policy.topping_risk.topping_wick_ratio_pause,
        consecutive_losses=0,
    )
    assert evaluate_permission_state(policy, context) == PermissionState.PAUSE


def test_permission_halt_on_reversal_tail() -> None:
    policy = RossMomentumPolicy()
    context = PermissionContext(
        topping_wick_ratio=policy.topping_risk.topping_wick_ratio_halt,
        consecutive_losses=0,
    )
    assert evaluate_permission_state(policy, context) == PermissionState.HALT


def test_permission_halt_on_consecutive_losses() -> None:
    policy = RossMomentumPolicy()
    context = PermissionContext(
        topping_wick_ratio=0.0,
        consecutive_losses=policy.risk.max_consecutive_losses,
    )
    assert evaluate_permission_state(policy, context) == PermissionState.HALT
