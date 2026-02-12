from __future__ import annotations

import threading

from src.ibkr.market_data_client import MarketDataClient


class DummyClient:
    def __init__(self) -> None:
        self._thread = threading.current_thread()
        self.disconnected = False

    def disconnect(self) -> None:
        self.disconnected = True


class DummyIB:
    async def connectAsync(self, host, port, clientId, timeout=5):  # noqa: N802 - IBKR naming
        return True

    def __init__(self) -> None:
        self.client = DummyClient()

    def isConnected(self) -> bool:
        return True

    def disconnect(self) -> None:
        raise RuntimeError("cannot join current thread")


def test_disconnect_skips_join_current_thread():
    client = MarketDataClient()
    client.ib = DummyIB()

    client.disconnect()

    assert client.ib.client.disconnected is True
