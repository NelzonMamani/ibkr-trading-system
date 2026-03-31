from __future__ import annotations

from types import SimpleNamespace

from src.config.config_resolver import set_config_overrides
from src.core_engine.events import RiskDecisionRecord
from src.core_engine.state import RunMode
from src.execution import order_router
from src.execution.order_router import execute_intents
from src.core_engine import orchestrator


def setup_function() -> None:
    set_config_overrides({})


def teardown_function() -> None:
    set_config_overrides({})


def _decision(*, qty: int = 5, entry_price: float = 10.0) -> RiskDecisionRecord:
    return RiskDecisionRecord(
        symbol="AAPL",
        intent_id="intent-1",
        decision="ALLOW",
        max_position_size=qty,
        constraints=[],
        triggered_rules=[],
        rationale="ok",
        available_funds=10000.0,
        order_value=float(qty) * entry_price,
        risk_allowed=True,
        capital_source="IBKR_CANONICAL",
        approved_quantity=qty,
        entry_price=entry_price,
    )


def test_no_test_fill_fallback_in_paper_runtime_by_default(monkeypatch):
    monkeypatch.delenv("IBKR_ENABLE_TEST_ONLY_FILL", raising=False)
    events = execute_intents(mode=RunMode.PAPER, decisions=[_decision()])
    assert len(events) == 1
    event = events[0]
    assert event.action == "SUBMITTED"
    assert event.event_type in {"ORDER_SUBMITTED", "ORDER_ACKNOWLEDGED", "ORDER_WORKING"}
    assert event.fill_source != "TEST_ONLY_FILL"
    assert event.lifecycle_state != "FILLED"


def test_position_open_requires_nonzero_authoritative_fill_price(monkeypatch):
    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True})

    def _fake_fetch(_mode):
        executions = [SimpleNamespace(orderId=1, shares=5, price=None)]
        return [], executions, []

    monkeypatch.setattr(order_router, "_fetch_ibkr_truth", _fake_fetch)
    events = execute_intents(mode=RunMode.PAPER, decisions=[_decision()])
    assert events[0].filled_quantity > 0
    assert events[0].avg_fill_price is None
    assert events[0].pending_fill_price_resolution is True


def test_test_only_fill_path_requires_explicit_test_flag(monkeypatch):
    monkeypatch.setenv("IBKR_ENABLE_TEST_ONLY_FILL", "true")
    monkeypatch.setenv("IBKR_TEST_FILL_TIMEOUT_SECONDS", "0")
    events = execute_intents(mode=RunMode.PAPER, decisions=[_decision()])
    assert events[0].fill_source == "TEST_ONLY_FILL"


def test_lifecycle_transitions_reflect_authoritative_broker_fill(monkeypatch):
    def _fake_fetch(_mode):
        executions = [SimpleNamespace(orderId=1, shares=3, price=11.25)]
        return [], executions, []

    monkeypatch.setattr(order_router, "_fetch_ibkr_truth", _fake_fetch)
    events = execute_intents(mode=RunMode.PAPER, decisions=[_decision(qty=3, entry_price=11.0)])
    event = events[0]
    assert event.event_type == "ORDER_FILLED"
    assert event.lifecycle_state == "FILLED"
    assert event.fill_source == "IBKR_EXECUTION"
    assert event.avg_fill_price == 11.25


def test_price_consistency_warn_emits_for_mismatch(capsys):
    orchestrator._emit_price_consistency_log(
        symbol="AAPL",
        scanner_price=10.0,
        intent_price=10.0,
        risk_entry_price=20.0,
        submission_context_price=22.0,
    )
    output = capsys.readouterr().out
    assert "[PRICE][CONSISTENCY]" in output
    assert "[PRICE][CONSISTENCY_WARN]" in output


def test_paper_micro_sizing_override_caps_quantity():
    set_config_overrides(
        {
            "PAPER_VALIDATION_SIZING_ENABLED": True,
            "PAPER_VALIDATION_MAX_SHARES": 2,
            "PAPER_VALIDATION_MAX_NOTIONAL": 15.0,
            "PAPER_VALIDATION_FORCE_SINGLE_SHARE": False,
        }
    )
    events = execute_intents(mode=RunMode.PAPER, decisions=[_decision(qty=10, entry_price=10.0)])
    assert events[0].remaining_quantity == 1


def test_paper_micro_sizing_force_single_share():
    set_config_overrides(
        {
            "PAPER_VALIDATION_SIZING_ENABLED": True,
            "PAPER_VALIDATION_MAX_SHARES": 10,
            "PAPER_VALIDATION_MAX_NOTIONAL": 100.0,
            "PAPER_VALIDATION_FORCE_SINGLE_SHARE": True,
        }
    )
    events = execute_intents(mode=RunMode.PAPER, decisions=[_decision(qty=10, entry_price=10.0)])
    assert events[0].remaining_quantity == 1
