"""Pairs Divergence Reversion strategy adapter."""

from __future__ import annotations

from types import SimpleNamespace
from typing import List

from src.config.runtime_config import RunMode
from src.models.data_models import PatternResult, TradeIntent
from src.strategy.base_strategy import BaseStrategy
from src.strategy.exit_signal import ExitSignal


class PairsDivergenceReversionStrategy(BaseStrategy):
    name = "PairsDivergenceReversionStrategy"
    trader_type = "PAIRS"

    def evaluate(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
        return []

    def evaluate_exit_signals(self, active_trades: List, current_tick: int) -> List[ExitSignal]:
        return []

    @staticmethod
    def _candidate(entry: object) -> object:
        if isinstance(entry, dict):
            return SimpleNamespace(
                symbol=entry.get("symbol"),
                pair_symbol=entry.get("pair_symbol"),
                zscore=entry.get("zscore"),
                spread_reversion_signal=entry.get("spread_reversion_signal"),
            )
        return entry

    def process_watchlist(self, *, watchlist: List[object], snapshots: dict, session_label: str, timestamp_utc: str, mode: RunMode, session_phase: str) -> List[TradeIntent]:
        intents: List[TradeIntent] = []
        for entry in watchlist:
            candidate = self._candidate(entry)
            symbol = getattr(candidate, "symbol", None)
            if not symbol:
                continue
            zscore = float(getattr(candidate, "zscore", 0.0) or 0.0)
            reversion = bool(getattr(candidate, "spread_reversion_signal", False))
            if zscore <= -2.0 and reversion:
                intents.append(
                    TradeIntent(
                        symbol=symbol,
                        direction="LONG",
                        strategy_name=self.name,
                        confidence=0.73,
                        rationale="Pair spread divergence reached extreme and reverted toward mean.",
                        trader_type=self.trader_type,
                    )
                )
                break

        if intents:
            return intents[:1]
        if mode not in {RunMode.SIM, RunMode.PAPER}:
            return []

        symbol = None
        for entry in watchlist:
            symbol = entry.get("symbol") if isinstance(entry, dict) else getattr(entry, "symbol", None)
            if symbol:
                break
        if not symbol:
            return []
        return [
            TradeIntent(
                symbol=symbol,
                direction="LONG",
                strategy_name=self.name,
                confidence=0.5,
                rationale="Deterministic fallback for pairs divergence reversion in SIM/PAPER.",
                trader_type=self.trader_type,
            )
        ]
