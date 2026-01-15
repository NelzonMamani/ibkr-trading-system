"""Scanner print contract helpers for Epoch 5."""
from __future__ import annotations

from typing import Dict, List


def _focus_symbols(payload: Dict[str, object]) -> List[str]:
    focus_rows = payload.get("focus_rows", [])
    return [row.symbol for row in focus_rows] if focus_rows else []


def print_scanner_contract(payload: Dict[str, object]) -> None:
    topn_count = int(payload.get("topn_count", len(payload.get("symbols", []))))
    survivors_count = int(payload.get("survivors_count", len(payload.get("watchlist", []))))
    watchlist = payload.get("watchlist", [])
    focus_symbols = _focus_symbols(payload)
    drop_summary = payload.get("drop_ledger_summary", {})

    print(f"TopN: {topn_count}")
    print(f"GatedSurvivors: {survivors_count}")
    print(f"DropReasons: {drop_summary}")
    print(f"WatchlistK: {watchlist}")
    print(f"FocusM: {focus_symbols}")
    if not watchlist:
        print("EMPTY WATCHLIST (valid)")
        if drop_summary:
            print(f"DropReasons: {drop_summary}")


def print_scanner_state(payload: Dict[str, object]) -> None:
    cycle_state = payload.get("cycle_state", {})
    new_symbols = cycle_state.get("new_symbols", [])
    continuing_symbols = cycle_state.get("continuing_symbols", [])
    dropped_symbols = cycle_state.get("dropped_symbols", [])

    if new_symbols or continuing_symbols or dropped_symbols:
        print(f"NEW: {new_symbols}")
        print(f"CONTINUING: {continuing_symbols}")
        print(f"DROPPED: {dropped_symbols}")
