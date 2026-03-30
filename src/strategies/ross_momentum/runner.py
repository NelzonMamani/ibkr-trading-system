"""Runner wrapper for Ross Momentum strategy."""

from __future__ import annotations

from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


class RossMomentumRunner:
    def __init__(self) -> None:
        self.strategy = RossMomentumStrategyV1()

    def run(self, context):
        intents = self.strategy.process_watchlist(
            watchlist=context.get("watchlist", []),
            snapshots=context.get("snapshots", {}),
            session_label=context.get("session_label"),
            timestamp_utc=context.get("timestamp_utc"),
            mode=context.get("mode"),
            session_phase=context.get("session_phase"),
            focus_diagnostics=context.get("focus_diagnostics", {}),
        )
        trade_ready_count = sum(
            1
            for intent in intents
            if str(getattr(intent, "decision", "TRADE_READY")).upper() == "TRADE_READY"
        )
        return {
            "trade_intents": intents,
            "trade_ready_count": trade_ready_count,
            "reports": [],
        }
