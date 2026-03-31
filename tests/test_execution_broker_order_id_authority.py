from __future__ import annotations

import threading
from types import SimpleNamespace

from src.core_engine.events import RiskDecisionRecord
from src.core_engine.state import RunMode
from src.execution import order_router


class _FakeClient:
    def __init__(self, next_id=1001):
        self.next_id = next_id
        self.orders = {}

    def submit_order(self, contract, order):
        order_id = self.next_id
        self.next_id += 1
        self.orders[order_id] = {
            "symbol": contract.symbol,
            "side": order.action,
            "quantity": order.totalQuantity,
            "status": "PENDING_SUBMIT",
            "filled": 0,
            "remaining": order.totalQuantity,
        }
        return order_id

    def get_working_order(self, broker_order_id):
        row = self.orders.get(broker_order_id)
        if not row:
            return None
        return dict(row)

    def wait_for_order_status(self, broker_order_id, timeout_seconds):
        row = self.orders.get(broker_order_id)
        if not row:
            return None
        return {"status": "Submitted", "filled": row["filled"], "remaining": row["remaining"]}


class _FakeManager:
    def __init__(self, client):
        self.client = client

    def get_client(self):
        return self.client


def _allow_decision() -> RiskDecisionRecord:
    return RiskDecisionRecord(
        symbol="MCRO",
        intent_id="MCRO-1",
        decision="ALLOW",
        max_position_size=1,
        constraints=[],
        triggered_rules=[],
        rationale="ok",
        approved_quantity=1,
        entry_price=25.0,
        capital_source="IBKR_CANONICAL",
    )


def test_submit_result_requires_broker_order_id(monkeypatch) -> None:
    class _MissingIdClient(_FakeClient):
        def submit_order(self, contract, order):
            return None

    monkeypatch.setattr(order_router, "_is_test_environment", lambda: True)
    monkeypatch.setattr(
        order_router,
        "get_shared_ibkr_connection_manager",
        lambda readonly_enabled=False: _FakeManager(_MissingIdClient()),
    )

    event = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_allow_decision()])[0]
    assert event.submitted is False
    assert event.broker_order_id is None
    assert event.reason_code == "missing_broker_order_id"


def test_successful_submit_registers_working_order(monkeypatch) -> None:
    fake = _FakeClient(next_id=4321)
    monkeypatch.setattr(order_router, "_is_test_environment", lambda: True)
    monkeypatch.setattr(
        order_router,
        "get_shared_ibkr_connection_manager",
        lambda readonly_enabled=False: _FakeManager(fake),
    )

    event = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_allow_decision()])[0]
    assert event.submitted is True
    assert event.broker_order_id == 4321
    assert event.lifecycle_tracking_ready is True


def test_no_position_open_on_submit_without_fill(monkeypatch) -> None:
    fake = _FakeClient(next_id=5001)
    monkeypatch.setattr(order_router, "_is_test_environment", lambda: True)
    monkeypatch.setattr(
        order_router,
        "get_shared_ibkr_connection_manager",
        lambda readonly_enabled=False: _FakeManager(fake),
    )
    event = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_allow_decision()])[0]
    assert event.filled_quantity == 0
    assert event.remaining_quantity == 1


def test_exec_details_opens_position_from_broker_truth(capsys) -> None:
    import pytest

    ibapi = pytest.importorskip("ibapi")
    _ = ibapi
    from src.adapters.brokers.ibkr.ibkr_client import IbkrClient

    client = IbkrClient.__new__(IbkrClient)
    client.NON_REJECTING_ORDER_WARNING_CODES = {2109}
    client._errors = {}
    client._order_status = {}
    client._order_errors = {}
    client._order_warnings = {}
    client._order_status_events = {101: threading.Event()}
    client._exec_details_by_order = {}
    client._contract_events = {}
    client._market_events = {}
    client._historical_events = {}
    client._account_summary_events = {}
    client._scanner_events = {}
    client._market_update_event = threading.Event()
    client._connection_event = threading.Event()
    client._order_state_registry = {}

    client.openOrder(101, SimpleNamespace(symbol="AAPL"), SimpleNamespace(), SimpleNamespace())
    execution = SimpleNamespace(orderId=101, execId="exec-1", time="now", price=101.0, shares=3)
    client.execDetails(0, SimpleNamespace(symbol="AAPL"), execution)
    out = capsys.readouterr().out
    assert "[EXECUTION][CALLBACK][EXEC_DETAILS]" in out
    assert client._order_state_registry[101]["status"] == "Filled"


def test_callback_reconciliation_uses_broker_order_id(capsys) -> None:
    import pytest

    ibapi = pytest.importorskip("ibapi")
    _ = ibapi
    from src.adapters.brokers.ibkr.ibkr_client import IbkrClient

    client = IbkrClient.__new__(IbkrClient)
    client.NON_REJECTING_ORDER_WARNING_CODES = {2109}
    client._errors = {}
    client._order_status = {}
    client._order_errors = {}
    client._order_warnings = {}
    client._order_status_events = {222: threading.Event()}
    client._exec_details_by_order = {}
    client._contract_events = {}
    client._market_events = {}
    client._historical_events = {}
    client._account_summary_events = {}
    client._scanner_events = {}
    client._market_update_event = threading.Event()
    client._connection_event = threading.Event()
    client._order_state_registry = {}

    client.openOrder(222, SimpleNamespace(symbol="MSFT"), SimpleNamespace(), SimpleNamespace())
    client.orderStatus(222, "Submitted", 0, 5, 0.0, 0, 0, 0.0, 0, "", 0.0)
    client.execDetails(0, SimpleNamespace(symbol="MSFT"), SimpleNamespace(orderId=222, execId="x", time="t", price=10.0, shares=5))
    assert client._order_state_registry[222]["broker_order_id"] == 222
    assert client._order_state_registry[222]["last_callback"] == "execDetails"
    out = capsys.readouterr().out
    assert "[EXECUTION][CALLBACK][OPEN_ORDER]" in out
    assert "[EXECUTION][CALLBACK][ORDER_STATUS]" in out
    assert "[EXECUTION][CALLBACK][EXEC_DETAILS]" in out
