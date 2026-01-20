from dataclasses import replace

from src.scanner.scanner_runner import run_scanner_cycle
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy



def test_scanner_policy_limits_applied_in_teaching_mode():
    base_policy = RossMomentumPolicy()
    tuned_stock_policy = replace(
        base_policy.stock_selection,
        watchlist_limit_k=3,
        focus_limit_m=2,
        top_gainers_n=5,
    )
    tuned_policy = replace(base_policy, stock_selection=tuned_stock_policy)

    payload = run_scanner_cycle(mode="READONLY", policy=tuned_policy.stock_selection)

    assert len(payload.get("watchlist_k", [])) == 3
    assert len(payload.get("focus_m", [])) == 2
