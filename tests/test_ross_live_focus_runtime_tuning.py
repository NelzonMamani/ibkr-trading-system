from dataclasses import replace

from src.config.config_resolver import set_config_overrides
from src.scanner.scanner_runner import (
    _evaluate_focus_gates,
    _evaluate_watchlist_gates,
    _gate_thresholds,
    _resolve_runtime_thresholds,
)
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


def test_env_overrides_runtime_thresholds_take_precedence() -> None:
    policy = RossMomentumPolicy().stock_selection
    set_config_overrides(
        {
            "WATCHLIST_RVOL_MIN": 0.3,
            "FOCUS_RVOL_MIN": 1.5,
            "MAX_SPREAD_PCT": 0.04,
            "ALLOW_UNKNOWN_FLOAT": True,
        }
    )
    try:
        runtime = _resolve_runtime_thresholds(policy)
        thresholds = _gate_thresholds(policy, runtime)
    finally:
        set_config_overrides(None)

    assert runtime.watchlist_rvol_source == "OVERRIDE"
    assert runtime.focus_rvol_source == "OVERRIDE"
    assert thresholds.watchlist_rvol_min == 0.3
    assert thresholds.focus_rvol_min == 1.5
    assert thresholds.spread_max_pct == 0.04


def test_early_rth_candidate_can_promote_with_discovery_context() -> None:
    policy = RossMomentumPolicy().stock_selection
    runtime = _resolve_runtime_thresholds(policy)
    thresholds = _gate_thresholds(replace(policy, gap_min_pct=8.0, watchlist_rvol_min=0.5, focus_rvol_min=2.0), runtime)
    thresholds = replace(thresholds, watchlist_rvol_min=0.5, focus_rvol_min=2.0)

    context = {
        "symbol": "CYN",
        "session": "RTH_OPEN",
        "pct_change": 12.0,
        "rvol_discovery": 14.88,
        "rvol_phase": 1.65,
        "volume": 1_400_000,
        "premarket_volume": 1_400_000,
        "dollar_volume": 8_000_000,
        "last_price": 5.7,
        "spread_pct": 0.02,
        "bid": 5.69,
        "ask": 5.71,
        "catalyst_present": True,
        "halted": False,
        "ssr": False,
    }

    assert _evaluate_watchlist_gates(context, thresholds) is None
    assert _evaluate_focus_gates(context, thresholds) is None


def test_unknown_float_allowed_does_not_drop_watchlist() -> None:
    policy = RossMomentumPolicy().stock_selection
    runtime = _resolve_runtime_thresholds(policy)
    thresholds = _gate_thresholds(policy, runtime)
    context = {
        "symbol": "XYZ",
        "session": "PRE",
        "pct_change": 15.0,
        "rvol_discovery": 3.0,
        "float_shares": None,
    }

    assert _evaluate_watchlist_gates(context, thresholds) is None
    assert context["float_status"] == "UNKNOWN"
