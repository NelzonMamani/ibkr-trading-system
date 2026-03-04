"""Runner wrapper for Mean Reversion strategy."""

from __future__ import annotations

from src.strategies.mean_reversion.strategy import MeanReversionStrategy


class MeanReversionRunner:
    def __init__(self) -> None:
        self.strategy = MeanReversionStrategy()

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
