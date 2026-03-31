import pytest

from src.core_engine.events import RiskDecisionRecord
from src.core_engine.state import RunMode
from src.execution import order_router


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


def test_test_environment_skips_ibkr_validation(monkeypatch, capsys) -> None:
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests::x")

    def _fail_validate(mode: RunMode) -> None:
        raise AssertionError(f"validation should be skipped in tests: {mode}")

    monkeypatch.setattr(order_router, "_validate_ibkr_connection", _fail_validate)

    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_allow_decision()])
    out = capsys.readouterr().out

    assert events[0].action == "SUBMITTED"
    assert "[EXECUTION][TEST_MODE] Skipping IBKR connection validation" in out


def test_non_test_environment_enforces_ibkr_validation(monkeypatch) -> None:
    monkeypatch.setattr(order_router, "_is_test_environment", lambda: False)

    def _raise_validate(mode: RunMode) -> None:
        raise RuntimeError(f"strict validation called for {mode.value}")

    monkeypatch.setattr(order_router, "_validate_ibkr_connection", _raise_validate)

    with pytest.raises(RuntimeError, match="strict validation called for LIVE"):
        order_router.execute_intents(mode=RunMode.LIVE, decisions=[_allow_decision()])


def test_paper_and_live_dispatch_use_ibkr(monkeypatch, capsys) -> None:
    monkeypatch.setattr(order_router, "_is_test_environment", lambda: False)
    monkeypatch.setattr(order_router, "_validate_ibkr_connection", lambda mode: None)

    order_router.execute_intents(mode=RunMode.PAPER, decisions=[_allow_decision()])
    paper_out = capsys.readouterr().out
    order_router.execute_intents(mode=RunMode.LIVE, decisions=[_allow_decision()])
    live_out = capsys.readouterr().out

    assert "[EXECUTION][DISPATCH] symbol=MCRO dispatch=IBKR" in paper_out
    assert "[EXECUTION][DISPATCH] symbol=MCRO dispatch=IBKR" in live_out


def test_mode_connection_state_logging(monkeypatch, capsys) -> None:
    monkeypatch.setattr(order_router, "_is_test_environment", lambda: False)
    monkeypatch.setattr(order_router, "_validate_ibkr_connection", lambda mode: None)

    order_router.execute_intents(mode=RunMode.PAPER, decisions=[_allow_decision()])
    paper_out = capsys.readouterr().out
    order_router.execute_intents(mode=RunMode.LIVE, decisions=[_allow_decision()])
    live_out = capsys.readouterr().out
    order_router.execute_intents(mode=RunMode.SIM, decisions=[_allow_decision()])
    sim_out = capsys.readouterr().out
    order_router.execute_intents(mode=RunMode.READ_ONLY, decisions=[_allow_decision()])
    read_only_out = capsys.readouterr().out

    assert "[EXECUTION][MODE] mode=PAPER broker_connection_state=CONNECTED" in paper_out
    assert "[EXECUTION][MODE] mode=LIVE broker_connection_state=CONNECTED" in live_out
    assert "[EXECUTION][MODE] mode=SIM broker_connection_state=DISCONNECTED" in sim_out
    assert "[EXECUTION][MODE] mode=READ_ONLY broker_connection_state=DISCONNECTED" in read_only_out
