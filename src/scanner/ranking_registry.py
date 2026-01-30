from __future__ import annotations

from typing import Callable, Sequence

from src.scanner.result_models import CandidateMetrics
from src.strategies.ross_momentum.strategy_policy import select_watchlist

WatchlistSelector = Callable[[Sequence[CandidateMetrics], object], list[CandidateMetrics]]

_RANKING_REGISTRY: dict[str, WatchlistSelector] = {
    "ROSS_MOMENTUM_STOCK_SELECTION": select_watchlist,
}


def resolve_watchlist_selector(ranking_intent: str | None) -> WatchlistSelector | None:
    if not ranking_intent:
        return None
    return _RANKING_REGISTRY.get(ranking_intent)
