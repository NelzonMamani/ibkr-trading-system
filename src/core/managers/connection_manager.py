from __future__ import annotations

from contextlib import contextmanager
from typing import Generator, Optional

from src.config.runtime_config import RunMode
from src.adapters.brokers.ibkr.ibkr_connection_manager import (
    IbkrConnectionManager,
    get_shared_ibkr_connection_manager,
)
from src.ibkr.market_data_client import MarketDataClient


class ConnectionManager:
    """Owns the single IBKR session lifecycle for the process."""

    def __init__(self, run_mode: RunMode) -> None:
        self.run_mode = run_mode
        self._client: Optional[MarketDataClient] = None
        self._client_id: Optional[int] = None
        self._connected = False
        self._ibkr_connection_manager: Optional[IbkrConnectionManager] = None

    @property
    def client(self) -> MarketDataClient:
        if self._client is None:
            raise RuntimeError("IBKR client not initialized.")
        return self._client

    @property
    def optional_client(self) -> MarketDataClient | None:
        return self._client

    @property
    def client_id(self) -> Optional[int]:
        return self._client_id

    def connect(self) -> None:
        if self.run_mode == RunMode.SIM:
            raise RuntimeError("Live broker connections are forbidden in SIM mode")
        manager = get_shared_ibkr_connection_manager()
        client = manager.get_market_data_client()
        client.connect()
        self._ibkr_connection_manager = manager
        self._client = client
        metadata = manager.connection_metadata()
        self._client_id = metadata.get("connected_client_id")
        self._connected = True

    def ensure_connected(self) -> None:
        if self.run_mode == RunMode.SIM:
            raise RuntimeError("Live broker connections are forbidden in SIM mode")
        if self._connected and self._client is not None and self.client.ib is not None and self.client.ib.isConnected():
            return
        self.connect()

    def disconnect(self) -> None:
        if not self._connected or self._client is None:
            return
        if self._ibkr_connection_manager is not None:
            self._ibkr_connection_manager.disconnect(reason="connection_manager.disconnect")
        elif self._client is not None:
            self._client.disconnect()
        self._connected = False

    def healthcheck(self) -> dict:
        metadata = (
            self._ibkr_connection_manager.connection_metadata()
            if self._ibkr_connection_manager is not None
            else {}
        )
        connected = bool(metadata.get("connected"))
        return {
            "connected": connected,
            "client_id": metadata.get("connected_client_id", self._client_id),
            "host": metadata.get("host"),
            "port": metadata.get("port"),
            "market_data_type": metadata.get("market_data_type"),
        }

    @contextmanager
    def with_ibkr_session(self) -> Generator[MarketDataClient, None, None]:
        self.ensure_connected()
        try:
            yield self.client
        finally:
            self.disconnect()

    def get_ibkr_client(self, ensure_connected: bool = False):
        if ensure_connected:
            self.ensure_connected()
        if self._ibkr_connection_manager is None:
            return None
        return self._ibkr_connection_manager.get_client()
