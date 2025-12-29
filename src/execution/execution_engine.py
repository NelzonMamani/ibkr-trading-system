"""
Execution engine with deterministic gateway, retry semantics, and liquidity routing.
"""

import hashlib
from typing import List, Optional

from config.runtime_config import RunMode, get_run_mode
from core.active_trade_registry import ActiveTradeRegistry, ActiveTrade
from core.event_collector import EventCollector
from execution.liquidity_model import LiquidityModel
from execution.order_gateway import GatewayDecision, OrderGateway
from execution.order_models import OrderRequest, PendingOrderBook
from execution.slippage_model import SlippageModel
from models.data_models import ExecutionResult, RiskDecision
from sim.price_feed import DeterministicPriceFeed


class ExecutionEngine:
    """Deterministic execution engine with retryable gateway semantics."""

    def __init__(
        self,
        broker: Optional[object] = None,
        trade_registry: Optional[ActiveTradeRegistry] = None,
        event_collector: Optional[EventCollector] = None,
        price_feed: Optional[DeterministicPriceFeed] = None,
    ) -> None:
        print("[BOOT] ExecutionEngine instantiated — deterministic gateway + liquidity")
        self.broker = broker
        self.trade_registry = trade_registry or ActiveTradeRegistry()
        self.event_collector = event_collector or EventCollector()
        self.price_feed = price_feed or DeterministicPriceFeed()
        self.gateway = OrderGateway()
        self.pending_book = PendingOrderBook()
        self.current_tick: Optional[int] = None
        self.run_mode: RunMode = get_run_mode()

    @staticmethod
    def _max_attempts(trader_type: str) -> int:
        normalized = (trader_type or "").upper()
        if normalized == "SCALPER":
            return 2
        if normalized == "MOMENTUM":
            return 3
        return 1

    @staticmethod
    def _client_order_id(
        symbol: str, trader_type: str, strategy_name: str, direction: str, created_tick: int
    ) -> str:
        key = f"{symbol}|{trader_type}|{strategy_name}|{direction}|{created_tick}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]

    def process_pending_orders(self, tick: int) -> List[ExecutionResult]:
        due_orders = self.pending_book.due_orders(tick)
        results: List[ExecutionResult] = []
        if due_orders:
            print(f"[PENDING] Processing {len(due_orders)} pending orders for tick={tick}")
        for order in due_orders:
            self.pending_book.remove(order.client_order_id)
            results.append(self._handle_order_attempt(order, tick))
        return results

    def execute_trade(self, risk_decision: Optional[RiskDecision]) -> ExecutionResult:
        """
        Convert a risk decision into an order request and route through the gateway.
        """

        print("[EXECUTION] Received risk decision for deterministic gateway flow")
        if risk_decision is None:
            print("[EXECUTION] No execution performed — placeholder path")
            return ExecutionResult(
                symbol="UNKNOWN",
                trader_type="MANUAL",
                attempted=False,
                status="SKIPPED",
                rationale="No risk decision provided; nothing to execute in teaching mode.",
            )

        if not getattr(risk_decision, "allowed", True):
            print("[EXECUTION] Risk decision not allowed — skipping gateway")
            return ExecutionResult(
                symbol=risk_decision.symbol,
                trader_type=risk_decision.trader_type,
                attempted=False,
                status="BLOCKED",
                rationale="Risk engine blocked this trade; no execution attempted.",
                direction=risk_decision.direction,
                quantity=getattr(risk_decision, "max_position_size", 1),
                stop_loss_price=risk_decision.stop_loss_price,
                take_profit_price=risk_decision.take_profit_price,
            )

        tick = self.current_tick if self.current_tick is not None else 0
        order = self._order_from_risk_decision(risk_decision, tick)
        self._emit_order_submitted(order)
        return self._handle_order_attempt(order, tick)

    def _order_from_risk_decision(
        self, risk_decision: RiskDecision, tick: int
    ) -> OrderRequest:
        requested_quantity = max(
            1, int(getattr(risk_decision, "max_position_size", 1) or 1)
        )
        client_order_id = self._client_order_id(
            risk_decision.symbol,
            risk_decision.trader_type,
            risk_decision.strategy_name,
            risk_decision.direction,
            tick,
        )
        print(
            "[ORDER] submit "
            f"id={client_order_id} symbol={risk_decision.symbol} qty={requested_quantity} "
            f"trader_type={risk_decision.trader_type} attempt=1"
        )
        return OrderRequest(
            client_order_id=client_order_id,
            symbol=risk_decision.symbol,
            trader_type=risk_decision.trader_type,
            strategy_name=risk_decision.strategy_name,
            direction=risk_decision.direction,
            requested_quantity=requested_quantity,
            created_tick=tick,
            attempt_number=1,
            stop_loss_price=risk_decision.stop_loss_price,
            take_profit_price=risk_decision.take_profit_price,
        )

    def _emit_order_submitted(self, order: OrderRequest) -> None:
        self.event_collector.emit(
            event_type="ORDER_SUBMITTED",
            source="ExecutionEngine",
            payload={
                "client_order_id": order.client_order_id,
                "symbol": order.symbol,
                "trader_type": order.trader_type,
                "strategy_name": order.strategy_name,
                "direction": order.direction,
                "requested_quantity": order.requested_quantity,
                "created_tick": order.created_tick,
                "attempt_number": order.attempt_number,
            },
        )

    def _handle_order_attempt(self, order: OrderRequest, tick: int) -> ExecutionResult:
        decision, decision_key, mapping_r = self.gateway.decide_with_trace(
            order.symbol, tick, order.trader_type, order.attempt_number
        )
        order.last_decision = decision.value
        print(
            f"[GATEWAY] id={order.client_order_id} tick={tick} "
            f"attempt={order.attempt_number} decision={decision.value}"
        )
        self.event_collector.emit(
            event_type="ORDER_GATEWAY_DECISION",
            source="ExecutionEngine",
            payload={
                "client_order_id": order.client_order_id,
                "symbol": order.symbol,
                "trader_type": order.trader_type,
                "tick": tick,
                "attempt_number": order.attempt_number,
                "decision": decision.value,
                "deterministic_key": decision_key,
                "mapping_r": mapping_r,
            },
        )

        if decision == GatewayDecision.REJECT:
            return self._on_hard_reject(order, tick)

        if decision == GatewayDecision.SOFT_REJECT:
            return self._on_soft_reject(order, tick)

        return self._execute_liquidity(order, tick)

    def _on_hard_reject(self, order: OrderRequest, tick: int) -> ExecutionResult:
        self.pending_book.remove(order.client_order_id)
        self.event_collector.emit(
            event_type="ORDER_REJECTED_HARD",
            source="ExecutionEngine",
            payload={
                "client_order_id": order.client_order_id,
                "symbol": order.symbol,
                "trader_type": order.trader_type,
                "tick": tick,
                "attempt_number": order.attempt_number,
                "reason": "GATEWAY_HARD_REJECT",
            },
        )
        return ExecutionResult(
            symbol=order.symbol,
            trader_type=order.trader_type,
            attempted=False,
            status="REJECTED",
            rationale="Deterministic gateway hard rejected the order.",
            direction=order.direction,
            quantity=0,
            entry_price=None,
            raw_price=None,
            entry_tick=tick,
            stop_loss_price=order.stop_loss_price,
            take_profit_price=order.take_profit_price,
            requested_quantity=order.requested_quantity,
            filled_quantity=0,
            remaining_quantity=order.requested_quantity,
            fill_status="NONE",
            average_fill_price=None,
            note="Gateway hard reject — no liquidity attempted.",
            gateway_decision=GatewayDecision.REJECT.value,
            attempt_number=order.attempt_number,
            client_order_id=order.client_order_id,
            retry_scheduled=False,
            next_retry_tick=None,
            rejection_reason="GATEWAY_HARD_REJECT",
        )

    def _on_soft_reject(self, order: OrderRequest, tick: int) -> ExecutionResult:
        max_attempts = self._max_attempts(order.trader_type)
        if order.attempt_number >= max_attempts:
            self.event_collector.emit(
                event_type="ORDER_EXPIRED",
                source="ExecutionEngine",
                payload={
                    "client_order_id": order.client_order_id,
                    "symbol": order.symbol,
                    "trader_type": order.trader_type,
                    "tick": tick,
                    "attempt_number": order.attempt_number,
                    "reason": "MAX_ATTEMPTS_REACHED",
                },
            )
            print(
                f"[EXPIRE] id={order.client_order_id} attempts={order.attempt_number} "
                f"max={max_attempts} dropped"
            )
            return ExecutionResult(
                symbol=order.symbol,
                trader_type=order.trader_type,
                attempted=False,
                status="EXPIRED",
                rationale="Soft reject but max attempts reached; expiring order.",
                direction=order.direction,
                quantity=0,
                entry_price=None,
                raw_price=None,
                entry_tick=tick,
                stop_loss_price=order.stop_loss_price,
                take_profit_price=order.take_profit_price,
                requested_quantity=order.requested_quantity,
                filled_quantity=0,
                remaining_quantity=order.requested_quantity,
                fill_status="NONE",
                average_fill_price=None,
                note="Gateway soft reject expired at max attempts.",
                gateway_decision=GatewayDecision.SOFT_REJECT.value,
                attempt_number=order.attempt_number,
                client_order_id=order.client_order_id,
                retry_scheduled=False,
                next_retry_tick=None,
                rejection_reason="EXPIRED",
            )

        order.attempt_number += 1
        order.next_retry_tick = tick + 1
        self.pending_book.add(order)
        self.event_collector.emit(
            event_type="ORDER_RETRY_SCHEDULED",
            source="ExecutionEngine",
            payload={
                "client_order_id": order.client_order_id,
                "symbol": order.symbol,
                "trader_type": order.trader_type,
                "from_tick": tick,
                "next_retry_tick": order.next_retry_tick,
                "next_attempt_number": order.attempt_number,
            },
        )
        print(
            f"[RETRY] id={order.client_order_id} scheduled next_tick={order.next_retry_tick} "
            f"next_attempt={order.attempt_number}"
        )
        return ExecutionResult(
            symbol=order.symbol,
            trader_type=order.trader_type,
            attempted=False,
            status="RETRY_SCHEDULED",
            rationale="Gateway soft reject — retry scheduled.",
            direction=order.direction,
            quantity=0,
            entry_price=None,
            raw_price=None,
            entry_tick=tick,
            stop_loss_price=order.stop_loss_price,
            take_profit_price=order.take_profit_price,
            requested_quantity=order.requested_quantity,
            filled_quantity=0,
            remaining_quantity=order.requested_quantity,
            fill_status="NONE",
            average_fill_price=None,
            note="Gateway soft reject; will retry deterministically.",
            gateway_decision=GatewayDecision.SOFT_REJECT.value,
            attempt_number=order.attempt_number - 1,
            client_order_id=order.client_order_id,
            retry_scheduled=True,
            next_retry_tick=order.next_retry_tick,
            rejection_reason="GATEWAY_SOFT_REJECT",
        )

    def _execute_liquidity(self, order: OrderRequest, tick: int) -> ExecutionResult:
        available_liquidity = LiquidityModel.available_liquidity(
            symbol=order.symbol,
            tick=tick,
            trader_type=order.trader_type,
        )
        requested_quantity = order.requested_quantity
        filled_quantity = min(requested_quantity, available_liquidity)
        remaining_quantity = max(0, requested_quantity - filled_quantity)
        fill_status = "NONE"
        if filled_quantity == requested_quantity and requested_quantity > 0:
            fill_status = "FULL"
        elif 0 < filled_quantity < requested_quantity:
            fill_status = "PARTIAL"
        raw_price = self.price_feed.price_for(order.symbol, tick)

        if filled_quantity == 0:
            reason = (
                "LIQUIDITY_ZERO" if available_liquidity == 0 else "LIQUIDITY_CAP"
            )
            print(
                "[LIQUIDITY] "
                f"symbol={order.symbol} tick={tick} trader_type={order.trader_type} "
                f"requested={requested_quantity} available={available_liquidity} "
                f"filled={filled_quantity} remaining={remaining_quantity} "
                "status=NONE (no trade opened)"
            )
            self.event_collector.emit(
                event_type="TRADE_NOT_FILLED",
                source="ExecutionEngine",
                payload={
                    "symbol": order.symbol,
                    "trader_type": order.trader_type,
                    "tick": tick,
                    "requested_quantity": requested_quantity,
                    "available_liquidity": available_liquidity,
                    "filled_quantity": 0,
                    "remaining_quantity": remaining_quantity,
                    "reason": reason,
                    "fill_status": "NONE",
                    "client_order_id": order.client_order_id,
                    "attempt_number": order.attempt_number,
                    "gateway_decision": GatewayDecision.ACCEPT.value,
                },
            )
            return ExecutionResult(
                symbol=order.symbol,
                trader_type=order.trader_type,
                attempted=True,
                status="NOT_FILLED",
                rationale="Deterministic liquidity returned zero available volume.",
                direction=order.direction,
                quantity=0,
                entry_price=None,
                raw_price=raw_price,
                entry_tick=tick,
                stop_loss_price=order.stop_loss_price,
                take_profit_price=order.take_profit_price,
                requested_quantity=requested_quantity,
                filled_quantity=0,
                remaining_quantity=remaining_quantity,
                fill_status="NONE",
                average_fill_price=None,
                note="No fill: liquidity zero for this tick/symbol combination.",
                gateway_decision=GatewayDecision.ACCEPT.value,
                attempt_number=order.attempt_number,
                client_order_id=order.client_order_id,
                retry_scheduled=False,
                next_retry_tick=None,
                rejection_reason=None,
            )

        entry_price = SlippageModel.apply_slippage(
            price=raw_price,
            direction=order.direction,
            trader_type=order.trader_type,
            quantity=filled_quantity,
        )
        slippage_applied = round(entry_price - raw_price, 2)
        active_trade = ActiveTrade(
            symbol=order.symbol,
            trader_type=order.trader_type,
            entry_tick=tick,
            entry_price=entry_price,
            direction=order.direction,
            quantity=filled_quantity,
            strategy_name=order.strategy_name,
            stop_loss_price=order.stop_loss_price,
            take_profit_price=order.take_profit_price,
        )
        self.trade_registry.register_trade(active_trade)
        self.event_collector.emit(
            event_type="TRADE_OPENED",
            source="ExecutionEngine",
            payload={
                "symbol": order.symbol,
                "trader_type": order.trader_type,
                "strategy_name": order.strategy_name,
                "entry_tick": tick,
                "opened_at_tick": tick,
                "entry_price": entry_price,
                "raw_price": raw_price,
                "slippage_applied": slippage_applied,
                "execution_price": entry_price,
                "mode": self.run_mode.value,
                "direction": order.direction,
                "quantity": filled_quantity,
                "stop_loss_price": order.stop_loss_price,
                "take_profit_price": order.take_profit_price,
                "requested_quantity": requested_quantity,
                "filled_quantity": filled_quantity,
                "remaining_quantity": remaining_quantity,
                "fill_status": fill_status,
                "client_order_id": order.client_order_id,
                "attempt_number": order.attempt_number,
                "gateway_decision": GatewayDecision.ACCEPT.value,
            },
        )
        print(
            f"[EVENT] TRADE_OPENED emitted for "
            f"{order.symbol} ({order.trader_type})"
            f" tick={tick} price={entry_price}"
        )
        print(
            "[EXECUTION:REGISTRY] Registered active trade "
            f"symbol={order.symbol} trader_type={order.trader_type}"
        )
        print(
            "[EXECUTION:REGISTRY] Active trades for trader_type "
            f"{order.trader_type}: {self.trade_registry.count_active_by_trader(order.trader_type)}"
        )
        print(
            f"[EXECUTION] {self.run_mode.value} mode active — no broker calls; returning simulated result."
        )

        liquidity_note = None
        if fill_status == "PARTIAL":
            liquidity_note = "Partial fill due to deterministic liquidity cap."
            print(
                "[LIQUIDITY] "
                f"symbol={order.symbol} tick={tick} trader_type={order.trader_type} "
                f"requested={requested_quantity} available={available_liquidity} "
                f"filled={filled_quantity} remaining={remaining_quantity} "
                f"status=PARTIAL"
            )

        return ExecutionResult(
            symbol=order.symbol,
            trader_type=order.trader_type,
            attempted=True,
            status="SIMULATED",
            rationale="Teaching-only: routed by trader_type with deterministic gateway and liquidity.",
            direction=order.direction,
            quantity=filled_quantity,
            entry_price=entry_price,
            raw_price=raw_price,
            slippage_applied=slippage_applied,
            entry_tick=tick,
            stop_loss_price=order.stop_loss_price,
            take_profit_price=order.take_profit_price,
            requested_quantity=requested_quantity,
            filled_quantity=filled_quantity,
            remaining_quantity=remaining_quantity,
            fill_status=fill_status,
            average_fill_price=entry_price,
            note=liquidity_note,
            gateway_decision=GatewayDecision.ACCEPT.value,
            attempt_number=order.attempt_number,
            client_order_id=order.client_order_id,
            retry_scheduled=False,
            next_retry_tick=None,
            rejection_reason=None,
        )

    def complete_trade(self, symbol: str, trader_type: str) -> None:
        """
        Teaching helper to remove an active trade when a lifecycle ends.

        No broker integration; purely updates the in-memory registry.
        """

        self.trade_registry.unregister_trade(symbol, trader_type)
        print(
            "[EXECUTION:REGISTRY] Completed trade "
            f"symbol={symbol} trader_type={trader_type}; "
            f"remaining active={self.trade_registry.count_active_by_trader(trader_type)}"
        )

    def close_all_active_trades(self):
        """
        Teaching-first lifecycle reset.

        Closes and deregisters all active trades so capacity is freed in the
        ActiveTradeRegistry for future cycles.
        """

        closed_trades = self.trade_registry.close_all_trades()
        if not closed_trades:
            print("[EXECUTION:REGISTRY] No active trades to close — registry already empty.")
            return []

        print("[EXECUTION:REGISTRY] Closing all active trades and resetting registry")
        for trade in closed_trades:
            print(
                "[EXECUTION:REGISTRY] Closed trade "
                f"symbol={getattr(trade, 'symbol', 'UNKNOWN')} "
                f"trader_type={getattr(trade, 'trader_type', 'UNKNOWN')}"
            )

        print(
            "[EXECUTION:REGISTRY] All trades closed; registry capacity reset for next cycle"
        )
        return closed_trades

    def shutdown(self) -> None:
        """
        Idempotent shutdown placeholder.

        Future implementation will release broker resources, cancel orders,
        and flush telemetry. For now this acts as a structural hook to enable
        safe orchestrator shutdown sequencing.
        """

        print("[EXECUTION] Shutdown requested — placeholder cleanup complete.")
