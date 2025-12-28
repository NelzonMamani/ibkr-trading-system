from typing import List
from datetime import datetime

from core.active_trade_registry import ActiveTradeRegistry
from core.events import SystemEvent
from models.data_models import ExecutionResult


class TradeExitEngine:
    """
    Teaching-first engine responsible for closing active trades explicitly.

    This engine exists to make trade lifecycle management visible,
    intentional, and extendable.
    """

    def __init__(self, trade_registry: ActiveTradeRegistry, event_collector):
        self.trade_registry = trade_registry
        self.event_collector = event_collector

    def evaluate_and_close_trades(self, run_mode: str, tick: int) -> List[ExecutionResult]:
        """
        Evaluate open trades and close them using simple teaching rules.

        Current teaching rule:
        - In SIM: do nothing (SIM auto-close already handled)
        - In LIVE / PAPER: close all trades after 1 tick
        """

        results: List[ExecutionResult] = []

        normalized_run_mode = (getattr(run_mode, "value", run_mode) or "").upper()
        if normalized_run_mode == "SIM":
            return results

        active_trades = self.trade_registry.snapshot()

        for trade in active_trades:
            symbol = getattr(trade, "symbol", None)
            trader_type = getattr(trade, "trader_type", "UNKNOWN")

            if symbol is None:
                continue

            self.trade_registry.unregister_trade(symbol, trader_type)

            self.event_collector.record(
                SystemEvent(
                    event_type="TRADE_CLOSED",
                    source="TradeExitEngine",
                    payload={
                        "symbol": symbol,
                        "trader_type": trader_type,
                        "tick": tick,
                        "reason": "Teaching exit after 1 tick",
                        "mode": normalized_run_mode,
                    },
                    timestamp=datetime.utcnow(),
                )
            )

            results.append(
                ExecutionResult(
                    symbol=symbol,
                    trader_type=trader_type,
                    attempted=True,
                    status="CLOSED",
                    rationale="Teaching-only exit via TradeExitEngine",
                )
            )

        return results
