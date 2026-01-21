import datetime
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

try:
    from adapters.brokers.ibkr.ibkr_client import IbkrClient  # noqa: E402
    from brokers.base_broker import BrokerOrderRequest  # noqa: E402
    from brokers.ibkr_broker import IbkrBroker, READONLY_ERROR  # noqa: E402
    from domain.market_snapshot import MarketSnapshot  # noqa: E402
    from ibapi.client import EClient  # noqa: E402
except ModuleNotFoundError:
    pytest.skip("ibapi dependency missing; skipping IBKR read-only tests", allow_module_level=True)


class DummyClient:
    def connect(self):
        raise AssertionError("connect should not be called in this test")

    def disconnect(self):
        raise AssertionError("disconnect should not be called in this test")

    def resolve_contract(self, symbol: str):
        return {"symbol": symbol}

    def get_market_snapshot(self, symbol: str):
        return {"symbol": symbol}

    def health(self):
        return {"connected": False}


def test_order_methods_raise_runtime_error():
    broker = IbkrBroker(client=DummyClient())
    request = BrokerOrderRequest(
        client_order_id="abc",
        symbol="AAPL",
        direction="LONG",
        quantity=1,
    )

    with pytest.raises(RuntimeError, match=READONLY_ERROR):
        broker.place_order(request)

    with pytest.raises(RuntimeError, match=READONLY_ERROR):
        broker.cancel_order(client_order_id="abc")

    with pytest.raises(RuntimeError, match=READONLY_ERROR):
        broker.replace_order(client_order_id="abc", new_request=request)


def test_market_snapshot_dataclass():
    snapshot_time = datetime.datetime.utcnow()
    snapshot = MarketSnapshot(
        symbol="AAPL",
        bid=100.0,
        ask=100.5,
        last=100.25,
        asof_utc=snapshot_time,
    )

    assert snapshot.symbol == "AAPL"
    assert snapshot.bid == 100.0
    assert snapshot.ask == 100.5
    assert snapshot.last == 100.25
    assert snapshot.asof_utc == snapshot_time
    assert snapshot.source == "IBKR"


def test_ibkr_client_connect_allows_non_readonly(monkeypatch):
    def _noop_connect(self, host, port, clientId):  # noqa: N802 - ibapi signature
        return None

    def _noop_req_market_data_type(self, _code):
        return None

    def _fast_loop(self):
        self._connection_event.set()

    def _noop_disconnect(self):
        return None

    monkeypatch.setattr(EClient, "connect", _noop_connect)
    monkeypatch.setattr(EClient, "disconnect", _noop_disconnect)
    monkeypatch.setattr(IbkrClient, "reqMarketDataType", _noop_req_market_data_type)
    monkeypatch.setattr(IbkrClient, "_run_loop", _fast_loop)

    client = IbkrClient(
        host="127.0.0.1",
        port=4000,
        client_id=1,
        snapshot_timeout_seconds=1,
        market_data_type="LIVE",
        readonly_enabled=False,
    )
    client.connect()
    client.disconnect()
