from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.config.runtime_config import RunMode
from src.core import paper_release
from src.ibkr.position_snapshot import BrokerPositionResult


class Client:
    client_id = 7
    _position_connection_epoch = 1
    _managed_accounts = ["DU100"]

    def __init__(self):
        self.rows = ()
        self.orders = []
        self.callback = None

    def is_connected(self):
        return True

    def register_reconciliation_callback(self, callback):
        self.callback = callback

    def position_snapshot(self):
        return BrokerPositionResult(self.rows, "COMPLETE", "DU100", datetime.now(timezone.utc))

    def openOrders(self, *, require_complete):
        assert require_complete
        return self.orders


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setattr(paper_release, "covered_opening_window",
                        lambda now: SimpleNamespace(phase="RTH_OPEN"))
    return SimpleNamespace(startup_recovery_complete=lambda: True,
                           _failsafe_block_new_entries=False, _native_quarantined=False)


def test_release_default_and_attestation(monkeypatch):
    monkeypatch.delenv("ROSS_PAPER_RELEASE_ENABLED", raising=False)
    assert paper_release.PaperRelease.from_environment(RunMode.READ_ONLY, False, []) is None
    monkeypatch.setenv("ROSS_PAPER_RELEASE_ENABLED", "1")
    monkeypatch.delenv("ROSS_PAPER_EXCLUSIVE_START_ATTESTED", raising=False)
    monkeypatch.setattr(paper_release, "get_config", lambda key: "MICRO")
    monkeypatch.setattr(paper_release, "get_force_clean_start", lambda: False)
    with pytest.raises(RuntimeError, match="PAPER_RELEASE_OPERATOR_ATTESTATION_REQUIRED"):
        paper_release.PaperRelease.from_environment(RunMode.PAPER, True, ["ross_momentum"])
    with pytest.raises(RuntimeError, match="PAPER_RELEASE_REQUIRES_PAPER_MICRO_ROSS"):
        paper_release.PaperRelease.from_environment(RunMode.READ_ONLY, False, ["ross_momentum"])


@pytest.mark.parametrize("quantity", [1, 0.125])
def test_legacy_positions_latch_refusal(engine, quantity):
    gate = paper_release.PaperRelease("DU100")
    client = Client()
    client.rows = (SimpleNamespace(account="DU100", symbol="XYZ", position=quantity),)
    with pytest.raises(RuntimeError, match="PAPER_RELEASE_START_NOT_FLAT"):
        gate.check_start(client, engine, datetime.now(timezone.utc))
    client.rows = ()
    with pytest.raises(RuntimeError, match="PAPER_RELEASE_START_NOT_FLAT"):
        gate.check_start(client, engine, datetime.now(timezone.utc))


@pytest.mark.parametrize(("change", "reason"), [
    (lambda client: setattr(client, "_position_connection_epoch", 2), "NATIVE_SCOPE_CHANGED"),
    (lambda client: client.callback({"event_type": "openOrder"}), "UNEXPECTED_ACTIVITY"),
    (lambda client: client.orders.append(object()), "CURRENT_CLIENT_ORDERS_PRESENT"),
])
def test_final_check_refuses_observed_change(engine, change, reason):
    gate = paper_release.PaperRelease("DU100")
    client = Client()
    gate.check_start(client, engine, datetime.now(timezone.utc))
    change(client)
    with pytest.raises(RuntimeError, match=f"PAPER_RELEASE_{reason}"):
        gate.check_start(client, engine, datetime.now(timezone.utc))


def test_final_boundary_consumes_only_one_attempt(engine):
    gate = paper_release.PaperRelease("DU100")
    client = Client()
    request = SimpleNamespace(setup_family_id="ABCD", relationship_context=None,
                              quantity=1, stop_loss_price=10, take_profit_price=None)
    contract = SimpleNamespace(secType="STK")
    order = SimpleNamespace(totalQuantity=1, action="BUY", account="DU100")
    consume = gate.authorize(request, client, contract, order, datetime.now(timezone.utc), engine)
    assert not gate.attempted
    consume()
    assert gate.attempted
    client.callback({"event_type": "position", "position": 1})
    assert gate.rejection is None
    with pytest.raises(RuntimeError, match="PAPER_RELEASE_ENTRY_ATTEMPT_USED"):
        gate.authorize(request, client, contract, order, datetime.now(timezone.utc), engine)


def test_unexpected_activity_between_prepare_and_wire_blocks_entry(engine):
    gate = paper_release.PaperRelease("DU100")
    client = Client()
    request = SimpleNamespace(setup_family_id="ABCD", relationship_context=None,
                              quantity=1, stop_loss_price=10, take_profit_price=None)
    order = SimpleNamespace(totalQuantity=1, action="BUY", account="DU100")
    consume = gate.authorize(request, client, SimpleNamespace(secType="STK"), order,
                             datetime.now(timezone.utc), engine)
    client.callback({"event_type": "openOrder"})
    with pytest.raises(RuntimeError, match="PAPER_RELEASE_UNEXPECTED_ACTIVITY"):
        consume()
    assert not gate.attempted
