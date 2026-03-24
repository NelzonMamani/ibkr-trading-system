from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from src.adapters.brokers.ibkr.ibkr_connection_manager import (
    IbkrConnectionConfig,
    IbkrConnectionManager,
)
from src.adapters.brokers.ibkr.ibkr_order_submitter import (
    IbkrOrderSubmitter,
    OrderSubmissionSettings,
)
from src.adapters.brokers.ibkr.submission_guard import SubmissionGuard
from src.config.runtime_config import RunMode
from src.core.event_collector import EventCollector
from src.core_engine import orchestrator as core_engine_orchestrator
from src.domain.models.internal_order import InternalOrder
from src.execution.execution_engine import ExecutionEngine


class FakeManagedClient:
    created_ids: list[int] = []

    def __init__(self, host, port, client_id, snapshot_timeout_seconds, market_data_type, readonly_enabled):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.connected = False
        FakeManagedClient.created_ids.append(client_id)

    def connect(self):
        if self.client_id == 7:
            raise RuntimeError("client id 7 already in use")
        self.connected = True

    def is_connected(self):
        return self.connected

    def disconnect(self):
        self.connected = False


def test_manager_reuses_single_connected_client(monkeypatch):
    from src.adapters.brokers.ibkr import ibkr_connection_manager as module

    FakeManagedClient.created_ids = []
    monkeypatch.setattr(module, "IbkrClient", FakeManagedClient)
    manager = IbkrConnectionManager(
        IbkrConnectionConfig(
            host="127.0.0.1",
            port=7497,
            base_client_id=8,
            snapshot_timeout_seconds=1,
            market_data_type="LIVE",
            readonly_enabled=False,
        )
    )

    first = manager.get_client()
    second = manager.get_client()

    assert first is second
    assert FakeManagedClient.created_ids == [8]


def test_manager_retries_deterministic_client_ids_and_keeps_config(monkeypatch):
    from src.adapters.brokers.ibkr import ibkr_connection_manager as module

    FakeManagedClient.created_ids = []
    monkeypatch.setattr(module, "IbkrClient", FakeManagedClient)
    manager = IbkrConnectionManager(
        IbkrConnectionConfig(
            host="127.0.0.1",
            port=7497,
            base_client_id=7,
            snapshot_timeout_seconds=1,
            market_data_type="LIVE",
            readonly_enabled=False,
        )
    )

    client = manager.get_client()
    metadata = manager.connection_metadata()

    assert client.client_id == 8
    assert FakeManagedClient.created_ids == [7, 8]
    assert metadata["host"] == "127.0.0.1"
    assert metadata["port"] == 7497


def test_read_only_mode_skips_real_connection(monkeypatch):
    from src.adapters.brokers.ibkr import ibkr_connection_manager as module

    class ShouldNotConnectClient(FakeManagedClient):
        def __init__(self, *args, **kwargs):
            raise AssertionError("IbkrClient should not be constructed in READ_ONLY mode")

    monkeypatch.setattr(module, "IbkrClient", ShouldNotConnectClient)
    manager = IbkrConnectionManager(
        IbkrConnectionConfig(
            host="127.0.0.1",
            port=7497,
            base_client_id=12,
            snapshot_timeout_seconds=1,
            market_data_type="LIVE",
            readonly_enabled=True,
            run_mode=RunMode.READ_ONLY.value,
        )
    )

    client = manager.get_client()
    metadata = manager.connection_metadata()

    assert client.is_connected() is True
    assert metadata["connected"] is True
    assert metadata["connected_client_id"] == 12


def test_live_capital_path_uses_manager(monkeypatch):
    class FakeManager:
        def __init__(self):
            self.called = 0

        def get_client(self):
            self.called += 1
            return object()

        def connection_metadata(self):
            return {"connected_client_id": 8, "connection_generation": 2}

    manager = FakeManager()
    monkeypatch.setattr(
        core_engine_orchestrator,
        "resolve_available_capital",
        lambda client, allow_fallback: 123.45,
    )
    monkeypatch.setattr(
        "src.adapters.brokers.ibkr.ibkr_connection_manager.get_shared_ibkr_connection_manager",
        lambda readonly_enabled=False: manager,
    )

    snapshot = core_engine_orchestrator._resolve_live_available_funds(
        SimpleNamespace(value="LIVE")
    )

    assert manager.called == 1
    assert snapshot.source == "IBKR_CANONICAL"
    assert snapshot.available_funds == 123.45


def test_submitter_does_not_connect_or_disconnect_directly():
    class FakeClient:
        def __init__(self):
            self.connect_calls = 0
            self.disconnect_calls = 0

        host = "127.0.0.1"
        port = 7496

        def is_connected(self):
            return True

        def submit_order(self, contract, order):
            return 1001

        def wait_for_order_status(self, order_id, timeout_seconds=5):
            return {"status": "ACKED", "filled": 1, "remaining": 0}

        def commission_for_order(self, order_id):
            return 0.0

        def connect(self):
            self.connect_calls += 1

        def disconnect(self):
            self.disconnect_calls += 1

    class FakeTranslator:
        def translate(self, internal_order):
            return object(), object()

    client = FakeClient()
    submitter = IbkrOrderSubmitter(
        ibkr_client=None,
        translator=FakeTranslator(),
        event_bus=EventCollector(),
        config=OrderSubmissionSettings(
            run_mode=RunMode.PAPER,
            order_submission_enabled=True,
            kill_switch=False,
            max_orders_per_run=1,
            paper_only_enforced=False,
            paper_host="127.0.0.1",
            paper_port=7497,
            live_port=7496,
            submit_only_symbol=None,
            ack_timeout_seconds=1,
            client_id=7,
            submit_only_order_type=None,
            allow_shorting=False,
        ),
        guard=SubmissionGuard(max_orders_per_run=1, persist_path=None),
        client_provider=lambda: client,
    )

    result = submitter.submit_once(
        InternalOrder(
            client_order_id="id-1",
            symbol="AAPL",
            direction="LONG",
            quantity=1,
            order_type="MKT",
            limit_price=None,
            time_in_force="DAY",
            strategy_name="TEST",
            trader_type="MANUAL",
        )
    )

    assert result.status == "ACKED"
    assert client.connect_calls == 0
    assert client.disconnect_calls == 0



