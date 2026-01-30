from dataclasses import replace

from src.config.config_resolver import set_config_overrides

from src.scanner.contracts import StockSelectionPolicy
from src.scanner.scanner_runner import run_scanner_cycle
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


def _to_scanner_policy(stock_policy) -> StockSelectionPolicy:
    return stock_policy


def test_scanner_policy_limits_applied_in_teaching_mode():
    set_config_overrides(
        {
            "RUN_MODE": "SIM",
            "SCANNER_DATA_SOURCE": "MOCK",
        }
    )
    base_policy = RossMomentumPolicy()
    tuned_stock_policy = replace(
        base_policy.stock_selection,
        watchlist_limit_k=3,
        focus_limit_m=2,
        top_gainers_n=5,
    )
    tuned_policy = replace(base_policy, stock_selection=tuned_stock_policy)
    scanner_policy = _to_scanner_policy(tuned_policy.stock_selection)

    try:
        payload = run_scanner_cycle(mode="READONLY", policy=scanner_policy)
    finally:
        set_config_overrides({})

    assert len(payload.get("watchlist_k", [])) == 3
    assert len(payload.get("focus_m", [])) == 2
    assert len(payload.get("focus_m_symbols", [])) == 2
