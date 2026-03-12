from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Optional

from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.brokers.base_broker import BaseBroker, BrokerOrderRequest
from src.config.runtime_config import (
    get_ibkr_client_id,
    get_ibkr_host,
    get_ibkr_market_data_type,
    get_ibkr_port,
    get_ibkr_readonly_enabled,
    get_ibkr_snapshot_timeout_seconds,
)
from src.domain.market_snapshot import MarketSnapshot
from src.models.execution_result import ExecutionResult


READONLY_ERROR = "IBKR READ-ONLY MODE: order submission disabled in READ_ONLY."


@dataclass
class IbkrBroker(BaseBroker):
    """
    Read-only IBKR broker adapter for Phase 15.1.

    Exposes contract resolution and market snapshot helpers while hard-failing
    any order submission attempts.
    """

    MAX_CLIENT_ID_RETRIES: ClassVar[int] = 10
    client: Optional[IbkrClient] = field(default=None)
    client_id: Optional[int] = field(default=None)

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
        self.client_id = getattr(self.client, "client_id", None)

    def name(self) -> str:
        return "IBKR_BROKER"

    def is_live(self) -> bool:
        return True

    # --- Read-only helpers ---
    def connect(self) -> None:
        host = get_ibkr_host()
        port = get_ibkr_port()
        base_client_id = get_ibkr_client_id()

        for attempt in range(self.MAX_CLIENT_ID_RETRIES):
            client_id = base_client_id + attempt
            print(f"[IBKR] host={host} port={port} client_id={client_id}")
            try:
                self.client = IbkrClient(
                    host=host,
                    port=port,
                    client_id=client_id,
                    snapshot_timeout_seconds=get_ibkr_snapshot_timeout_seconds(),
                    market_data_type=get_ibkr_market_data_type(),
                    readonly_enabled=get_ibkr_readonly_enabled(),
                )
                print(f"[IBKR] Attempting connection client_id={client_id}")
                self.client.connect()
                status = self.client.is_connected()
                print(f"[IBKR] connection_status={status}")
                if status:
                    self.client_id = client_id
                    print(f"[IBKR][CONNECTED] Connected client_id={client_id}")
                    return
            except Exception as exc:
                message = str(exc).lower()
                if "client id" in message or "326" in message:
                    print(
                        f"[IBKR][RETRY] client_id={client_id} already in use. Trying next client id."
                    )
                    continue
                print(f"[IBKR][CONNECT_FAIL] client_id={client_id} error={exc}")
                raise

        print("[IBKR][CONNECT_FAIL] IBKR connection failed after clientId retries")
        raise RuntimeError("IBKR connection failed after clientId retries")

    def disconnect(self) -> None:
        try:
            if self.client and self.client.is_connected():
                print(f"[IBKR] Disconnecting client_id={getattr(self, 'client_id', None)}")
                self.client.disconnect()
                print("[IBKR][DISCONNECTED] client disconnected")
        except Exception as exc:
            print(f"[IBKR] Disconnect warning: {exc}")

    def ensure_connection(self) -> None:
        if not self.client or not self.client.is_connected():
            print("[IBKR] Connection lost. Reconnecting.")
            self.connect()

    def resolve_contract(self, symbol: str) -> object:
        self.ensure_connection()
        assert self.client is not None
        return self.client.resolve_contract(symbol)

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        self.ensure_connection()
        assert self.client is not None
        return self.client.get_market_snapshot(symbol)

    def health(self) -> dict:
        assert self.client is not None
        return self.client.health()

    # --- Order lifecycle: hard fail in read-only mode ---
    def _order_error(self) -> RuntimeError:
        return RuntimeError(READONLY_ERROR)

    def place_order(self, request: BrokerOrderRequest) -> ExecutionResult:
        raise self._order_error()

    def cancel_order(self, client_order_id: str) -> None:
        raise self._order_error()

    def replace_order(self, client_order_id: str, new_request: BrokerOrderRequest) -> None:
        raise self._order_error()
