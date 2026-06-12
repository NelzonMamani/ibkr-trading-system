"""Ross RVOL policy section."""

from __future__ import annotations

from dataclasses import dataclass

from src.strategies.ross_momentum.strategy_policy import StockSelectionSpec


@dataclass(frozen=True)
class RvolPolicy:
    minimum: float
    watchlist_min: float
    focus_min: float
    session_watchlist_min: dict[str, float]
    session_focus_min: dict[str, float]

    @classmethod
    def from_stock_selection(cls, stock_selection: StockSelectionSpec) -> "RvolPolicy":
        return cls(
            minimum=float(stock_selection.rvol_min),
            watchlist_min=float(stock_selection.watchlist_rvol_min),
            focus_min=float(stock_selection.focus_rvol_min),
            session_watchlist_min=dict(stock_selection.session_watchlist_rvol_min),
            session_focus_min=dict(stock_selection.session_focus_rvol_min),
        )
