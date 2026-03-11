from src.scanner.scanner_runner import GateThresholds, _evaluate_focus_gates, _ross_reason_from_drop


def test_premarket_volume_gate_enforced() -> None:
    thresholds = GateThresholds(
        min_price=1.0,
        max_price=20.0,
        min_pct_change=10.0,
        max_pct_change=None,
        watchlist_rvol_min=0.5,
        focus_rvol_min=2.0,
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
        "premarket_volume": 85_000,
        "dollar_volume": 500_000,
        "halted": False,
        "ssr": False,
        "rvol_discovery": 3.0,
    }
    reason = _evaluate_focus_gates(context, thresholds)
    assert reason == "DROP_PREMARKET_VOLUME"
    assert _ross_reason_from_drop(reason) == "LIQUIDITY_FAIL"
