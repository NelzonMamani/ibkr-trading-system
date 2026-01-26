"""
Statistical Intraday Momentum strategy plugin (wiring-only placeholder).
"""

from typing import List

from src.models.data_models import PatternResult, TradeIntent
from src.strategy.base_strategy import BaseStrategy


class StatisticalIntradayMomentumStrategy(BaseStrategy):
    name = "StatisticalIntradayMomentum"

    def evaluate(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
        print(
            "[STRATEGY:StatisticalIntradayMomentum] Wiring-only evaluation — "
            f"received {len(pattern_results)} pattern(s); no intents emitted."
        )
        return []
