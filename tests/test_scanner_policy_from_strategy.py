from dataclasses import replace

from src.config.config_resolver import set_config_overrides

from src.scanner.contracts import StockSelectionPolicy
from src.scanner.scanner_runner import run_scanner_cycle
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


def _to_scanner_policy(stock_policy) -> StockSelectionPolicy:
    return stock_policy


def test_scanner_policy_limits_applied_in_teaching_mode():
    # Keep OVN behavior explicit for environments that support configurable OVN tradeability.
    # Current fixtures still allow OVN prep focus candidates; execution remains blocked downstream.
    import os
    prior_ovn = os.environ.get("ENABLE_OVN_TRADING")
    os.environ["ENABLE_OVN_TRADING"] = "true"
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
        float_max_millions=50_000.0,
        session_allowlist=("PRE", "REG", "AFTER", "OVN"),
    )
    tuned_policy = replace(base_policy, stock_selection=tuned_stock_policy)
    scanner_policy = _to_scanner_policy(tuned_policy.stock_selection)

    ovn_enabled = os.environ.get("ENABLE_OVN_TRADING", "").lower() == "true"
    try:
        payload = run_scanner_cycle(mode="READONLY", policy=scanner_policy)
    finally:
        if prior_ovn is None:
            os.environ.pop("ENABLE_OVN_TRADING", None)
        else:
            os.environ["ENABLE_OVN_TRADING"] = prior_ovn
        set_config_overrides({})

    assert len(payload.get("watchlist_k", [])) == 3
    assert len(payload.get("focus_m", [])) <= 3
    assert len(payload.get("focus_m_symbols", [])) <= 3
    focus = payload.get("focus_m", [])
    watchlist = payload.get("watchlist_k", [])
    candidate = watchlist[0] if watchlist else None
    session = getattr(candidate, "session_label", None) if candidate is not None else None

    if session == "OVN" and not ovn_enabled:
        assert focus == []
    else:
        assert len(focus) >= min(1, len(watchlist))


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

    raw_n = payload.get("raw_universe_count", payload["topn_count"])
    gated_n = payload.get("gated_survivors_count", payload["survivors_count"])
    watchlist_n = payload.get("watchlist_count", len(payload.get("watchlist_k", [])))
    focus_n = payload.get("focus_count", len(payload.get("focus_m", [])))

    assert raw_n == scanner_policy.top_gainers_n
    assert gated_n <= raw_n
    assert watchlist_n <= scanner_policy.watchlist_limit_k
    assert focus_n <= scanner_policy.focus_limit_m
    assert payload["survivors_count"] == gated_n

    watchlist_symbols = set(payload.get("watchlist_k_symbols", []))
    focus_symbols = payload.get("focus_m_symbols", [])
    assert len(focus_symbols) <= scanner_policy.focus_limit_m
    assert set(focus_symbols).issubset(watchlist_symbols)
