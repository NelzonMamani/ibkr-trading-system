"""Long Horizon Quality Compounder strategy adapter."""

from __future__ import annotations

import hashlib
from typing import List

from src.config.runtime_config import RunMode
from src.models.data_models import PatternResult, TradeIntent
from src.strategy.base_strategy import BaseStrategy
from src.strategy.exit_signal import ExitSignal


class LongHorizonQualityCompounderStrategy(BaseStrategy):
    name = "LongHorizonQualityCompounderStrategy"
    trader_type = "INVESTMENT"

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
    def _quality(symbol: str) -> float:
        raw = int(hashlib.sha256(symbol.encode("utf-8")).hexdigest()[:8], 16)
        return raw / 0xFFFFFFFF

    def process_watchlist(self, *, watchlist: List[object], snapshots: dict, session_label: str, timestamp_utc: str, mode: RunMode, session_phase: str) -> List[TradeIntent]:
        symbols = self._extract_symbols(watchlist)
        if not symbols:
            return []
        if mode in {RunMode.READ_ONLY, RunMode.LIVE}:
            return []

        for symbol in symbols:
            quality = self._quality(symbol)
            if quality >= 0.80:
                return [
                    TradeIntent(
                        symbol=symbol,
                        direction="LONG",
                        strategy_name=self.name,
                        confidence=0.60,
                        rationale=(
                            "reason_code=QUALITY_COMPOUNDER_LONG; deterministic "
                            f"quality={quality:.3f}; horizon=LONG_HORIZON; mode={mode.value}"
                        ),
                        trader_type=self.trader_type,
                    )
                ]
        return []
