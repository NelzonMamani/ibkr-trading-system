from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Optional

from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.config.runtime_config import (
    RuntimeConfigError,
    get_execution_enabled,
    get_ibkr_market_data_type,
    get_ibkr_readonly_enabled,
    get_ibkr_snapshot_timeout_seconds,
    resolve_ibkr_connection,
)


@dataclass(frozen=True)
class IbkrConnectionConfig:
    host: str
    port: int
    base_client_id: int
    snapshot_timeout_seconds: int
    market_data_type: str
    readonly_enabled: bool
    run_mode: str = "READ_ONLY"
    max_client_id_retries: int = 10


class IbkrConnectionManager:
    """Single authoritative owner for IBKR runtime connectivity."""

    def __init__(self, config: IbkrConnectionConfig) -> None:
        self._config = config
        self._client: Optional[IbkrClient] = None
        self._market_data_client = None
        self._connected_client_id: Optional[int] = None
        self._connection_generation = 0
        self._last_error: Optional[str] = None
        self._last_reconnect_time: Optional[str] = None
        self._reconnect_count = 0
        self._last_disconnect_reason: Optional[str] = None
        self._shutdown_requested = False
        self._lock = Lock()
        print(
            "[IBKR][CONFIG] "
            f"mode={config.run_mode} port={config.port} host={config.host} "
            f"client_id={config.base_client_id}"
        )
        print(
            "[IBKR][MANAGER] init "
            f"mode={config.run_mode} host={config.host} port={config.port} "
            f"base_client_id={config.base_client_id} "
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
        self._validate_runtime_safety()

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
                raise RuntimeError(
                    "IBKR CONNECTION FAILED — SYSTEM NOT SAFE TO RUN"
                ) from exc

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
            account_id = self._resolve_account_id(client)
            print(
                f"[IBKR][SESSION] mode={config.run_mode} "
                f"account={account_id} readonly={config.readonly_enabled}"
            )
            return client

        raise RuntimeError(
            "IBKR CONNECTION FAILED — SYSTEM NOT SAFE TO RUN "
            f"(host={config.host} port={config.port} "
            f"base_client_id={config.base_client_id} last_error={self._last_error})"
        )

    def disconnect(self, reason: str = "manual") -> None:
        with self._lock:
            self._last_disconnect_reason = reason
            if "shutdown" in reason.lower():
                self._shutdown_requested = True
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

    def ensure_connection_health(self) -> Optional[IbkrClient]:
        with self._lock:
            if self._shutdown_requested:
                return None
            if self._client is not None and self._client.is_connected():
                return self._client
            print("[IBKR][MANAGER] connection_lost")
            print("[IBKR][MANAGER] connection lost — attempting reconnect")
            self._reconnect_count += 1
            self._last_reconnect_time = datetime.now(timezone.utc).isoformat()
            print(
                "[IBKR][MANAGER] reconnect_attempt "
                f"client_id={self._config.base_client_id}"
            )
            self._client = None
            self._connected_client_id = None
            client = self._connect_locked()
            print(
                "[IBKR][MANAGER] reconnect_success "
                f"client_id={self._connected_client_id} generation={self._connection_generation}"
            )
            return client

    def heartbeat(self) -> None:
        if not self.is_connected():
            self.ensure_connection_health()
            return
        print(
            "[IBKR][MANAGER] heartbeat ok "
            f"client_id={self._connected_client_id}"
        )


    def get_market_data_client(self):
        """Return the shared market data client bound to this manager."""
        if self._market_data_client is None:
            from src.ibkr.market_data_client import MarketDataClient

            self._market_data_client = MarketDataClient(
                market_data_type=self._config.market_data_type,
                snapshot_timeout_seconds=self._config.snapshot_timeout_seconds,
                default_exchange="SMART",
                default_currency="USD",
                connection_manager=self,
                allow_direct_connection=False,
            )
        return self._market_data_client

    def connection_metadata(self) -> dict:
        return {
            "host": self._config.host,
            "port": self._config.port,
            "base_client_id": self._config.base_client_id,
            "run_mode": self._config.run_mode,
            "connected_client_id": self._connected_client_id,
            "connection_generation": self._connection_generation,
            "connected": self.is_connected(),
            "last_error": self._last_error,
            "reconnect_count": self._reconnect_count,
            "last_reconnect_time": self._last_reconnect_time,
            "last_disconnect_reason": self._last_disconnect_reason,
            "readonly_enabled": self._config.readonly_enabled,
            "market_data_type": self._config.market_data_type,
            "snapshot_timeout_seconds": self._config.snapshot_timeout_seconds,
        }

    @staticmethod
    def _is_client_id_conflict(exc: Exception) -> bool:
        message = str(exc).lower()
        return "client id" in message or "clientid" in message or "326" in message

    def _validate_runtime_safety(self) -> None:
        run_mode = self._config.run_mode.upper()
        if run_mode == "LIVE" and self._config.port != 7496:
            raise RuntimeConfigError("LIVE mode must use port 7496")
        if run_mode in {"PAPER", "SIM"} and self._config.port != 7497:
            raise RuntimeConfigError("PAPER mode must use port 7497")
        if run_mode == "LIVE" and not self._config.readonly_enabled and not get_execution_enabled():
            raise RuntimeConfigError(
                "LIVE trading requires EXECUTION_ENABLED=true before orders are allowed"
            )

    @staticmethod
    def _resolve_account_id(client: IbkrClient) -> str:
        try:
            account_id = client.get_primary_account()
        except Exception:
            account_id = None
        return account_id or "UNKNOWN"


_default_manager: Optional[IbkrConnectionManager] = None
_default_manager_lock = Lock()


def get_shared_ibkr_connection_manager(
    *,
    readonly_enabled: Optional[bool] = None,
) -> IbkrConnectionManager:
    global _default_manager
    with _default_manager_lock:
        if _default_manager is None:
            host, port, client_id, run_mode = resolve_ibkr_connection()
            execution_enabled = get_execution_enabled()
            readonly = (
                get_ibkr_readonly_enabled()
                if readonly_enabled is None
                else readonly_enabled
            )

            run_mode_upper = str(run_mode).upper()

            # Unified runtime authority wins over caller overrides.
            if run_mode_upper == "READ_ONLY":
                readonly = True
            elif not execution_enabled:
                readonly = True
            else:
                readonly = False

            print(
                f"[IBKR][READONLY_OVERRIDE] readonly={readonly} "
                f"(execution_enabled={execution_enabled}, run_mode={run_mode_upper})"
            )
            _default_manager = IbkrConnectionManager(
                IbkrConnectionConfig(
                    host=host,
                    port=port,
                    base_client_id=client_id,
                    run_mode=run_mode,
                    snapshot_timeout_seconds=get_ibkr_snapshot_timeout_seconds(),
                    market_data_type=get_ibkr_market_data_type(),
                    readonly_enabled=readonly,
                )
            )
        return _default_manager
