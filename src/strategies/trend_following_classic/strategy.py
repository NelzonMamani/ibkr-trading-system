"""Trend Following Classic strategy adapter."""

from __future__ import annotations

import hashlib
import random
import statistics
from typing import List

from src.config.runtime_config import RunMode
from src.models.data_models import PatternResult, TradeIntent
from src.strategy.base_strategy import BaseStrategy
from src.strategy.exit_signal import ExitSignal


class TrendFollowingClassicStrategy(BaseStrategy):
    name = "TrendFollowingClassicStrategy"
    trader_type = "MOMENTUM"

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
    def _stable_seed(text: str) -> int:
        return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)

    def _series(self, symbol: str) -> List[float]:
        rng = random.Random(self._stable_seed(f"{self.name}:{symbol}"))
        price = 100.0
        series = [price]
        for _ in range(49):
            price *= 1.0 + rng.uniform(-0.015, 0.02)
            series.append(price)
        return series

    @staticmethod
    def _sma(values: List[float]) -> tuple[float, float]:
        fast = statistics.fmean(values[-10:])
        slow = statistics.fmean(values[-30:])
        return fast, slow

    def process_watchlist(self, *, watchlist: List[object], snapshots: dict, session_label: str, timestamp_utc: str, mode: RunMode, session_phase: str) -> List[TradeIntent]:
        symbols = self._extract_symbols(watchlist)
        if not symbols:
            return []
        if mode in {RunMode.READ_ONLY, RunMode.LIVE}:
            return []

        for symbol in symbols:
            series = self._series(symbol)
            fast, slow = self._sma(series)
            if fast > slow:
                return [
                    TradeIntent(
                        symbol=symbol,
                        direction="LONG",
                        strategy_name=self.name,
                        confidence=0.58,
                        rationale=(
                            "reason_code=TREND_SMA_CROSS_LONG; deterministic "
                            f"fast={fast:.2f}>slow={slow:.2f}; mode={mode.value}"
                        ),
                        trader_type=self.trader_type,
                    )
                ]
        return []
