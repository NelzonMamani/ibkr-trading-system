"""Console logging helpers for operator-grade output."""

from __future__ import annotations

from typing import Iterable, Mapping


def print_section(title: str) -> None:
    print(f"\n=== {title} ===")


def format_symbol_list(symbols: Iterable[str]) -> str:
    return "[" + ", ".join(symbols) + "]"


def print_watchlist_focus(
    watchlist: list[str],
    focus: list[str],
    drop_summary: Mapping[str, int] | None = None,
) -> None:
    if not watchlist:
        print("EMPTY WATCHLIST (valid)")
        if drop_summary:
            print(f"DropReasons: {dict(drop_summary)}")
        print("WATCHLIST_K: []")
        print("FOCUS_M: []")
        return
    print(f"WATCHLIST_K: {format_symbol_list(watchlist)}")
    print(f"FOCUS_M: {format_symbol_list(focus)}")


def print_drop_summary(drop_summary: Mapping[str, int]) -> None:
    print(f"DropReasons: {dict(drop_summary)}")


def print_status_list(label: str, symbols: Iterable[str]) -> None:
    print(f"{label}: {format_symbol_list(list(symbols))}")
