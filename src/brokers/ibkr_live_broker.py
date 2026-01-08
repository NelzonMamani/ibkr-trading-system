from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from adapters.brokers.ibkr.ibkr_client import IbkrClient
from adapters.brokers.ibkr.ibkr_order_submitter import (
    IbkrOrderSubmitter,
    OrderSubmissionSettings,
)
from adapters.brokers.ibkr.ibkr_order_translator import IbkrOrderTranslator
from adapters.brokers.ibkr.submission_guard import SubmissionGuard
from brokers.base_broker import BaseBroker, BrokerOrderRequest
from config.runtime_config import (
    RunMode,
    get_ibkr_ack_timeout_seconds,
    get_ibkr_client_id_order_submit,
    get_ibkr_default_currency,
    get_ibkr_default_exchange,
    get_ibkr_guard_persist_path,
    get_ibkr_host,
    get_ibkr_kill_switch,
    get_ibkr_live_port,
    get_ibkr_market_data_type,
    get_ibkr_max_orders_per_run,
    get_ibkr_order_submission_enabled,
    get_ibkr_order_translation_enabled,
    get_ibkr_paper_host,
    get_ibkr_paper_only_enforced,
    get_ibkr_paper_port,
    get_ibkr_readonly_enabled,
    get_ibkr_snapshot_timeout_seconds,
)
from core.active_trade_registry import ActiveTrade, ActiveTradeRegistry
from core.event_collector import EventCollector
from domain.models.internal_order import InternalOrder
from models.execution_result import ExecutionResult


@dataclass
class IbkrLiveBroker(BaseBroker):
    """
    Live micro-execution broker for Phase 16.

    Submits real IBKR orders under strict micro-execution constraints.
    """

    event_collector: EventCollector
    trade_registry: ActiveTradeRegistry
    run_mode: RunMode = RunMode.LIVE_MICRO
    client: Optional[IbkrClient] = field(default=None)
    translator: Optional[IbkrOrderTranslator] = field(default=None)
    submitter: Optional[IbkrOrderSubmitter] = field(default=None)

    def __post_init__(self) -> None:
        if get_ibkr_readonly_enabled():
            raise RuntimeError(
                "IBKR_READONLY_ENABLED must be False for LIVE_MICRO execution."
            )
        if not get_ibkr_order_translation_enabled():
            raise RuntimeError("IBKR order translation disabled; cannot submit live orders.")
        if not get_ibkr_order_submission_enabled(default=False):
            raise RuntimeError("IBKR order submission disabled; enable IBKR_ORDER_SUBMISSION_ENABLED.")

        if self.client is None:
            self.client = IbkrClient(
                host=get_ibkr_host(),
                port=get_ibkr_live_port(),
                client_id=get_ibkr_client_id_order_submit(),
                snapshot_timeout_seconds=get_ibkr_snapshot_timeout_seconds(),
                market_data_type=get_ibkr_market_data_type(),
                readonly_enabled=False,
            )
        if self.translator is None:
            self.translator = IbkrOrderTranslator(
                order_translation_enabled=True,
                default_exchange=get_ibkr_default_exchange(),
                default_currency=get_ibkr_default_currency(),
            )
        settings = OrderSubmissionSettings(
            run_mode=self.run_mode,
            order_submission_enabled=get_ibkr_order_submission_enabled(default=False),
            kill_switch=get_ibkr_kill_switch(),
            max_orders_per_run=get_ibkr_max_orders_per_run(),
            paper_only_enforced=get_ibkr_paper_only_enforced(),
            paper_host=get_ibkr_paper_host(),
            paper_port=get_ibkr_paper_port(),
            live_port=get_ibkr_live_port(),
            submit_only_symbol=None,
            ack_timeout_seconds=get_ibkr_ack_timeout_seconds(),
            client_id=get_ibkr_client_id_order_submit(),
            submit_only_order_type=None,
            allow_shorting=False,
        )
        guard = SubmissionGuard(
            max_orders_per_run=settings.max_orders_per_run,
            persist_path=get_ibkr_guard_persist_path(),
        )
        self.submitter = IbkrOrderSubmitter(
            ibkr_client=self.client,
            translator=self.translator,
            event_bus=self.event_collector,
            config=settings,
            guard=guard,
        )

    def name(self) -> str:
        return "IBKR_LIVE_BROKER"

    def is_live(self) -> bool:
        return True

    def place_order(self, request: BrokerOrderRequest) -> ExecutionResult:
        if request.quantity != 1:
            rationale = "LIVE_MICRO_BLOCK: quantity must be exactly 1 share."
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
                note="LIVE_MICRO_SIZE_LIMIT",
                rejection_reason="LIVE_MICRO_SIZE_LIMIT",
                client_order_id=request.client_order_id,
                attempt_number=request.attempt_number,
            )

        timestamp = datetime.now(timezone.utc).isoformat()
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

        try:
            result = self.submitter.submit_once(internal_order)
        except Exception as exc:
            rationale = f"LIVE_MICRO_SUBMISSION_FAILED: {exc}"
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

        if fill_status in {"FULL", "PARTIAL"} and filled_quantity > 0:
            entry_price = average_fill_price
            if entry_price is not None:
                active_trade = ActiveTrade(
                    symbol=request.symbol,
                    trader_type=request.trader_type or "UNKNOWN",
                    entry_tick=request.created_tick or 0,
                    entry_price=entry_price,
                    direction=request.direction,
                    quantity=filled_quantity,
                    strategy_name=request.strategy_name or "UNKNOWN",
                    stop_loss_price=request.stop_loss_price,
                    take_profit_price=request.take_profit_price,
                )
                self.trade_registry.register_trade(active_trade)
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
                        "stop_loss_price": (
                            float(request.stop_loss_price)
                            if request.stop_loss_price is not None
                            else None
                        ),
                        "take_profit_price": (
                            float(request.take_profit_price)
                            if request.take_profit_price is not None
                            else None
                        ),
                        "requested_quantity": request.quantity,
                        "filled_quantity": filled_quantity,
                        "remaining_quantity": remaining_quantity,
                        "fill_status": fill_status,
                        "client_order_id": request.client_order_id,
                        "attempt_number": request.attempt_number,
                        "gateway_decision": "LIVE_MICRO",
                    },
                )

        status = "ACKED" if result.status == "ACKED" else result.status
        attempted = result.status in {"ACKED"}

        return ExecutionResult(
            symbol=request.symbol,
            trader_type=request.trader_type or "UNKNOWN",
            attempted=attempted,
            status=status,
            rationale=result.error or "Live micro order submission completed.",
            direction=request.direction,
            quantity=request.quantity,
            entry_price=average_fill_price,
            stop_loss_price=request.stop_loss_price,
            take_profit_price=request.take_profit_price,
            requested_quantity=request.quantity,
            filled_quantity=filled_quantity,
            remaining_quantity=remaining_quantity,
            fill_status=fill_status,
            average_fill_price=average_fill_price,
            commission=result.commission or 0.0,
            note="LIVE_MICRO_EXECUTION",
            attempt_number=request.attempt_number,
            client_order_id=request.client_order_id,
            retry_scheduled=False,
            next_retry_tick=None,
        )

    def cancel_order(self, client_order_id: str) -> None:
        raise RuntimeError("Live order cancellation not implemented in LIVE_MICRO.")

    def replace_order(self, client_order_id: str, new_request: BrokerOrderRequest) -> None:
        raise RuntimeError("Live order replace not implemented in LIVE_MICRO.")
