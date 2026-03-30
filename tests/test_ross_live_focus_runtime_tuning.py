from dataclasses import replace

from src.config.config_resolver import set_config_overrides
from src.scanner.scanner_runner import (
    _evaluate_focus_gates,
    _evaluate_watchlist_gates,
    _gate_thresholds,
    _resolve_focus_rvol_min_for_session,
    _resolve_runtime_thresholds,
    _resolve_rvol_for_focus_gate,
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
    assert context["float_status"] == "UNKNOWN_ALLOWED"



def test_early_rth_focus_volume_is_distinct_from_execution_min_volume() -> None:
    policy = RossMomentumPolicy().stock_selection
    runtime = _resolve_runtime_thresholds(policy)
    thresholds = _gate_thresholds(policy, runtime)

    assert thresholds.focus_volume_min == policy.min_volume
    assert thresholds.focus_volume_min_early_rth < thresholds.min_volume
    assert thresholds.focus_volume_min_early_rth >= thresholds.min_premarket_volume


def test_live_like_cvgi_cyn_reach_focus_in_early_rth() -> None:
    policy = RossMomentumPolicy().stock_selection
    runtime = _resolve_runtime_thresholds(policy)
    thresholds = _gate_thresholds(replace(policy, gap_min_pct=8.0), runtime)
    thresholds = replace(
        thresholds,
        watchlist_rvol_min=0.3,
        focus_rvol_min=1.5,
        spread_max_pct=0.015,
        allow_unknown_float=True,
    )

    live_like = [
        {
            "symbol": "CVGI",
            "session": "RTH_OPEN",
            "pct_change": 55.56,
            "rvol_discovery": 1.94,
            "rvol_phase": 1.94,
            "volume": 280_252,
            "premarket_volume": 280_252,
            "dollar_volume": 706_235,
            "last_price": 2.52,
            "spread_pct": 0.01,
            "bid": 2.51,
            "ask": 2.53,
            "catalyst_present": True,
            "halted": False,
            "ssr": False,
        },
        {
            "symbol": "CYN",
            "session": "RTH_OPEN",
            "pct_change": 20.63,
            "rvol_discovery": 5.57,
            "rvol_phase": 5.57,
            "volume": 321_080,
            "premarket_volume": 321_080,
            "dollar_volume": 619_684,
            "last_price": 1.93,
            "spread_pct": 0.012,
            "bid": 1.92,
            "ask": 1.94,
            "catalyst_present": True,
            "halted": False,
            "ssr": False,
        },
    ]

    assert all(ctx["volume"] < thresholds.min_volume for ctx in live_like)
    assert all(ctx["volume"] >= thresholds.focus_volume_min_early_rth for ctx in live_like)
    assert all(_evaluate_watchlist_gates(ctx, thresholds) is None for ctx in live_like)
    assert all(_evaluate_focus_gates(ctx, thresholds) is None for ctx in live_like)


def test_drop_volume_logs_threshold_context(capsys) -> None:
    policy = RossMomentumPolicy().stock_selection
    runtime = _resolve_runtime_thresholds(policy)
    thresholds = _gate_thresholds(policy, runtime)
    thresholds = replace(thresholds, watchlist_rvol_min=0.3, focus_rvol_min=1.5, spread_max_pct=0.015)

    context = {
        "symbol": "THIN",
        "session": "RTH_OPEN",
        "phase": "OPENING",
        "pct_change": 18.0,
        "rvol_discovery": 4.0,
        "rvol_phase": 4.0,
        "volume": 10_000,
        "premarket_volume": 10_000,
        "dollar_volume": 100_000,
        "last_price": 2.0,
        "spread_pct": 0.01,
        "bid": 1.99,
        "ask": 2.01,
        "catalyst_present": True,
        "halted": False,
        "ssr": False,
    }

    assert _evaluate_focus_gates(context, thresholds) == "DROP_VOLUME"
    output = capsys.readouterr().out
    assert "[VOLUME_GATE]" in output
    assert "symbol=THIN" in output
    assert "stage=focus" in output
    assert "threshold_source=policy.session_focus_volume_min[RTH_OPEN]" in output
    assert "session=RTH_OPEN" in output
    assert "phase=OPENING" in output


def test_focus_gate_prefers_scanner_rvol_in_rth_open(capsys) -> None:
    policy = RossMomentumPolicy().stock_selection
    runtime = _resolve_runtime_thresholds(policy)
    thresholds = _gate_thresholds(policy, runtime)
    thresholds = replace(thresholds, watchlist_rvol_min=0.5, focus_rvol_min=2.0)

    context = {
        "symbol": "OPEN",
        "session": "RTH_OPEN",
        "pct_change": 12.0,
        "scanner_rvol": 2.4,
        "rvol_discovery": 0.6,
        "rvol_phase": 2.4,
        "volume": 500_000,
        "premarket_volume": 500_000,
        "dollar_volume": 2_000_000,
        "last_price": 4.0,
        "spread_pct": 0.01,
        "bid": 3.99,
        "ask": 4.01,
        "catalyst_present": True,
        "halted": False,
        "ssr": False,
    }

    assert _evaluate_focus_gates(context, thresholds) is None
    metric, value = _resolve_rvol_for_focus_gate(context)
    assert metric == "scanner_rvol"
    assert value == 2.4
    output = capsys.readouterr().out
    assert "rvol_metric_used=scanner_rvol" in output
    assert "reason=PASS_RVOL_THRESHOLD" in output


def test_focus_rvol_min_is_session_aware() -> None:
    assert _resolve_focus_rvol_min_for_session("PRE") == 0.3
    assert _resolve_focus_rvol_min_for_session("PREMARKET") == 0.3
    assert _resolve_focus_rvol_min_for_session("RTH") == 1.0
    assert _resolve_focus_rvol_min_for_session("REGULAR") == 1.0
    assert _resolve_focus_rvol_min_for_session("AH") == 0.5
    assert _resolve_focus_rvol_min_for_session("AFTER_HOURS") == 0.5
    assert _resolve_focus_rvol_min_for_session("RTH_OPEN") == 1.0


def test_unknown_float_allowed_removes_degrading_flag() -> None:
    policy = RossMomentumPolicy().stock_selection
    runtime = _resolve_runtime_thresholds(policy)
    thresholds = _gate_thresholds(policy, runtime)

    context = {
        "symbol": "UFLO",
        "session": "PRE",
        "pct_change": 15.0,
        "float_shares": None,
        "data_quality_flags": ["FLOAT_UNKNOWN", "SPREAD_UNKNOWN"],
    }

    assert _evaluate_watchlist_gates(context, thresholds) is None
    assert context["float_status"] == "UNKNOWN_ALLOWED"
    assert context["float_tolerated"] is True
    assert context["data_quality_flags"] == ["SPREAD_UNKNOWN"]



def test_midday_focus_volume_threshold_is_session_aware_for_ross_policy() -> None:
    policy = RossMomentumPolicy().stock_selection
    runtime = _resolve_runtime_thresholds(policy)
    thresholds = _gate_thresholds(policy, runtime)

    assert thresholds.focus_volume_min == policy.min_volume
    assert thresholds.session_focus_volume_min["RTH_MID"] == 300_000
    assert thresholds.session_focus_volume_min["RTH_MID"] < thresholds.focus_volume_min


def test_rth_mid_candidate_with_realistic_intraday_volume_can_enter_focus() -> None:
    policy = RossMomentumPolicy().stock_selection
    runtime = _resolve_runtime_thresholds(policy)
    thresholds = _gate_thresholds(policy, runtime)
    thresholds = replace(thresholds, watchlist_rvol_min=0.5, focus_rvol_min=2.0, spread_max_pct=0.02)

    context = {
        "symbol": "ARTL",
        "session": "RTH_MID",
        "phase": "RTH_MID",
        "pct_change": 31.5,
        "rvol_discovery": 6.1,
        "rvol_phase": 4.4,
        "volume": 511_545,
        "premarket_volume": 175_000,
        "dollar_volume": 2_813_497.5,
        "last_price": 5.5,
        "spread_pct": 0.012,
        "bid": 5.49,
        "ask": 5.51,
        "catalyst_present": True,
        "halted": False,
        "ssr": False,
    }

    assert _evaluate_watchlist_gates(context, thresholds) is None
    assert _evaluate_focus_gates(context, thresholds) is None


def test_rth_mid_illiquid_candidate_still_fails_focus_volume_gate() -> None:
    policy = RossMomentumPolicy().stock_selection
    runtime = _resolve_runtime_thresholds(policy)
    thresholds = _gate_thresholds(policy, runtime)
    thresholds = replace(thresholds, watchlist_rvol_min=0.5, focus_rvol_min=2.0, spread_max_pct=0.02)

    context = {
        "symbol": "MNDR",
        "session": "RTH_MID",
        "phase": "RTH_MID",
        "pct_change": 22.0,
        "rvol_discovery": 3.0,
        "rvol_phase": 2.7,
        "volume": 6_144,
        "premarket_volume": 2_000,
        "dollar_volume": 24_576,
        "last_price": 4.0,
        "spread_pct": 0.015,
        "bid": 3.99,
        "ask": 4.01,
        "catalyst_present": True,
        "halted": False,
        "ssr": False,
    }

    assert _evaluate_watchlist_gates(context, thresholds) is None
    assert _evaluate_focus_gates(context, thresholds) == "DROP_VOLUME"


def test_live_like_focus_list_can_be_non_zero_in_rth_mid() -> None:
    policy = RossMomentumPolicy().stock_selection
    runtime = _resolve_runtime_thresholds(policy)
    thresholds = _gate_thresholds(policy, runtime)
    thresholds = replace(thresholds, watchlist_rvol_min=0.5, focus_rvol_min=2.0, spread_max_pct=0.02)

    live_like = [
        {
            "symbol": "AIB",
            "session": "RTH_MID",
            "phase": "RTH_MID",
            "pct_change": 18.2,
            "rvol_discovery": 3.4,
            "rvol_phase": 2.8,
            "volume": 66_247,
            "premarket_volume": 18_000,
            "dollar_volume": 264_988,
            "last_price": 4.0,
            "spread_pct": 0.018,
            "bid": 3.99,
            "ask": 4.01,
            "catalyst_present": True,
            "halted": False,
            "ssr": False,
        },
        {
            "symbol": "ARTL",
            "session": "RTH_MID",
            "phase": "RTH_MID",
            "pct_change": 31.5,
            "rvol_discovery": 6.1,
            "rvol_phase": 4.4,
            "volume": 511_545,
            "premarket_volume": 175_000,
            "dollar_volume": 2_813_497.5,
            "last_price": 5.5,
            "spread_pct": 0.012,
            "bid": 5.49,
            "ask": 5.51,
            "catalyst_present": True,
            "halted": False,
            "ssr": False,
        },
        {
            "symbol": "MIDOK",
            "session": "RTH_MID",
            "phase": "RTH_MID",
            "pct_change": 24.0,
            "rvol_discovery": 5.2,
            "rvol_phase": 3.1,
            "volume": 342_000,
            "premarket_volume": 120_000,
            "dollar_volume": 1_881_000,
            "last_price": 5.5,
            "spread_pct": 0.01,
            "bid": 5.49,
            "ask": 5.51,
            "catalyst_present": True,
            "halted": False,
            "ssr": False,
        },
    ]

    focus = [ctx["symbol"] for ctx in live_like if _evaluate_watchlist_gates(ctx, thresholds) is None and _evaluate_focus_gates(ctx, thresholds) is None]

    assert focus == ["ARTL", "MIDOK"]
    assert len(focus) > 0
