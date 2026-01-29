from __future__ import annotations

from contextlib import contextmanager
import os
import time
from typing import Generator, Optional

from src.config.config_resolver import get_config
from src.config.runtime_config import (
    RunMode,
    get_ibkr_client_id,
    get_ibkr_host,
    get_ibkr_market_data_type,
    get_ibkr_port,
    get_ibkr_snapshot_timeout_seconds,
)
from src.ibkr.market_data_client import MarketDataClient


class ConnectionManager:
    """Owns the single IBKR session lifecycle for the process."""

    def __init__(self, run_mode: RunMode) -> None:
        self.run_mode = run_mode
        self._client: Optional[MarketDataClient] = None
        self._client_id: Optional[int] = None
        self._connected = False

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
        if self._connected and self._client is not None and self.client.ib.isConnected():
            return
        base_client_id = get_ibkr_client_id()
        host = get_ibkr_host()
        port = get_ibkr_port()
        host_fallback = "127.0.0.1"
        port_fallback = 7497
        if not host or str(host).strip().lower() in {"none", "null"}:
            print(
                "[IBKR][CONNECT][WARN] host missing; "
                f"falling back to {host_fallback}"
            )
            host = host_fallback
        if not port:
            print(
                "[IBKR][CONNECT][WARN] port missing; "
                f"falling back to {port_fallback}"
            )
            port = port_fallback
        market_data_type = get_ibkr_market_data_type()
        snapshot_timeout = get_ibkr_snapshot_timeout_seconds()

        for attempt_index, candidate_id in enumerate(
            self._candidate_client_ids(base_client_id), start=1
        ):
            print(
                "[IBKR][CONNECT] attempt={attempt} host={host} port={port} client_id={client_id}".format(
                    attempt=attempt_index,
                    host=host,
                    port=port,
                    client_id=candidate_id,
                )
            )
            client = MarketDataClient(
                host=host,
                port=port,
                client_id=candidate_id,
                market_data_type=market_data_type,
                snapshot_timeout_seconds=snapshot_timeout,
            )
            try:
                client.connect()
            except Exception as exc:
                message = str(exc)
                if self._is_client_id_conflict(message):
                    print(
                        "[IBKR][CONNECT][WARN] clientId conflict detected; "
                        f"retrying next client_id reason={message}"
                    )
                    continue
                backoff = min(8, 2 ** max(attempt_index - 1, 0))
                print(
                    "[IBKR][CONNECT][WARN] connection failed; "
                    f"backoff={backoff}s reason={message}"
                )
                time.sleep(backoff)
                continue

            self._client = client
            self._client_id = candidate_id
            self._connected = True
            print(f"[IBKR][CONNECT] connected client_id={candidate_id}")
            return

        raise RuntimeError(
            "IBKR connection failed after clientId retries. "
            f"host={host} port={port} base_client_id={base_client_id}"
        )

    def ensure_connected(self) -> None:
        if self.run_mode == RunMode.SIM and get_config("SCANNER_DATA_SOURCE") == "MOCK":
            print("[IBKR][CONNECT] SIM mode with MOCK scanner; skipping IBKR connect.")
            return
        if self._connected and self._client is not None and self.client.ib.isConnected():
            return
        self.connect()

    def disconnect(self) -> None:
        if not self._connected or self._client is None:
            return
        self._client.disconnect()
        self._connected = False

    def healthcheck(self) -> dict:
        connected = (
            self._client is not None
            and self._client.ib is not None
            and self._client.ib.isConnected()
        )
        return {
            "connected": connected,
            "client_id": self._client_id,
            "host": get_ibkr_host(),
            "port": get_ibkr_port(),
            "market_data_type": get_ibkr_market_data_type(),
        }

    @contextmanager
    def with_ibkr_session(self) -> Generator[MarketDataClient, None, None]:
        self.ensure_connected()
        try:
            yield self.client
        finally:
            self.disconnect()

    @staticmethod
    def _candidate_client_ids(base_id: int) -> list[int]:
        jitter = os.getpid() % 7
        candidates = [base_id + jitter]
        for offset in range(0, 5):
            candidate = base_id + offset
            if candidate not in candidates:
                candidates.append(candidate)
        return candidates

    @staticmethod
    def _is_client_id_conflict(message: str) -> bool:
        lowered = message.lower()
        keywords = ("clientid", "client id", "already in use", "duplicate")
        return any(keyword in lowered for keyword in keywords)