def test_manager_heartbeat_reconnects_when_connection_lost(monkeypatch):
    from src.adapters.brokers.ibkr import ibkr_connection_manager as module

    class FlakyClient(FakeManagedClient):
        connect_attempts = 0

        def connect(self):
            FlakyClient.connect_attempts += 1
            self.connected = True

    FakeManagedClient.created_ids = []
    FlakyClient.connect_attempts = 0
    monkeypatch.setattr(module, "IbkrClient", FlakyClient)
    manager = IbkrConnectionManager(
        IbkrConnectionConfig(
            host="127.0.0.1",
            port=7497,
            base_client_id=8,
            snapshot_timeout_seconds=1,
            market_data_type="LIVE",
            readonly_enabled=False,
        )
    )

    client = manager.get_client()
    client.connected = False

    manager.heartbeat()
    metadata = manager.connection_metadata()

    assert metadata["connected"] is True
    assert metadata["reconnect_count"] == 1
    assert metadata["last_reconnect_time"] is not None
    assert FlakyClient.connect_attempts == 2


def test_manager_heartbeat_no_reconnect_when_healthy(monkeypatch):
    from src.adapters.brokers.ibkr import ibkr_connection_manager as module

    FakeManagedClient.created_ids = []
    monkeypatch.setattr(module, "IbkrClient", FakeManagedClient)
    manager = IbkrConnectionManager(
        IbkrConnectionConfig(
            host="127.0.0.1",
            port=7497,
            base_client_id=8,
            snapshot_timeout_seconds=1,
            market_data_type="LIVE",
            readonly_enabled=False,
        )
    )

    manager.get_client()
    manager.heartbeat()
    metadata = manager.connection_metadata()

    assert metadata["reconnect_count"] == 0
    assert FakeManagedClient.created_ids == [8]


def test_reconnect_preserves_immutable_config(monkeypatch):
    from src.adapters.brokers.ibkr import ibkr_connection_manager as module

    FakeManagedClient.created_ids = []
    monkeypatch.setattr(module, "IbkrClient", FakeManagedClient)
    manager = IbkrConnectionManager(
        IbkrConnectionConfig(
            host="127.0.0.1",
            port=7497,
            base_client_id=8,
            snapshot_timeout_seconds=1,
            market_data_type="LIVE",
            readonly_enabled=False,
        )
    )

    original = manager.config
    client = manager.get_client()
    client.connected = False
    manager.ensure_connection_health()

    assert manager.config == original
    metadata = manager.connection_metadata()
    assert metadata["host"] == "127.0.0.1"
    assert metadata["port"] == 7497
    assert metadata["base_client_id"] == 8


def test_shutdown_prevents_reconnect(monkeypatch):
    from src.adapters.brokers.ibkr import ibkr_connection_manager as module

    FakeManagedClient.created_ids = []
    monkeypatch.setattr(module, "IbkrClient", FakeManagedClient)
    manager = IbkrConnectionManager(
        IbkrConnectionConfig(
            host="127.0.0.1",
            port=7497,
            base_client_id=8,
            snapshot_timeout_seconds=1,
            market_data_type="LIVE",
            readonly_enabled=False,
        )
    )

    manager.get_client()
    manager.disconnect(reason="execution_engine_shutdown")
    manager.heartbeat()

    metadata = manager.connection_metadata()
    assert metadata["connected"] is False
    assert metadata["reconnect_count"] == 0


def test_metadata_exposes_reconnect_and_disconnect_fields(monkeypatch):
    from src.adapters.brokers.ibkr import ibkr_connection_manager as module

    FakeManagedClient.created_ids = []
    monkeypatch.setattr(module, "IbkrClient", FakeManagedClient)
    manager = IbkrConnectionManager(
        IbkrConnectionConfig(
            host="127.0.0.1",
            port=7497,
            base_client_id=8,
            snapshot_timeout_seconds=1,
            market_data_type="LIVE",
            readonly_enabled=False,
        )
    )

    manager.get_client()
    manager.disconnect(reason="manual")
    metadata = manager.connection_metadata()

    assert "reconnect_count" in metadata
    assert "last_reconnect_time" in metadata
    assert metadata["last_disconnect_reason"] == "manual"


def test_execution_engine_shutdown_disconnects_once():
    class FakeBroker:
        def __init__(self):
            self.calls = 0

        def disconnect(self, reason="manual"):
            self.calls += 1

    broker = FakeBroker()
    provider = SimpleNamespace(broker=broker)
    engine = ExecutionEngine.__new__(ExecutionEngine)
    engine._provider = provider

    ExecutionEngine.shutdown(engine)

    assert broker.calls == 1
