"""Long Horizon Value strategy adapter for StrategyRunner."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from src.config.runtime_config import RunMode
from src.models.data_models import PatternResult, TradeIntent
from src.strategy.base_strategy import BaseStrategy
from src.strategy.exit_signal import ExitSignal
from src.strategies.long_horizon_value.runner import LongHorizonValueRunner


class LongHorizonValueStrategy(BaseStrategy):
    name = "LongHorizonValueStrategy"
    trader_type = "LONG_HORIZON_VALUE"

    def __init__(self) -> None:
        self._runner = LongHorizonValueRunner()

    def evaluate(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
        return []

    def evaluate_exit_signals(self, active_trades: List, current_tick: int) -> List[ExitSignal]:
        return []

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
        now = timestamp_utc or datetime.now(timezone.utc).isoformat()
        print(
            "[LHV][CYCLE] "
            f"timestamp={now} mode={mode.value} session={session_label} phase={session_phase} "
            f"watchlist={len(watchlist)}"
        )
        result = self._runner.run(
            {
                "watchlist": watchlist,
                "snapshots": snapshots,
                "session_label": session_label,
                "timestamp_utc": now,
                "mode": mode.value,
                "session_phase": session_phase,
            }
        )
        intents = list(result.get("trade_intents", []))
        reports = list(result.get("reports", []))
        print(
            "[LHV][SUMMARY] "
            f"reports={len(reports)} intents={len(intents)} execution_allowed={mode == RunMode.LIVE}"
        )
        return intents
