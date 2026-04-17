from __future__ import annotations

from src.core.engines.position_management_engine import ManagedPosition, PositionManagementEngine
from src.core.engines.trade_lifecycle_engine import LifecycleEvent, TradeLifecycleEngine
from src.execution import order_router


class _Execution:
    def __init__(self, *, order_id: int, shares: int, price: float) -> None:
        self.orderId = order_id
        self.shares = shares
        self.price = price


def _reset_router_state() -> None:
    order_router._EXECUTION_EVENT_BUFFER.clear()
    order_router._RUNTIME_ORDERS.clear()
    order_router._RUNTIME_POSITIONS.clear()
    order_router._SEEN_EXEC_IDS.clear()
    order_router._UNMATCHED_CALLBACK_COUNT = 0
    order_router._RECONCILIATION_SUCCESSES = 0
    order_router._RECONCILIATION_FAILURES = 0
    order_router._UNRESOLVED_EXECUTION_RECONCILIATION_COUNT = 0
    order_router._NON_ORDER_UNMATCHED_CALLBACK_COUNT = 0
    order_router._FILL_AUTHORITY_STATE = "UNKNOWN"
    order_router._VISIBILITY_BY_ORDER_ID.clear()
    order_router._LAST_CALLBACK_FINGERPRINT_BY_ORDER_ID.clear()
    order_router._BROKER_ERRORS_BY_ORDER_ID.clear()


def _seed_tracked_order(*, order_id: int = 101, symbol: str = "AAPL", qty: int = 10) -> order_router.TrackedOrder:
    row = order_router._upsert_order_from_submission(
        order_id=order_id,
        symbol=symbol,
        side="BUY",
        total_qty=qty,
        order_ref="TRADING_OS|ROSS_MOMENTUM|intent-1",
    )
    order_router._initialize_visibility(order_id)
    return row


def test_tracked_openorder_and_orderstatus_callbacks_are_processed() -> None:
    _reset_router_state()
    row = _seed_tracked_order(order_id=201)

    order_router._on_ibkr_callback({"event_type": "openOrder", "order_id": 201, "symbol": "AAPL"})
    order_router._on_ibkr_callback({"event_type": "orderStatus", "order_id": 201, "status": "Submitted", "remaining": 10})

    assert row.ack_seen is True
    assert row.working_seen is True
    assert order_router._VISIBILITY_BY_ORDER_ID[201]["openOrder_seen"] is True
    assert order_router._VISIBILITY_BY_ORDER_ID[201]["orderStatus_seen"] is True


def test_untracked_openorder_and_orderstatus_callbacks_remain_ignored(capsys) -> None:
    _reset_router_state()

    order_router._on_ibkr_callback({"event_type": "openOrder", "order_id": 999, "symbol": "ZZZZ"})
    order_router._on_ibkr_callback({"event_type": "orderStatus", "order_id": 999, "status": "Submitted"})

    out = capsys.readouterr().out
    assert "[EXECUTION][CALLBACK_IGNORED] event_type=openorder order_id=999" in out
    assert "[EXECUTION][CALLBACK_IGNORED] event_type=orderstatus order_id=999" in out
    assert not order_router._RUNTIME_ORDERS


def test_execdetails_is_single_fill_authority_and_orderstatus_fill_signal_is_ignored() -> None:
    _reset_router_state()
    row = _seed_tracked_order(order_id=301)

    order_router._on_ibkr_callback(
        {"event_type": "orderStatus", "order_id": 301, "status": "Filled", "filled_qty": 10, "remaining": 0}
    )
    assert row.filled_qty == 0
    assert row.canonical_state != "FILLED"

    order_router._on_ibkr_callback(
        {
            "event_type": "execDetails",
            "order_id": 301,
            "symbol": "AAPL",
            "shares": 10,
            "price": 101.25,
            "execId": "abc-301",
            "execution": _Execution(order_id=301, shares=10, price=101.25),
        }
    )

    assert row.filled_qty == 10
    assert row.canonical_state == "FILLED"
    assert row.fill_seen is True


