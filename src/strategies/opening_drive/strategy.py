"""Opening Drive strategy adapter."""

from __future__ import annotations

import hashlib
from datetime import datetime
from types import SimpleNamespace
from typing import List

from src.config.runtime_config import RunMode
from src.models.data_models import PatternResult, TradeIntent
from src.strategy.base_strategy import BaseStrategy
from src.strategy.exit_signal import ExitSignal


class OpeningDriveStrategy(BaseStrategy):
    name = "OpeningDriveStrategy"
    trader_type = "OPENING_DRIVE"

    def evaluate(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
        return []

    def evaluate_exit_signals(self, active_trades: List, current_tick: int) -> List[ExitSignal]:
        return []

    @staticmethod
    def _candidate(entry: object) -> object:
        if isinstance(entry, dict):
            return SimpleNamespace(symbol=entry.get("symbol"))
        return entry

    @staticmethod
    def _score(seed: str, *, scale: int = 10_000) -> float:
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        return (int(digest[:8], 16) % scale) / scale

    @staticmethod
    def _parse_hour(timestamp_utc: str) -> int:
        normalized = timestamp_utc.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized).hour
        except ValueError:
            return -1

    def _first_symbol(self, watchlist: List[object]) -> str | None:
        for entry in watchlist:
            symbol = getattr(self._candidate(entry), "symbol", None)
            if symbol:
                return str(symbol)
        return None

    def process_watchlist(self, *, watchlist: List[object], snapshots: dict, session_label: str, timestamp_utc: str, mode: RunMode, session_phase: str) -> List[TradeIntent]:
        del snapshots, session_label
        if mode in {RunMode.READ_ONLY, RunMode.LIVE}:
            return []
        symbol = self._first_symbol(watchlist)
        if not symbol:
            return []
        if not self._qualifies(symbol=symbol, timestamp_utc=timestamp_utc, session_phase=session_phase):
            return []
        confidence = 0.55 + self._score(f"{self.name}:{symbol}:{timestamp_utc}", scale=1000) * 0.2
        return [
            TradeIntent(
                symbol=symbol,
                direction="LONG",
                strategy_name=self.name,
                confidence=round(confidence, 4),
                rationale="Opening drive conditions met: open-session phase and deterministic timestamp bucket.",
                trader_type=self.trader_type,
            )
        ]

    def _qualifies(self, *, symbol: str, timestamp_utc: str, session_phase: str) -> bool:
        normalized_phase = str(session_phase or "").upper()
        if normalized_phase not in {"OPEN", "MORNING"}:
            return False
        bucket = self._score(f"opening-drive:{timestamp_utc}", scale=100)
        return bucket >= 0.35
