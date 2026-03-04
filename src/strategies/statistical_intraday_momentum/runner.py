"""Runner wrapper for Statistical Intraday Momentum strategy."""

from __future__ import annotations

from src.strategies.statistical_intraday_momentum.strategy import StatisticalIntradayMomentum


class StatisticalIntradayMomentumRunner:
    def __init__(self) -> None:
        self.strategy = StatisticalIntradayMomentum()

    def run(self, context):
        intents = self.strategy.process_watchlist(
            watchlist=context.get("watchlist", []),
            snapshots=context.get("snapshots", {}),
            session_label=context.get("session_label"),
            timestamp_utc=context.get("timestamp_utc"),
            mode=context.get("mode"),
            session_phase=context.get("session_phase"),
        )
        return {"trade_intents": intents, "reports": []}
