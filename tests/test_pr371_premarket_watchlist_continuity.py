from src.scanner import scanner_runner


def test_prep_seeded_symbols_keep_pre_watchlist_non_empty() -> None:
    watchlist_contexts, seeded, invalidated = scanner_runner._seed_watchlist_from_prep(
        session_label="PRE",
        watchlist_contexts=[],
        context_by_symbol={},
        candidates=[],
        drop_ledger={},
        watchlist_limit=5,
        prep_candidates={"ATRA": {"symbol": "ATRA", "persisted_rvol": 0.05}},
    )
    assert watchlist_contexts
    assert seeded == 1
    assert invalidated == 0
    assert watchlist_contexts[0]["prep_seeded"] is True
    assert watchlist_contexts[0]["live_confirmation_pending"] is True


def test_prep_seeded_can_stay_watchlist_and_pass_focus_when_confirmation_pending_in_premarket() -> None:
    thresholds = scanner_runner.GateThresholds(
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
        "volume": 15_000,
        "premarket_volume": 15_000,
        "scanner_rvol": 3.0,
        "rvol_phase": 3.0,
        "rvol_discovery": 0.1,
        "live_confirmation_pending": True,
    }
    assert scanner_runner._evaluate_focus_gates(context, thresholds) is None


def test_premarket_float_gate_is_relaxed_but_rth_remains_strict() -> None:
    thresholds = scanner_runner.GateThresholds(
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
    pre_context = {"symbol": "ATRA", "session": "PRE", "float_shares": 90_000_000}
    rth_context = {"symbol": "ATRA", "session": "RTH", "float_shares": 90_000_000}
    assert scanner_runner._evaluate_float_gate(pre_context, thresholds) is None
    assert scanner_runner._evaluate_float_gate(rth_context, thresholds) == "DROP_FLOAT_MAX"
