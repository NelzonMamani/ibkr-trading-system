from datetime import time

from src.scanner.scanner_runner import (
    GateThresholds,
    _evaluate_focus_gates,
    _focus_volume_threshold_for_session,
    _resolve_premarket_volume_threshold,
    _ross_reason_from_drop,
)


def test_premarket_volume_gate_enforced() -> None:
    thresholds = GateThresholds(
        min_price=1.0,
        max_price=20.0,
        min_pct_change=10.0,
        max_pct_change=None,
        watchlist_rvol_min=0.5,
        focus_rvol_min=2.0,
        focus_volume_min=1_000_000,
        focus_volume_min_early_rth=250_000,
        focus_volume_min_early_rth_ratio=0.25,
        min_volume=1_000_000,
        min_premarket_volume=100_000,
        max_float=20_000_000,
        spread_max_pct=None,
        min_dollar_volume=None,
        require_price=True,
        require_bid_ask=False,
        require_catalyst=False,
        allow_halts=False,
        allow_ssr=True,
        allow_unknown_float=True,
    )
    context = {
        "symbol": "XYZ",
        "session": "PRE",
        "last_price": 4.2,
        "volume": 150_000,
        "premarket_volume": 5_000,
        "dollar_volume": 500_000,
        "halted": False,
        "ssr": False,
        "rvol_discovery": 3.0,
    }
    reason = _evaluate_focus_gates(context, thresholds)
    assert reason == "DROP_PREMARKET_VOLUME"
    assert _ross_reason_from_drop(reason) == "LIQUIDITY_FAIL"



def test_premarket_volume_gate_relaxed_for_discovery() -> None:
    thresholds = GateThresholds(
        min_price=1.0,
        max_price=20.0,
        min_pct_change=10.0,
        max_pct_change=None,
        watchlist_rvol_min=0.5,
        focus_rvol_min=2.0,
        focus_volume_min=1_000_000,
        focus_volume_min_early_rth=250_000,
        focus_volume_min_early_rth_ratio=0.25,
        min_volume=1_000_000,
        min_premarket_volume=100_000,
        max_float=20_000_000,
        spread_max_pct=None,
        min_dollar_volume=None,
        require_price=True,
        require_bid_ask=False,
        require_catalyst=False,
        allow_halts=False,
        allow_ssr=True,
        allow_unknown_float=True,
    )
    context = {
        "symbol": "XYZ",
        "session": "PRE",
        "last_price": 4.2,
        "volume": 150_000,
        "premarket_volume": 15_000,
        "dollar_volume": 500_000,
        "halted": False,
        "ssr": False,
        "rvol_discovery": 3.0,
    }

    original = _evaluate_focus_gates.__globals__["_resolve_premarket_volume_threshold"]
    try:
        _evaluate_focus_gates.__globals__["_resolve_premarket_volume_threshold"] = lambda *_args, **_kwargs: 50_000
        reason = _evaluate_focus_gates(context, thresholds)
    finally:
        _evaluate_focus_gates.__globals__["_resolve_premarket_volume_threshold"] = original

    assert reason is None


def test_prep_seeded_can_stay_watchlist_and_pass_focus_when_confirmation_pending_in_premarket() -> None:
    thresholds = GateThresholds(
        min_price=1.0,
        max_price=20.0,
        min_pct_change=10.0,
        max_pct_change=None,
        watchlist_rvol_min=0.5,
        focus_rvol_min=2.0,
        focus_volume_min=1_000_000,
        focus_volume_min_early_rth=250_000,
        focus_volume_min_early_rth_ratio=0.25,
        min_volume=1_000_000,
        min_premarket_volume=100_000,
        max_float=20_000_000,
        spread_max_pct=None,
        min_dollar_volume=None,
        require_price=True,
        require_bid_ask=False,
        require_catalyst=False,
        allow_halts=False,
        allow_ssr=True,
        allow_unknown_float=True,
    )
    context = {
        "symbol": "ATRA",
        "session": "PRE",
        "last_price": 2.0,
        "volume": 15_000,
        "premarket_volume": 15_000,
        "dollar_volume": 500_000,
        "halted": False,
        "ssr": False,
        "rvol_phase": 3.0,
        "rvol_discovery": 3.0,
        "scanner_rvol": 3.0,
    }

    original = _evaluate_focus_gates.__globals__["_resolve_premarket_volume_threshold"]
    try:
        _evaluate_focus_gates.__globals__["_resolve_premarket_volume_threshold"] = lambda *_args, **_kwargs: 50_000
        reason = _evaluate_focus_gates(context, thresholds)
    finally:
        _evaluate_focus_gates.__globals__["_resolve_premarket_volume_threshold"] = original

    assert reason is None

def test_resolve_premarket_volume_threshold() -> None:
    thresholds = GateThresholds(
        min_price=1.0,
        max_price=20.0,
        min_pct_change=10.0,
        max_pct_change=None,
        watchlist_rvol_min=0.5,
        focus_rvol_min=2.0,
        focus_volume_min=1_000_000,
        focus_volume_min_early_rth=250_000,
        focus_volume_min_early_rth_ratio=0.25,
        min_volume=1_000_000,
        min_premarket_volume=100_000,
        max_float=20_000_000,
        spread_max_pct=None,
        min_dollar_volume=None,
        require_price=True,
        require_bid_ask=False,
        require_catalyst=False,
        allow_halts=False,
        allow_ssr=True,
        allow_unknown_float=True,
    )

    assert _resolve_premarket_volume_threshold(time(4, 0), thresholds) == 10_000
    assert _resolve_premarket_volume_threshold(time(7, 29), thresholds) == 10_000
    assert _resolve_premarket_volume_threshold(time(7, 30), thresholds) == 50_000
    assert _resolve_premarket_volume_threshold(time(9, 29), thresholds) == 50_000
    assert _resolve_premarket_volume_threshold(time(9, 30), thresholds) == thresholds.min_premarket_volume


def test_focus_volume_threshold_is_session_aware() -> None:
    thresholds = GateThresholds(
        min_price=1.0,
        max_price=20.0,
        min_pct_change=10.0,
        max_pct_change=None,
        watchlist_rvol_min=0.5,
        focus_rvol_min=2.0,
        focus_volume_min=1_000_000,
        focus_volume_min_early_rth=250_000,
        focus_volume_min_early_rth_ratio=0.25,
        min_volume=1_000_000,
        min_premarket_volume=100_000,
        max_float=20_000_000,
        spread_max_pct=None,
        min_dollar_volume=None,
        require_price=True,
        require_bid_ask=False,
        require_catalyst=False,
        allow_halts=False,
        allow_ssr=True,
        allow_unknown_float=True,
    )

    assert _focus_volume_threshold_for_session("PRE", thresholds) == (50_000.0, "session_default[PRE]")
    assert _focus_volume_threshold_for_session("RTH_OPEN", thresholds) == (100_000.0, "session_default[RTH_OPEN]")
    assert _focus_volume_threshold_for_session("RTH", thresholds) == (300_000.0, "session_default[RTH]")
