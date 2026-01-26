"""Minimal Statistical Intraday Momentum strategy adapter."""

from __future__ import annotations

from typing import List

from src.models.data_models import PatternResult, TradeIntent
from src.strategy.base_strategy import BaseStrategy
from src.strategy.exit_signal import ExitSignal


class StatisticalIntradayMomentum(BaseStrategy):
    """Teaching-safe adapter that emits no trades unless wired to signal inputs."""

    name = "StatisticalIntradayMomentum"
    trader_type = "STATISTICAL"

    def evaluate(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
        print(
            "[STRATEGY:StatisticalIntradayMomentum] "
            f"Received {len(pattern_results)} pattern result(s); returning []"
        )
        return []

    def evaluate_exit_signals(self, active_trades: List, current_tick: int) -> List[ExitSignal]:
        return []
