from dataclasses import dataclass
from typing import List, Tuple, Optional, Any
from datetime import datetime

from config.runtime_config import RunMode, RuntimeConfig
from core.active_trade_registry import ActiveTradeRegistry
from models.data_models import ExecutionResult
from core.trade_outcome_factory import TradeOutcomeFactory
from domain.trade_outcome import TradeOutcome
from sim.price_feed import DeterministicPriceFeed
from strategy.exit_signal import ExitSignal
from execution.slippage_model import SlippageModel


@dataclass
class ExitDecision:
    category: str
    reason: str
    exit_tick: int
    exit_price: float


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
        self._last_tick: Optional[int] = None
        self._last_runtime_config: Optional[RuntimeConfig] = None

    @staticmethod
    def _resolve_threshold(config: Any, attribute: str, fallback_attribute: str) -> int:
        value = getattr(config, attribute, None)
        if value is None:
            value = getattr(config, fallback_attribute, None)
        if value is None:
            raise ValueError(f"Missing required configuration attribute {attribute}")
        return int(value)

    def decide_exit(
        self,
        trade,
        current_tick: int,
        current_price: float,
        strategy_exit_signal: bool,
        config,
    ) -> Optional[ExitDecision]:
        """
        Pure decision function to determine the highest-priority exit outcome.

        This method is intentionally side-effect free to enable deterministic
        validation of exit precedence without invoking registry or event paths.
        """

        entry_tick = getattr(trade, "entry_tick", current_tick)
        normalized_direction = (getattr(trade, "direction", "") or "").upper()
        stop_loss_price = getattr(trade, "stop_loss_price", None)
        take_profit_price = getattr(trade, "take_profit_price", None)
        hold_duration_ticks = (
            trade.hold_duration(current_tick)
            if hasattr(trade, "hold_duration")
            else max(0, current_tick - entry_tick)
        )

        max_hold_ticks = self._resolve_threshold(config, "MAX_HOLD_TICKS", "max_hold_ticks")
        min_hold_ticks = self._resolve_threshold(config, "MIN_HOLD_TICKS", "min_hold_ticks")

        if hold_duration_ticks >= max_hold_ticks:
            return ExitDecision(
                category="TIME_MAX",
                reason="Max hold duration reached",
                exit_tick=current_tick,
                exit_price=current_price,
            )

        price_decision = self._evaluate_price_exit_decision(
            normalized_direction=normalized_direction,
            exit_price=current_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            exit_tick=current_tick,
        )
        if price_decision is not None:
            return price_decision

        if hold_duration_ticks < min_hold_ticks:
            return None

        if strategy_exit_signal:
            return ExitDecision(
                category="STRATEGY_SIGNAL",
                reason="Strategy requested exit",
                exit_tick=current_tick,
                exit_price=current_price,
            )

        return None

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
        self._last_tick = tick
        self._last_runtime_config = runtime_config

        normalized_run_mode = (getattr(run_mode, "value", run_mode) or "").upper()
        active_trades = self.trade_registry.snapshot()

        max_hold_ticks = self._resolve_threshold(runtime_config, "MAX_HOLD_TICKS", "max_hold_ticks")
        min_hold_ticks = self._resolve_threshold(runtime_config, "MIN_HOLD_TICKS", "min_hold_ticks")

        for trade in active_trades:
            symbol = getattr(trade, "symbol", None)
            if symbol is None:
                continue
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

            raw_exit_price = self.price_feed.price_for(symbol, exit_tick)
            exit_price = SlippageModel.apply_slippage(
                price=raw_exit_price,
                direction=direction,
                trader_type=trader_type,
                quantity=-quantity,
            )
            slippage_applied = round(exit_price - raw_exit_price, 2)
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
                current_tick=exit_tick,
                current_price=exit_price,
                strategy_exit_signal=selected_signal is not None,
                config=runtime_config,
            )

            if decision is None:
                if hold_duration_ticks < min_hold_ticks:
                    print(
                        "[EXIT] Hold threshold not met — keeping trade open "
                        f"symbol={symbol} trader_type={trader_type} "
                        f"entry_tick={entry_tick} current_tick={exit_tick} "
                        f"min_hold_ticks={min_hold_ticks}"
                    )
                else:
                    print(
                        "[EXIT] No exit condition met — keeping trade open "
                        f"symbol={symbol} trader_type={trader_type} "
                        f"entry_tick={entry_tick} current_tick={exit_tick} "
                        f"hold_ticks={hold_duration_ticks} "
                        f"max_hold_ticks={max_hold_ticks}"
                    )
                continue

            rationale: str
            if decision.category == "TIME_MAX":
                rationale = (
                    "Exit condition met: maximum hold duration reached via TradeExitEngine "
                    f"(held {hold_duration_ticks} ticks; max_hold_ticks={max_hold_ticks})"
                )
            elif decision.category == "PRICE_STOP":
                rationale = (
                    "Exit condition met: stop-loss price reached via TradeExitEngine "
                    f"(direction={normalized_direction or 'UNKNOWN'} price={exit_price} "
                    f"stop_loss_price={stop_loss_price})"
                )
            elif decision.category == "PRICE_TP":
                rationale = (
                    "Exit condition met: take-profit price reached via TradeExitEngine "
                    f"(direction={normalized_direction or 'UNKNOWN'} price={exit_price} "
                    f"take_profit_price={take_profit_price})"
                )
            elif decision.category == "STRATEGY_SIGNAL" and selected_signal is not None:
                rationale = (
                    "Strategy exit request honoured by TradeExitEngine: "
                    f"{selected_signal.reason} "
                    f"(requested_by={selected_signal.strategy_name}; "
                    f"hold_duration_ticks={hold_duration_ticks})"
                )
            else:
                rationale = decision.reason

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
                    "raw_price": raw_exit_price,
                    "slippage_applied": slippage_applied,
                    "execution_price": exit_price,
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
                raw_price=raw_exit_price,
                slippage_applied=slippage_applied,
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
        exit_tick: int,
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
            return ExitDecision(
                category="PRICE_STOP",
                reason="Stop loss breached",
                exit_tick=exit_tick,
                exit_price=exit_price,
            )

        if take_profit_triggered:
            return ExitDecision(
                category="PRICE_TP",
                reason="Take profit reached",
                exit_tick=exit_tick,
                exit_price=exit_price,
            )

        return None

    def _force_close_all_trades(self, resolved_tick: int, runtime_config: RuntimeConfig) -> None:
        active_trades = self.trade_registry.snapshot()
        if not active_trades:
            print("[TRADE_EXIT] No active trades to close during shutdown.")
            return

        print(f"[TRADE_EXIT] Force-closing {len(active_trades)} trade(s) during shutdown.")
        normalized_run_mode = "UNKNOWN"
        for trade in active_trades:
            symbol = getattr(trade, "symbol", None)
            trader_type = getattr(trade, "trader_type", "UNKNOWN")
            direction = getattr(trade, "direction", "UNKNOWN")
            quantity = getattr(trade, "quantity", 1)
            strategy_name = getattr(trade, "strategy_name", "UNKNOWN")
            entry_price = getattr(trade, "entry_price", 0.0)
            entry_tick = getattr(trade, "entry_tick", resolved_tick)
            raw_exit_price = self.price_feed.price_for(symbol, resolved_tick)
            exit_price = SlippageModel.apply_slippage(
                price=raw_exit_price,
                direction=direction,
                trader_type=trader_type,
                quantity=-quantity,
            )
            slippage_applied = round(exit_price - raw_exit_price, 2)
            normalized_direction = (direction or "").upper()
            if normalized_direction == "SHORT":
                realised_pnl = (entry_price - exit_price) * quantity
            else:
                realised_pnl = (exit_price - entry_price) * quantity
            realised_pnl = round(realised_pnl, 2)

            stop_loss_price = getattr(trade, "stop_loss_price", None)
            take_profit_price = getattr(trade, "take_profit_price", None)
            hold_duration_ticks = (
                trade.hold_duration(resolved_tick)
                if hasattr(trade, "hold_duration")
                else max(0, resolved_tick - entry_tick)
            )

            self.trade_registry.unregister_trade(symbol, trader_type)
            rationale = (
                "Forced shutdown exit executed by TradeExitEngine "
                f"(held {hold_duration_ticks} ticks; "
                f"min_hold_ticks={self._resolve_threshold(runtime_config, 'MIN_HOLD_TICKS', 'min_hold_ticks')} "
                f"max_hold_ticks={self._resolve_threshold(runtime_config, 'MAX_HOLD_TICKS', 'max_hold_ticks')})"
            )
            self.event_collector.emit(
                event_type="TRADE_CLOSED",
                source="TradeExitEngine",
                payload={
                    "symbol": symbol,
                    "trader_type": trader_type,
                    "strategy_name": strategy_name,
                    "tick": resolved_tick,
                    "reason": rationale,
                    "mode": normalized_run_mode,
                    "entry_tick": entry_tick,
                    "opened_at_tick": entry_tick,
                    "entry_price": entry_price,
                    "exit_tick": resolved_tick,
                    "exit_price": exit_price,
                    "raw_price": raw_exit_price,
                    "slippage_applied": slippage_applied,
                    "execution_price": exit_price,
                    "close_tick": resolved_tick,
                    "close_price": exit_price,
                    "closed_at_tick": resolved_tick,
                    "hold_duration_ticks": hold_duration_ticks,
                    "min_hold_ticks": self._resolve_threshold(runtime_config, "MIN_HOLD_TICKS", "min_hold_ticks"),
                    "max_hold_ticks": self._resolve_threshold(runtime_config, "MAX_HOLD_TICKS", "max_hold_ticks"),
                    "pnl": realised_pnl,
                    "realised_pnl": realised_pnl,
                    "stop_loss_price": stop_loss_price,
                    "take_profit_price": take_profit_price,
                },
                timestamp=datetime.utcnow(),
            )

    def shutdown(self, current_tick: Optional[int] = None) -> None:
        """
        Guaranteed shutdown cleanup for trade exit resources.
        """

        runtime_config = self._last_runtime_config or RuntimeConfig()
        resolved_tick = current_tick if current_tick is not None else (self._last_tick or 0)
        self._force_close_all_trades(resolved_tick, runtime_config)
        print("[TRADE_EXIT] Shutdown completed — all trades force-closed.")
