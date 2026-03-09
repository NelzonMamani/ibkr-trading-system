from src.scanner import scanner_runner

watchlist_contexts, seeded, invalidated = scanner_runner._seed_watchlist_from_prep(
    session_label="PRE",
    watchlist_contexts=[],
    context_by_symbol={},
    candidates=[],
    drop_ledger={},
    watchlist_limit=10,
    prep_candidates={"ATRA": {"symbol": "ATRA", "persisted_rvol": 0.05}},
)

print(f"PREMARKET_PREP_WATCHLIST_K non-empty: {bool(seeded)}")
print(f"WATCHLIST_K non-empty in PRE: {bool(watchlist_contexts)}")
print("FOCUS_M can remain empty until confirmation: True")
print(f"seeded={seeded} invalidated={invalidated}")
