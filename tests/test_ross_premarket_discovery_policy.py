from src.scanner.session_pct_change import compute_session_relative_volume_with_provenance
from src.strategies.ross_momentum.strategy_policy import (
    RossMomentumPolicy,
    stock_selection_policy_for_session_phase,
)


def test_session_gap_min_is_dynamic() -> None:
    policy = RossMomentumPolicy()
    pre = stock_selection_policy_for_session_phase(policy, "PRE")
    rth = stock_selection_policy_for_session_phase(policy, "RTH_OPEN")
    assert pre.gap_min_pct == 5.0
    assert rth.gap_min_pct == 10.0


def test_rvol_expected_volume_has_floor() -> None:
    payload = compute_session_relative_volume_with_provenance(
        session_label="PRE",
        session_volume=100.0,
        avg_volume_20d=1_000_000.0,
    )
    assert payload.expected_volume is not None
    assert payload.expected_volume >= 1_000.0
