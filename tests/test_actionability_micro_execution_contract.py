from __future__ import annotations

import pytest

from src.core.engines.trigger_engine import TriggerEngine
from src.core_engine.events import ExecutionEvent, PatternSummary, RiskDecisionRecord, TradeIntentRecord
from src.core_engine.orchestrator import _emit_final_decisions
from src.core_engine.state import RunMode
from src.execution import order_router
from src.execution.order_router import execute_intents
from src.risk.risk_audit import INITIAL_POSITION_PCT, AccountSnapshot, evaluate_trade_intents


@pytest.fixture(autouse=True)
def _test_execution_mode(monkeypatch) -> None:
    monkeypatch.setenv("EXECUTION_ENV", "TEST")
    order_router._EXECUTION_EVENT_BUFFER.clear()


def _assert_broker_truth_lifecycle(event: ExecutionEvent) -> None:
    normalized_source = "IBKR_EXECUTION" if event.source == "IBKR" else event.source
    assert normalized_source in {"IBKR_ORDER_STATUS", "IBKR_EXECUTION", "IBKR_RESYNC", "IBKR"}
    if event.filled_quantity > 0 and (event.avg_fill_price or 0) > 0:
        assert event.event_type == "ORDER_FILLED"
    elif event.filled_quantity > 0:
        assert event.event_type in {"ORDER_PARTIALLY_FILLED"}
    else:
        assert event.event_type in {"ORDER_ACKNOWLEDGED", "ORDER_WORKING"}


def test_trigger_engine_breakout_reports_actionable_reason() -> None:
    triggers = TriggerEngine().evaluate_triggers(
        symbol="ABCD",
        candles=[{"close": 10.2, "high": 10.3, "low": 9.9}],
        setups=[
            {
                "setup_family_id": "FLAT_TOP_BREAKOUT",
                "setup_detected": True,
                "required_trigger_types": ["BREAKOUT_HIGH"],
                "trigger_level": 10.0,
            }
        ],
        levels={"hod": 10.0},
        structure={"is_actionable": True},
    )
    assert triggers[0]["trigger_ready_now"] is True
    assert triggers[0]["trigger_reason"] == "breakout_already_through_level"


