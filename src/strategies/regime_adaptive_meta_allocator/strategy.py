"""Regime Adaptive Meta Allocator strategy adapter."""

from __future__ import annotations

import hashlib
import random
import statistics
from typing import List

from src.config.runtime_config import RunMode
from src.models.data_models import PatternResult, TradeIntent
from src.strategy.base_strategy import BaseStrategy
from src.strategy.exit_signal import ExitSignal


class RegimeAdaptiveMetaAllocatorStrategy(BaseStrategy):
    name = "RegimeAdaptiveMetaAllocatorStrategy"
    trader_type = "META"

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
        return [rng.uniform(-0.025, 0.025) for _ in range(20)]

    def _strength(self, symbol: str) -> float:
        series = self._series(symbol)
        return statistics.fmean(series) / (statistics.pstdev(series) + 1e-6)

    def _volatility(self, symbol: str) -> float:
        return statistics.pstdev(self._series(symbol))

    def _regime(self, cycle_key: str) -> str:
        regime_idx = self._stable_seed(cycle_key) % 3
        return ["RISK_ON", "RISK_OFF", "NEUTRAL"][regime_idx]

    def process_watchlist(self, *, watchlist: List[object], snapshots: dict, session_label: str, timestamp_utc: str, mode: RunMode, session_phase: str) -> List[TradeIntent]:
        symbols = self._extract_symbols(watchlist)
        if not symbols:
            return []
        if mode in {RunMode.READ_ONLY, RunMode.LIVE}:
            return []

        regime = self._regime(f"{session_label}|{timestamp_utc}|{session_phase}")
        if regime == "NEUTRAL":
            return []
        if regime == "RISK_ON":
            symbol = max(symbols, key=self._strength)
            reason = "reason_code=META_ALLOCATOR_RISK_ON"
        else:
            symbol = min(symbols, key=self._volatility)
            reason = "reason_code=META_ALLOCATOR_RISK_OFF"

        return [
            TradeIntent(
                symbol=symbol,
                direction="LONG",
                strategy_name=self.name,
                confidence=0.57,
                rationale=f"{reason}; regime={regime}; mode={mode.value}",
                trader_type=self.trader_type,
            )
        ]
