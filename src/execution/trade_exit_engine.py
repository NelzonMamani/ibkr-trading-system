from typing import List, Tuple, Optional
from datetime import datetime

from core.active_trade_registry import ActiveTradeRegistry
from core.events import SystemEvent
from models.data_models import ExecutionResult
from core.trade_outcome_factory import TradeOutcomeFactory
from domain.trade_outcome import TradeOutcome
from sim.price_feed import DeterministicPriceFeed


class TradeExitEngine:
    """
    Teaching-first engine responsible for closing active trades explicitly.

    This engine exists to make trade lifecycle management visible,
    intentional, and extendable.
    """

    def __init__(
        self,
        trade_registry: ActiveTradeRegistry,
        event_collector,
        price_feed: Optional[DeterministicPriceFeed] = None,
    ):
        self.trade_registry = trade_registry
        self.event_collector = event_collector
        self.price_feed = price_feed or DeterministicPriceFeed()

    def evaluate_and_close_trades(
        self,
        run_mode: str,
        tick: int,
    ) -> Tuple[List[ExecutionResult], List[TradeOutcome]]:
        """
        Evaluate open trades and close them using simple teaching rules.

        Current teaching rule:
        - In SIM: do nothing (SIM auto-close already handled)
        - In LIVE / PAPER: close all trades after 1 tick
        """

        results: List[ExecutionResult] = []
        trade_outcomes: List[TradeOutcome] = []

        normalized_run_mode = (getattr(run_mode, "value", run_mode) or "").upper()
        if normalized_run_mode == "SIM":
            return results, trade_outcomes

        active_trades = self.trade_registry.snapshot()

        for trade in active_trades:
            symbol = getattr(trade, "symbol", None)
            trader_type = getattr(trade, "trader_type", "UNKNOWN")
            direction = getattr(trade, "direction", "UNKNOWN")
            quantity = getattr(trade, "quantity", 1)
            strategy_name = getattr(trade, "strategy_name", "UNKNOWN")
            entry_price = getattr(trade, "entry_price", 0.0)
            entry_tick = getattr(trade, "entry_tick", tick)
            exit_tick = tick

            if symbol is None:
                continue

            exit_price = self.price_feed.price_for(symbol, exit_tick)
            normalized_direction = (direction or "").upper()
            if normalized_direction == "SHORT":
                realised_pnl = (entry_price - exit_price) * quantity
            else:
                realised_pnl = (exit_price - entry_price) * quantity
            realised_pnl = round(realised_pnl, 2)

            self.trade_registry.unregister_trade(symbol, trader_type)

            self.event_collector.record(
                SystemEvent(
                    event_type="TRADE_CLOSED",
                    source="TradeExitEngine",
                    payload={
                        "symbol": symbol,
                        "trader_type": trader_type,
                        "strategy_name": strategy_name,
                        "tick": tick,
                        "reason": "Teaching exit after 1 tick",
                        "mode": normalized_run_mode,
                        "entry_tick": entry_tick,
                        "opened_at_tick": entry_tick,
                        "entry_price": entry_price,
                        "exit_tick": exit_tick,
                        "exit_price": exit_price,
                        "close_tick": exit_tick,
                        "close_price": exit_price,
                        "closed_at_tick": exit_tick,
                        "pnl": realised_pnl,
                        "realised_pnl": realised_pnl,
                    },
                    timestamp=datetime.utcnow(),
                )
            )

            closed_result = ExecutionResult(
                symbol=symbol,
                trader_type=trader_type,
                attempted=True,
                status="CLOSED",
                rationale="Teaching-only exit via TradeExitEngine",
                direction=direction,
                quantity=quantity,
                entry_price=entry_price,
                exit_price=exit_price,
                entry_tick=entry_tick,
                exit_tick=exit_tick,
            )
            results.append(closed_result)
            trade_outcomes.append(
                TradeOutcomeFactory.from_execution_result(
                    closed_result,
                    strategy_name=strategy_name,
                    trader_type=trader_type,
                )
            )

        return results, trade_outcomes
