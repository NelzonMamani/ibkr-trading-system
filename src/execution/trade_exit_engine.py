from dataclasses import dataclass
from typing import List, Tuple, Optional
from datetime import datetime

from config.runtime_config import RunMode, RuntimeConfig
from core.active_trade_registry import ActiveTradeRegistry
from models.data_models import ExecutionResult
from core.trade_outcome_factory import TradeOutcomeFactory
from domain.trade_outcome import TradeOutcome
from sim.price_feed import DeterministicPriceFeed
from strategy.exit_signal import ExitSignal


@dataclass
class ExitDecision:
    should_exit: bool
    reason: str
    rationale: str


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

    def decide_exit(
        self,
        trade,
        tick: int,
        current_price: float,
        strategy_exit_signal: bool,
        config: RuntimeConfig,
    ) -> ExitDecision:
        """
        Pure decision function to determine the highest-priority exit outcome.

        This method is intentionally side-effect free to enable deterministic
        validation of exit precedence without invoking registry or event paths.
        """

        entry_tick = getattr(trade, "entry_tick", tick)
        normalized_direction = (getattr(trade, "direction", "") or "").upper()
        stop_loss_price = getattr(trade, "stop_loss_price", None)
        take_profit_price = getattr(trade, "take_profit_price", None)
        hold_duration_ticks = tick - entry_tick

        if hold_duration_ticks >= config.max_hold_ticks:
            rationale = (
                "Exit condition met: maximum hold duration reached via TradeExitEngine "
                f"(held {hold_duration_ticks} ticks; max_hold_ticks={config.max_hold_ticks})"
            )
            return ExitDecision(True, "TIME_MAX", rationale)

        price_decision = self._evaluate_price_exit_decision(
            normalized_direction=normalized_direction,
            exit_price=current_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
        )
        if price_decision is not None:
            return price_decision

        if hold_duration_ticks < config.min_hold_ticks:
            rationale = (
                "Minimum hold duration not yet reached — strategy exits blocked "
                f"(held {hold_duration_ticks} ticks; min_hold_ticks={config.min_hold_ticks})"
            )
            return ExitDecision(False, "TIME_MIN_BLOCK", rationale)

        if strategy_exit_signal:
            return ExitDecision(
                True,
                "STRATEGY_SIGNAL",
                "Strategy exit request honoured by TradeExitEngine",
            )

        return ExitDecision(
            False,
            "HOLD",
            "No exit condition met — holding trade open.",
        )

    def evaluate_and_close_trades(
        self,
        run_mode: RunMode,
        tick: int,
        exit_signals: Optional[List[ExitSignal]] = None,
        config: Optional[RuntimeConfig] = None,
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
        runtime_config = config or RuntimeConfig()

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

            stop_loss_price = getattr(trade, "stop_loss_price", None)
            take_profit_price = getattr(trade, "take_profit_price", None)

            signals_for_trade = exit_signal_map.get((symbol, trader_type), [])
            selected_signal = next(
                (
                    signal
                    for signal in signals_for_trade
                    if signal.strategy_name == strategy_name
                ),
                signals_for_trade[0] if signals_for_trade else None,
            )

            decision = self.decide_exit(
                trade=trade,
                tick=exit_tick,
                current_price=exit_price,
                strategy_exit_signal=selected_signal is not None,
                config=runtime_config,
            )

            if not decision.should_exit:
                if decision.reason == "TIME_MIN_BLOCK":
                    print(
                        "[EXIT] Hold threshold not met — keeping trade open "
                        f"symbol={symbol} trader_type={trader_type} "
                        f"entry_tick={entry_tick} current_tick={exit_tick} "
                        f"min_hold_ticks={runtime_config.min_hold_ticks}"
                    )
                elif decision.reason == "HOLD":
                    print(
                        "[EXIT] No strategy exit request — keeping trade open "
                        f"symbol={symbol} trader_type={trader_type} "
                        f"entry_tick={entry_tick} current_tick={exit_tick} "
                        f"hold_ticks={hold_duration_ticks} "
                        f"max_hold_ticks={runtime_config.max_hold_ticks}"
                    )
                continue

            rationale: str
            if decision.reason == "STRATEGY_SIGNAL" and selected_signal is not None:
                rationale = (
                    "Strategy exit request honoured by TradeExitEngine: "
                    f"{selected_signal.reason} "
                    f"(requested_by={selected_signal.strategy_name}; "
                    f"hold_duration_ticks={hold_duration_ticks})"
                )
            else:
                rationale = decision.rationale

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
                    "min_hold_ticks": runtime_config.min_hold_ticks,
                    "max_hold_ticks": runtime_config.max_hold_ticks,
                    "pnl": realised_pnl,
                    "realised_pnl": realised_pnl,
                    "stop_loss_price": stop_loss_price,
                    "take_profit_price": take_profit_price,
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
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
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

    @staticmethod
    def _evaluate_price_exit_decision(
        normalized_direction: str,
        exit_price: float,
        stop_loss_price: Optional[float],
        take_profit_price: Optional[float],
    ) -> Optional[ExitDecision]:
        stop_loss_triggered = False
        take_profit_triggered = False

        if stop_loss_price is not None:
            if normalized_direction == "SHORT":
                stop_loss_triggered = exit_price >= stop_loss_price
            else:
                stop_loss_triggered = exit_price <= stop_loss_price

        if take_profit_price is not None:
            if normalized_direction == "SHORT":
                take_profit_triggered = exit_price <= take_profit_price
            else:
                take_profit_triggered = exit_price >= take_profit_price

        if stop_loss_triggered:
            rationale = (
                "Exit condition met: stop-loss price reached via TradeExitEngine "
                f"(direction={normalized_direction or 'UNKNOWN'} price={exit_price} "
                f"stop_loss_price={stop_loss_price})"
            )
            return ExitDecision(True, "PRICE_STOP", rationale)

        if take_profit_triggered:
            rationale = (
                "Exit condition met: take-profit price reached via TradeExitEngine "
                f"(direction={normalized_direction or 'UNKNOWN'} price={exit_price} "
                f"take_profit_price={take_profit_price})"
            )
            return ExitDecision(True, "PRICE_TP", rationale)

        return None

    def shutdown(self) -> None:
        """
        Idempotent shutdown placeholder for trade exit resources.

        Future implementations will include broker-driven cancel/flatten logic.
        """

        print("[TRADE_EXIT] Shutdown requested — placeholder cleanup complete.")
