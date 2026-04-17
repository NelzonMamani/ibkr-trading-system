from __future__ import annotations

from types import SimpleNamespace

from src.core_engine.events import ExecutionEvent, RiskDecisionRecord, TradeIntentRecord
from src.core_engine.orchestrator import _compute_expectancy_metrics, run_cycle
from src.core_engine.state import SessionState


def _lifecycle_engine_from_trades(trades: dict[str, SimpleNamespace]) -> SimpleNamespace:
    return SimpleNamespace(
        snapshot=lambda: {trade_id: trade.to_dict() if hasattr(trade, "to_dict") else {} for trade_id, trade in trades.items()},
        get_trade=lambda trade_id: trades.get(str(trade_id)),
    )


def _configure_single_symbol_pipeline(monkeypatch, execution_events: list[ExecutionEvent]) -> None:
    monkeypatch.setattr(
        "src.core_engine.orchestrator.run_scanner_cycle",
        lambda **_: {
            "watchlist_k_symbols": ["ABCD"],
            "focus_m_symbols": ["ABCD"],
            "data_quality_by_symbol": {},
            "watchlist_k": [{"symbol": "ABCD", "last_price": 5.0}],
        },
    )
    monkeypatch.setattr("src.core_engine.orchestrator.resolve_entry_price", lambda *_args, **_kwargs: (5.0, "IBKR_SNAPSHOT"))
    monkeypatch.setattr(
        "src.core_engine.orchestrator.build_trade_intents",
        lambda *args, **_kwargs: [
            TradeIntentRecord(
                symbol=args[1],
                intent_id="intent-ABCD",
                setup_id="GAP_GO",
                side="LONG",
                entry="breakout",
                stop="structure",
                rationale="test",
                entry_price_source="IBKR_SNAPSHOT",
            )
        ],
    )
    monkeypatch.setattr(
        "src.core_engine.orchestrator.evaluate_trade_intents",
        lambda **_: [
            RiskDecisionRecord(
                symbol="ABCD",
                intent_id="intent-ABCD",
                decision="ALLOW",
                max_position_size=100,
                constraints=[],
                triggered_rules=[],
                rationale="PASS",
                approved_quantity=1,
            )
        ],
    )
    monkeypatch.setattr("src.core_engine.orchestrator.execute_intents", lambda **_: execution_events)


def test_analytics_uses_lifecycle_truth(monkeypatch, capsys) -> None:
    event = ExecutionEvent(
        symbol="ABCD",
        intent_id="intent-ABCD",
        action="SUBMITTED",
        detail="event_detail_not_authoritative",
        event_type="ORDER_FILLED",
        filled_quantity=10,
        avg_fill_price=999.0,
    )
    event.lifecycle_trade_id = "trade-1"
    _configure_single_symbol_pipeline(monkeypatch, [event])

    trade = SimpleNamespace(
        state="EXITED",
        symbol="ABCD",
        entry_fill_price=5.0,
        avg_fill_price=5.0,
        exit_fill_price=5.5,
        realized_pnl=50.0,
        holding_duration_seconds=90,
        exit_reason="TARGET_FILLED",
        partial_exit_count=1,
        entry_fill_time="2026-04-17T12:00:00+00:00",
        entry_time="2026-04-17T11:59:00+00:00",
        last_update_ts="2026-04-17T12:01:00+00:00",
        exit_fill_time="2026-04-17T12:02:00+00:00",
        exit_time="2026-04-17T12:02:00+00:00",
    )
    lifecycle_engine = _lifecycle_engine_from_trades({"trade-1": trade})

    run_cycle(cycle_id=1, mode_value="PAPER", forced_session_state=SessionState.PRE, lifecycle_engine=lifecycle_engine)
    out = capsys.readouterr().out
    assert "[TRACE][ANALYTICS_SOURCE] trade_id=trade-1 symbol=ABCD source=trade_registry" in out
    assert "'exit_price': 5.5" in out
    assert "'realized_pnl': 50.0" in out
    assert "'exit_reason': 'TARGET_FILLED'" in out
    analytics_row_line = next(line for line in out.splitlines() if line.startswith("[TRADE_ANALYTICS][ROW]"))
    assert "event_detail_not_authoritative" not in analytics_row_line


