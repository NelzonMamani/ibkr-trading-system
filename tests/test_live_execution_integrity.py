from types import SimpleNamespace

import pytest

from src.core_engine.events import TradeIntentRecord, RiskDecisionRecord
from src.core_engine.health import HealthStatus
from src.core_engine.state import RunMode
from src.execution.order_router import execute_intents
from src.risk.risk_audit import AccountSnapshot, evaluate_trade_intents
from src.utils.capital_resolver import resolve_available_capital


class FailingClient:
    def get_account_summary(self):
        raise RuntimeError("no account")


class GoodClient:
    def get_account_summary(self):
        return {"AvailableFunds": "168.42"}


def _intent(symbol: str, price: float = 2.5) -> TradeIntentRecord:
    return TradeIntentRecord(
        symbol=symbol,
        intent_id=f"{symbol}-1",
        setup_id="Micro Pullback",
        side="LONG",
        entry="Breakout",
        stop="Below support",
        rationale="test",
        tags=[],
        entry_price=price,
    )


def test_live_capital_unavailable_blocks_execution():
    decisions = evaluate_trade_intents(
        intents=[_intent("POLA")],
        mode=RunMode.LIVE,
        health_status=None,
        account=AccountSnapshot(available_funds=0.0, source="UNAVAILABLE", canonical=False, broker_connection_state="DEGRADED"),
    )
    assert decisions[0].decision == "BLOCK"
    assert "CANONICAL_CAPITAL_UNAVAILABLE" in decisions[0].triggered_rules


def test_live_forbids_capital_fallback():
    with pytest.raises(RuntimeError, match="CANONICAL_CAPITAL_UNAVAILABLE"):
        resolve_available_capital(FailingClient(), allow_fallback=False)


def test_approved_quantity_propagates_to_submission_detail():
    decision = RiskDecisionRecord(
        symbol="POLA",
        intent_id="POLA-1",
        decision="ALLOW",
        max_position_size=24,
        constraints=[],
        triggered_rules=[],
        rationale="ok",
        available_funds=168.0,
        order_value=60.0,
        risk_allowed=True,
        capital_source="IBKR_CANONICAL",
        approved_quantity=24,
        entry_price=2.5,
    )
    events = execute_intents(mode=RunMode.LIVE, decisions=[decision])
    assert events[0].action == "SUBMITTED"
    assert "qty=24" in events[0].detail


def test_quantity_mismatch_blocks():
    decision = RiskDecisionRecord(
        symbol="POLA",
        intent_id="POLA-1",
        decision="ALLOW",
        max_position_size=1,
        constraints=[],
        triggered_rules=[],
        rationale="ok",
        capital_source="IBKR_CANONICAL",
        approved_quantity=24,
        entry_price=2.5,
    )
    events = execute_intents(mode=RunMode.LIVE, decisions=[decision])
    assert events[0].action == "BLOCKED"
    assert "EXECUTION_QUANTITY_MISMATCH" in events[0].detail


def test_focus_split_position_size_deterministic():
    account = AccountSnapshot(available_funds=168.0, source="IBKR_CANONICAL", canonical=True, broker_connection_state="CONNECTED")
    decisions = evaluate_trade_intents(
        intents=[_intent("AAA"), _intent("BBB"), _intent("CCC")],
        mode=RunMode.LIVE,
        health_status=HealthStatus.DEGRADED,
        account=account,
    )
    assert all(d.max_position_size == 22 for d in decisions)


def test_capital_resolver_uses_ibkr_when_available():
    assert resolve_available_capital(GoodClient(), allow_fallback=False) == 168.42


def test_ibkr_validation_skipped_in_test_env(monkeypatch, capsys):
    monkeypatch.delenv("IBKR_CONNECTION_ACTIVE", raising=False)
    decision = RiskDecisionRecord(
        symbol="POLA",
        intent_id="POLA-1",
        decision="ALLOW",
        max_position_size=24,
        constraints=[],
        triggered_rules=[],
        rationale="ok",
        available_funds=168.0,
        order_value=60.0,
        risk_allowed=True,
        capital_source="IBKR_CANONICAL",
        approved_quantity=24,
        entry_price=2.5,
    )
    events = execute_intents(mode=RunMode.LIVE, decisions=[decision])
    out = capsys.readouterr().out
    assert events[0].action == "SUBMITTED"
    assert "[EXECUTION][TEST_MODE] Skipping IBKR connection validation" in out


def test_ibkr_validation_enforced_outside_test_env(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("TEST_MODE", raising=False)
    monkeypatch.delenv("IBKR_CONNECTION_ACTIVE", raising=False)
    decision = RiskDecisionRecord(
        symbol="POLA",
        intent_id="POLA-1",
        decision="ALLOW",
        max_position_size=24,
        constraints=[],
        triggered_rules=[],
        rationale="ok",
        available_funds=168.0,
        order_value=60.0,
        risk_allowed=True,
        capital_source="IBKR_CANONICAL",
        approved_quantity=24,
        entry_price=2.5,
    )
    with pytest.raises(RuntimeError, match="IBKR connection is not active"):
        execute_intents(mode=RunMode.LIVE, decisions=[decision])
