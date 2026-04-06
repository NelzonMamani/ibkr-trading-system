from types import SimpleNamespace

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


def test_submit_order_ack_enforced_in_strict_mode(monkeypatch) -> None:
    submitted_orders = []

    class _Client:
        def qualifyContracts(self, contract):
            contract.conId = 123
            contract.exchange = "SMART"
            contract.currency = "USD"
            contract.primaryExchange = "NASDAQ"
            contract.secType = "STK"
            return [contract]

        def submit_order(self, _contract, _order):
            submitted_orders.append(_order)
            return 111

        def wait_for_order_status(self, _order_id, timeout_seconds=5):
            return None

    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: False)
    with pytest.raises(RuntimeError, match="IBKR_ACKNOWLEDGEMENT_FAILED"):
        order_router._submit_ibkr_order(
            mode=RunMode.PAPER,
            client=_Client(),
            symbol="MCRO",
            side="BUY",
            quantity=1,
            order_ref="TRADING_OS|ROSS_MOMENTUM|MCRO-1",
        )
    assert len(submitted_orders) == 1
    assert getattr(submitted_orders[0], "outsideRth", None) is True
    assert submitted_orders[0].tif == "DAY"
    assert submitted_orders[0].orderType in {"MKT", "LMT", "STP", "STP LMT", "STP-LMT"}


@pytest.mark.parametrize("mode", [RunMode.PAPER, RunMode.LIVE])
def test_strict_mode_raises_broker_truth_not_confirmed_when_no_callbacks(monkeypatch, mode) -> None:
    order_router._RUNTIME_ORDERS.clear()
    order_router._VISIBILITY_BY_ORDER_ID.clear()
    order_router._RUNTIME_ORDERS[404] = order_router.TrackedOrder(
        broker_order_id=404,
        order_ref="MCRO-1",
        symbol="MCRO",
        side="BUY",
        total_qty=1,
        remaining_qty=1,
    )
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: False)
    with pytest.raises(RuntimeError, match="BROKER_TRUTH_NOT_CONFIRMED"):
        order_router._post_submission_ibkr_diagnostics(
            mode=mode,
            manager=SimpleNamespace(get_client=lambda: SimpleNamespace(openOrders=lambda: [], executions=lambda: [])),
            submitted_order_ids=[404],
        )
