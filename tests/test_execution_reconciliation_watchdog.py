from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.execution import order_router


def _reset_state() -> None:
    order_router._RUNTIME_ORDERS.clear()
    order_router._RUNTIME_POSITIONS.clear()
    order_router._BROKER_POSITION_LAST_QTY_BY_SYMBOL.clear()
    order_router._IBKR_HEALTH_STATE.update(
        {
            "broker_connected": False,
            "market_data_ok": True,
            "historical_data_ok": True,
            "order_channel_ok": True,
            "degraded": False,
            "recovered_at": None,
            "last_error_codes": [],
            "last_recovery_codes": [],
        }
    )


def test_position_reconciliation_verdicts(capsys, monkeypatch) -> None:
    _reset_state()
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(order_router, "_position_reconciliation_window_seconds", lambda: 1)

    order_router._RUNTIME_ORDERS[1] = order_router.TrackedOrder(
        broker_order_id=1,
        order_ref="A",
        symbol="AAA",
        side="BUY",
        total_qty=10,
        filled_qty=10,
        first_fill_seen_at=(now - timedelta(seconds=10)).isoformat(),
    )
    order_router._RUNTIME_ORDERS[2] = order_router.TrackedOrder(
        broker_order_id=2,
        order_ref="B",
        symbol="BBB",
        side="BUY",
        total_qty=5,
        filled_qty=0,
    )
    order_router._RUNTIME_ORDERS[3] = order_router.TrackedOrder(
        broker_order_id=3,
        order_ref="C",
        symbol="CCC",
        side="BUY",
        total_qty=7,
        filled_qty=7,
        first_fill_seen_at=(now - timedelta(seconds=10)).isoformat(),
    )
    order_router._RUNTIME_ORDERS[4] = order_router.TrackedOrder(
        broker_order_id=4,
        order_ref="D",
        symbol="DDD",
        side="BUY",
        total_qty=5,
        filled_qty=5,
        avg_fill_price=10.0,
        first_fill_seen_at=(now - timedelta(seconds=10)).isoformat(),
    )
    order_router._BROKER_POSITION_LAST_QTY_BY_SYMBOL["EEE"] = 5

    positions = [
        type("Pos", (), {"symbol": "AAA", "position": 10, "avgCost": 10.0})(),
        type("Pos", (), {"symbol": "BBB", "position": 5, "avgCost": 10.0})(),
        type("Pos", (), {"symbol": "DDD", "position": 5, "avgCost": 11.0})(),
        type("Pos", (), {"symbol": "EEE", "position": 0, "avgCost": 0.0})(),
    ]

    order_router._run_passive_position_reconciliation(positions=positions)
    out = capsys.readouterr().out

    assert "symbol=AAA" in out and "verdict=ALIGNED" in out
    assert "symbol=BBB" in out and "[POSITION][REPAIR_CREATE]" in out
    assert "symbol=BBB" in out and "verdict=ALIGNED" in out
    assert "symbol=CCC" in out and "verdict=LOCAL_FILL_WITHOUT_BROKER_POSITION" in out
    assert "symbol=DDD" in out and "[POSITION][REPAIR_UPDATE]" in out
    assert "symbol=DDD" in out and "verdict=ALIGNED" in out
    assert "symbol=EEE" in out and "verdict=POSITION_CLOSED_ALIGNED" in out
    assert order_router._RUNTIME_POSITIONS["BBB"].qty == 5
    assert order_router._RUNTIME_POSITIONS["DDD"].avg_price == 11.0


def test_watchdog_classification() -> None:
    _reset_state()
    now = datetime.now(timezone.utc)

    sub = order_router.TrackedOrder(broker_order_id=10, order_ref="S", symbol="SUB", side="BUY", total_qty=1)
    sub.first_seen_at = (now - timedelta(seconds=20)).isoformat()

    working = order_router.TrackedOrder(broker_order_id=11, order_ref="W", symbol="WRK", side="BUY", total_qty=1)
    working.first_seen_at = (now - timedelta(seconds=30)).isoformat()
    working.ack_seen = True
    working.working_seen = True
    working.working_seen_at = (now - timedelta(seconds=30)).isoformat()

    partial = order_router.TrackedOrder(broker_order_id=12, order_ref="P", symbol="PRT", side="BUY", total_qty=10, filled_qty=5)
    partial.ack_seen = True
    partial.working_seen = True
    partial.first_fill_seen_at = (now - timedelta(seconds=40)).isoformat()

    normal = order_router.TrackedOrder(broker_order_id=13, order_ref="N", symbol="NRM", side="BUY", total_qty=1)
    normal.first_seen_at = now.isoformat()

    assert order_router._classify_watchdog_state(sub, now)[0] == "SUBMITTED_NO_ACK_TIMEOUT"
    assert order_router._classify_watchdog_state(working, now)[0] == "WORKING_NO_FILL_TIMEOUT"
    assert order_router._classify_watchdog_state(partial, now)[0] == "PARTIAL_FILL_STALLED"
    assert order_router._classify_watchdog_state(normal, now)[0] == "NORMAL_IN_FLIGHT"


