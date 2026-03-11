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


def test_prep_seeded_can_stay_watchlist_but_fail_focus_pending_confirmation() -> None:
    thresholds = scanner_runner.GateThresholds(
        min_price=1.0,
        max_price=20.0,
        min_pct_change=5.0,
        max_pct_change=None,
        watchlist_rvol_min=1.0,
        focus_rvol_min=2.0,
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
        "volume": 500,
        "premarket_volume": 500,
        "scanner_rvol": 3.0,
        "rvol_phase": 3.0,
        "rvol_discovery": 0.1,
        "live_confirmation_pending": True,
    }
    assert scanner_runner._evaluate_focus_gates(context, thresholds) == "DROP_LIVE_CONFIRMATION_PENDING"