def test_open_trade_not_emitted(monkeypatch, capsys) -> None:
    event = ExecutionEvent(symbol="ABCD", intent_id="intent-ABCD", action="SUBMITTED", detail="ok")
    event.lifecycle_trade_id = "trade-open"
    _configure_single_symbol_pipeline(monkeypatch, [event])

    lifecycle_engine = _lifecycle_engine_from_trades(
        {"trade-open": SimpleNamespace(state="PROTECTED", symbol="ABCD", exit_fill_price=5.5, exit_fill_time="t")}
    )
    run_cycle(cycle_id=2, mode_value="PAPER", forced_session_state=SessionState.PRE, lifecycle_engine=lifecycle_engine)
    out = capsys.readouterr().out
    assert "[ANALYTICS][SKIP] trade_id=trade-open reason=trade_not_closed" in out
    assert "[TRADE_ANALYTICS][ROW]" not in out


def test_missing_exit_truth_not_emitted(monkeypatch, capsys) -> None:
    event = ExecutionEvent(symbol="ABCD", intent_id="intent-ABCD", action="SUBMITTED", detail="ok")
    event.lifecycle_trade_id = "trade-incomplete"
    _configure_single_symbol_pipeline(monkeypatch, [event])

    lifecycle_engine = _lifecycle_engine_from_trades(
        {"trade-incomplete": SimpleNamespace(state="EXITED", symbol="ABCD", exit_fill_price=None, exit_fill_time=None)}
    )
    run_cycle(cycle_id=3, mode_value="PAPER", forced_session_state=SessionState.PRE, lifecycle_engine=lifecycle_engine)
    out = capsys.readouterr().out
    assert "[ANALYTICS][SKIP] trade_id=trade-incomplete reason=incomplete_lifecycle" in out
    assert "[TRADE_ANALYTICS][ROW]" not in out


def test_no_synthetic_trade_id(monkeypatch, capsys) -> None:
    event = ExecutionEvent(symbol="ABCD", intent_id="intent-only", action="SUBMITTED", detail="ok")
    _configure_single_symbol_pipeline(monkeypatch, [event])

    lifecycle_engine = _lifecycle_engine_from_trades({})
    run_cycle(cycle_id=4, mode_value="PAPER", forced_session_state=SessionState.PRE, lifecycle_engine=lifecycle_engine)
    out = capsys.readouterr().out
    assert "[ANALYTICS][NO_TRADES_AVAILABLE]" in out
    assert "[TRADE_ANALYTICS][ROW]" not in out
    assert "trade_id': '4-intent-only'" not in out


def test_expectancy_formula_correct() -> None:
    metrics = _compute_expectancy_metrics(
        [
            {"realized_pnl": 10.0},
            {"realized_pnl": -5.0},
            {"realized_pnl": 20.0},
            {"realized_pnl": -15.0},
        ]
    )
    assert metrics["win_rate"] == 0.5
    assert metrics["avg_winner"] == 15.0
    assert metrics["avg_loser"] == -10.0
    assert metrics["expectancy"] == 2.5


def test_duplicate_execution_events_same_trade_emit_one_row(monkeypatch, capsys) -> None:
    event_a = ExecutionEvent(symbol="ABCD", intent_id="intent-ABCD", action="SUBMITTED", detail="ok")
    event_b = ExecutionEvent(symbol="ABCD", intent_id="intent-ABCD", action="SUBMITTED", detail="ok")
    event_a.lifecycle_trade_id = "trade-dup"
    event_b.lifecycle_trade_id = "trade-dup"
    _configure_single_symbol_pipeline(monkeypatch, [event_a, event_b])

    lifecycle_engine = _lifecycle_engine_from_trades(
        {"trade-dup": SimpleNamespace(
            state="EXITED",
            symbol="ABCD",
            entry_fill_price=5.0,
            avg_fill_price=5.0,
            exit_fill_price=5.2,
            realized_pnl=20.0,
            holding_duration_seconds=60,
            exit_reason="TARGET_FILLED",
            partial_exit_count=0,
            entry_fill_time="2026-04-17T12:00:00+00:00",
            entry_time="2026-04-17T12:00:00+00:00",
            last_update_ts="2026-04-17T12:01:00+00:00",
            exit_fill_time="2026-04-17T12:02:00+00:00",
            exit_time="2026-04-17T12:02:00+00:00",
        )}
    )
    run_cycle(cycle_id=5, mode_value="PAPER", forced_session_state=SessionState.PRE, lifecycle_engine=lifecycle_engine)
    out = capsys.readouterr().out
    assert out.count("[TRADE_ANALYTICS][ROW]") == 1