def test_watchdog_reprice_attempt_increments(monkeypatch) -> None:
    _reset_state()
    now = datetime.now(timezone.utc)
    row = order_router.TrackedOrder(
        broker_order_id=44,
        order_ref="TRADING_OS|ROSS_MOMENTUM|WRK-1",
        symbol="WRK",
        side="BUY",
        total_qty=10,
        market_session="PREMARKET",
        working_seen=True,
        ack_seen=True,
        working_seen_at=(now - timedelta(seconds=20)).isoformat(),
        min_tick=0.01,
    )
    row.last_limit_price = 10.05
    row.max_reprice_attempts = 3
    order_router._RUNTIME_ORDERS[44] = row
    monkeypatch.setattr(order_router, "_watchdog_reprice_schedule_seconds", lambda: [1, 2, 3])
    monkeypatch.setattr(order_router, "_wait_for_ibkr_snapshot_for_symbol", lambda *_a, **_k: {"bid": 10.0, "ask": 10.05})

    calls = []

    class _Client:
        def qualifyContracts(self, c):
            c.conId = 1
            return [c]

        def placeOrder(self, oid, _contract, order):
            calls.append((oid, order.lmtPrice, order.eTradeOnly, order.firmQuoteOnly, order.outsideRth))

    class _Manager:
        def get_client(self):
            return _Client()

    monkeypatch.setattr(order_router, "get_shared_ibkr_connection_manager", lambda readonly_enabled=False: _Manager())
    order_router._run_watchdog_checks(now=now)
    assert row.reprice_attempt_count == 1
    assert len(calls) == 1
    assert calls[0][2:] == (False, False, True)


def test_watchdog_reprice_aborts_without_quote_context(monkeypatch, capsys) -> None:
    _reset_state()
    now = datetime.now(timezone.utc)
    row = order_router.TrackedOrder(
        broker_order_id=45,
        order_ref="TRADING_OS|ROSS_MOMENTUM|WRK-2",
        symbol="WRK",
        side="BUY",
        total_qty=10,
        market_session="PREMARKET",
        working_seen=True,
        ack_seen=True,
        working_seen_at=(now - timedelta(seconds=20)).isoformat(),
    )
    row.max_reprice_attempts = 3
    order_router._RUNTIME_ORDERS[45] = row
    monkeypatch.setattr(order_router, "_watchdog_reprice_schedule_seconds", lambda: [1, 2, 3])
    monkeypatch.setattr(order_router, "_wait_for_ibkr_snapshot_for_symbol", lambda *_a, **_k: {"bid": None, "ask": None})
    order_router._run_watchdog_checks(now=now)
    assert row.reprice_attempt_count == 0
    assert "reason=NO_QUOTE_CONTEXT" in capsys.readouterr().out


def test_watchdog_reprice_aborts_when_attempt_budget_exhausted(monkeypatch, capsys) -> None:
    _reset_state()
    now = datetime.now(timezone.utc)
    row = order_router.TrackedOrder(
        broker_order_id=46,
        order_ref="TRADING_OS|ROSS_MOMENTUM|WRK-3",
        symbol="WRK",
        side="BUY",
        total_qty=10,
        market_session="PREMARKET",
        working_seen=True,
        ack_seen=True,
        working_seen_at=(now - timedelta(seconds=20)).isoformat(),
        reprice_attempt_count=3,
        max_reprice_attempts=3,
    )
    order_router._RUNTIME_ORDERS[46] = row
    order_router._run_watchdog_checks(now=now)
    assert "reason=MAX_REPRICE_ATTEMPTS_REACHED" in capsys.readouterr().out


def test_canonical_session_mapping() -> None:
    assert order_router._canonical_execution_session("PRE") == "PREMARKET"
    assert order_router._canonical_execution_session("REG") == "RTH"
    assert order_router._canonical_execution_session("AFTER") == "AFTER_HOURS"
    assert order_router._canonical_execution_session("X") == "CLOSED"


def test_ibkr_health_recovers_when_substates_restore(capsys) -> None:
    _reset_state()

    order_router._update_ibkr_health(event_type="connect")
    order_router._update_ibkr_health(event_type="error", code=2103)
    assert order_router._IBKR_HEALTH_STATE["degraded"] is True

    order_router._update_ibkr_health(event_type="error", code=2104)
    out = capsys.readouterr().out

    assert order_router._IBKR_HEALTH_STATE["degraded"] is False
    assert order_router._IBKR_HEALTH_STATE["recovered_at"] is not None
    assert "[IBKR][HEALTH_RECOVERY]" in out


def test_fill_and_position_lifecycle_evidence(capsys) -> None:
    _reset_state()
    order_router._upsert_order_from_submission(order_id=77, symbol="TRTH", side="BUY", total_qty=10, order_ref="TRADING_OS|ROSS_MOMENTUM|TRTH-77")

    order_router._apply_fill_to_tracked_order(
        order_id=77,
        symbol="TRTH",
        fill_qty=10,
        fill_price=22.0,
        exec_id="EX-77",
        timestamp=datetime.now(timezone.utc).isoformat(),
        source="IBKR_EXECUTION",
    )
    order_router._run_passive_position_reconciliation(
        positions=[type("Pos", (), {"symbol": "TRTH", "position": 10, "avgCost": 22.0})()]
    )
    out = capsys.readouterr().out

    assert "[EXECUTION][FILL_CONFIRMED] symbol=TRTH" in out
    assert "marker=FILL_CONFIRMED_AWAITING_POSITION" in out
    assert "[EXECUTION][POSITION_OPEN_CONFIRMED] symbol=TRTH" in out


def test_reconciliation_summary_log_populates(monkeypatch, capsys) -> None:
    _reset_state()
    monkeypatch.setattr(order_router, "_fetch_ibkr_truth", lambda _mode: ([], [], []))
    monkeypatch.setattr(order_router, "_post_submission_ibkr_diagnostics", lambda **_: None)

    order_router.execute_intents(mode=order_router.RunMode.READ_ONLY, decisions=[])
    out = capsys.readouterr().out
    assert "[EXECUTION][RECONCILIATION_SUMMARY]" in out
    assert "intents_received=0" in out
