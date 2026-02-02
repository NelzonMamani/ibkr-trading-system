from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.adapters.brokers.ibkr.ibkr_order_submitter import (
    IbkrOrderSubmitter,
    OrderSubmissionSettings,
)
from src.adapters.brokers.ibkr.ibkr_order_translator import IbkrOrderTranslator
from src.adapters.brokers.ibkr.submission_guard import SubmissionGuard
from src.brokers.base_broker import BaseBroker, BrokerOrderRequest
from src.config.runtime_config import (
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
    get_risk_profile_name,
    is_execution_enabled,
)
from src.config.risk_profiles import RISK_PROFILES
from src.core.active_trade_registry import ActiveTrade, ActiveTradeRegistry
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
    client: Optional[IbkrClient] = field(default=None)
    translator: Optional[IbkrOrderTranslator] = field(default=None)
    submitter: Optional[IbkrOrderSubmitter] = field(default=None)

    def __post_init__(self) -> None:
        if not is_execution_enabled(self.run_mode):
            raise RuntimeError("EXECUTION_ENABLED must be True for broker execution.")
        if get_ibkr_readonly_enabled() and self.run_mode == RunMode.LIVE:
            raise RuntimeError("IBKR_READONLY_ENABLED must be False for LIVE execution.")
        if not get_ibkr_order_translation_enabled():
            raise RuntimeError("IBKR order translation disabled; cannot submit live orders.")
        if not get_ibkr_order_submission_enabled(default=False):
            raise RuntimeError("IBKR order submission disabled; enable IBKR_ORDER_SUBMISSION_ENABLED.")

        if self.client is None:
            port = get_ibkr_live_port()
            if self.run_mode == RunMode.PAPER:
                port = get_ibkr_paper_port()
            self.client = IbkrClient(
                host=get_ibkr_host(),
                port=port,
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
                    if last_transition.get("to") == "PROTECTED":
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
        )

    def cancel_order(self, client_order_id: str) -> None:
        raise RuntimeError("Live order cancellation not implemented in LIVE mode.")

    def replace_order(self, client_order_id: str, new_request: BrokerOrderRequest) -> None:
        raise RuntimeError("Live order replace not implemented in LIVE mode.")
