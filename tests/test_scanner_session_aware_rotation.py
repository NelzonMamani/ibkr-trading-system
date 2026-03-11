from src.scanner.scanner_runner import _seed_watchlist_from_prep


def test_rth_does_not_seed_from_prep_candidates() -> None:
    watchlist, seeded, invalidated = _seed_watchlist_from_prep(
        session_label="RTH_OPEN",
        watchlist_contexts=[],
        context_by_symbol={},
        candidates=[],
        drop_ledger={},
        watchlist_limit=5,
        prep_candidates={"PREP": {"symbol": "PREP", "pct_change_context": 10.0}},
    )
    assert watchlist == []
    assert seeded == 0
    assert invalidated == 0


def test_pre_can_seed_from_prep_candidates() -> None:
    watchlist, seeded, _ = _seed_watchlist_from_prep(
        session_label="PRE",
        watchlist_contexts=[],
        context_by_symbol={},
        candidates=[],
        drop_ledger={},
        watchlist_limit=5,
        prep_candidates={"PREP": {"symbol": "PREP", "pct_change_context": 10.0, "persisted_rvol": 2.0}},
    )
    assert seeded == 1
    assert watchlist and watchlist[0]["symbol"] == "PREP"
    assert watchlist[0].get("prep_seeded") is True
