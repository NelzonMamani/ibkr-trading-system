"""Volatility Carry Risk Premium strategy adapter."""

from __future__ import annotations

from types import SimpleNamespace
from typing import List

from src.config.runtime_config import RunMode
from src.models.data_models import PatternResult, TradeIntent
from src.strategy.base_strategy import BaseStrategy
from src.strategy.exit_signal import ExitSignal


class VolatilityCarryRiskPremiumStrategy(BaseStrategy):
    name = "VolatilityCarryRiskPremiumStrategy"
    trader_type = "VOLATILITY"

    def evaluate(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
        return []

    def evaluate_exit_signals(self, active_trades: List, current_tick: int) -> List[ExitSignal]:
        return []

    @staticmethod
    def _candidate(entry: object) -> object:
        if isinstance(entry, dict):
            return SimpleNamespace(
                symbol=entry.get("symbol"),
                iv_rank=entry.get("iv_rank"),
                realized_vol=entry.get("realized_vol"),
                implied_vol=entry.get("implied_vol"),
            )
        return entry

    def process_watchlist(self, *, watchlist: List[object], snapshots: dict, session_label: str, timestamp_utc: str, mode: RunMode, session_phase: str) -> List[TradeIntent]:
        intents: List[TradeIntent] = []
        for entry in watchlist:
            candidate = self._candidate(entry)
            symbol = getattr(candidate, "symbol", None)
            if not symbol:
                continue
            iv_rank = float(getattr(candidate, "iv_rank", 0.0) or 0.0)
            realized_vol = float(getattr(candidate, "realized_vol", 1.0) or 1.0)
            implied_vol = float(getattr(candidate, "implied_vol", 0.0) or 0.0)
            if iv_rank >= 0.7 and implied_vol >= 1.2 * realized_vol:
                intents.append(
                    TradeIntent(
                        symbol=symbol,
                        direction="SHORT",
                        strategy_name=self.name,
                        confidence=0.7,
                        rationale="Implied volatility rich versus realized volatility for carry premium capture.",
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
                direction="SHORT",
                strategy_name=self.name,
                confidence=0.5,
                rationale="Deterministic fallback for volatility carry risk premium in SIM/PAPER.",
                trader_type=self.trader_type,
            )
        ]