def test_paper_mode_sizes_from_capital_and_price(capsys) -> None:
    available_capital = 50_000
    focus_count = 1
    entry_price = 25.0
    decisions = evaluate_trade_intents(
        intents=[
            TradeIntentRecord(
                symbol="MCRO",
                intent_id="MCRO-1",
                setup_id="GAP_GO",
                side="LONG",
                entry="breakout",
                stop="structure",
                rationale="test",
                entry_price=25.0,
            )
        ],
        mode=RunMode.PAPER,
        health_status=None,
        account=AccountSnapshot(available_funds=available_capital, source="PAPER", canonical=True, broker_connection_state="SIMULATED"),
    )
    capital_per_symbol = available_capital / focus_count
    initial_capital = capital_per_symbol * INITIAL_POSITION_PCT
    expected_quantity = int(initial_capital // entry_price)
    out = capsys.readouterr().out
    assert decisions[0].approved_quantity == expected_quantity
    assert decisions[0].sizing_basis == "CAPITAL_BASED"
    assert f"[RISK][SIZE_RESULT] symbol=MCRO approved_quantity={expected_quantity}" in out
    assert decisions[0].entry_price == 25.0


def test_missing_price_blocks_pipeline(capsys) -> None:
    decisions = evaluate_trade_intents(
        intents=[
            TradeIntentRecord(
                symbol="NOPX",
                intent_id="NOPX-1",
                setup_id="GAP_GO",
                side="LONG",
                entry="breakout",
                stop="structure",
                rationale="test",
                entry_price=None,
            )
        ],
        mode=RunMode.PAPER,
        health_status=None,
        account=AccountSnapshot(available_funds=50_000, source="PAPER", canonical=True, broker_connection_state="SIMULATED"),
    )
    out = capsys.readouterr().out
    assert decisions[0].decision == "BLOCK"
    assert "INVALID_ENTRY_PRICE" in decisions[0].triggered_rules
    assert "[RISK][SIZE_BLOCK] symbol=NOPX reason=INVALID_ENTRY_PRICE" in out


def test_price_sanity_guard_rejects_placeholder_one_dollar(capsys) -> None:
    decisions = evaluate_trade_intents(
        intents=[
            TradeIntentRecord(
                symbol="PENNY",
                intent_id="PENNY-1",
                setup_id="GAP_GO",
                side="LONG",
                entry="breakout",
                stop="structure",
                rationale="test",
                entry_price=1.0,
            )
        ],
        mode=RunMode.PAPER,
        health_status=None,
        account=AccountSnapshot(available_funds=50_000, source="PAPER", canonical=True, broker_connection_state="SIMULATED"),
    )
    out = capsys.readouterr().out
    assert decisions[0].decision == "BLOCK"
    assert "INVALID_PRICE_SANITY_CHECK" in decisions[0].triggered_rules
    assert "[RISK][SIZE_BLOCK] symbol=PENNY reason=INVALID_PRICE_SANITY_CHECK" in out


def test_execution_dispatch_uses_approved_quantity_and_is_truthful(capsys) -> None:
    events = execute_intents(
        mode=RunMode.PAPER,
        decisions=[
            RiskDecisionRecord(
                symbol="MCRO",
                intent_id="MCRO-1",
                decision="ALLOW",
                max_position_size=1,
                constraints=[],
                triggered_rules=[],
                rationale="ok",
                approved_quantity=1,
                entry_price=25.0,
            )
        ],
    )
    out = capsys.readouterr().out
    assert events[0].action == "SUBMITTED"
    assert "qty=1" in events[0].detail
    assert "[EXECUTION][DISPATCH] symbol=MCRO dispatch=IBKR" in out


def test_final_decision_emits_one_terminal_line_per_symbol(capsys) -> None:
    _emit_final_decisions(
        focus=["ABCD"],
        pattern_summaries=[PatternSummary(symbol="ABCD", best_setup="P_GAP_GO", confidence=0.8, rationale="r", all_patterns=[])],
        intents=[TradeIntentRecord(symbol="ABCD", intent_id="1", setup_id="P_GAP_GO", side="LONG", entry="x", stop="y", rationale="r")],
        risk_decisions=[RiskDecisionRecord(symbol="ABCD", intent_id="1", decision="ALLOW", max_position_size=1, constraints=[], triggered_rules=[], rationale="ok", approved_quantity=1)],
        execution_events=[ExecutionEvent(symbol="ABCD", intent_id="1", action="SUBMITTED", detail="submitted qty=1", broker_order_id=12345, broker_status="Submitted")],
    )
    out = capsys.readouterr().out
    assert out.count("[ROSS][FINAL_DECISION] symbol=ABCD") == 1
    assert "outcome=ORDER_ACKNOWLEDGED" in out


def test_final_decision_flags_submission_without_broker_order_id(capsys) -> None:
    _emit_final_decisions(
        focus=["ABCD"],
        pattern_summaries=[PatternSummary(symbol="ABCD", best_setup="P_GAP_GO", confidence=0.8, rationale="r", all_patterns=[])],
        intents=[TradeIntentRecord(symbol="ABCD", intent_id="1", setup_id="P_GAP_GO", side="LONG", entry="x", stop="y", rationale="r")],
        risk_decisions=[RiskDecisionRecord(symbol="ABCD", intent_id="1", decision="ALLOW", max_position_size=1, constraints=[], triggered_rules=[], rationale="ok", approved_quantity=1)],
        execution_events=[ExecutionEvent(symbol="ABCD", intent_id="1", action="SUBMITTED", detail="submitted qty=1")],
    )
    out = capsys.readouterr().out
    assert "outcome=ORDER_SUBMISSION_TRACKING_ERROR" in out


def test_selected_setup_family_maps_to_trigger_candidate() -> None:
    from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1

    selected = RossMomentumStrategyV1._select_trigger_candidate(
        setup_family_id="ORB",
        trigger_candidates=[
            {"setup_family_id": "OPENING_RANGE_BREAKOUT", "trigger_type": "BREAKOUT_HIGH", "trigger_ready_now": True},
        ],
    )
    assert selected is not None
    assert selected["trigger_type"] == "BREAKOUT_HIGH"


def test_execute_intents_syncs_fill_from_ibkr_truth(monkeypatch, capsys) -> None:
    class _Exec:
        def __init__(self) -> None:
            self.orderId = 1
            self.shares = 10
            self.price = 25.5

    monkeypatch.setattr(
        "src.execution.order_router._fetch_ibkr_truth",
        lambda _mode: ([], [_Exec()], []),
    )
    events = execute_intents(
        mode=RunMode.PAPER,
        decisions=[
            RiskDecisionRecord(
                symbol="MCRO",
                intent_id="MCRO-1",
                decision="ALLOW",
                max_position_size=10,
                constraints=[],
                triggered_rules=[],
                rationale="ok",
                approved_quantity=10,
                entry_price=25.0,
            )
        ],
    )
    out = capsys.readouterr().out
    assert events[0].broker_order_id == 1
    assert events[0].filled_quantity == 10
    assert events[0].avg_fill_price == 25.5
    assert events[0].broker_status == "Filled"
    assert events[0].last_update_time is not None
    assert "[EXECUTION][FILL] symbol=MCRO qty=10 price=25.5" in out


def test_execute_intents_blocks_duplicate_symbol_using_ibkr_truth(monkeypatch, capsys) -> None:
    class _Pos:
        symbol = "MCRO"
        position = 100
        avgCost = 24.0

    monkeypatch.setattr(
        "src.execution.order_router._fetch_ibkr_truth",
        lambda _mode: ([], [], [_Pos()]),
    )
    events = execute_intents(
        mode=RunMode.PAPER,
        decisions=[
            RiskDecisionRecord(
                symbol="MCRO",
                intent_id="MCRO-1",
                decision="ALLOW",
                max_position_size=10,
                constraints=[],
                triggered_rules=[],
                rationale="ok",
                approved_quantity=10,
                entry_price=25.0,
            )
        ],
    )
    out = capsys.readouterr().out
    assert events[0].action == "BLOCKED"
    assert events[0].detail == "reason=DUPLICATE_PROTECTION"
    assert "[EXECUTION][BLOCK] symbol=MCRO reason=DUPLICATE_PROTECTION" in out


def test_ibkr_callback_creates_order_filled_event(monkeypatch, capsys) -> None:
    from src.execution import order_router

    monkeypatch.setattr("src.execution.order_router._fetch_ibkr_truth", lambda _mode: ([], [], []))
    monkeypatch.setenv("IBKR_ENABLE_TEST_ONLY_FILL", "false")
    order_router._on_ibkr_callback(
        {
            "symbol": "MCRO",
            "orderId": 1,
            "shares": 10,
            "price": 25.5,
            "time": "2026-03-31T00:00:00Z",
        }
    )
    events = execute_intents(
        mode=RunMode.PAPER,
        decisions=[
            RiskDecisionRecord(
                symbol="MCRO",
                intent_id="MCRO-1",
                decision="ALLOW",
                max_position_size=10,
                constraints=[],
                triggered_rules=[],
                rationale="ok",
                approved_quantity=10,
                entry_price=25.0,
            )
        ],
    )
    out = capsys.readouterr().out
    _assert_broker_truth_lifecycle(events[0])
    assert events[0].filled_quantity == 10
    assert "[EXECUTION][CALLBACK_RECEIVED]" in out


def test_paper_mode_can_emit_test_fill_fallback(monkeypatch, capsys) -> None:
    monkeypatch.setattr("src.execution.order_router._fetch_ibkr_truth", lambda _mode: ([], [], []))
    monkeypatch.setenv("IBKR_ENABLE_TEST_ONLY_FILL", "true")
    monkeypatch.setenv("EXECUTION_ENV", "TEST")
    monkeypatch.setenv("IBKR_TEST_FILL_TIMEOUT_SECONDS", "0")
    events = execute_intents(
        mode=RunMode.PAPER,
        decisions=[
            RiskDecisionRecord(
                symbol="MCRO",
                intent_id="MCRO-1",
                decision="ALLOW",
                max_position_size=10,
                constraints=[],
                triggered_rules=[],
                rationale="ok",
                approved_quantity=10,
                entry_price=25.0,
            )
        ],
    )
    out = capsys.readouterr().out
    assert events[0].source in {"TEST_FILL", "IBKR_ORDER_STATUS", "IBKR_EXECUTION", "IBKR_RESYNC", "IBKR"}
    if events[0].source == "TEST_FILL":
        assert events[0].event_type == "ORDER_FILLED"
        assert events[0].filled_quantity == 10
        assert "[EXECUTION][EVENT_CREATED] event_type=ORDER_FILLED source=TEST_FILL" in out
    else:
        _assert_broker_truth_lifecycle(events[0])
