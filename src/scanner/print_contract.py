"""Scanner output contract helpers for Epoch 5."""

from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable, List


def summarize_drop_reasons(drop_ledger: Dict[str, str]) -> Dict[str, int]:
    return dict(Counter(drop_ledger.values()))


def print_scanner_contract(
    topn_count: int,
    survivors_count: int,
    watchlist_k: List[str],
    focus_m: List[str],
    drop_summary: Dict[str, int],
    new_symbols: Iterable[str],
    continuing_symbols: Iterable[str],
    dropped_symbols: Iterable[str],
) -> None:
    print(f"TopN: {topn_count}")
    print(f"GatedSurvivors: {survivors_count}")
    print(f"DropReasons: {drop_summary}")
    if not watchlist_k:
        print("EMPTY WATCHLIST (valid)")
    print(f"WATCHLIST_K: {watchlist_k}")
    print(f"FOCUS_M: {focus_m}")
    print(f"NEW: {list(new_symbols)}")
    print(f"CONTINUING: {list(continuing_symbols)}")
    print(f"DROPPED: {list(dropped_symbols)}")
