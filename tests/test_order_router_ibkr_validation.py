import pytest

from src.core_engine.events import RiskDecisionRecord
from src.core_engine.state import RunMode
from src.execution import order_router


def _reset_router() -> None:
    order_router._RUNTIME_ORDERS.clear()
    order_router._RUNTIME_POSITIONS.clear()
    order_router._SEEN_EXEC_IDS.clear()
    order_router._EXECUTION_EVENT_BUFFER.clear()
    order_router._UNMATCHED_CALLBACK_COUNT = 0
    order_router._RECONCILED_ORDERS_COUNT = 0
    order_router._RECONCILED_POSITIONS_COUNT = 0


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
    monkeypatch.setenv("EXECUTION_ENV", "TEST")

    def _fail_validate(mode: RunMode) -> None:
        raise AssertionError(f"validation should be skipped in tests: {mode}")

    monkeypatch.setattr(order_router, "_validate_ibkr_connection", _fail_validate)

    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_allow_decision()])
    out = capsys.readouterr().out

    assert events[0].action == "SUBMITTED"
    assert "[EXECUTION][TEST_MODE] Skipping IBKR connection validation" in out


def test_non_test_environment_enforces_ibkr_validation(monkeypatch) -> None:
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: False)

    def _raise_validate(mode: RunMode) -> None:
        raise RuntimeError(f"strict validation called for {mode.value}")

    monkeypatch.setattr(order_router, "_validate_ibkr_connection", _raise_validate)

    with pytest.raises(RuntimeError, match="strict validation called for LIVE"):
        order_router.execute_intents(mode=RunMode.LIVE, decisions=[_allow_decision()])


def test_paper_and_live_dispatch_use_ibkr(monkeypatch, capsys) -> None:
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: False)
    monkeypatch.setattr(order_router, "_validate_ibkr_connection", lambda mode: None)

    order_router.execute_intents(mode=RunMode.PAPER, decisions=[_allow_decision()])
    paper_out = capsys.readouterr().out
    order_router.execute_intents(mode=RunMode.LIVE, decisions=[_allow_decision()])
    live_out = capsys.readouterr().out

    assert "[EXECUTION][DISPATCH] symbol=MCRO dispatch=IBKR" in paper_out
    assert "[EXECUTION][DISPATCH] symbol=MCRO dispatch=IBKR" in live_out


def test_mode_connection_state_logging(monkeypatch, capsys) -> None:
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: False)
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


def test_callback_registration_unavailable_surfaces_degraded_fill_authority(monkeypatch, capsys) -> None:
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: False)
    monkeypatch.setattr(order_router, "_validate_ibkr_connection", lambda mode: None)
    monkeypatch.setattr(order_router, "_fetch_ibkr_truth", lambda mode: ([], [], []))

    class _NoCallbackClient:
        pass

    class _Manager:
        def get_client(self):
            return _NoCallbackClient()

        def connection_metadata(self):
            return {"connected_client_id": 1}

    monkeypatch.setattr(order_router, "get_shared_ibkr_connection_manager", lambda readonly_enabled=False: _Manager())
    _ = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_allow_decision()])
    out = capsys.readouterr().out
    assert "[EXECUTION][CALLBACK_UNAVAILABLE]" in out
    assert "[EXECUTION][FILL_AUTHORITY_DEGRADED] reason=execution_callback_unavailable" in out


def test_callback_registration_supported_logs_registered(monkeypatch, capsys) -> None:
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: False)
    monkeypatch.setattr(order_router, "_validate_ibkr_connection", lambda mode: None)
    monkeypatch.setattr(order_router, "_fetch_ibkr_truth", lambda mode: ([], [], []))

    class _CallbackClient:
        def register_execution_callback(self, cb):
            self.cb = cb

    class _Manager:
        def get_client(self):
            return _CallbackClient()

        def connection_metadata(self):
            return {"connected_client_id": 1}

    monkeypatch.setattr(order_router, "get_shared_ibkr_connection_manager", lambda readonly_enabled=False: _Manager())
    _ = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_allow_decision()])
    out = capsys.readouterr().out
    assert "[EXECUTION][CALLBACK_REGISTERED]" in out


def test_paper_mode_applies_size_override_and_system_order_ref(monkeypatch, capsys) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    decision = _allow_decision()
    decision.approved_quantity = 250.9
    decision.max_position_size = 100
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[decision])
    out = capsys.readouterr().out
    oid = events[0].broker_order_id
    tracked = order_router._RUNTIME_ORDERS[oid]
    assert tracked.total_qty == 100
    assert tracked.order_ref.startswith("TRADING_OS|ROSS_TEST|")
    assert "[EXECUTION][SIZE_NORMALIZED] symbol=MCRO raw_qty=250.9 final_qty=250" in out
    assert "[EXECUTION][SIZE_OVERRIDE] symbol=MCRO original_qty=250 overridden_qty=100" in out


def test_live_mode_not_overridden_by_paper_size_clamp(monkeypatch) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    decision = _allow_decision()
    decision.approved_quantity = 250
    decision.max_position_size = 250
    events = order_router.execute_intents(mode=RunMode.LIVE, decisions=[decision])
    oid = events[0].broker_order_id
    assert order_router._RUNTIME_ORDERS[oid].total_qty == 250
