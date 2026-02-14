"""Cross-sectional Relative Strength Rotation strategy adapter."""

from __future__ import annotations

import hashlib
import random
import statistics
from typing import List

from src.config.runtime_config import RunMode
from src.models.data_models import PatternResult, TradeIntent
from src.strategy.base_strategy import BaseStrategy
from src.strategy.exit_signal import ExitSignal


class CrossSectionalRelativeStrengthRotationStrategy(BaseStrategy):
    name = "CrossSectionalRelativeStrengthRotationStrategy"
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
    def _stable_seed(text: str) -> int:
        return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)

    def _relative_strength_score(self, symbol: str) -> float:
        rng = random.Random(self._stable_seed(f"{self.name}:{symbol}"))
        returns = [rng.uniform(-0.03, 0.03) for _ in range(20)]
        mean_return = statistics.fmean(returns)
        stdev = statistics.pstdev(returns) + 1e-6
        return mean_return / stdev

    def process_watchlist(self, *, watchlist: List[object], snapshots: dict, session_label: str, timestamp_utc: str, mode: RunMode, session_phase: str) -> List[TradeIntent]:
        symbols = self._extract_symbols(watchlist)
        if not symbols:
            return []

        if mode in {RunMode.READ_ONLY, RunMode.LIVE}:
            return []

        scored = sorted(
            ((symbol, self._relative_strength_score(symbol)) for symbol in symbols),
            key=lambda item: item[1],
            reverse=True,
        )
        picks = [(symbol, score) for symbol, score in scored[:2] if score > 0.10]
        intents: List[TradeIntent] = []
        for symbol, score in picks:
            intents.append(
                TradeIntent(
                    symbol=symbol,
                    direction="LONG",
                    strategy_name=self.name,
                    confidence=min(0.95, 0.50 + max(0.0, score) / 6.0),
                    rationale=(
                        "reason_code=RS_ROTATION_LONG; deterministic relative-strength "
                        f"score={score:.3f}; mode={mode.value}"
                    ),
                    trader_type=self.trader_type,
                )
            )
        return intents[:2]
