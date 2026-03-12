from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Optional

from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.config.runtime_config import (
    get_ibkr_client_id,
    get_ibkr_host,
    get_ibkr_market_data_type,
    get_ibkr_port,
    get_ibkr_readonly_enabled,
    get_ibkr_snapshot_timeout_seconds,
)


@dataclass(frozen=True)
class IbkrConnectionConfig:
    host: str
    port: int
    base_client_id: int
    snapshot_timeout_seconds: int
    market_data_type: str
    readonly_enabled: bool
    max_client_id_retries: int = 10


class IbkrConnectionManager:
    """Single authoritative owner for IBKR runtime connectivity."""

    def __init__(self, config: IbkrConnectionConfig) -> None:
        self._config = config
        self._client: Optional[IbkrClient] = None
        self._connected_client_id: Optional[int] = None
        self._connection_generation = 0
        self._last_error: Optional[str] = None
        self._lock = Lock()
        print(
            "[IBKR][MANAGER] init "
            f"host={config.host} port={config.port} base_client_id={config.base_client_id} "
            f"readonly={config.readonly_enabled} market_data_type={config.market_data_type} "
            f"snapshot_timeout_seconds={config.snapshot_timeout_seconds}"
        )

    @property
    def config(self) -> IbkrConnectionConfig:
        return self._config

    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected()

    def get_client(self) -> IbkrClient:
        return self.ensure_connected()

    def ensure_connected(self) -> IbkrClient:
        with self._lock:
            if self.is_connected():
                assert self._client is not None
                print(
                    "[IBKR][MANAGER] reuse "
                    f"client_id={self._connected_client_id} generation={self._connection_generation}"
                )
                return self._client
            return self._connect_locked()

    def connect(self) -> IbkrClient:
        return self.ensure_connected()

    def _connect_locked(self) -> IbkrClient:
        config = self._config
        if not config.host or config.port <= 0:
            raise RuntimeError("INVALID_RETRY_CONFIGURATION")

        self._last_error = None
        for offset in range(config.max_client_id_retries):
            client_id = config.base_client_id + offset
            print(f"[IBKR][MANAGER] connect_attempt client_id={client_id}")
            client = IbkrClient(
                host=config.host,
                port=config.port,
                client_id=client_id,
                snapshot_timeout_seconds=config.snapshot_timeout_seconds,
                market_data_type=config.market_data_type,
                readonly_enabled=config.readonly_enabled,
            )
            try:
                client.connect()
            except Exception as exc:
                self._last_error = str(exc)
                if self._is_client_id_conflict(exc):
                    print(
                        "[IBKR][MANAGER] connect_retry "
                        f"client_id={client_id} reason={exc}"
                    )
                    continue
                print(
                    "[IBKR][MANAGER] connect_failed "
                    f"client_id={client_id} reason={exc}"
                )
                raise

            if not client.is_connected():
                self._last_error = "connect() returned without active connection"
                print(
                    "[IBKR][MANAGER] connect_retry "
                    f"client_id={client_id} reason={self._last_error}"
                )
                continue

            self._client = client
            self._connected_client_id = client_id
            self._connection_generation += 1
            print(
                "[IBKR][MANAGER] connected "
                f"client_id={client_id} generation={self._connection_generation}"
            )
            return client

        raise RuntimeError(
            "IBKR manager connection failed after retries "
            f"host={config.host} port={config.port} base_client_id={config.base_client_id} "
            f"last_error={self._last_error}"
        )

    def disconnect(self, reason: str = "manual") -> None:
        with self._lock:
            if self._client is None:
                return
            client_id = self._connected_client_id
            if self._client.is_connected():
                print(
                    "[IBKR][MANAGER] disconnect "
                    f"reason={reason} client_id={client_id}"
                )
                self._client.disconnect()
            self._client = None
            self._connected_client_id = None

    def connection_metadata(self) -> dict:
        return {
            "host": self._config.host,
            "port": self._config.port,
            "base_client_id": self._config.base_client_id,
            "connected_client_id": self._connected_client_id,
            "connection_generation": self._connection_generation,
            "connected": self.is_connected(),
            "last_error": self._last_error,
            "readonly_enabled": self._config.readonly_enabled,
        }

    @staticmethod
    def _is_client_id_conflict(exc: Exception) -> bool:
        message = str(exc).lower()
        return "client id" in message or "clientid" in message or "326" in message


_default_manager: Optional[IbkrConnectionManager] = None
_default_manager_lock = Lock()


def get_shared_ibkr_connection_manager(
    *,
    readonly_enabled: Optional[bool] = None,
) -> IbkrConnectionManager:
    global _default_manager
    with _default_manager_lock:
        if _default_manager is None:
            _default_manager = IbkrConnectionManager(
                IbkrConnectionConfig(
                    host=get_ibkr_host(),
                    port=get_ibkr_port(),
                    base_client_id=get_ibkr_client_id(),
                    snapshot_timeout_seconds=get_ibkr_snapshot_timeout_seconds(),
                    market_data_type=get_ibkr_market_data_type(),
                    readonly_enabled=(
                        get_ibkr_readonly_enabled()
                        if readonly_enabled is None
                        else readonly_enabled
                    ),
                )
            )
        return _default_manager
