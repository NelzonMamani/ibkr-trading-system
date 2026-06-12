"""Ross stock selection policy compatibility surface."""

from __future__ import annotations

from src.strategies.ross_momentum.strategy_policy import (
    RossMomentumPolicy,
    RossStockSelectionPolicy,
    StockSelectionSpec,
    select_watchlist,
    stock_selection_policy_for_session_phase,
)

__all__ = [
    "RossMomentumPolicy",
    "RossStockSelectionPolicy",
    "StockSelectionSpec",
    "select_watchlist",
    "stock_selection_policy_for_session_phase",
]
