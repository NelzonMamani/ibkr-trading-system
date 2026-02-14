"""Event News Shock Continuation strategy adapter."""

from __future__ import annotations

from types import SimpleNamespace
from typing import List

from src.config.runtime_config import RunMode
from src.models.data_models import PatternResult, TradeIntent
from src.strategy.base_strategy import BaseStrategy
from src.strategy.exit_signal import ExitSignal


class EventNewsShockContinuationStrategy(BaseStrategy):
    name = "EventNewsShockContinuationStrategy"
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
                news_score=entry.get("news_score"),
                pct_change=entry.get("pct_change"),
                relative_volume=entry.get("relative_volume") or entry.get("rvol"),
            )
        return entry

    def process_watchlist(self, *, watchlist: List[object], snapshots: dict, session_label: str, timestamp_utc: str, mode: RunMode, session_phase: str) -> List[TradeIntent]:
        intents: List[TradeIntent] = []
        for entry in watchlist:
            candidate = self._candidate(entry)
            symbol = getattr(candidate, "symbol", None)
            if not symbol:
                continue
            news_score = float(getattr(candidate, "news_score", 0.0) or 0.0)
            pct_change = float(getattr(candidate, "pct_change", 0.0) or 0.0)
            rvol = float(getattr(candidate, "relative_volume", 0.0) or 0.0)
            if news_score >= 0.7 and pct_change >= 3.0 and rvol >= 1.8:
                intents.append(
                    TradeIntent(
                        symbol=symbol,
                        direction="LONG",
                        strategy_name=self.name,
                        confidence=0.76,
                        rationale="News shock continuation confirmed by price and relative volume.",
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
                rationale="Deterministic fallback for event news shock continuation in SIM/PAPER.",
                trader_type=self.trader_type,
            )
        ]
