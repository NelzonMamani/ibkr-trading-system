"""Ross watchlist and focus policy section."""

from __future__ import annotations

from dataclasses import dataclass

from src.strategies.ross_momentum.strategy_policy import StockSelectionSpec


@dataclass(frozen=True)
class WatchlistPolicy:
    top_gainers_n: int
    watchlist_limit_k: int
    focus_limit_m: int
    session_allowlist: tuple[str, ...]

    @classmethod
    def from_stock_selection(cls, stock_selection: StockSelectionSpec) -> "WatchlistPolicy":
        return cls(
            top_gainers_n=int(stock_selection.top_gainers_n),
            watchlist_limit_k=int(stock_selection.watchlist_limit_k),
            focus_limit_m=int(stock_selection.focus_limit_m),
            session_allowlist=tuple(stock_selection.session_allowlist),
        )
