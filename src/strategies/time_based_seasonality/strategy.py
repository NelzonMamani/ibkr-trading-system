"""Time-based Seasonality strategy adapter."""

from __future__ import annotations

from datetime import datetime
from typing import List

from src.config.runtime_config import RunMode
from src.models.data_models import PatternResult, TradeIntent
from src.strategy.base_strategy import BaseStrategy
from src.strategy.exit_signal import ExitSignal


class TimeBasedSeasonalityStrategy(BaseStrategy):
    name = "TimeBasedSeasonalityStrategy"
    trader_type = "QUANT"

    def evaluate(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
        return []

    def evaluate_exit_signals(self, active_trades: List, current_tick: int) -> List[ExitSignal]:
        return []

    @staticmethod
    def _extract_symbols(watchlist: List[object]) -> List[str]:
        symbols: List[str] = []
        for entry in watchlist:
            symbol = entry.get("symbol") if isinstance(entry, dict) else getattr(entry, "symbol", None)
            if symbol:
                symbols.append(str(symbol).upper())
        return sorted(set(symbols))

    @staticmethod
    def _bucket(timestamp_utc: str) -> int:
        dt = datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00"))
        minute_of_day = dt.hour * 60 + dt.minute
        return (minute_of_day // 30) % 8

    def process_watchlist(self, *, watchlist: List[object], snapshots: dict, session_label: str, timestamp_utc: str, mode: RunMode, session_phase: str) -> List[TradeIntent]:
        symbols = self._extract_symbols(watchlist)
        if not symbols:
            return []
        if mode in {RunMode.READ_ONLY, RunMode.LIVE}:
            return []

        bucket = self._bucket(timestamp_utc)
        if bucket not in {2, 3}:
            return []
        symbol = symbols[0]
        return [
            TradeIntent(
                symbol=symbol,
                direction="LONG",
                strategy_name=self.name,
                confidence=0.56,
                rationale=(
                    "reason_code=SEASONALITY_BUCKET_LONG; deterministic bucket "
                    f"{bucket}; mode={mode.value}"
                ),
                trader_type=self.trader_type,
            )
        ]