def test_duplicate_execdetails_is_deduped() -> None:
    _reset_router_state()
    row = _seed_tracked_order(order_id=401)

    payload = {
        "event_type": "execDetails",
        "order_id": 401,
        "symbol": "AAPL",
        "shares": 5,
        "price": 99.0,
        "execId": "dup-401",
    }
    order_router._on_ibkr_callback(payload)
    order_router._on_ibkr_callback(payload)

    assert row.filled_qty == 5
    assert len(row.seen_exec_ids) == 1


def test_fill_awaits_ibkr_position_confirmation_and_management_path_can_emit_exit() -> None:
    _reset_router_state()
    _seed_tracked_order(order_id=501, symbol="AAPL", qty=8)

    order_router._on_ibkr_callback(
        {
            "event_type": "execDetails",
            "order_id": 501,
            "symbol": "AAPL",
            "shares": 8,
            "price": 100.0,
            "execId": "fill-501",
        }
    )

    assert "AAPL" not in order_router._RUNTIME_POSITIONS
    order_router._on_ibkr_callback({"event_type": "position", "order_id": 501, "symbol": "AAPL", "position": 8, "avgCost": 100.0})
    assert order_router._IBKR_POSITIONS_BY_SYMBOL["AAPL"].quantity == 8

    manager = PositionManagementEngine()
    managed = ManagedPosition(symbol="AAPL", side="LONG", quantity=8, entry_price=100.0, stop_price=99.0)
    result = manager.manage_position(managed, {"current_price": 98.5, "structure_broken": True})

    assert result.closed is True
    assert result.exit_reason == "structure_break"


def test_exit_fill_reaches_terminal_closed_lifecycle_state() -> None:
    engine = TradeLifecycleEngine()
    trade_id = "trade-601"

    opened = engine.apply_event(
        LifecycleEvent(
            event_id="e1",
            lifecycle_trade_id=trade_id,
            symbol="AAPL",
            side="LONG",
            event_type="ENTRY_FILL",
            quantity=10,
            price=100.0,
            timestamp="2026-04-09T00:00:00+00:00",
            order_id="entry-1",
            execution_id="exec-entry-1",
        )
    )
    closed = engine.apply_event(
        LifecycleEvent(
            event_id="e2",
            lifecycle_trade_id=trade_id,
            symbol="AAPL",
            side="LONG",
            event_type="EXIT_FILL",
            quantity=10,
            price=101.0,
            timestamp="2026-04-09T00:01:00+00:00",
            order_id="exit-1",
            execution_id="exec-exit-1",
        )
    )

    assert opened is not None
    assert closed is not None
    assert closed.status == "CLOSED"
    assert closed.quantity_open == 0
    assert closed.closed_at == "2026-04-09T00:01:00+00:00"


def test_outside_rth_warning_does_not_force_broker_inactive_unknown() -> None:
    _reset_router_state()
    row = _seed_tracked_order(order_id=701)

    order_router._on_ibkr_callback(
        {
            "event_type": "error",
            "order_id": 701,
            "errorCode": 2109,
            "errorString": "Outside Regular Trading Hours is ignored",
        }
    )
    order_router._on_ibkr_callback(
        {"event_type": "orderStatus", "order_id": 701, "status": "Inactive", "remaining": 10}
    )

    assert row.queued_for_rth_seen is True
    assert row.final_execution_state != "BROKER_INACTIVE_UNKNOWN"


def test_unknown_orderid_and_symbol_leakage_is_rejected_without_backfill(capsys) -> None:
    _reset_router_state()

    order_router._on_ibkr_callback(
        {
            "event_type": "execDetails",
            "execution": _Execution(order_id=0, shares=5, price=99.0),
            "execId": "orphan-fill",
        }
    )

    out = capsys.readouterr().out
    assert "[EXECUTION][FORCED_BACKFILL]" not in out
    assert "[ORDER_EVENT][UNMATCHED] event=EXECUTION reason=unknown_order_id order_id=0" in out
    assert "[EXECUTION][RECONCILIATION_FAILED] event=EXECUTION callback=execDetails order_id=0" in out
    assert 0 not in order_router._RUNTIME_ORDERS
