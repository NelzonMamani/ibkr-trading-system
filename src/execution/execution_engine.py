"""
Execution engine that routes through a broker adapter with deterministic retry semantics.
"""

import hashlib
import os
from typing import List, Optional

from src.brokers.base_broker import BrokerOrderRequest
from src.config.config_resolver import get_config
from src.config.runtime_config import (
    RunMode,
    get_ibkr_readonly_enabled,
)
from src.core.active_trade_registry import ActiveTradeRegistry
from src.core.event_collector import EventCollector
from src.core.stop_controller import StopController
from src.core.managers.runtime_mode_manager import RuntimeModeManager
from src.execution.execution_providers import ExecutionProvider, PaperExecutionProvider
from src.execution.order_models import PendingOrderBook
from src.models.execution_result import ExecutionResult
from src.models.data_models import RiskDecision
from src.models.risk_decision import DECISION_ARTIFACT_MISSING
from src.sim.price_feed import DeterministicPriceFeed, PriceFeed


class ExecutionEngine:
    """Deterministic execution engine with broker routing and retry semantics."""

    def __init__(
        self,
        provider: Optional[ExecutionProvider] = None,
        trade_registry: Optional[ActiveTradeRegistry] = None,
        event_collector: Optional[EventCollector] = None,
        price_feed: Optional[PriceFeed] = None,
        stop_controller: Optional[StopController] = None,
    ) -> None:
        print("[BOOT] ExecutionEngine instantiated — broker-routed deterministic flow")
        self.run_mode: RunMode = RunMode(get_config("RUN_MODE_EFFECTIVE"))
        self.runtime_mode_manager = RuntimeModeManager.resolve()
        self.execution_enabled = bool(get_config("EXECUTION_ENABLED_EFFECTIVE"))
        self.max_shares_per_order = self.runtime_mode_manager.max_shares_per_order
        if not self.execution_enabled:
            print("[SAFETY] EXECUTION: HARD DISABLED")
            print("[EXECUTION] Gateway: DISABLED")
            print("[EXECUTION] Liquidity checks: DISABLED")
            print("[EXECUTION] Broker submission: DISABLED")
        elif self.run_mode == RunMode.PAPER:
            print("[SAFETY] PAPER-EXECUTION MODE ACTIVE")
        self.trade_registry = trade_registry or ActiveTradeRegistry()
        self.event_collector = event_collector or EventCollector()
        self.stop_controller = stop_controller or StopController()
        self.price_feed = price_feed or DeterministicPriceFeed()
        self.pending_book = PendingOrderBook()
        self.current_tick: Optional[int] = None
        self._seen_idempotency_keys: set[str] = set()
        self._provider = self._resolve_provider(provider)
        self.provider: Optional[ExecutionProvider] = self._provider
        self.broker = getattr(self._provider, "broker", None)

    def _resolve_provider(
        self, provider: Optional[ExecutionProvider]
    ) -> Optional[ExecutionProvider]:
        if not self.execution_enabled:
            if provider is not None:
                raise RuntimeError(
                    "Execution disabled; execution providers must not be instantiated."
                )
            return None
        if self.run_mode == RunMode.PAPER:
            if provider is not None and not isinstance(provider, PaperExecutionProvider):
                print("[EXECUTION][PAPER] Overriding non-paper provider with PaperExecutionProvider")
            return provider if isinstance(provider, PaperExecutionProvider) else PaperExecutionProvider(
                price_feed=self.price_feed,
                trade_registry=self.trade_registry,
                event_collector=self.event_collector,
                run_mode=self.run_mode,
            )
        if provider is None:
            raise RuntimeError(
                "Execution provider missing in live execution mode. "
                "Verify TWS/Gateway connectivity, RUN_MODE=LIVE, EXECUTION_ENABLED=true, "
                "IBKR_ORDER_SUBMISSION_ENABLED=true, IBKR_READONLY_ENABLED=false, and IBKR_LIVE_PORT=7496."
            )
        return provider

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

        tick = self.current_tick if self.current_tick is not None else 0
        idempotency_key = self._resolve_idempotency_key(risk_decision, tick)
        if self._is_duplicate(idempotency_key):
            return self._duplicate_result(risk_decision, idempotency_key)
        risk_decision.idempotency_key = idempotency_key

        preflight_result = self._preflight_check(risk_decision)
        if preflight_result is not None:
            return preflight_result

        gate_result = self._session_gate_check(risk_decision)
        if gate_result is not None:
            return gate_result

        order = self._order_from_risk_decision(risk_decision, tick)
        return self._route_order(order)

    def _session_gate_check(self, risk_decision: RiskDecision) -> Optional[ExecutionResult]:
        if os.getenv("TEST_PIPELINE_MODE") == "LIVE":
            print("[EXECUTION] test_pipeline_override=True")
            return None

        if self.run_mode == RunMode.PAPER:
            return None

        context = self._execution_context(risk_decision)
        if not context["execution_allowed"]:
            print("[EXECUTION][BLOCKED] reason=session_not_permitted")
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="SESSION_NOT_PERMITTED",
            )
        if not context["execution_ready"]:
            print("[EXECUTION][BLOCKED] reason=execution_not_ready")
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="EXECUTION_NOT_READY",
            )
        if context["prep_only"]:
            print("[EXECUTION][BLOCKED] reason=prep_only_mode")
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="PREP_ONLY_MODE",
            )
        return None

    @staticmethod
    def _execution_context(risk_decision: RiskDecision) -> dict:
        evaluated = getattr(risk_decision, "evaluated_limits", {}) or {}
        session = str(evaluated.get("session") or "UNKNOWN").upper()
        execution_allowed = bool(evaluated.get("execution_allowed", True))
        execution_ready = bool(evaluated.get("execution_ready", True))
        prep_only = bool(evaluated.get("prep_only", False))
        return {
            "session": session,
            "execution_allowed": execution_allowed,
            "execution_ready": execution_ready,
            "prep_only": prep_only,
        }

    def _preflight_check(self, risk_decision: RiskDecision) -> Optional[ExecutionResult]:
        if self.stop_controller.is_breaker_tripped():
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="CIRCUIT_BREAKER_TRIPPED",
            )
        if self.run_mode == RunMode.READ_ONLY:
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="LIVE_READ_ONLY_BLOCK",
            )
        if self.run_mode == RunMode.SIM:
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale=f"RUN_MODE_BLOCK:{self.run_mode.value}",
            )
        if self.run_mode not in {RunMode.PAPER, RunMode.LIVE}:
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale=f"RUN_MODE_BLOCK:{self.run_mode.value}",
            )
        if not self.execution_enabled:
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="EXECUTION_DISABLED",
            )
        if not getattr(risk_decision, "decision_id", None):
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale=DECISION_ARTIFACT_MISSING,
            )
        if get_ibkr_readonly_enabled() and self.run_mode == RunMode.LIVE:
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="BROKER_READONLY_BLOCK",
            )
        if self.run_mode == RunMode.LIVE and not getattr(risk_decision, "allowed", True):
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
        payload = {
            "symbol": risk_decision.symbol,
            "trader_type": risk_decision.trader_type,
            "strategy_name": risk_decision.strategy_name,
            "direction": risk_decision.direction,
            "requested_quantity": getattr(risk_decision, "max_position_size", 1),
            "stop_loss_price": risk_decision.stop_loss_price,
            "take_profit_price": risk_decision.take_profit_price,
            "tick": tick,
        }
        payload_components = [f"{key}={payload[key]}" for key in sorted(payload)]
        payload_fingerprint = "|".join(payload_components)

        decision_id = getattr(risk_decision, "decision_id", None)
        if decision_id:
            base = f"decision:{decision_id}|{payload_fingerprint}"
        else:
            intent_id = getattr(risk_decision, "intent_id", None)
            if intent_id:
                base = f"intent:{intent_id}|{payload_fingerprint}"
            else:
                base = f"payload:{payload_fingerprint}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]

    def _is_duplicate(self, idempotency_key: str) -> bool:
        if idempotency_key in self._seen_idempotency_keys:
            return True
        self._seen_idempotency_keys.add(idempotency_key)
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

    def _order_from_risk_decision(
        self, risk_decision: RiskDecision, tick: int
    ) -> BrokerOrderRequest:
        self._assert_execution_enabled_for_order_construction("risk decision")
        raw_quantity = int(getattr(risk_decision, "max_position_size", 0) or 0)
        if self.run_mode == RunMode.LIVE and raw_quantity <= 0:
            raise RuntimeError("INVALID_INTERNAL_ORDER_QUANTITY")
        raw_quantity = max(1, raw_quantity)
        requested_quantity = self._clamp_order_quantity(raw_quantity, symbol=risk_decision.symbol)
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
        if self._provider is None:
            raise RuntimeError("ExecutionEngine execution provider missing for execution path.")
        print(
            "[EXECUTION][AUDIT] "
            f"symbol={request.symbol} "
            f"side={request.direction} "
            f"size={request.quantity} "
            f"session={getattr(request, 'session', 'UNKNOWN')} "
            f"strategy={request.strategy_name or 'UNKNOWN'} "
            f"pattern={request.pattern_name or 'UNKNOWN'} "
            f"capital={request.quantity} "
            f"ibkr_order_id={request.client_order_id}"
        )
        result = self._provider.place_order(request)
        self._log_ibkr_status(request, result)
        if not self._provider.is_live():
            print(
                f"[EXECUTION] {self.run_mode.value} mode active — "
                f"provider={self._provider.name()} deterministic flow."
            )
        else:
            print("[EXECUTION] LIVE broker order routed.")
        self._schedule_retry(request, result)
        return result

    def _log_ibkr_status(self, request: BrokerOrderRequest, result: ExecutionResult) -> None:
        normalized = str(getattr(result, "status", "UNKNOWN") or "UNKNOWN").upper()
        print(f"[EXECUTION][IBKR] order_id={request.client_order_id} status={normalized}")
        if normalized in {"ACKED", "ACKNOWLEDGED"}:
            print(f"[EXECUTION][IBKR] order_id={request.client_order_id} status=ACKNOWLEDGED")
        if normalized in {"ACKED", "FILLED"} and getattr(result, "filled_quantity", 0) > 0:
            print(f"[EXECUTION][IBKR] order_id={request.client_order_id} status=FILLED")
        if normalized in {"BLOCKED", "FAILED", "REJECTED", "TIMED_OUT"}:
            print(f"[EXECUTION][IBKR] order_id={request.client_order_id} status=REJECTED")
        if normalized in {"CANCELLED", "CANCELED"}:
            print(f"[EXECUTION][IBKR] order_id={request.client_order_id} status=CANCELLED")

    def _clamp_order_quantity(self, quantity: int, *, symbol: str) -> int:
        if self.max_shares_per_order is None:
            return quantity
        clamped = min(max(1, int(quantity)), int(self.max_shares_per_order))
        if clamped != quantity:
            print(
                "[RISK][MICRO_CLAMP] "
                f"symbol={symbol} requested_qty={quantity} clamped_qty={clamped} "
                f"max_shares_per_order={self.max_shares_per_order}"
            )
        return clamped

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

        broker = getattr(self._provider, "broker", None)
        if broker is not None and hasattr(broker, "disconnect"):
            broker.disconnect(reason="execution_engine_shutdown")
        print("[EXECUTION] Shutdown requested — broker cleanup complete.")
