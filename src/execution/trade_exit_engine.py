from typing import List, Tuple, Optional
from datetime import datetime

from config.runtime_config import RunMode
from config.trading_config import MIN_HOLD_TICKS
from core.active_trade_registry import ActiveTradeRegistry
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
        run_mode: RunMode,
        tick: int,
    ) -> Tuple[List[ExecutionResult], List[TradeOutcome]]:
        """
        Evaluate open trades and close them using the authoritative exit path.

        Rule: close only when explicit exit condition is met. ExecutionEngine
        opens trades; TradeExitEngine is the single closer.
        """

        results: List[ExecutionResult] = []
        trade_outcomes: List[TradeOutcome] = []

        normalized_run_mode = (getattr(run_mode, "value", run_mode) or "").upper()
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

            if (exit_tick - entry_tick) < MIN_HOLD_TICKS:
                print(
                    "[EXIT] Hold threshold not met — keeping trade open "
                    f"symbol={symbol} trader_type={trader_type} "
                    f"entry_tick={entry_tick} current_tick={exit_tick} "
                    f"min_hold_ticks={MIN_HOLD_TICKS}"
                )
                continue

            exit_price = self.price_feed.price_for(symbol, exit_tick)
            normalized_direction = (direction or "").upper()
            if normalized_direction == "SHORT":
                realised_pnl = (entry_price - exit_price) * quantity
            else:
                realised_pnl = (exit_price - entry_price) * quantity
            realised_pnl = round(realised_pnl, 2)

            self.trade_registry.unregister_trade(symbol, trader_type)

            self.event_collector.emit(
                event_type="TRADE_CLOSED",
                source="TradeExitEngine",
                payload={
                    "symbol": symbol,
                    "trader_type": trader_type,
                    "strategy_name": strategy_name,
                    "tick": tick,
                    "reason": f"Exit condition met: held for {exit_tick - entry_tick} ticks",
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

            closed_result = ExecutionResult(
                symbol=symbol,
                trader_type=trader_type,
                attempted=True,
                status="CLOSED",
                rationale=(
                    "Exit condition met: minimum hold duration satisfied via TradeExitEngine"
                ),
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

    def shutdown(self) -> None:
        """
        Idempotent shutdown placeholder for trade exit resources.

        Future implementations will include broker-driven cancel/flatten logic.
        """

        print("[TRADE_EXIT] Shutdown requested — placeholder cleanup complete.")
