from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Tuple

from src.brokers.base_broker import BaseBroker, BrokerOrderRequest
from src.config.runtime_config import RunMode, get_run_mode
from src.core.active_trade_registry import ActiveTrade, ActiveTradeRegistry
from src.core.event_collector import EventCollector
from src.execution.liquidity_engine import LiquidityEngine
from src.execution.order_gateway import GatewayDecision, OrderGateway
from src.execution.slippage_model import SlippageModel
from src.execution.exit_plan import compute_stop_price, compute_take_profit_price
from src.models.execution_result import ExecutionResult
from src.sim.price_feed import PriceFeed
from src.utils.price_math import (
    apply_slippage,
    apply_spread_mid_to_quote,
    choose_execution_reference_price,
    deterministic_spread,
    q_price,
    to_decimal,
)


@dataclass
class SimBroker(BaseBroker):
    """
    Teaching-safe SIM broker.

    Reuses the deterministic gateway + liquidity + price feed.
    The goal is to make ExecutionEngine broker-agnostic without changing behaviour.
    """

    gateway: OrderGateway
    price_feed: PriceFeed
    trade_registry: ActiveTradeRegistry
    event_collector: EventCollector
    run_mode: Optional[RunMode] = None

    def __post_init__(self) -> None:
        if self.run_mode is None:
            self.run_mode = get_run_mode()

    def name(self) -> str:
        return "SIM_BROKER"

    def is_live(self) -> bool:
        return False

    def _max_attempts(self, trader_type: Optional[str]) -> int:
        normalized = (trader_type or "").upper()
        if normalized == "SCALPER":
            return 2
        if normalized == "MOMENTUM":
            return 3
        return 1

    def _compute_quote_context(
        self, request: BrokerOrderRequest, tick: int
    ) -> Tuple[
        Optional[Decimal],
        Optional[Decimal],
        Optional[Decimal],
        Optional[Decimal],
        Optional[Decimal],
    ]:
        raw_mid = q_price(to_decimal(self.price_feed.price_for(request.symbol, tick)))
        if raw_mid is None:
            return None, None, None, None, None
        spread = deterministic_spread(request.symbol, tick, request.trader_type)
        bid_price, ask_price = apply_spread_mid_to_quote(raw_mid, spread)
        reference_price = choose_execution_reference_price(
            request.direction,
            bid_price,
            ask_price,
        )
        return raw_mid, spread, bid_price, ask_price, reference_price

    @staticmethod
    def _slippage_value(direction: str, trader_type: Optional[str], quantity: int):
        normalized_direction = (direction or "").upper()
        normalized_trader_type = (trader_type or "").upper()
        base_slippage = to_decimal(
            SlippageModel._SLIPPAGE_TABLE.get(
                (normalized_trader_type, normalized_direction),
                0.0,
            )
        )
        if base_slippage is None:
            base_slippage = to_decimal(0)
        is_exit = quantity < 0
        if is_exit and normalized_direction == "LONG":
            applied_slippage = -base_slippage
        else:
            applied_slippage = base_slippage
        return q_price(abs(applied_slippage))

    def _emit_order_submitted(self, request: BrokerOrderRequest, tick: int) -> None:
        print(
            "[SIM_ORDER] Submitted "
            f"symbol={request.symbol} direction={request.direction} quantity={request.quantity}"
        )
        self.event_collector.emit(
            event_type="ORDER_SUBMITTED",
            source="ExecutionEngine",
            payload={
                "client_order_id": request.client_order_id,
                "symbol": request.symbol,
                "trader_type": request.trader_type,
                "strategy_name": request.strategy_name,
                "direction": request.direction,
                "requested_quantity": request.quantity,
                "created_tick": tick,
                "attempt_number": request.attempt_number,
                "broker": self.name(),
            },
        )

    def _emit_gateway_decision(
        self,
        request: BrokerOrderRequest,
        tick: int,
        decision: GatewayDecision,
        decision_key: str,
        mapping_r: int,
    ) -> None:
        print(
            f"[GATEWAY] id={request.client_order_id} tick={tick} "
            f"attempt={request.attempt_number} decision={decision.value}"
        )
        self.event_collector.emit(
            event_type="ORDER_GATEWAY_DECISION",
            source="ExecutionEngine",
            payload={
                "client_order_id": request.client_order_id,
                "symbol": request.symbol,
                "trader_type": request.trader_type,
                "tick": tick,
                "attempt_number": request.attempt_number,
                "decision": decision.value,
                "deterministic_key": decision_key,
                "mapping_r": mapping_r,
            },
        )

    def place_order(self, request: BrokerOrderRequest) -> ExecutionResult:
        tick = request.created_tick if request.created_tick is not None else 0
        self._emit_order_submitted(request, tick)
        decision, decision_key, mapping_r = self.gateway.decide_with_trace(
            request.symbol, tick, request.trader_type, request.attempt_number
        )
        self._emit_gateway_decision(request, tick, decision, decision_key, mapping_r)

        if decision == GatewayDecision.REJECT:
            return self._on_hard_reject(request, tick)

        if decision == GatewayDecision.SOFT_REJECT:
            return self._on_soft_reject(request, tick)

        return self._execute_liquidity(request, tick)

    def _on_hard_reject(self, request: BrokerOrderRequest, tick: int) -> ExecutionResult:
        raw_mid, spread, bid_price, ask_price, reference_price = self._compute_quote_context(request, tick)
        self.event_collector.emit(
            event_type="ORDER_REJECTED_HARD",
            source="ExecutionEngine",
            payload={
                "client_order_id": request.client_order_id,
                "symbol": request.symbol,
                "trader_type": request.trader_type,
                "tick": tick,
                "attempt_number": request.attempt_number,
                "reason": "GATEWAY_HARD_REJECT",
            },
        )
        return ExecutionResult(
            symbol=request.symbol,
            trader_type=request.trader_type or "UNKNOWN",
            attempted=False,
            status="REJECTED",
            rationale="Deterministic gateway hard rejected the order.",
            direction=request.direction,
            quantity=0,
            entry_price=None,
            raw_price=raw_mid,
            entry_tick=tick,
            stop_loss_price=to_decimal(request.stop_loss_price) if request.stop_loss_price is not None else None,
            take_profit_price=to_decimal(request.take_profit_price) if request.take_profit_price is not None else None,
            requested_quantity=request.quantity,
            filled_quantity=0,
            remaining_quantity=request.quantity,
            fill_status="NONE",
            average_fill_price=None,
            note="Gateway hard reject — no liquidity attempted.",
            gateway_decision=GatewayDecision.REJECT.value,
            attempt_number=request.attempt_number,
            client_order_id=request.client_order_id,
            retry_scheduled=False,
            next_retry_tick=None,
            rejection_reason="GATEWAY_HARD_REJECT",
            spread=spread,
            bid_price=bid_price,
            ask_price=ask_price,
            reference_price=reference_price,
        )

    def _on_soft_reject(self, request: BrokerOrderRequest, tick: int) -> ExecutionResult:
        raw_mid, spread, bid_price, ask_price, reference_price = self._compute_quote_context(request, tick)
        max_attempts = self._max_attempts(request.trader_type)
        if request.attempt_number >= max_attempts:
            self.event_collector.emit(
                event_type="ORDER_EXPIRED",
                source="ExecutionEngine",
                payload={
                    "client_order_id": request.client_order_id,
                    "symbol": request.symbol,
                    "trader_type": request.trader_type,
                    "tick": tick,
                    "attempt_number": request.attempt_number,
                    "reason": "MAX_ATTEMPTS_REACHED",
                },
            )
            print(
                f"[EXPIRE] id={request.client_order_id} attempts={request.attempt_number} "
                f"max={max_attempts} dropped"
            )
            return ExecutionResult(
                symbol=request.symbol,
                trader_type=request.trader_type or "UNKNOWN",
                attempted=False,
                status="EXPIRED",
                rationale="Soft reject but max attempts reached; expiring order.",
                direction=request.direction,
                quantity=0,
                entry_price=None,
                raw_price=raw_mid,
                entry_tick=tick,
                stop_loss_price=to_decimal(request.stop_loss_price) if request.stop_loss_price is not None else None,
                take_profit_price=to_decimal(request.take_profit_price) if request.take_profit_price is not None else None,
                requested_quantity=request.quantity,
                filled_quantity=0,
                remaining_quantity=request.quantity,
                fill_status="NONE",
                average_fill_price=None,
                note="Gateway soft reject expired at max attempts.",
                gateway_decision=GatewayDecision.SOFT_REJECT.value,
                attempt_number=request.attempt_number,
                client_order_id=request.client_order_id,
                retry_scheduled=False,
                next_retry_tick=None,
                rejection_reason="EXPIRED",
                spread=spread,
                bid_price=bid_price,
                ask_price=ask_price,
                reference_price=reference_price,
            )

        next_retry_tick = tick + 1
        next_attempt = request.attempt_number + 1
        self.event_collector.emit(
            event_type="ORDER_RETRY_SCHEDULED",
            source="ExecutionEngine",
            payload={
                "client_order_id": request.client_order_id,
                "symbol": request.symbol,
                "trader_type": request.trader_type,
                "from_tick": tick,
                "next_retry_tick": next_retry_tick,
                "next_attempt_number": next_attempt,
            },
        )
        print(
            f"[RETRY] id={request.client_order_id} scheduled next_tick={next_retry_tick} "
            f"next_attempt={next_attempt}"
        )
        return ExecutionResult(
            symbol=request.symbol,
            trader_type=request.trader_type or "UNKNOWN",
            attempted=False,
            status="RETRY_SCHEDULED",
            rationale="Gateway soft reject — retry scheduled.",
            direction=request.direction,
            quantity=0,
            entry_price=None,
            raw_price=raw_mid,
            entry_tick=tick,
            stop_loss_price=to_decimal(request.stop_loss_price) if request.stop_loss_price is not None else None,
            take_profit_price=to_decimal(request.take_profit_price) if request.take_profit_price is not None else None,
            requested_quantity=request.quantity,
            filled_quantity=0,
            remaining_quantity=request.quantity,
            fill_status="NONE",
            average_fill_price=None,
            note="Gateway soft reject; will retry deterministically.",
            gateway_decision=GatewayDecision.SOFT_REJECT.value,
            attempt_number=request.attempt_number,
            client_order_id=request.client_order_id,
            retry_scheduled=True,
            next_retry_tick=next_retry_tick,
            rejection_reason="GATEWAY_SOFT_REJECT",
            spread=spread,
            bid_price=bid_price,
            ask_price=ask_price,
            reference_price=reference_price,
        )

    def _execute_liquidity(self, request: BrokerOrderRequest, tick: int) -> ExecutionResult:
        available_liquidity = LiquidityEngine.available_liquidity(
            symbol=request.symbol,
            tick=tick,
            trader_type=request.trader_type,
        )
        raw_mid, spread, bid_price, ask_price, reference_price = self._compute_quote_context(request, tick)
        requested_quantity = request.quantity
        filled_quantity = min(requested_quantity, available_liquidity)
        remaining_quantity = max(0, requested_quantity - filled_quantity)

        fill_status = "NONE"
        if filled_quantity == requested_quantity and requested_quantity > 0:
            fill_status = "FULL"
        elif 0 < filled_quantity < requested_quantity:
            fill_status = "PARTIAL"

        if filled_quantity == 0:
            reason = (
                "LIQUIDITY_ZERO" if available_liquidity == 0 else "LIQUIDITY_CAP"
            )
            print(
                "[LIQUIDITY] "
                f"symbol={request.symbol} tick={tick} trader_type={request.trader_type} "
                f"requested={requested_quantity} available={available_liquidity} "
                f"filled={filled_quantity} remaining={remaining_quantity} "
                "status=NONE (no trade opened)"
            )
            self.event_collector.emit(
                event_type="TRADE_NOT_FILLED",
                source="ExecutionEngine",
                payload={
                    "symbol": request.symbol,
                    "trader_type": request.trader_type,
                    "tick": tick,
                    "requested_quantity": requested_quantity,
                    "available_liquidity": available_liquidity,
                    "filled_quantity": 0,
                    "remaining_quantity": remaining_quantity,
                    "reason": reason,
                    "fill_status": "NONE",
                    "client_order_id": request.client_order_id,
                    "attempt_number": request.attempt_number,
                    "gateway_decision": GatewayDecision.ACCEPT.value,
                },
            )
            return ExecutionResult(
                symbol=request.symbol,
                trader_type=request.trader_type or "UNKNOWN",
                attempted=True,
                status="NOT_FILLED",
                rationale="Deterministic liquidity returned zero available volume.",
                direction=request.direction,
                quantity=0,
                entry_price=None,
                raw_price=raw_mid,
                spread=spread,
                bid_price=bid_price,
                ask_price=ask_price,
                reference_price=reference_price,
                execution_price=None,
                entry_tick=tick,
                stop_loss_price=to_decimal(request.stop_loss_price) if request.stop_loss_price is not None else None,
                take_profit_price=to_decimal(request.take_profit_price) if request.take_profit_price is not None else None,
                requested_quantity=requested_quantity,
                filled_quantity=0,
                remaining_quantity=remaining_quantity,
                fill_status="NONE",
                average_fill_price=None,
                note="No fill: liquidity zero for this tick/symbol combination.",
                gateway_decision=GatewayDecision.ACCEPT.value,
                attempt_number=request.attempt_number,
                client_order_id=request.client_order_id,
                retry_scheduled=False,
                next_retry_tick=None,
                rejection_reason=None,
            )

        slippage_value = self._slippage_value(request.direction, request.trader_type, filled_quantity)
        execution_price, slippage_applied = apply_slippage(reference_price, slippage_value, request.direction)
        entry_price = execution_price
        registry_entry_price = float(entry_price)
        pattern_name = request.pattern_name
        resolved_stop_loss = request.stop_loss_price
        if resolved_stop_loss is None:
            resolved_stop_loss = request.invalidation_level
        if resolved_stop_loss is None:
            resolved_stop_loss = compute_stop_price(
                registry_entry_price,
                request.direction,
                pattern_name=pattern_name,
                strategy_name=request.strategy_name,
            )
        resolved_take_profit = request.take_profit_price
        if resolved_take_profit is None:
            resolved_take_profit = compute_take_profit_price(
                registry_entry_price,
                resolved_stop_loss,
                request.direction,
                pattern_name=pattern_name,
                strategy_name=request.strategy_name,
            )
        active_trade = ActiveTrade(
            symbol=request.symbol,
            trader_type=request.trader_type or "UNKNOWN",
            entry_tick=tick,
            entry_price=registry_entry_price,
            direction=request.direction,
            quantity=filled_quantity,
            strategy_name=request.strategy_name or "UNKNOWN",
            stop_loss_price=resolved_stop_loss,
            take_profit_price=resolved_take_profit,
            pattern_name=pattern_name,
            invalidation_level=request.invalidation_level,
        )
        self.event_collector.emit(
            event_type="PROTECTIVE_STOP_PLACED",
            source="ExecutionEngine",
            payload={
                "symbol": request.symbol,
                "trader_type": request.trader_type,
                "strategy_name": request.strategy_name,
                "pattern_name": pattern_name,
                "stop_loss_price": float(resolved_stop_loss),
                "take_profit_price": float(resolved_take_profit),
                "rationale": "Protective stop assigned immediately upon fill.",
                "tick": tick,
            },
        )
        self.trade_registry.register_trade(active_trade)
        if active_trade.state_history:
            last_transition = active_trade.state_history[-1]
            if last_transition.get("to") == "PROTECTED":
                self.event_collector.emit(
                    event_type="TRADE_STATE_UPDATED",
                    source="ExecutionEngine",
                    payload={
                        "symbol": request.symbol,
                        "trader_type": request.trader_type or "UNKNOWN",
                        "strategy_name": request.strategy_name or "UNKNOWN",
                        "from_state": last_transition.get("from"),
                        "to_state": last_transition.get("to"),
                        "tick": last_transition.get("tick"),
                        "reason": last_transition.get("reason"),
                    },
                )
        self.event_collector.emit(
            event_type="TRADE_OPENED",
            source="ExecutionEngine",
            payload={
                "symbol": request.symbol,
                "trader_type": request.trader_type,
                "strategy_name": request.strategy_name,
                "entry_tick": tick,
                "opened_at_tick": tick,
                "entry_price": float(entry_price),
                "raw_price": float(raw_mid) if raw_mid is not None else None,
                "slippage_applied": float(slippage_applied),
                "execution_price": float(entry_price),
                "mode": self.run_mode.value if isinstance(self.run_mode, RunMode) else RunMode.SIM.value,
                "direction": request.direction,
                "quantity": filled_quantity,
                "stop_loss_price": float(resolved_stop_loss),
                "take_profit_price": float(resolved_take_profit),
                "requested_quantity": requested_quantity,
                "filled_quantity": filled_quantity,
                "remaining_quantity": remaining_quantity,
                "fill_status": fill_status,
                "client_order_id": request.client_order_id,
                "attempt_number": request.attempt_number,
                "gateway_decision": GatewayDecision.ACCEPT.value,
                "pattern_name": pattern_name,
            },
        )
        print(
            f"[EVENT] TRADE_OPENED emitted for "
            f"{request.symbol} ({request.trader_type})"
            f" tick={tick} price={entry_price}"
        )
        print(
            "[EXECUTION:REGISTRY] Registered active trade "
            f"symbol={request.symbol} trader_type={request.trader_type}"
        )
        print(
            "[EXECUTION:REGISTRY] Active trades for trader_type "
            f"{request.trader_type}: {self.trade_registry.count_active_by_trader(request.trader_type or 'UNKNOWN')}"
        )
        print(
            f"[EXECUTION] {self.run_mode.value if isinstance(self.run_mode, RunMode) else RunMode.SIM.value} mode active — no broker calls; returning simulated result."
        )

        liquidity_note = None
        if fill_status == "PARTIAL":
            liquidity_note = "Partial fill due to deterministic liquidity cap."
            print(
                "[LIQUIDITY] "
                f"symbol={request.symbol} tick={tick} trader_type={request.trader_type} "
                f"requested={requested_quantity} available={available_liquidity} "
                f"filled={filled_quantity} remaining={remaining_quantity} "
                f"status=PARTIAL"
            )

        return ExecutionResult(
            symbol=request.symbol,
            trader_type=request.trader_type or "UNKNOWN",
            attempted=True,
            status="SIMULATED",
            rationale="Teaching-only: routed by trader_type with deterministic gateway and liquidity.",
            direction=request.direction,
            quantity=filled_quantity,
            entry_price=entry_price,
            raw_price=raw_mid,
            slippage_applied=slippage_applied,
            entry_tick=tick,
            stop_loss_price=to_decimal(resolved_stop_loss),
            take_profit_price=to_decimal(resolved_take_profit),
            requested_quantity=requested_quantity,
            filled_quantity=filled_quantity,
            remaining_quantity=remaining_quantity,
            fill_status=fill_status,
            average_fill_price=entry_price,
            note=liquidity_note,
            gateway_decision=GatewayDecision.ACCEPT.value,
            attempt_number=request.attempt_number,
            client_order_id=request.client_order_id,
            retry_scheduled=False,
            next_retry_tick=None,
            rejection_reason=None,
            spread=spread,
            bid_price=bid_price,
            ask_price=ask_price,
            reference_price=reference_price,
            execution_price=execution_price,
        )
