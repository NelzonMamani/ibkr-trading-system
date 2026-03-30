from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional

from src.adapters.brokers.ibkr.ibkr_order_submitter import (
    IbkrOrderSubmitter,
    OrderSubmissionSettings,
)
from src.adapters.brokers.ibkr.ibkr_order_translator import IbkrOrderTranslator
from src.adapters.brokers.ibkr.submission_guard import SubmissionGuard
from src.brokers.base_broker import BaseBroker, BrokerOrderRequest
from src.adapters.brokers.ibkr.ibkr_connection_manager import (
    IbkrConnectionManager,
    get_shared_ibkr_connection_manager,
)
from src.config.runtime_config import (
    RunMode,
    get_ibkr_ack_timeout_seconds,
    get_ibkr_default_currency,
    get_ibkr_default_exchange,
    get_ibkr_guard_persist_path,
    get_ibkr_kill_switch,
    get_ibkr_live_port,
    get_ibkr_max_orders_per_run,
    get_ibkr_order_submission_enabled,
    get_ibkr_order_translation_enabled,
    get_ibkr_paper_host,
    get_ibkr_paper_only_enforced,
    get_ibkr_paper_port,
    get_ibkr_readonly_enabled,
    get_risk_profile_name,
    is_execution_enabled,
)
from src.config.risk_profiles import RISK_PROFILES
from src.core.active_trade_registry import ActiveTrade, ActiveTradeRegistry
from src.core.position_lifecycle_engine import (
    LifecycleIntent,
    PositionLifecycle,
    PositionLifecycleEngine,
    PositionState,
)
from src.core.event_collector import EventCollector
from src.domain.models.internal_order import InternalOrder
from src.execution.exit_plan import compute_stop_price, compute_take_profit_price
from src.models.execution_result import ExecutionResult


