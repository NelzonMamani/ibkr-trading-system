from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from adapters.brokers.ibkr.ibkr_client import IbkrClient
from brokers.base_broker import BaseBroker, BrokerOrderRequest
from config.runtime_config import (
    get_ibkr_client_id,
    get_ibkr_host,
    get_ibkr_market_data_type,
    get_ibkr_port,
    get_ibkr_readonly_enabled,
    get_ibkr_snapshot_timeout_seconds,
)
from domain.market_snapshot import MarketSnapshot
from models.execution_result import ExecutionResult


READONLY_ERROR = "IBKR READ-ONLY MODE: order submission disabled in LIVE_READ_ONLY."


@dataclass
class IbkrBroker(BaseBroker):
    """
    Read-only IBKR broker adapter for Phase 15.1.

    Exposes contract resolution and market snapshot helpers while hard-failing
    any order submission attempts.
    """

    client: Optional[IbkrClient] = field(default=None)

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = IbkrClient(
                host=get_ibkr_host(),
                port=get_ibkr_port(),
                client_id=get_ibkr_client_id(),
                snapshot_timeout_seconds=get_ibkr_snapshot_timeout_seconds(),
                market_data_type=get_ibkr_market_data_type(),
                readonly_enabled=get_ibkr_readonly_enabled(),
            )

    def name(self) -> str:
        return "IBKR_BROKER"

    def is_live(self) -> bool:
        return True

    # --- Read-only helpers ---
    def connect(self) -> None:
        assert self.client is not None
        self.client.connect()

    def disconnect(self) -> None:
        assert self.client is not None
        self.client.disconnect()

    def resolve_contract(self, symbol: str) -> object:
        assert self.client is not None
        return self.client.resolve_contract(symbol)

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        assert self.client is not None
        return self.client.get_market_snapshot(symbol)

    def health(self) -> dict:
        assert self.client is not None
        return self.client.health()

    # --- Order lifecycle: hard fail in read-only mode ---
    def _order_error(self) -> RuntimeError:
        return RuntimeError(READONLY_ERROR)

    def place_order(self, request: BrokerOrderRequest) -> ExecutionResult:
        return ExecutionResult(
            symbol=request.symbol,
            trader_type=request.trader_type or "UNKNOWN",
            attempted=False,
            status="BLOCKED",
            rationale="READ_ONLY_BLOCK: IBKR broker is read-only; no order submitted.",
            direction=request.direction,
            quantity=request.quantity,
            stop_loss_price=request.stop_loss_price,
            take_profit_price=request.take_profit_price,
            requested_quantity=request.quantity,
            filled_quantity=0,
            remaining_quantity=request.quantity,
            fill_status="NONE",
            note="READ_ONLY_BLOCK",
            rejection_reason="READ_ONLY_BLOCK",
            attempt_number=request.attempt_number,
            client_order_id=request.client_order_id,
        )

    def cancel_order(self, client_order_id: str) -> None:
        raise self._order_error()

    def replace_order(self, client_order_id: str, new_request: BrokerOrderRequest) -> None:
        raise self._order_error()
