from __future__ import annotations

from dataclasses import dataclass

from brokers.base_broker import BaseBroker, BrokerOrderRequest
from models.execution_result import ExecutionResult


@dataclass
class IbkrBroker(BaseBroker):
    """
    LIVE-capable broker adapter (stub in Phase 12.1).

    In later steps this will wrap ibapi/ib_insync or your IBKR client.
    For now: return a safe stub result and emit NO broker-side actions.
    """

    def name(self) -> str:
        return "IBKR_BROKER"

    def is_live(self) -> bool:
        return True

    def place_order(self, request: BrokerOrderRequest) -> ExecutionResult:
        return ExecutionResult(
            symbol=request.symbol,
            trader_type=request.trader_type or "UNKNOWN",
            attempted=False,
            status="LIVE_STUB",
            rationale="LIVE broker stub: Phase 12.1 does not submit to IBKR.",
            direction=request.direction,
            quantity=0,
            entry_price=None,
            exit_price=None,
            raw_price=None,
            slippage_applied=0,
            entry_tick=request.created_tick,
            exit_tick=None,
            stop_loss_price=None,
            take_profit_price=None,
            gross_realised_pnl=0,
            commission=0,
            net_realised_pnl=0,
            requested_quantity=request.quantity,
            filled_quantity=0,
            remaining_quantity=request.quantity,
            fill_status="UNKNOWN",
            average_fill_price=None,
            note="No broker interaction performed.",
            gateway_decision=None,
            attempt_number=request.attempt_number,
            client_order_id=request.client_order_id,
            retry_scheduled=False,
            next_retry_tick=None,
            rejection_reason=None,
            spread=None,
            bid_price=None,
            ask_price=None,
            reference_price=None,
            execution_price=None,
        )
