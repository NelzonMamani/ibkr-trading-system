from dataclasses import dataclass
from typing import List, Tuple, Optional, Any
from datetime import datetime

from src.config.runtime_config import RunMode, RuntimeConfig
from src.core.active_trade_registry import ActiveTradeRegistry
from src.core.position_lifecycle_engine import (
    LifecycleIntent,
    PositionLifecycle,
    PositionLifecycleEngine,
    PositionState,
)
from src.core.stop_controller import StopController
from src.models.data_models import ExecutionResult
from src.core.trade_outcome_factory import TradeOutcomeFactory
from src.domain.trade_outcome import TradeOutcome
from src.sim.price_feed import DeterministicPriceFeed, PriceFeed
from src.strategy.exit_signal import ExitSignal
from src.execution.slippage_model import SlippageModel
from src.execution.exit_plan import (
    compute_take_profit_price,
    resolve_exit_plan,
    resolve_max_hold_ticks,
    resolve_momentum_fail_ticks,
)
from src.execution.commission_model import CommissionModel


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
        price_feed: Optional[PriceFeed] = None,
        stop_controller: Optional[StopController] = None,
    ):
        self.trade_registry = trade_registry
        self.event_collector = event_collector
        self.price_feed = price_feed or DeterministicPriceFeed()
        self.stop_controller = stop_controller or StopController()
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
        breaker_tripped: bool = False,
        risk_exit_signal: bool = False,
        exhaustion_signal: bool = False,
        exhaustion_confidence: float = 0.0,
    ) -> Optional[ExitDecision]:
        """
        Pure decision function to determine the highest-priority exit outcome.

        This method is intentionally side-effect free to enable deterministic
        validation of exit precedence without invoking registry or event paths.
        """

        entry_tick = getattr(trade, "entry_tick", current_tick)
        entry_price = getattr(trade, "entry_price", current_price)
        normalized_direction = (getattr(trade, "direction", "") or "").upper()
        stop_loss_price = getattr(trade, "stop_loss_price", None)
        take_profit_price = getattr(trade, "take_profit_price", None)
        trader_type = getattr(trade, "trader_type", "UNKNOWN")
        strategy_name = getattr(trade, "strategy_name", None)
        pattern_name = getattr(trade, "pattern_name", None)
        hold_duration_ticks = (
            trade.hold_duration(current_tick)
            if hasattr(trade, "hold_duration")
            else max(0, current_tick - entry_tick)
        )

        min_hold_ticks = self._resolve_threshold(config, "MIN_HOLD_TICKS", "min_hold_ticks")
        max_hold_ticks = resolve_max_hold_ticks(
            trader_type=trader_type,
            pattern_name=pattern_name,
            strategy_name=strategy_name,
            fallback=self._resolve_threshold(config, "MAX_HOLD_TICKS", "max_hold_ticks"),
        )

        if breaker_tripped:
            return ExitDecision(
                category="EXIT_BREAKER",
                reason="Circuit breaker kill-switch triggered",
                exit_tick=current_tick,
                exit_price=current_price,
            )

        if stop_loss_price is not None and take_profit_price is None:
            take_profit_price = compute_take_profit_price(
                entry_price=entry_price,
                stop_loss_price=stop_loss_price,
                direction=normalized_direction,
                pattern_name=pattern_name,
                strategy_name=strategy_name,
            )

        stop_loss_triggered = False
        take_profit_triggered = False
        if stop_loss_price is not None:
            if normalized_direction == "SHORT":
                stop_loss_triggered = current_price >= stop_loss_price
            else:
                stop_loss_triggered = current_price <= stop_loss_price

        if take_profit_price is not None:
            if normalized_direction == "SHORT":
                take_profit_triggered = current_price <= take_profit_price
            else:
                take_profit_triggered = current_price >= take_profit_price

        if stop_loss_triggered:
            trade_state = getattr(trade, "state", PositionState.OPEN)
            category = "EXIT_STOP_LOSS" if trade_state == PositionState.CLOSING else "EXIT_FAILED_SETUP"
            reason = (
                "Pattern invalidation / failed breakout — stop-loss breached"
                if category == "EXIT_FAILED_SETUP"
                else "Protective stop-loss breached"
            )
            return ExitDecision(
                category=category,
                reason=reason,
                exit_tick=current_tick,
                exit_price=current_price,
            )

        if exhaustion_signal:
            action = "tighten_stop_partial_exit" if exhaustion_confidence < 0.85 else "full_exit"
            print(
                "[EXIT][PARABOLIC_EXHAUSTION] "
                f"symbol={getattr(trade, 'symbol', 'UNKNOWN')} action={action} confidence={exhaustion_confidence:.2f}"
            )
            return ExitDecision(
                category="EXIT_RISK",
                reason=(
                    "Parabolic exhaustion active — tighten stop and partial exit"
                    if exhaustion_confidence < 0.85
                    else "Parabolic exhaustion high confidence — full exit"
                ),
                exit_tick=current_tick,
                exit_price=current_price,
            )

        if risk_exit_signal:
            return ExitDecision(
                category="EXIT_RISK",
                reason="Risk engine veto requested immediate exit",
                exit_tick=current_tick,
                exit_price=current_price,
            )

        if take_profit_triggered:
            return ExitDecision(
                category="EXIT_TARGET",
                reason="Profit target reached",
                exit_tick=current_tick,
                exit_price=current_price,
            )

        if hold_duration_ticks < min_hold_ticks:
            return None

        if strategy_exit_signal:
            return ExitDecision(
                category="EXIT_STRATEGY",
                reason="Strategy requested exit",
                exit_tick=current_tick,
                exit_price=current_price,
            )

        if hold_duration_ticks >= max_hold_ticks:
            return ExitDecision(
                category="EXIT_TIME",
                reason="Max hold duration reached",
                exit_tick=current_tick,
                exit_price=current_price,
            )

        momentum_fail_ticks = resolve_momentum_fail_ticks(
            trader_type=trader_type,
            pattern_name=pattern_name,
            strategy_name=strategy_name,
            fallback=min_hold_ticks,
        )
        plan = resolve_exit_plan(pattern_name, strategy_name)
        risk_amount = max(abs(entry_price - (stop_loss_price or entry_price)), 0.01)
        if normalized_direction == "SHORT":
            progress_r = (entry_price - current_price) / risk_amount
        else:
            progress_r = (current_price - entry_price) / risk_amount
        if hold_duration_ticks >= momentum_fail_ticks and progress_r < plan.momentum_min_r_multiple:
            return ExitDecision(
                category="EXIT_TIME",
                reason=(
                    "Momentum failed or volume collapsed — "
                    f"progress={progress_r:.2f}R after {hold_duration_ticks} ticks"
                ),
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
        risk_exit_requests: Optional[set[tuple[str, str]]] = None,
        breaker_tripped: Optional[bool] = None,
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

        min_hold_ticks = self._resolve_threshold(runtime_config, "MIN_HOLD_TICKS", "min_hold_ticks")

        breaker_active = (
            breaker_tripped
            if breaker_tripped is not None
            else self.stop_controller.is_breaker_tripped()
        )
        risk_exit_requests = risk_exit_requests or set()

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
                gross_realised_pnl = (entry_price - exit_price) * quantity
            else:
                gross_realised_pnl = (exit_price - entry_price) * quantity
            gross_realised_pnl = round(gross_realised_pnl, 2)
            commission = CommissionModel.calculate_commission(trader_type, quantity)
            net_realised_pnl = round(gross_realised_pnl - commission, 2)

            stop_loss_price = getattr(trade, "stop_loss_price", None)
            take_profit_price = getattr(trade, "take_profit_price", None)
            pattern_name = getattr(trade, "pattern_name", None)
            plan = resolve_exit_plan(pattern_name, strategy_name)
            resolved_max_hold_ticks = resolve_max_hold_ticks(
                trader_type=trader_type,
                pattern_name=pattern_name,
                strategy_name=strategy_name,
                fallback=self._resolve_threshold(runtime_config, "MAX_HOLD_TICKS", "max_hold_ticks"),
            )
            risk_amount = max(abs(entry_price - (stop_loss_price or entry_price)), 0.01)
            if stop_loss_price is not None and take_profit_price is None:
                take_profit_price = compute_take_profit_price(
                    entry_price=entry_price,
                    stop_loss_price=stop_loss_price,
                    direction=normalized_direction,
                    pattern_name=pattern_name,
                    strategy_name=strategy_name,
                )
                trade.take_profit_price = take_profit_price

            if getattr(trade, "state", None) in {PositionState.OPEN, PositionState.SCALING_IN}:
                if normalized_direction == "SHORT":
                    progress_r = (entry_price - exit_price) / risk_amount
                else:
                    progress_r = (exit_price - entry_price) / risk_amount
                if progress_r >= 0.5:
                    print(
                        "[EXIT] Trade reached +0.5R unrealised gain "
                        f"symbol={symbol} trader_type={trader_type}"
                    )

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
                breaker_tripped=breaker_active,
                risk_exit_signal=(symbol, trader_type) in risk_exit_requests,
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
                        f"max_hold_ticks={resolved_max_hold_ticks}"
                    )
                continue

            rationale: str
            if decision.category == "EXIT_TIME":
                if decision.reason.startswith("Momentum failed"):
                    rationale = (
                        "Exit condition met: momentum failed within time budget via TradeExitEngine "
                        f"({decision.reason}; max_hold_ticks={resolved_max_hold_ticks})"
                    )
                else:
                    rationale = (
                        "Exit condition met: maximum hold duration reached via TradeExitEngine "
                        f"(held {hold_duration_ticks} ticks; max_hold_ticks={resolved_max_hold_ticks})"
                    )
            elif decision.category == "EXIT_STOP_LOSS":
                rationale = (
                    "Exit condition met: stop-loss price reached via TradeExitEngine "
                    f"(direction={normalized_direction or 'UNKNOWN'} price={exit_price} "
                    f"stop_loss_price={stop_loss_price})"
                )
            elif decision.category == "EXIT_FAILED_SETUP":
                rationale = (
                    "Exit condition met: failed setup / invalidation breached "
                    f"(direction={normalized_direction or 'UNKNOWN'} price={exit_price} "
                    f"invalidation_level={stop_loss_price})"
                )
            elif decision.category == "EXIT_TARGET":
                rationale = (
                    "Exit condition met: take-profit price reached via TradeExitEngine "
                    f"(direction={normalized_direction or 'UNKNOWN'} price={exit_price} "
                    f"take_profit_price={take_profit_price}; micro-safe full exit logged)"
                )
            elif decision.category == "EXIT_RISK":
                rationale = (
                    "Exit condition met: risk engine veto enforced via TradeExitEngine "
                    f"(reason={decision.reason})"
                )
            elif decision.category == "EXIT_BREAKER":
                rationale = (
                    "Exit condition met: circuit breaker enforced via TradeExitEngine "
                    f"(reason={decision.reason})"
                )
            elif decision.category == "EXIT_STRATEGY" and selected_signal is not None:
                rationale = (
                    "Strategy exit request honoured by TradeExitEngine: "
                    f"{selected_signal.reason} "
                    f"(requested_by={selected_signal.strategy_name}; "
                    f"hold_duration_ticks={hold_duration_ticks})"
                )
            else:
                rationale = decision.reason

            self._transition_trade_state(
                trade,
                new_state=PositionState.CLOSING,
                tick=exit_tick,
                reason=rationale,
            )
            self.trade_registry.unregister_trade(symbol, trader_type)
            self._transition_trade_state(
                trade,
                new_state=PositionState.CLOSED,
                tick=exit_tick,
                reason="Trade closed by TradeExitEngine",
            )

            self._emit_lifecycle_exit_intent(
                decision=decision,
                trade=trade,
                run_mode=run_mode,
                reason=rationale,
            )
            self._emit_exit_event(
                decision=decision,
                trade=trade,
                exit_tick=exit_tick,
                exit_price=exit_price,
                net_realised_pnl=net_realised_pnl,
                hold_duration_ticks=hold_duration_ticks,
            )

            self.event_collector.emit(
                event_type="TRADE_CLOSED",
                source="TradeExitEngine",
                payload={
                    "symbol": symbol,
                    "trader_type": trader_type,
                    "strategy_name": strategy_name,
                    "pattern_name": pattern_name,
                    "tick": tick,
                    "reason": rationale,
                    "exit_category": decision.category,
                    "exit_reason": decision.reason,
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
                    "max_hold_ticks": resolved_max_hold_ticks,
                    "pnl": net_realised_pnl,
                    "realised_pnl": net_realised_pnl,
                    "gross_realised_pnl": gross_realised_pnl,
                    "commission": commission,
                    "net_realised_pnl": net_realised_pnl,
                    "stop_loss_price": stop_loss_price,
                    "take_profit_price": take_profit_price,
                    "quantity": quantity,
                    "state_history": getattr(trade, "state_history", []),
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
                gross_realised_pnl=gross_realised_pnl,
                commission=commission,
                net_realised_pnl=net_realised_pnl,
                requested_quantity=quantity,
                filled_quantity=quantity,
                remaining_quantity=0,
                fill_status="FULL",
                average_fill_price=entry_price,
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

    def _transition_trade_state(self, trade, new_state: PositionState | str, tick: int, reason: str) -> None:
        if not hasattr(trade, "transition_state"):
            return
        previous_state = getattr(trade, "state", None)
        try:
            trade.transition_state(new_state, tick, reason)
        except ValueError as exc:
            print(f"[STATE] Transition blocked: {exc}")
            return
        self.event_collector.emit(
            event_type="TRADE_STATE_UPDATED",
            source="TradeExitEngine",
            payload={
                "symbol": getattr(trade, "symbol", "UNKNOWN"),
                "trader_type": getattr(trade, "trader_type", "UNKNOWN"),
                "strategy_name": getattr(trade, "strategy_name", "UNKNOWN"),
                "from_state": getattr(previous_state, "value", previous_state),
                "to_state": getattr(new_state, "value", new_state),
                "tick": tick,
                "reason": reason,
            },
        )

    def _emit_exit_event(
        self,
        decision: ExitDecision,
        trade,
        exit_tick: int,
        exit_price: float,
        net_realised_pnl: float,
        hold_duration_ticks: int,
    ) -> None:
        event_type = decision.category
        self.event_collector.emit(
            event_type=event_type,
            source="TradeExitEngine",
            payload={
                "symbol": getattr(trade, "symbol", "UNKNOWN"),
                "trader_type": getattr(trade, "trader_type", "UNKNOWN"),
                "strategy_name": getattr(trade, "strategy_name", "UNKNOWN"),
                "exit_tick": exit_tick,
                "exit_price": exit_price,
                "exit_category": decision.category,
                "exit_reason": decision.reason,
                "pnl": net_realised_pnl,
                "hold_duration_ticks": hold_duration_ticks,
            },
        )

    def _emit_lifecycle_exit_intent(
        self,
        decision: ExitDecision,
        trade,
        run_mode: RunMode,
        reason: str,
    ) -> None:
        intent_map = {
            "EXIT_STOP_LOSS": LifecycleIntent.STOP_EXIT,
            "EXIT_TIME": LifecycleIntent.TIME_EXIT,
            "EXIT_RISK": LifecycleIntent.RISK_EXIT,
            "EXIT_BREAKER": LifecycleIntent.SYSTEM_EXIT,
            "EXIT_TARGET": LifecycleIntent.FULL_EXIT,
            "EXIT_FAILED_SETUP": LifecycleIntent.STOP_EXIT,
            "EXIT_STRATEGY": LifecycleIntent.FULL_EXIT,
        }
        intent = intent_map.get(decision.category)
        if intent is None:
            return
        lifecycle_engine = PositionLifecycleEngine(event_collector=self.event_collector)
        lifecycle_position = PositionLifecycle(
            symbol=getattr(trade, "symbol", "UNKNOWN"),
            trader_type=getattr(trade, "trader_type", "UNKNOWN"),
            quantity=getattr(trade, "quantity", 0),
            state=PositionState.OPEN,
        )
        lifecycle_engine.apply_intent(
            lifecycle_position,
            intent,
            requested_quantity=max(getattr(trade, "quantity", 0), 1),
            run_mode=run_mode,
            reason=reason,
            risk_approved=True,
            filled_quantity_override=getattr(trade, "quantity", 0),
            fill_status_override="FULL",
        )

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
                gross_realised_pnl = (entry_price - exit_price) * quantity
            else:
                gross_realised_pnl = (exit_price - entry_price) * quantity
            gross_realised_pnl = round(gross_realised_pnl, 2)
            commission = CommissionModel.calculate_commission(trader_type, quantity)
            net_realised_pnl = round(gross_realised_pnl - commission, 2)

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
            forced_decision = ExitDecision(
                category="EXIT_TIME",
                reason="Forced shutdown exit",
                exit_tick=resolved_tick,
                exit_price=exit_price,
            )
            self._transition_trade_state(
                trade,
                new_state=PositionState.CLOSING,
                tick=resolved_tick,
                reason=rationale,
            )
            self._transition_trade_state(
                trade,
                new_state=PositionState.CLOSED,
                tick=resolved_tick,
                reason="Forced shutdown close",
            )
            self._emit_lifecycle_exit_intent(
                decision=forced_decision,
                trade=trade,
                run_mode=run_mode,
                reason=rationale,
            )
            self._emit_exit_event(
                decision=forced_decision,
                trade=trade,
                exit_tick=resolved_tick,
                exit_price=exit_price,
                net_realised_pnl=net_realised_pnl,
                hold_duration_ticks=hold_duration_ticks,
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
                    "exit_category": forced_decision.category,
                    "exit_reason": forced_decision.reason,
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
                    "pnl": net_realised_pnl,
                    "realised_pnl": net_realised_pnl,
                    "gross_realised_pnl": gross_realised_pnl,
                    "commission": commission,
                    "net_realised_pnl": net_realised_pnl,
                    "stop_loss_price": stop_loss_price,
                    "take_profit_price": take_profit_price,
                    "quantity": quantity,
                    "state_history": getattr(trade, "state_history", []),
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
