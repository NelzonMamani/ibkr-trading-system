"""Opening Drive strategy adapter for StrategyRunner."""

from __future__ import annotations

from typing import List

from src.config.runtime_config import RunMode
from src.models.data_models import PatternResult, TradeIntent
from src.strategy.base_strategy import BaseStrategy
from src.strategy.exit_signal import ExitSignal
from src.strategies.common.deterministic_watchlist_strategy import (
    DeterministicPolicy,
    build_deterministic_watchlist_intents,
)
from src.strategies.opening_drive.strategy_policy import POLICY


class OpeningDriveStrategy(BaseStrategy):
    name = "OpeningDriveStrategy"
    trader_type = "SCALPER"

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
        policy = DeterministicPolicy(
            strategy_name=POLICY.name,
            strategy_label=POLICY.display_name,
            trader_type=POLICY.trader_type,
            allowed_sessions=POLICY.allowed_sessions,
            allowed_modes_for_intents=POLICY.allowed_modes_for_intents,
            min_price=POLICY.min_price,
            min_volume=POLICY.min_volume,
            max_intents_per_cycle=POLICY.max_intents_per_cycle,
        )
        return build_deterministic_watchlist_intents(
            policy=policy,
            watchlist=watchlist,
            snapshots=snapshots,
            mode=mode,
            session_label=session_label,
            timestamp_utc=timestamp_utc,
        )
