from __future__ import annotations

from src.scanner.scanner_runner import GateThresholds, _evaluate_focus_gates


def test_pre_focus_allows_missing_rvol_and_marks_unknown() -> None:
    thresholds = GateThresholds(
        min_price=1.0,
        max_price=20.0,
        min_pct_change=5.0,
        max_pct_change=None,
        watchlist_rvol_min=1.0,
        focus_rvol_min=2.0,
        focus_volume_min=100,
        focus_volume_min_early_rth=50,
        focus_volume_min_early_rth_ratio=0.5,
        min_volume=100,
        min_premarket_volume=50,
        max_float=20_000_000,
        spread_max_pct=None,
        min_dollar_volume=None,
        require_price=False,
        require_bid_ask=False,
        require_catalyst=False,
        allow_halts=False,
        allow_ssr=False,
        allow_unknown_float=True,
    )
    context = {
        "symbol": "ATRA",
        "session": "PRE",
        "last_price": 2.0,
        "pct_change": 25.0,
        "volume": 500,
        "premarket_volume": 500,
        "scanner_rvol": None,
        "rvol_phase": None,
        "rvol_discovery": None,
        "priority_penalty": 0.0,
    }

    assert _evaluate_focus_gates(context, thresholds) is None
    assert context["rvol_status"] == "UNKNOWN"
    assert context["priority_penalty"] > 0.0
