"""
Execution engine that routes through a broker adapter with deterministic retry semantics.
"""

import hashlib
from typing import List, Optional

from brokers.base_broker import BaseBroker, BrokerOrderRequest
from brokers.sim_broker import SimBroker
from config.runtime_config import (
    RunMode,
    get_ibkr_readonly_enabled,
    get_live_micro_max_concurrent_trades,
    get_run_mode,
)
from config.trading_config import is_strategy_enabled
from core.active_trade_registry import ActiveTradeRegistry
from core.event_collector import EventCollector
from execution.order_gateway import OrderGateway
from execution.order_models import PendingOrderBook
from models.execution_result import ExecutionResult
from models.data_models import RiskDecision
from sim.price_feed import DeterministicPriceFeed, PriceFeed


class ExecutionEngine:
    """Deterministic execution engine with broker routing and retry semantics."""

    def __init__(
        self,
        broker: Optional[BaseBroker] = None,
        trade_registry: Optional[ActiveTradeRegistry] = None,
        event_collector: Optional[EventCollector] = None,
        price_feed: Optional[PriceFeed] = None,
    ) -> None:
        print("[BOOT] ExecutionEngine instantiated — broker-routed deterministic flow")
        self.run_mode: RunMode = get_run_mode()
        self.read_only_mode = self.run_mode == RunMode.LIVE_READ_ONLY
        self.ibkr_readonly_enabled = get_ibkr_readonly_enabled()
        self.readonly_gate_active = self.read_only_mode or (
            self.ibkr_readonly_enabled
            and self.run_mode in {RunMode.LIVE, RunMode.LIVE_READ_ONLY, RunMode.LIVE_MICRO}
        )
        if self.read_only_mode:
            print("[SAFETY] LIVE READ-ONLY MODE ACTIVE")
            print("[SAFETY] NO EXECUTION ENABLED")
        elif self.run_mode == RunMode.LIVE_MICRO:
            print("[SAFETY] LIVE MICRO-EXECUTION MODE ACTIVE")
            print("[SAFETY] 1-SHARE LIMIT ENFORCED")
        elif self.run_mode == RunMode.LIVE and self.ibkr_readonly_enabled:
            print("[SAFETY] IBKR READ-ONLY ENABLED (LIVE mode) — execution remains gated by broker.")
        if self.readonly_gate_active:
            print("[SAFETY] LIVE DATA — READ ONLY MODE")
            print("[SAFETY] NO ORDERS WILL BE SENT")
        self.trade_registry = trade_registry or ActiveTradeRegistry()
        self.event_collector = event_collector or EventCollector()
        self.price_feed = price_feed or DeterministicPriceFeed()
        self.pending_book = PendingOrderBook()
        self.current_tick: Optional[int] = None
        self._broker: BaseBroker = broker or SimBroker(
            gateway=OrderGateway(),
            price_feed=self.price_feed,
            trade_registry=self.trade_registry,
            event_collector=self.event_collector,
            run_mode=self.run_mode,
        )
        self.broker: BaseBroker = self._broker

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
            results.append(self._route_order(order))
        return results

    def execute_trade(self, risk_decision: Optional[RiskDecision]) -> ExecutionResult:
        """
        Convert a risk decision into a broker request and route through the broker adapter.
        """

        print("[EXECUTION] Received risk decision for broker-routed flow")
        if self.readonly_gate_active:
            return self._blocked_execution_from_risk_decision(risk_decision)
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
            print("[EXECUTION] Risk decision not allowed — skipping broker routing")
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

        if self.run_mode == RunMode.LIVE_MICRO:
            return self._execute_live_micro(risk_decision)

        tick = self.current_tick if self.current_tick is not None else 0
        order = self._order_from_risk_decision(risk_decision, tick)
        return self._route_order(order)

    def _execute_live_micro(self, risk_decision: RiskDecision) -> ExecutionResult:
        max_concurrent = get_live_micro_max_concurrent_trades()
        active_count = self.trade_registry.count_active()
        if active_count >= max_concurrent:
            rationale = (
                "LIVE_MICRO_BLOCK: max concurrent trade limit reached "
                f"({active_count}/{max_concurrent})."
            )
            print(f"[SAFETY] {rationale}")
            self.event_collector.emit(
                event_type="TRADE_BLOCKED",
                source="ExecutionEngine",
                payload={
                    "symbol": risk_decision.symbol,
                    "trader_type": risk_decision.trader_type,
                    "strategy_name": risk_decision.strategy_name,
                    "reason_code": "MAX_CONCURRENT_TRADES",
                    "human_readable_rationale": rationale,
                    "reason": rationale,
                },
            )
            return ExecutionResult(
                symbol=risk_decision.symbol,
                trader_type=risk_decision.trader_type,
                attempted=False,
                status="BLOCKED",
                rationale=rationale,
                direction=risk_decision.direction,
                quantity=getattr(risk_decision, "max_position_size", 1) or 1,
                stop_loss_price=risk_decision.stop_loss_price,
                take_profit_price=risk_decision.take_profit_price,
            )

        strategy_name = risk_decision.strategy_name or "UNKNOWN"
        if not is_strategy_enabled(strategy_name):
            rationale = (
                "LIVE_MICRO_BLOCK: strategy not approved for live micro-execution "
                f"(strategy={strategy_name})."
            )
            print(f"[SAFETY] {rationale}")
            self.event_collector.emit(
                event_type="TRADE_BLOCKED",
                source="ExecutionEngine",
                payload={
                    "symbol": risk_decision.symbol,
                    "trader_type": risk_decision.trader_type,
                    "strategy_name": strategy_name,
                    "reason_code": "STRATEGY_NOT_APPROVED",
                    "human_readable_rationale": rationale,
                    "reason": rationale,
                },
            )
            return ExecutionResult(
                symbol=risk_decision.symbol,
                trader_type=risk_decision.trader_type,
                attempted=False,
                status="BLOCKED",
                rationale=rationale,
                direction=risk_decision.direction,
                quantity=getattr(risk_decision, "max_position_size", 1) or 1,
                stop_loss_price=risk_decision.stop_loss_price,
                take_profit_price=risk_decision.take_profit_price,
            )

        requested_quantity = int(getattr(risk_decision, "max_position_size", 1) or 1)
        if requested_quantity != 1:
            rationale = (
                "LIVE_MICRO_BLOCK: quantity must be exactly 1 share "
                f"(requested={requested_quantity})."
            )
            print(f"[SAFETY] {rationale}")
            self.event_collector.emit(
                event_type="TRADE_BLOCKED",
                source="ExecutionEngine",
                payload={
                    "symbol": risk_decision.symbol,
                    "trader_type": risk_decision.trader_type,
                    "strategy_name": strategy_name,
                    "reason_code": "LIVE_MICRO_SIZE_LIMIT",
                    "human_readable_rationale": rationale,
                    "reason": rationale,
                },
            )
            return ExecutionResult(
                symbol=risk_decision.symbol,
                trader_type=risk_decision.trader_type,
                attempted=False,
                status="BLOCKED",
                rationale=rationale,
                direction=risk_decision.direction,
                quantity=requested_quantity,
                stop_loss_price=risk_decision.stop_loss_price,
                take_profit_price=risk_decision.take_profit_price,
            )

        tick = self.current_tick if self.current_tick is not None else 0
        order = self._order_from_risk_decision(risk_decision, tick)
        return self._route_order(order)

    def _order_from_risk_decision(
        self, risk_decision: RiskDecision, tick: int
    ) -> BrokerOrderRequest:
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
        return BrokerOrderRequest(
            client_order_id=client_order_id,
            symbol=risk_decision.symbol,
            direction=risk_decision.direction,
            quantity=requested_quantity,
            order_type="MKT",
            trader_type=risk_decision.trader_type,
            strategy_name=risk_decision.strategy_name,
            attempt_number=1,
            created_tick=tick,
            stop_loss_price=risk_decision.stop_loss_price,
            take_profit_price=risk_decision.take_profit_price,
            pattern_name=getattr(risk_decision, "pattern_name", None),
            invalidation_level=getattr(risk_decision, "invalidation_level", None),
            next_retry_tick=None,
        )

    def _route_order(self, request: BrokerOrderRequest) -> ExecutionResult:
        if self.readonly_gate_active:
            return self._blocked_execution_from_request(request)
        result = self._broker.place_order(request)
        if not self._broker.is_live():
            print(
                f"[EXECUTION] {self.run_mode.value} mode active — broker={self._broker.name()} deterministic flow."
            )
        else:
            print("[EXECUTION] LIVE broker stub result returned; no live order placed.")
        self._schedule_retry(request, result)
        return result

    def _blocked_execution_from_risk_decision(
        self, risk_decision: Optional[RiskDecision]
    ) -> ExecutionResult:
        if risk_decision is None:
            symbol = "UNKNOWN"
            trader_type = "MANUAL"
            direction = "UNKNOWN"
            quantity = 0
            strategy_name = "UNKNOWN"
        else:
            symbol = risk_decision.symbol
            trader_type = risk_decision.trader_type
            direction = risk_decision.direction
            quantity = getattr(risk_decision, "max_position_size", 1)
            strategy_name = risk_decision.strategy_name

        rationale = "READONLY_BLOCK: IBKR_READONLY_ENABLED active — execution blocked."
        self.event_collector.emit(
            event_type="ORDER_BLOCKED_READONLY",
            source="ExecutionEngine",
            payload={
                "symbol": symbol,
                "trader_type": trader_type,
                "strategy_name": strategy_name,
                "direction": direction,
                "requested_quantity": quantity,
                "run_mode": self.run_mode.value,
                "readonly_enabled": self.ibkr_readonly_enabled or self.read_only_mode,
                "reason": rationale,
            },
        )
        return ExecutionResult(
            symbol=symbol,
            trader_type=trader_type,
            attempted=False,
            status="BLOCKED",
            rationale=rationale,
            direction=direction,
            quantity=quantity,
            stop_loss_price=getattr(risk_decision, "stop_loss_price", None),
            take_profit_price=getattr(risk_decision, "take_profit_price", None),
            requested_quantity=quantity,
            filled_quantity=0,
            remaining_quantity=quantity,
            fill_status="NONE",
            note="ORDER_BLOCKED_READONLY",
            rejection_reason="ORDER_BLOCKED_READONLY",
        )

    def _blocked_execution_from_request(
        self, request: BrokerOrderRequest
    ) -> ExecutionResult:
        rationale = "READONLY_BLOCK: IBKR_READONLY_ENABLED active — execution blocked."
        self.event_collector.emit(
            event_type="ORDER_BLOCKED_READONLY",
            source="ExecutionEngine",
            payload={
                "symbol": request.symbol,
                "trader_type": request.trader_type or "UNKNOWN",
                "strategy_name": request.strategy_name or "UNKNOWN",
                "direction": request.direction,
                "requested_quantity": request.quantity,
                "run_mode": self.run_mode.value,
                "readonly_enabled": self.ibkr_readonly_enabled or self.read_only_mode,
                "reason": rationale,
            },
        )
        return ExecutionResult(
            symbol=request.symbol,
            trader_type=request.trader_type or "UNKNOWN",
            attempted=False,
            status="BLOCKED",
            rationale=rationale,
            direction=request.direction,
            quantity=request.quantity,
            stop_loss_price=request.stop_loss_price,
            take_profit_price=request.take_profit_price,
            requested_quantity=request.quantity,
            filled_quantity=0,
            remaining_quantity=request.quantity,
            fill_status="NONE",
            note="ORDER_BLOCKED_READONLY",
            rejection_reason="ORDER_BLOCKED_READONLY",
            attempt_number=request.attempt_number,
            client_order_id=request.client_order_id,
            retry_scheduled=False,
            next_retry_tick=None,
        )

    def _schedule_retry(self, request: BrokerOrderRequest, result: ExecutionResult) -> None:
        if self.readonly_gate_active:
            return
        if not getattr(result, "retry_scheduled", False) or result.next_retry_tick is None:
            return

        next_attempt = request.attempt_number + 1
        max_attempts = self._max_attempts(request.trader_type or "")
        if next_attempt > max_attempts:
            print(
                f"[RETRY] id={request.client_order_id} reached max attempts; not scheduling further retries."
            )
            return

        scheduled_request = BrokerOrderRequest(
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            direction=request.direction,
            quantity=request.quantity,
            order_type=request.order_type,
            trader_type=request.trader_type,
            strategy_name=request.strategy_name,
            attempt_number=next_attempt,
            created_tick=result.next_retry_tick,
            stop_loss_price=request.stop_loss_price,
            take_profit_price=request.take_profit_price,
            pattern_name=request.pattern_name,
            invalidation_level=request.invalidation_level,
            next_retry_tick=result.next_retry_tick,
        )
        self.pending_book.add(scheduled_request)
        print(
            f"[PENDING] Added retry for id={request.client_order_id} "
            f"attempt={next_attempt} tick={result.next_retry_tick}"
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
