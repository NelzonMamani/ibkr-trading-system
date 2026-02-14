from dataclasses import replace

from src.config.config_resolver import set_config_overrides
from src.scanner.scanner_contract import scanner_request_from_policy
from src.scanner.scanner_runner import run_scanner_cycle
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy, select_watchlist


def test_ross_policy_to_scanner_request_contract() -> None:
    policy = RossMomentumPolicy().stock_selection
    request = scanner_request_from_policy(policy, strategy_name="ross_momentum", session_phase="MORNING")

    assert request.ranking_intent == policy.ranking_intent
    assert request.policy_name == policy.policy_name
    assert request.requested_top_n == policy.top_gainers_n


def test_ross_selector_preserves_top_k_deterministically() -> None:
    set_config_overrides({"RUN_MODE": "SIM", "SCANNER_DATA_SOURCE": "MOCK"})
    try:
        stock_policy = replace(
            RossMomentumPolicy().stock_selection,
            watchlist_limit_k=10,
            focus_limit_m=4,
            top_gainers_n=25,
            session_allowlist=("PRE", "REG", "AFTER", "OVN"),
        )
        payload = run_scanner_cycle(mode="SIM", policy=stock_policy)
    finally:
        set_config_overrides({})

    ranked = select_watchlist(payload.get("candidate_metrics", []), policy=stock_policy)
    watchlist_symbols = [row.symbol for row in payload.get("watchlist_k", [])]
    expected_symbols = [row.symbol for row in ranked[: stock_policy.watchlist_limit_k]]
    assert watchlist_symbols == expected_symbols


def test_ross_focus_is_subset_of_watchlist() -> None:
    set_config_overrides({"RUN_MODE": "PAPER", "SCANNER_DATA_SOURCE": "MOCK"})
    try:
        payload = run_scanner_cycle(mode="PAPER", policy=RossMomentumPolicy().stock_selection)
    finally:
        set_config_overrides({})

    watchlist = set(payload.get("watchlist_k_symbols", []))
    focus = set(payload.get("focus_m_symbols", []))
    assert focus.issubset(watchlist)