@dataclass
class IbkrLiveBroker(BaseBroker):
    """
    Live execution broker for Phase 16.
    """

    event_collector: EventCollector
    trade_registry: ActiveTradeRegistry
    run_mode: RunMode = RunMode.LIVE
    connection_manager: Optional[IbkrConnectionManager] = field(default=None)
    translator: Optional[IbkrOrderTranslator] = field(default=None)
    submitter: Optional[IbkrOrderSubmitter] = field(default=None)

    def __post_init__(self) -> None:
        if self.run_mode == RunMode.LIVE and not is_execution_enabled(self.run_mode):
            raise RuntimeError("EXECUTION_ENABLED must be True for broker execution.")
        if get_ibkr_readonly_enabled() and self.run_mode == RunMode.LIVE:
            raise RuntimeError("IBKR_READONLY_ENABLED must be False for LIVE execution.")
        if not get_ibkr_order_translation_enabled():
            raise RuntimeError("IBKR order translation disabled; cannot submit live orders.")
        if not get_ibkr_order_submission_enabled(default=False):
            raise RuntimeError("IBKR order submission disabled; enable IBKR_ORDER_SUBMISSION_ENABLED.")

        if self.connection_manager is None:
            self.connection_manager = get_shared_ibkr_connection_manager(readonly_enabled=False)
        if self.translator is None:
            self.translator = IbkrOrderTranslator(
                order_translation_enabled=True,
                default_exchange=get_ibkr_default_exchange(),
                default_currency=get_ibkr_default_currency(),
            )
        paper_only_enforced = get_ibkr_paper_only_enforced()
        if self.run_mode == RunMode.LIVE:
            paper_only_enforced = False
            print("[EXECUTION][MODE] LIVE execution unlocked")

        kill_switch_enabled = get_ibkr_kill_switch() if self.run_mode == RunMode.LIVE else False
        if self.run_mode == RunMode.PAPER and get_ibkr_kill_switch():
            print("[EXECUTION][PAPER] Ignoring IBKR_KILL_SWITCH for paper submission path")

        settings = OrderSubmissionSettings(
            run_mode=self.run_mode,
            order_submission_enabled=get_ibkr_order_submission_enabled(default=False),
            kill_switch=kill_switch_enabled,
            max_orders_per_run=get_ibkr_max_orders_per_run(),
            paper_only_enforced=paper_only_enforced,
            paper_host=get_ibkr_paper_host(),
            paper_port=get_ibkr_paper_port(),
            live_port=get_ibkr_live_port(),
            submit_only_symbol=None,
            ack_timeout_seconds=get_ibkr_ack_timeout_seconds(),
            client_id=self.connection_manager.config.base_client_id,
            submit_only_order_type=None,
            allow_shorting=False,
        )
        guard = SubmissionGuard(
            max_orders_per_run=settings.max_orders_per_run,
            persist_path=get_ibkr_guard_persist_path(),
        )
        self.submitter = IbkrOrderSubmitter(
            ibkr_client=None,
            translator=self.translator,
            event_bus=self.event_collector,
            config=settings,
            guard=guard,
            client_provider=self.connection_manager.get_client,
        )

    def name(self) -> str:
        return "IBKR_LIVE_BROKER"

    def is_live(self) -> bool:
        return True

    def ensure_connection(self) -> None:
        assert self.connection_manager is not None
        client = self.connection_manager.ensure_connected()
        metadata = self.connection_manager.connection_metadata()
        print(
            "[TRACE][stage=broker_connection] "
            f"owner={self.__class__.__name__} host={metadata.get('host')} port={metadata.get('port')} "
            f"client_id={metadata.get('connected_client_id')} connected={client.is_connected()}"
        )

    def disconnect(self, reason: str = "manual") -> None:
        if self.connection_manager is None:
            return
        self.connection_manager.disconnect(reason=reason)

    def place_order(self, request: BrokerOrderRequest) -> ExecutionResult:
        profile_name = str(get_risk_profile_name() or "NORMAL").upper()
        profile = RISK_PROFILES.get(profile_name)
        if profile and profile.max_shares is not None and request.quantity > profile.max_shares:
            rationale = f"RISK_PROFILE_{profile_name}_SIZE_LIMIT"
            return ExecutionResult(
                symbol=request.symbol,
                trader_type=request.trader_type or "UNKNOWN",
                attempted=False,
                status="BLOCKED",
                rationale=rationale,
                direction=request.direction,
                quantity=request.quantity,
                requested_quantity=request.quantity,
                filled_quantity=0,
                remaining_quantity=request.quantity,
                fill_status="NONE",
                note=rationale,
                rejection_reason=rationale,
                client_order_id=request.client_order_id,
                attempt_number=request.attempt_number,
            )

        cycle_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        trace_id = f"{request.client_order_id}-{uuid4().hex[:8]}"
        timestamp = datetime.now(timezone.utc).isoformat()
        print(
            "[TRACE] "
            f"cycle_id={cycle_id} trace_id={trace_id} symbol={request.symbol} mode={self.run_mode.value} "
            f"stage=order_intake approved_quantity={request.quantity}"
        )
        if int(request.quantity) <= 0:
            return ExecutionResult(
                symbol=request.symbol,
                trader_type=request.trader_type or "UNKNOWN",
                attempted=False,
                status="BLOCKED",
                rationale="INVALID_INTERNAL_ORDER_QUANTITY",
                direction=request.direction,
                quantity=request.quantity,
                requested_quantity=request.quantity,
                filled_quantity=0,
                remaining_quantity=request.quantity,
                fill_status="NONE",
                note="INVALID_INTERNAL_ORDER_QUANTITY",
                rejection_reason="INVALID_INTERNAL_ORDER_QUANTITY",
                client_order_id=request.client_order_id,
                attempt_number=request.attempt_number,
            )
        self.event_collector.emit(
            event_type="ORDER_SUBMITTED",
            source="IbkrLiveBroker",
            payload={
                "client_order_id": request.client_order_id,
                "symbol": request.symbol,
                "trader_type": request.trader_type,
                "strategy_name": request.strategy_name,
                "direction": request.direction,
                "requested_quantity": request.quantity,
                "created_tick": request.created_tick or 0,
                "attempt_number": request.attempt_number,
                "order_type": request.order_type,
                "quantity": request.quantity,
                "timestamp": timestamp,
            },
        )

        internal_order = InternalOrder(
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            direction=request.direction,
            quantity=request.quantity,
            order_type=request.order_type,
            limit_price=None,
            time_in_force="DAY",
            strategy_name=request.strategy_name or "UNKNOWN",
            trader_type=request.trader_type or "UNKNOWN",
        )

        print(
            "[TRACE] "
            f"cycle_id={cycle_id} trace_id={trace_id} symbol={request.symbol} "
            f"stage=order_build internal_order_quantity={internal_order.quantity}"
        )
        if int(internal_order.quantity) != int(request.quantity):
            return ExecutionResult(
                symbol=request.symbol,
                trader_type=request.trader_type or "UNKNOWN",
                attempted=False,
                status="BLOCKED",
                rationale="EXECUTION_QUANTITY_MISMATCH",
                direction=request.direction,
                quantity=request.quantity,
                requested_quantity=request.quantity,
                filled_quantity=0,
                remaining_quantity=request.quantity,
                fill_status="NONE",
                note="EXECUTION_QUANTITY_MISMATCH",
                rejection_reason="EXECUTION_QUANTITY_MISMATCH",
                client_order_id=request.client_order_id,
                attempt_number=request.attempt_number,
            )
        try:
            self.ensure_connection()
            assert self.submitter is not None
            result = self.submitter.submit_once(internal_order)
        except Exception as exc:
            rationale = f"LIVE_SUBMISSION_FAILED: {exc}"
            return ExecutionResult(
                symbol=request.symbol,
                trader_type=request.trader_type or "UNKNOWN",
                attempted=False,
                status="FAILED",
                rationale=rationale,
                direction=request.direction,
                quantity=request.quantity,
                requested_quantity=request.quantity,
                filled_quantity=0,
                remaining_quantity=request.quantity,
                fill_status="NONE",
                note="IBKR_SUBMISSION_FAILED",
                rejection_reason=str(exc),
                client_order_id=request.client_order_id,
                attempt_number=request.attempt_number,
            )

        average_fill_price = (
            float(result.average_fill_price)
            if result.average_fill_price is not None
            else None
        )
        filled_quantity = int(result.filled_quantity or 0)
        remaining_quantity = int(result.remaining_quantity or request.quantity)
        fill_status = result.fill_status or "NONE"
        resolved_stop_loss = request.stop_loss_price
        resolved_take_profit = request.take_profit_price

        if fill_status in {"FULL", "PARTIAL"} and filled_quantity > 0:
            entry_price = average_fill_price
            if entry_price is not None:
                pattern_name = request.pattern_name
                if resolved_stop_loss is None:
                    resolved_stop_loss = request.invalidation_level
                if resolved_stop_loss is None:
                    resolved_stop_loss = compute_stop_price(
                        entry_price,
                        request.direction,
                        pattern_name=pattern_name,
                        strategy_name=request.strategy_name,
                    )
                if resolved_take_profit is None:
                    resolved_take_profit = compute_take_profit_price(
                        entry_price,
                        resolved_stop_loss,
                        request.direction,
                        pattern_name=pattern_name,
                        strategy_name=request.strategy_name,
                    )
                active_trade = ActiveTrade(
                    symbol=request.symbol,
                    trader_type=request.trader_type or "UNKNOWN",
                    entry_tick=request.created_tick or 0,
                    entry_price=entry_price,
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
                    source="IbkrLiveBroker",
                    payload={
                        "symbol": request.symbol,
                        "trader_type": request.trader_type or "UNKNOWN",
                        "strategy_name": request.strategy_name or "UNKNOWN",
                        "pattern_name": pattern_name,
                        "stop_loss_price": float(resolved_stop_loss),
                        "take_profit_price": float(resolved_take_profit),
                        "rationale": "Protective stop assigned immediately upon fill.",
                        "tick": request.created_tick or 0,
                    },
                )
                self.trade_registry.register_trade(active_trade)
                if active_trade.state_history:
                    last_transition = active_trade.state_history[-1]
                    if last_transition.get("to") == "OPEN":
                        self.event_collector.emit(
                            event_type="TRADE_STATE_UPDATED",
                            source="IbkrLiveBroker",
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
                    source="IbkrLiveBroker",
                    payload={
                        "symbol": request.symbol,
                        "trader_type": request.trader_type or "UNKNOWN",
                        "strategy_name": request.strategy_name or "UNKNOWN",
                        "entry_tick": request.created_tick or 0,
                        "opened_at_tick": request.created_tick or 0,
                        "entry_price": float(entry_price),
                        "raw_price": float(entry_price),
                        "slippage_applied": 0.0,
                        "execution_price": float(entry_price),
                        "mode": self.run_mode.value,
                        "direction": request.direction,
                        "quantity": filled_quantity,
                        "stop_loss_price": float(resolved_stop_loss),
                        "take_profit_price": float(resolved_take_profit),
                        "requested_quantity": request.quantity,
                        "filled_quantity": filled_quantity,
                        "remaining_quantity": remaining_quantity,
                        "fill_status": fill_status,
                        "client_order_id": request.client_order_id,
                        "attempt_number": request.attempt_number,
                        "gateway_decision": "LIVE",
                        "pattern_name": pattern_name,
                    },
                )
                lifecycle_engine = PositionLifecycleEngine(event_collector=self.event_collector)
                lifecycle_position = PositionLifecycle(
                    symbol=request.symbol,
                    trader_type=request.trader_type or "UNKNOWN",
                    quantity=0,
                    state=PositionState.FLAT,
                )
                lifecycle_engine.apply_intent(
                    lifecycle_position,
                    LifecycleIntent.OPEN,
                    requested_quantity=filled_quantity,
                    run_mode=self.run_mode,
                    reason="Live fill recorded",
                    risk_approved=True,
                    filled_quantity_override=filled_quantity,
                    fill_status_override=fill_status,
                )

        status = "ACKED" if result.status == "ACKED" else result.status
        attempted = result.status in {"ACKED"}
        print(
            "[TRACE] "
            f"cycle_id={cycle_id} trace_id={trace_id} symbol={request.symbol} stage=submission "
            f"submitted_qty={request.quantity} final_execution_status={status}"
        )

        return ExecutionResult(
            symbol=request.symbol,
            trader_type=request.trader_type or "UNKNOWN",
            attempted=attempted,
            status=status,
            rationale=result.error or "Live micro order submission completed.",
            direction=request.direction,
            quantity=request.quantity,
            entry_price=average_fill_price,
            stop_loss_price=resolved_stop_loss,
            take_profit_price=resolved_take_profit,
            requested_quantity=request.quantity,
            filled_quantity=filled_quantity,
            remaining_quantity=remaining_quantity,
            fill_status=fill_status,
            average_fill_price=average_fill_price,
            commission=result.commission or 0.0,
            note="LIVE_EXECUTION",
            attempt_number=request.attempt_number,
            client_order_id=request.client_order_id,
            retry_scheduled=False,
            next_retry_tick=None,
            gateway_decision="BLOCK" if status == "BLOCKED" else "LIVE",
            rejection_reason=result.rejection_reason or result.error,
            broker_error_code=result.broker_error_code,
            broker_error_message=result.broker_error_message,
        )

    def cancel_order(self, client_order_id: str) -> None:
        raise RuntimeError("Live order cancellation not implemented in LIVE mode.")

    def replace_order(self, client_order_id: str, new_request: BrokerOrderRequest) -> None:
        raise RuntimeError("Live order replace not implemented in LIVE mode.")
