from __future__ import annotations

from types import SimpleNamespace

from src.core_engine.state import RunMode, SessionState
from src.execution import order_router


class _FakeStock:
    def __init__(self, symbol: str, exchange: str, currency: str) -> None:
        self.symbol = symbol
        self.exchange = exchange
        self.currency = currency


class _FakeClient:
    def __init__(self) -> None:
        self.last_order = None

    def qualifyContracts(self, contract):
        contract.conId = 1001
        contract.exchange = "SMART"
        contract.primaryExchange = "NASDAQ"
        contract.currency = "USD"
        contract.secType = "STK"
        return [contract]

    def submit_order(self, _contract, order):
        self.last_order = order
        return 42

    def wait_for_order_status(self, _order_id, timeout_seconds=5):
        return "Submitted"


def _reset_state() -> None:
    order_router._RUNTIME_ORDERS.clear()
    order_router._RUNTIME_POSITIONS.clear()
    order_router._VISIBILITY_BY_ORDER_ID.clear()
    order_router._BROKER_ERRORS_BY_ORDER_ID.clear()
    order_router._EXECUTION_EVENT_BUFFER.clear()


def test_premarket_buy_entry_uses_limit_not_market(monkeypatch) -> None:
    _reset_state()
    monkeypatch.setattr(order_router, "safe_import_ib_insync", lambda: (None, _FakeStock, None))
    monkeypatch.setattr(order_router, "resolve_session_state", lambda: SessionState.PRE)
    monkeypatch.setattr(order_router, "_wait_for_ibkr_snapshot_for_symbol", lambda *_args, **_kwargs: {"ask": 10.0, "bid": 9.9, "last": 9.95})
    monkeypatch.setenv("PREMARKET_ENTRY_LIMIT_OFFSET_ABS", "0.05")

    client = _FakeClient()
    order_router._submit_ibkr_order(
        mode=RunMode.PAPER,
        client=client,
        symbol="AAPL",
        side="BUY",
        quantity=10,
        order_ref="TRADING_OS|ROSS_MOMENTUM|intent-1",
        intent_id="intent-1",
        fallback_entry_price=9.9,
    )

    assert client.last_order.orderType == "LMT"
    assert client.last_order.lmtPrice == 10.05


def test_premarket_sell_exit_uses_bid_minus_offset(monkeypatch) -> None:
    _reset_state()
    monkeypatch.setattr(order_router, "safe_import_ib_insync", lambda: (None, _FakeStock, None))
    monkeypatch.setattr(order_router, "resolve_session_state", lambda: SessionState.PRE)
    monkeypatch.setattr(order_router, "_wait_for_ibkr_snapshot_for_symbol", lambda *_args, **_kwargs: {"ask": 10.1, "bid": 10.0, "last": 10.05})
    monkeypatch.setenv("PREMARKET_EXIT_LIMIT_OFFSET_ABS", "0.03")
    order_router._RUNTIME_POSITIONS["AAPL"] = order_router.TrackedPosition(symbol="AAPL", qty=100)

    client = _FakeClient()
    order_router._submit_ibkr_order(
        mode=RunMode.PAPER,
        client=client,
        symbol="AAPL",
        side="SELL",
        quantity=10,
        order_ref="TRADING_OS|ROSS_MOMENTUM|intent-2",
        intent_id="intent-2",
        fallback_entry_price=10.0,
    )

    assert client.last_order.orderType == "LMT"
    assert client.last_order.lmtPrice == 9.97


def test_regular_session_behavior_keeps_market_order(monkeypatch) -> None:
    _reset_state()
    monkeypatch.setattr(order_router, "safe_import_ib_insync", lambda: (None, _FakeStock, None))
    monkeypatch.setattr(order_router, "resolve_session_state", lambda: SessionState.REG)

    client = _FakeClient()
    order_router._submit_ibkr_order(
        mode=RunMode.PAPER,
        client=client,
        symbol="AAPL",
        side="BUY",
        quantity=10,
        order_ref="TRADING_OS|ROSS_MOMENTUM|intent-3",
        intent_id="intent-3",
        fallback_entry_price=9.9,
    )

    assert client.last_order.orderType == "MKT"


