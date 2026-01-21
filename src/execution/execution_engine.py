"""
Execution engine that routes through a broker adapter with deterministic retry semantics.
"""

import hashlib
from typing import List, Optional

from src.brokers.base_broker import BaseBroker, BrokerOrderRequest
from src.brokers.sim_broker import SimBroker
from src.config.config_resolver import get_config
from src.config.runtime_config import (
    RunMode,
    get_ibkr_readonly_enabled,
    get_ibkr_submit_only_symbol,
    get_live_micro_max_symbols_per_cycle,
    get_paper_max_concurrent_trades,
)
from src.config.trading_config import is_strategy_enabled
from src.core.active_trade_registry import ActiveTradeRegistry
from src.core.event_collector import EventCollector
from src.core.stop_controller import StopController
from src.execution.order_gateway import OrderGateway
from src.execution.order_models import PendingOrderBook
from src.models.execution_result import ExecutionResult
from src.models.data_models import RiskDecision
from src.sim.price_feed import DeterministicPriceFeed, PriceFeed


class ExecutionEngine:
    """Deterministic execution engine with broker routing and retry semantics."""

    def __init__(
        self,
        broker: Optional[BaseBroker] = None,
        trade_registry: Optional[ActiveTradeRegistry] = None,
        event_collector: Optional[EventCollector] = None,
        price_feed: Optional[PriceFeed] = None,
        stop_controller: Optional[StopController] = None,
    ) -> None:
        print("[BOOT] ExecutionEngine instantiated — broker-routed deterministic flow")
        self.run_mode: RunMode = RunMode(get_config("RUN_MODE_EFFECTIVE"))
        self.execution_enabled = bool(get_config("EXECUTION_ENABLED_EFFECTIVE"))
        if not self.execution_enabled:
            print("[SAFETY] EXECUTION: HARD DISABLED")
            print("[EXECUTION] Gateway: DISABLED")
            print("[EXECUTION] Liquidity checks: DISABLED")
            print("[EXECUTION] Broker submission: DISABLED")
        elif self.run_mode == RunMode.LIVE_MICRO:
            print("[SAFETY] LIVE MICRO-EXECUTION MODE ACTIVE")
            print("[SAFETY] 1-SHARE LIMIT ENFORCED")
        elif self.run_mode == RunMode.PAPER:
            print("[SAFETY] PAPER-EXECUTION MODE ACTIVE")
            print("[SAFETY] 1-SHARE LIMIT ENFORCED")
        self.trade_registry = trade_registry or ActiveTradeRegistry()
        self.event_collector = event_collector or EventCollector()
        self.stop_controller = stop_controller or StopController()
        self.price_feed = price_feed or DeterministicPriceFeed()
        self.pending_book = PendingOrderBook()
        self.current_tick: Optional[int] = None
        self._idempotency_cache: dict[int, set[str]] = {}
        self._last_idempotency_tick: Optional[int] = None
        self._live_micro_symbols_this_cycle: set[str] = set()
        if self.run_mode == RunMode.SIM:
            if self.execution_enabled:
                if broker is not None and not isinstance(broker, SimBroker):
                    print("[EXECUTION][SIM] Overriding non-SIM broker with SIM broker")
                self._broker = SimBroker(
                    gateway=OrderGateway(),
                    price_feed=self.price_feed,
                    trade_registry=self.trade_registry,
                    event_collector=self.event_collector,
                    run_mode=self.run_mode,
                )
            else:
                if broker is not None:
                    raise RuntimeError(
                        "Execution disabled; broker adapters must not be instantiated."
                    )
                self._broker = None
        else:
            if not self.execution_enabled:
                if broker is not None:
                    raise RuntimeError(
                        "Execution disabled; broker adapters must not be instantiated."
                    )
                self._broker = None
            else:
                if broker is None:
                    print(
                        "[EXECUTION][WARN] Broker adapter missing; "
                        "forcing execution disabled for safety."
                    )
                    self.execution_enabled = False
                    self._broker = None
                else:
                    self._broker = broker
        self.broker: Optional[BaseBroker] = self._broker

    @staticmethod
    def _max_attempts(trader_type: str) -> int:
        normalized = (trader_type or "").upper()
        limits = get_config("EXECUTION_MAX_ATTEMPTS_BY_TRADER")
        if normalized in limits:
            return int(limits[normalized])
        return int(limits.get("DEFAULT", 1))

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
        if risk_decision is None:
            print("[EXECUTION] No execution performed — placeholder path")
            return ExecutionResult(
                symbol="UNKNOWN",
                trader_type="MANUAL",
                attempted=False,
                status="SKIPPED",
                rationale="No risk decision provided; nothing to execute in teaching mode.",
            )

        preflight_result = self._preflight_check(risk_decision)
        if preflight_result is not None:
            return preflight_result

        tick = self.current_tick if self.current_tick is not None else 0
        idempotency_key = self._resolve_idempotency_key(risk_decision, tick)
        if self._is_duplicate(idempotency_key, tick):
            return self._duplicate_result(risk_decision, idempotency_key)
        risk_decision.idempotency_key = idempotency_key

        if self.run_mode == RunMode.LIVE_MICRO:
            return self._execute_live_micro(risk_decision)
        if self.run_mode == RunMode.PAPER:
            return self._execute_paper(risk_decision)

        order = self._order_from_risk_decision(risk_decision, tick)
        return self._route_order(order)

    def _preflight_check(self, risk_decision: RiskDecision) -> Optional[ExecutionResult]:
        if self.stop_controller.is_breaker_tripped():
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="CIRCUIT_BREAKER_TRIPPED",
            )
        if self.run_mode == RunMode.LIVE_READ_ONLY:
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="LIVE_READ_ONLY_BLOCK",
            )
        if self.run_mode not in {RunMode.SIM, RunMode.PAPER, RunMode.LIVE_MICRO, RunMode.LIVE}:
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale=f"RUN_MODE_BLOCK:{self.run_mode.value}",
            )
        if not self.execution_enabled:
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="EXECUTION_DISABLED",
            )
        if get_ibkr_readonly_enabled() and self.run_mode in {RunMode.LIVE, RunMode.LIVE_MICRO}:
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="BROKER_READONLY_BLOCK",
            )
        if not getattr(risk_decision, "allowed", True):
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
        return None

    def _resolve_idempotency_key(self, risk_decision: RiskDecision, tick: int) -> str:
        intent_id = getattr(risk_decision, "intent_id", None)
        if intent_id:
            base = f"{intent_id}|{tick}"
        else:
            base = (
                f"{risk_decision.symbol}|{risk_decision.trader_type}|"
                f"{risk_decision.strategy_name}|{risk_decision.direction}|"
                f"{getattr(risk_decision, 'max_position_size', 1)}|{tick}"
            )
        return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]

    def _is_duplicate(self, idempotency_key: str, tick: int) -> bool:
        if self._last_idempotency_tick != tick:
            self._idempotency_cache[tick] = set()
            self._last_idempotency_tick = tick
        seen = self._idempotency_cache.setdefault(tick, set())
        if idempotency_key in seen:
            return True
        seen.add(idempotency_key)
        return False

    def _duplicate_result(
        self, risk_decision: RiskDecision, idempotency_key: str
    ) -> ExecutionResult:
        self.event_collector.emit(
            event_type="ORDER_BLOCKED_READONLY",
            source="ExecutionEngine",
            payload={
                "symbol": risk_decision.symbol,
                "trader_type": risk_decision.trader_type,
                "strategy_name": risk_decision.strategy_name,
                "direction": risk_decision.direction,
                "requested_quantity": getattr(risk_decision, "max_position_size", 1),
                "run_mode": self.run_mode.value,
                "execution_enabled": self.execution_enabled,
                "readonly_enabled": get_ibkr_readonly_enabled(),
                "reason": "IDEMPOTENT_DUPLICATE",
                "idempotency_key": idempotency_key,
            },
        )
        return ExecutionResult(
            symbol=risk_decision.symbol,
            trader_type=risk_decision.trader_type,
            attempted=False,
            status="DUPLICATE",
            rationale="Duplicate intent detected; skipping submission.",
            direction=risk_decision.direction,
            quantity=getattr(risk_decision, "max_position_size", 1),
            stop_loss_price=risk_decision.stop_loss_price,
            take_profit_price=risk_decision.take_profit_price,
            requested_quantity=getattr(risk_decision, "max_position_size", 1),
            filled_quantity=0,
            remaining_quantity=getattr(risk_decision, "max_position_size", 1),
            fill_status="NONE",
            note="IDEMPOTENT_DUPLICATE",
            rejection_reason="IDEMPOTENT_DUPLICATE",
            client_order_id=idempotency_key,
        )

    def _execute_live_micro(self, risk_decision: RiskDecision) -> ExecutionResult:
        tick = self.current_tick if self.current_tick is not None else 0
        if self._last_idempotency_tick != tick:
            self._live_micro_symbols_this_cycle = set()

        symbol = risk_decision.symbol
        self._live_micro_symbols_this_cycle.add(symbol)
        max_symbols = get_live_micro_max_symbols_per_cycle()
        if len(self._live_micro_symbols_this_cycle) > max_symbols:
            rationale = (
                "LIVE_MICRO_BLOCK: max symbols per cycle exceeded "
                f"({len(self._live_micro_symbols_this_cycle)}/{max_symbols})."
            )
            print(f"[SAFETY] {rationale}")
            self.event_collector.emit(
                event_type="TRADE_BLOCKED",
                source="ExecutionEngine",
                payload={
                    "symbol": symbol,
                    "trader_type": risk_decision.trader_type,
                    "strategy_name": risk_decision.strategy_name,
                    "reason_code": "LIVE_MICRO_SYMBOL_CAP",
                    "human_readable_rationale": rationale,
                    "reason": rationale,
                },
            )
            return ExecutionResult(
                symbol=symbol,
                trader_type=risk_decision.trader_type,
                attempted=False,
                status="BLOCKED",
                rationale=rationale,
                direction=risk_decision.direction,
                quantity=getattr(risk_decision, "max_position_size", 1) or 1,
                stop_loss_price=risk_decision.stop_loss_price,
                take_profit_price=risk_decision.take_profit_price,
            )

        max_concurrent = get_config("LIVE_MICRO_MAX_CONCURRENT_TRADES")
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
        required_quantity = int(get_config("LIVE_MICRO_REQUIRED_QUANTITY"))
        if requested_quantity != required_quantity:
            rationale = (
                "LIVE_MICRO_BLOCK: quantity must be exactly "
                f"{required_quantity} share(s) (requested={requested_quantity})."
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

        submit_only_symbol = get_ibkr_submit_only_symbol()
        if submit_only_symbol and submit_only_symbol != risk_decision.symbol:
            rationale = (
                "LIVE_MICRO_BLOCK: symbol not on allowlist "
                f"(symbol={risk_decision.symbol} allowed={submit_only_symbol})."
            )
            print(f"[SAFETY] {rationale}")
            self.event_collector.emit(
                event_type="TRADE_BLOCKED",
                source="ExecutionEngine",
                payload={
                    "symbol": risk_decision.symbol,
                    "trader_type": risk_decision.trader_type,
                    "strategy_name": strategy_name,
                    "reason_code": "LIVE_MICRO_SYMBOL_ALLOWLIST",
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

    def _execute_paper(self, risk_decision: RiskDecision) -> ExecutionResult:
        symbol = risk_decision.symbol
        max_concurrent = get_paper_max_concurrent_trades()
        active_count = self.trade_registry.count_active()
        if active_count >= max_concurrent:
            rationale = (
                "PAPER_BLOCK: max concurrent trade limit reached "
                f"({active_count}/{max_concurrent})."
            )
            print(f"[SAFETY] {rationale}")
            self.event_collector.emit(
                event_type="TRADE_BLOCKED",
                source="ExecutionEngine",
                payload={
                    "symbol": symbol,
                    "trader_type": risk_decision.trader_type,
                    "strategy_name": risk_decision.strategy_name,
                    "reason_code": "MAX_CONCURRENT_TRADES",
                    "human_readable_rationale": rationale,
                    "reason": rationale,
                },
            )
            return ExecutionResult(
                symbol=symbol,
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
                "PAPER_BLOCK: quantity must be exactly 1 share "
                f"(requested={requested_quantity})."
            )
            print(f"[SAFETY] {rationale}")
            self.event_collector.emit(
                event_type="TRADE_BLOCKED",
                source="ExecutionEngine",
                payload={
                    "symbol": symbol,
                    "trader_type": risk_decision.trader_type,
                    "strategy_name": risk_decision.strategy_name,
                    "reason_code": "PAPER_SIZE_LIMIT",
                    "human_readable_rationale": rationale,
                    "reason": rationale,
                },
            )
            return ExecutionResult(
                symbol=symbol,
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
        self._assert_execution_enabled_for_order_construction("risk decision")
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
        if not self.execution_enabled:
            raise RuntimeError("Execution disabled: refusing to route order.")
        if self._broker is None:
            raise RuntimeError("ExecutionEngine broker adapter missing for execution path.")
        result = self._broker.place_order(request)
        if not self._broker.is_live():
            print(
                f"[EXECUTION] {self.run_mode.value} mode active — broker={self._broker.name()} deterministic flow."
            )
        else:
            print("[EXECUTION] LIVE broker order routed.")
        self._schedule_retry(request, result)
        return result

    def _blocked_execution_from_risk_decision(
        self, risk_decision: Optional[RiskDecision], rationale: str = "EXECUTION_DISABLED"
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
                "execution_enabled": self.execution_enabled,
                "readonly_enabled": get_ibkr_readonly_enabled(),
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
            note=rationale,
            rejection_reason=rationale,
        )

    def _blocked_execution_from_request(
        self, request: BrokerOrderRequest
    ) -> ExecutionResult:
        rationale = "EXECUTION_DISABLED"
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
                "execution_enabled": self.execution_enabled,
                "readonly_enabled": get_ibkr_readonly_enabled(),
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
            note="EXECUTION_DISABLED",
            rejection_reason="EXECUTION_DISABLED",
            attempt_number=request.attempt_number,
            client_order_id=request.client_order_id,
            retry_scheduled=False,
            next_retry_tick=None,
        )

    def _schedule_retry(self, request: BrokerOrderRequest, result: ExecutionResult) -> None:
        if not self.execution_enabled:
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

        self._assert_execution_enabled_for_order_construction("retry schedule")
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

    def _assert_execution_enabled_for_order_construction(self, context: str) -> None:
        if not self.execution_enabled:
            raise RuntimeError(
                "Execution disabled: order construction blocked "
                f"(context={context})."
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
