"""Long Horizon Value strategy adapter for StrategyRunner."""

from __future__ import annotations

from typing import List

from src.config.runtime_config import RunMode
from src.models.data_models import PatternResult, TradeIntent
from src.strategy.base_strategy import BaseStrategy
from src.strategies.long_horizon_value.runner import LongHorizonValueRunner


class LongHorizonValueStrategy(BaseStrategy):
    """Adapter that runs the long-horizon pipeline in watchlist cycles."""

    name = "LongHorizonValue"
    trader_type = "VALUE"

    def __init__(self) -> None:
        self._runner = LongHorizonValueRunner()

    def evaluate(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
        print(
            "[STRATEGY:LongHorizonValue] "
            f"Received {len(pattern_results)} pattern result(s); returning []."
        )
        return []

    def process_watchlist(
        self,
        *,
        watchlist: List[object],
        snapshots: dict,
        session_label: str,
        timestamp_utc: str,
        mode: RunMode,
        session_phase: str,
    ) -> List[TradeIntent]:
        context = {
            "watchlist_symbols": [
                getattr(entry, "symbol", None) for entry in watchlist if getattr(entry, "symbol", None)
            ],
            "price_snapshots": snapshots,
            "session_label": session_label,
            "session_phase": session_phase,
            "timestamp_utc": timestamp_utc,
            "mode": mode,
        }
        output = self._runner.run(context)
        intents = output.get("trade_intents", [])
        print(
            "[LHV][SUMMARY] "
            f"reports={len(output.get('reports', []))} intents={len(intents)}"
        )
        return intents
