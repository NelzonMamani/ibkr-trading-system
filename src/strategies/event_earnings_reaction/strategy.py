"""Event Earnings Reaction strategy adapter."""

from __future__ import annotations

from types import SimpleNamespace
from typing import List

from src.config.runtime_config import RunMode
from src.models.data_models import PatternResult, TradeIntent
from src.strategy.base_strategy import BaseStrategy
from src.strategy.exit_signal import ExitSignal


class EventEarningsReactionStrategy(BaseStrategy):
    name = "EventEarningsReactionStrategy"
    trader_type = "EVENT"

    def evaluate(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
        return []

    def evaluate_exit_signals(self, active_trades: List, current_tick: int) -> List[ExitSignal]:
        return []

    @staticmethod
    def _candidate(entry: object) -> object:
        if isinstance(entry, dict):
            return SimpleNamespace(
                symbol=entry.get("symbol"),
                earnings_surprise=entry.get("earnings_surprise"),
                gap_pct=entry.get("gap_pct"),
                relative_volume=entry.get("relative_volume") or entry.get("rvol"),
            )
        return entry

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
        intents: List[TradeIntent] = []
        for entry in watchlist:
            candidate = self._candidate(entry)
            symbol = getattr(candidate, "symbol", None)
            if not symbol:
                continue
            surprise = float(getattr(candidate, "earnings_surprise", 0.0) or 0.0)
            gap_pct = float(getattr(candidate, "gap_pct", 0.0) or 0.0)
            rvol = float(getattr(candidate, "relative_volume", 0.0) or 0.0)
            has_signal = surprise >= 0.05 and gap_pct >= 2.0 and rvol >= 1.5
            if has_signal:
                intents.append(
                    TradeIntent(
                        symbol=symbol,
                        direction="LONG",
                        strategy_name=self.name,
                        confidence=0.74,
                        rationale="Post-earnings upside surprise with gap and volume confirmation.",
                        trader_type=self.trader_type,
                    )
                )
                break

        if intents:
            return intents[:1]
        if mode not in {RunMode.SIM, RunMode.PAPER}:
            return []

        fallback_symbol = None
        for entry in watchlist:
            fallback_symbol = entry.get("symbol") if isinstance(entry, dict) else getattr(entry, "symbol", None)
            if fallback_symbol:
                break
        if not fallback_symbol:
            return []
        return [
            TradeIntent(
                symbol=fallback_symbol,
                direction="LONG",
                strategy_name=self.name,
                confidence=0.51,
                rationale="Deterministic fallback for event earnings reaction in SIM/PAPER.",
                trader_type=self.trader_type,
            )
        ]
