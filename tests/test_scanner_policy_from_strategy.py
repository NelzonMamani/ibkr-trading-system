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
        "RUN_MODE": "PAPER",
            "SCANNER_DATA_SOURCE": "MOCK",
        }
    )
    base_policy = RossMomentumPolicy()
    tuned_stock_policy = replace(
        base_policy.stock_selection,
        watchlist_limit_k=3,
        focus_limit_m=2,
        top_gainers_n=5,
        session_allowlist=("PRE", "REG", "AFTER", "OVN"),
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


def test_scanner_keeps_top_k_and_drops_only_below_watchlist_rank():
    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "SCANNER_DATA_SOURCE": "MOCK",
        }
    )
    base_policy = RossMomentumPolicy()
    tuned_stock_policy = replace(
        base_policy.stock_selection,
        watchlist_limit_k=15,
        focus_limit_m=5,
        top_gainers_n=50,
        max_symbols_per_cycle=50,
        session_allowlist=("PRE", "REG", "AFTER", "OVN"),
    )
    scanner_policy = _to_scanner_policy(tuned_stock_policy)

    try:
        payload = run_scanner_cycle(mode="SIM", policy=scanner_policy)
    finally:
        set_config_overrides({})

    assert payload.get("raw_universe_count") == 50
    assert payload.get("gated_survivors_count") == 46
    assert payload.get("survivors_count") == payload.get("gated_survivors_count")
    assert len(payload.get("watchlist_k", [])) == 15
    drop_summary = payload.get("drop_reason_summary", {})
    assert drop_summary.get("DROP_RANK_BELOW_WATCHLIST") == 31
    assert drop_summary.get("DROP_PCT_CHANGE") == 4

    watchlist_symbols = set(payload.get("watchlist_k_symbols", []))
    focus_symbols = payload.get("focus_m_symbols", [])
    assert len(focus_symbols) <= 5
    assert set(focus_symbols).issubset(watchlist_symbols)
