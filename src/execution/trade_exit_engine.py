from typing import List, Tuple, Optional
from datetime import datetime

from config.runtime_config import RunMode
from config.trading_config import MAX_HOLD_TICKS, MIN_HOLD_TICKS
from core.active_trade_registry import ActiveTradeRegistry
from models.data_models import ExecutionResult
from core.trade_outcome_factory import TradeOutcomeFactory
from domain.trade_outcome import TradeOutcome
from sim.price_feed import DeterministicPriceFeed
from strategy.exit_signal import ExitSignal


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
        exit_signals: Optional[List[ExitSignal]] = None,
    ) -> Tuple[List[ExecutionResult], List[TradeOutcome]]:
        """
        Evaluate open trades and close them using the authoritative exit path.

        Rule: close only when explicit exit condition is met. ExecutionEngine
        opens trades; TradeExitEngine is the single closer. Strategy-driven
        exit_signals are advisory inputs; time-based exits still override
        everything.
        """

        results: List[ExecutionResult] = []
        trade_outcomes: List[TradeOutcome] = []
        exit_signal_map = {}
        for signal in exit_signals or []:
            key = (signal.symbol, signal.trader_type)
            exit_signal_map.setdefault(key, []).append(signal)

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

            hold_duration_ticks = exit_tick - entry_tick

            exit_price = self.price_feed.price_for(symbol, exit_tick)
            normalized_direction = (direction or "").upper()
            if normalized_direction == "SHORT":
                realised_pnl = (entry_price - exit_price) * quantity
            else:
                realised_pnl = (exit_price - entry_price) * quantity
            realised_pnl = round(realised_pnl, 2)

            rationale: Optional[str] = None

            if hold_duration_ticks < MIN_HOLD_TICKS:
                print(
                    "[EXIT] Hold threshold not met — keeping trade open "
                    f"symbol={symbol} trader_type={trader_type} "
                    f"entry_tick={entry_tick} current_tick={exit_tick} "
                    f"min_hold_ticks={MIN_HOLD_TICKS}"
                )
                continue

            if hold_duration_ticks >= MAX_HOLD_TICKS:
                rationale = (
                    "Exit condition met: maximum hold duration reached via TradeExitEngine "
                    f"(held {hold_duration_ticks} ticks; max_hold_ticks={MAX_HOLD_TICKS})"
                )
            else:
                signals_for_trade = exit_signal_map.get((symbol, trader_type), [])
                if not signals_for_trade:
                    print(
                        "[EXIT] No strategy exit request — keeping trade open "
                        f"symbol={symbol} trader_type={trader_type} "
                        f"entry_tick={entry_tick} current_tick={exit_tick} "
                        f"hold_ticks={hold_duration_ticks} "
                        f"max_hold_ticks={MAX_HOLD_TICKS}"
                    )
                    continue
                selected_signal = next(
                    (
                        signal
                        for signal in signals_for_trade
                        if signal.strategy_name == strategy_name
                    ),
                    signals_for_trade[0],
                )
                rationale = (
                    "Strategy exit request honoured by TradeExitEngine: "
                    f"{selected_signal.reason} "
                    f"(requested_by={selected_signal.strategy_name}; "
                    f"hold_duration_ticks={hold_duration_ticks})"
                )

            self.trade_registry.unregister_trade(symbol, trader_type)

            self.event_collector.emit(
                event_type="TRADE_CLOSED",
                source="TradeExitEngine",
                payload={
                    "symbol": symbol,
                    "trader_type": trader_type,
                    "strategy_name": strategy_name,
                    "tick": tick,
                    "reason": rationale,
                    "mode": normalized_run_mode,
                    "entry_tick": entry_tick,
                    "opened_at_tick": entry_tick,
                    "entry_price": entry_price,
                    "exit_tick": exit_tick,
                    "exit_price": exit_price,
                    "close_tick": exit_tick,
                    "close_price": exit_price,
                    "closed_at_tick": exit_tick,
                    "hold_duration_ticks": hold_duration_ticks,
                    "min_hold_ticks": MIN_HOLD_TICKS,
                    "max_hold_ticks": MAX_HOLD_TICKS,
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
                rationale=rationale,
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