def test_10197_is_normalized_as_broker_environment_conflict() -> None:
    _reset_state()
    row = order_router._upsert_order_from_submission(
        order_id=501,
        symbol="AAPL",
        side="BUY",
        total_qty=10,
        order_ref="TRADING_OS|ROSS_MOMENTUM|intent-4",
    )
    order_router._initialize_visibility(501)

    order_router._on_ibkr_callback(
        {
            "event_type": "error",
            "order_id": 501,
            "errorCode": 10197,
            "errorString": "No market data during competing live session",
        }
    )

    assert row.normalized_reject_reason == "BROKER_ENV_COMPETING_SESSION_MD"
    assert row.final_execution_state == "BROKER_ENVIRONMENT_BLOCKED"


def test_permission_restriction_is_normalized_as_broker_reject() -> None:
    _reset_state()
    row = order_router._upsert_order_from_submission(
        order_id=502,
        symbol="AAPL",
        side="BUY",
        total_qty=10,
        order_ref="TRADING_OS|ROSS_MOMENTUM|intent-5",
    )
    order_router._initialize_visibility(502)

    order_router._on_ibkr_callback(
        {
            "event_type": "error",
            "order_id": 502,
            "errorCode": 201,
            "errorString": "Order rejected - permission restriction",
        }
    )

    assert row.normalized_reject_reason == "PERMISSION_SMALL_CAP_OPENING_RESTRICTED"
    assert row.reject_seen is True


def test_presubmitted_without_execdetails_is_classified_as_resting(monkeypatch) -> None:
    _reset_state()
    row = order_router._upsert_order_from_submission(
        order_id=601,
        symbol="AAPL",
        side="BUY",
        total_qty=10,
        order_ref="TRADING_OS|ROSS_MOMENTUM|intent-6",
    )
    row.ack_seen = True
    row.working_seen = True
    row.broker_status = "PreSubmitted"

    clock = {"t": 0.0}

    def _fake_time() -> float:
        clock["t"] += 10.0
        return clock["t"]

    monkeypatch.setattr(order_router.time, "time", _fake_time)
    monkeypatch.setattr(order_router.time, "sleep", lambda _x: None)
    monkeypatch.setattr(order_router, "_strict_broker_truth_required", lambda _mode: False)

    manager = SimpleNamespace(get_client=lambda: SimpleNamespace(openOrders=lambda: [], executions=lambda: [], positions=lambda: []))
    order_router._post_submission_ibkr_diagnostics(mode=RunMode.PAPER, manager=manager, submitted_order_ids=[601])

    assert row.final_execution_state == "PREMARKET_LIMIT_RESTING"


def test_execdetails_remains_sole_fill_authority() -> None:
    _reset_state()
    row = order_router._upsert_order_from_submission(
        order_id=701,
        symbol="AAPL",
        side="BUY",
        total_qty=10,
        order_ref="TRADING_OS|ROSS_MOMENTUM|intent-7",
    )
    order_router._initialize_visibility(701)

    order_router._on_ibkr_callback({"event_type": "orderStatus", "order_id": 701, "status": "Filled", "filled": 10, "remaining": 0})
    assert row.filled_qty == 0

    order_router._on_ibkr_callback(
        {
            "event_type": "execDetails",
            "order_id": 701,
            "symbol": "AAPL",
            "shares": 10,
            "price": 100.0,
            "execId": "exec-701",
        }
    )
    assert row.filled_qty == 10


def test_broker_error_store_carries_normalized_reason_for_summary() -> None:
    _reset_state()
    row = order_router._upsert_order_from_submission(
        order_id=801,
        symbol="AAPL",
        side="BUY",
        total_qty=10,
        order_ref="TRADING_OS|ROSS_MOMENTUM|intent-8",
    )
    order_router._initialize_visibility(801)
    order_router._on_ibkr_callback(
        {
            "event_type": "error",
            "order_id": 801,
            "errorCode": 10197,
            "errorString": "No market data during competing live session",
        }
    )

    normalized = order_router._BROKER_ERRORS_BY_ORDER_ID[801][-1]["normalized"]
    assert normalized == "BROKER_ENV_COMPETING_SESSION_MD"
    assert row.normalized_reject_reason == normalized
