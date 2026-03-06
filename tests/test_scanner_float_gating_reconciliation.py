from src.scanner.scanner_runner import GateThresholds, _evaluate_watchlist_gates


def _thresholds() -> GateThresholds:
    return GateThresholds(
        min_price=1.0,
        max_price=500.0,
        min_pct_change=1.0,
        max_pct_change=None,
        watchlist_rvol_min=0.5,
        focus_rvol_min=2.0,
        min_volume=1000,
        min_premarket_volume=0,
        max_float=100_000_000,
        spread_max_pct=None,
        min_dollar_volume=None,
        require_price=True,
        require_bid_ask=False,
        require_catalyst=False,
        allow_halts=True,
        allow_ssr=True,
    )


def test_symbol_survives_when_float_present_from_external_cache() -> None:
    context = {"symbol": "ABC", "session": "RTH", "pct_change": 5.0, "scanner_rvol": 1.2, "float_shares": 5_000_000}
    assert _evaluate_watchlist_gates(context, _thresholds()) is None


def test_symbol_rejected_when_float_truly_missing() -> None:
    context = {"symbol": "ABC", "session": "RTH", "pct_change": 5.0, "scanner_rvol": 1.2, "float_shares": None}
    assert _evaluate_watchlist_gates(context, _thresholds()) == "DROP_FLOAT_MISSING"
