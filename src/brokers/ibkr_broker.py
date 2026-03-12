from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.adapters.brokers.ibkr.ibkr_connection_manager import (
    IbkrConnectionManager,
    get_shared_ibkr_connection_manager,
)
from src.brokers.base_broker import BaseBroker, BrokerOrderRequest
from src.domain.market_snapshot import MarketSnapshot
from src.models.execution_result import ExecutionResult


READONLY_ERROR = "IBKR READ-ONLY MODE: order submission disabled in READ_ONLY."


@dataclass
class IbkrBroker(BaseBroker):
    """Read-only IBKR broker facade backed by the canonical connection manager."""

    connection_manager: Optional[IbkrConnectionManager] = None

    def __post_init__(self) -> None:
        if self.connection_manager is None:
            self.connection_manager = get_shared_ibkr_connection_manager(readonly_enabled=True)

    @property
    def client(self):
        assert self.connection_manager is not None
        return self.connection_manager.get_client()

    @property
    def client_id(self) -> Optional[int]:
        assert self.connection_manager is not None
        return self.connection_manager.connection_metadata().get("connected_client_id")

    def name(self) -> str:
        return "IBKR_BROKER"

    def is_live(self) -> bool:
        return True

    def connect(self) -> None:
        assert self.connection_manager is not None
        self.connection_manager.connect()

    def disconnect(self) -> None:
        assert self.connection_manager is not None
        self.connection_manager.disconnect(reason="ibkr_broker_disconnect")

    def ensure_connection(self) -> None:
        assert self.connection_manager is not None
        self.connection_manager.ensure_connected()

    def resolve_contract(self, symbol: str) -> object:
        return self.client.resolve_contract(symbol)

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        return self.client.get_market_snapshot(symbol)

    def health(self) -> dict:
        return self.client.health()

    def _order_error(self) -> RuntimeError:
        return RuntimeError(READONLY_ERROR)

    def place_order(self, request: BrokerOrderRequest) -> ExecutionResult:
        raise self._order_error()

    def cancel_order(self, client_order_id: str) -> None:
        raise self._order_error()

    def replace_order(self, client_order_id: str, new_request: BrokerOrderRequest) -> None:
        raise self._order_error()
