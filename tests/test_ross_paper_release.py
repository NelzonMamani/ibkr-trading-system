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


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig"])
def test_release_fee_ceiling_requires_applicable_private_broker_receipt(tmp_path, encoding):
    import json
    from decimal import Decimal

    from src.core.capital_management_authority import PaperEntryFeeCeiling

    stamp = datetime.fromisoformat("2026-11-23T14:35:00+00:00")
    path = tmp_path / "entry-fee-ceiling.json"
    with pytest.raises(RuntimeError, match="PAPER_RELEASE_ENTRY_COST_AUTHORITY_REQUIRED"):
        PaperEntryFeeCeiling.load(path, expected_account="DU123", now=stamp)
    receipt = {
        "schema": "IBKR_CONFIRMED_USD_ENTRY_FEE_CEILING_V1",
        "account": "DU123", "currency": "USD", "security_type": "STK", "exchange": "SMART",
        "side": "BUY", "quantity": 1, "max_limit_price": "20", "max_fee": "0",
        "valid_until_utc": "2026-11-23T15:00:00Z", "broker_reference": "inert receipt",
    }
    path.write_text(json.dumps(receipt), encoding=encoding)
    assert PaperEntryFeeCeiling.load(path, expected_account="DU123", now=stamp).max_fee == Decimal("0")
    with pytest.raises(RuntimeError, match="PAPER_RELEASE_ENTRY_COST_AUTHORITY_WRONG_ACCOUNT"):
        PaperEntryFeeCeiling.load(path, expected_account="DU456", now=stamp)
    with pytest.raises(RuntimeError, match="PAPER_RELEASE_ENTRY_COST_AUTHORITY_EXPIRED"):
        PaperEntryFeeCeiling.load(path, expected_account="DU123",
                                  now=datetime.fromisoformat("2026-11-23T15:00:00+00:00"))
    receipt.pop("max_fee")
    path.write_text(json.dumps(receipt), encoding=encoding)
    with pytest.raises(RuntimeError, match="PAPER_RELEASE_ENTRY_COST_AUTHORITY_INVALID"):
        PaperEntryFeeCeiling.load(path, expected_account="DU123", now=stamp)


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


def test_exclusive_start_does_not_enter_generic_adoption_or_repair(engine):
    from src.core.active_trade_registry import ActiveTradeRegistry
    from src.execution.startup_recovery_authority import StartupRecoveryAuthority

    def forbidden(*args, **kwargs):
        pytest.fail("clean profile called generic startup adoption or repair")

    client = Client()
    client.rows = (SimpleNamespace(account="DU100", symbol="XYZ", position=0.125),)
    gate = paper_release.PaperRelease("DU100")
    authority = StartupRecoveryAuthority(
        run_mode="PAPER", provider=SimpleNamespace(
            get_positions=forbidden, get_open_orders=forbidden),
        post_fill_lifecycle=SimpleNamespace(startup_safe_state=forbidden, reconcile_orders=forbidden),
        trade_registry=ActiveTradeRegistry(),
        clean_start_check=lambda: gate.check_start(
            client, engine, datetime.now(timezone.utc), require_recovery=False))
    result = authority.run()
    assert not result.complete and result.reason == "PAPER_RELEASE_START_NOT_FLAT"


@pytest.mark.parametrize("absent,expected", [
    ("volume", "PAPER_RELEASE_VOLUME_CALIBRATION_REQUIRED"),
    ("fees", "PAPER_RELEASE_ENTRY_COST_AUTHORITY_REQUIRED"),
])
def test_laptop_preflight_refuses_missing_private_evidence(tmp_path, monkeypatch, absent, expected):
    from hashlib import sha256
    import json

    from scripts.certification import ross_paper_release_operator as operator

    monkeypatch.setattr(operator, "runtime_inventory", lambda **_: {"completed": True, "runtimes": []})
    state = tmp_path / "state"
    state.mkdir()
    for name in ("ibkr_system.db", "order-id.json", "submission-guard.json"):
        (state / name).touch()
    calendar = tmp_path / "calendar.json"
    calendar.write_text(json.dumps({
        "coverage": {}, "holidays": "", "half_days": "", "early_close": "13:00",
    }), encoding="utf-8")
    witness = tmp_path / "calibration-for-this-session.json"
    if absent != "volume":
        witness.touch()
    if absent != "fees":
        (state / "entry-fee-ceiling.json").touch()

    assert operator.run(state, tmp_path, calendar, sha256(calendar.read_bytes()).hexdigest(),
                        witness) == (expected, 2)


@pytest.mark.parametrize("installed,captured,accepted", [
    ("10.50.2", "10.50.2", True),
    ("9.81.1.post1", "9.81.1.post1", True),
    ("9.81.1.post1", "10.50.2", False),
    ("10.50.2", "9.81.1.post1", False),
    ("10.50.2", None, False),
])
def test_laptop_preflight_binds_execution_sdk_to_volume_witness(monkeypatch, installed, captured, accepted):
    from scripts.certification import ross_paper_release_operator as operator
    from src.ibkr import sdk_profile

    monkeypatch.setattr(sdk_profile, "require_supported_sdk", lambda: installed)
    calibration = {"sdk_distribution": captured}
    if accepted:
        operator.require_calibrated_sdk(calibration)
    else:
        with pytest.raises(RuntimeError, match="PAPER_RELEASE_VOLUME_SDK_MISMATCH"):
            operator.require_calibrated_sdk(calibration)


def test_laptop_preflight_rejects_unattested_sdk_before_broker_import(monkeypatch):
    from scripts.certification import ross_paper_release_operator as operator
    from src.ibkr import sdk_profile

    def unverified():
        raise RuntimeError("IBKR_SDK_PROFILE_UNVERIFIED")

    monkeypatch.setattr(sdk_profile, "require_supported_sdk", unverified)
    with pytest.raises(RuntimeError, match="PAPER_RELEASE_SDK_PROFILE_UNVERIFIED"):
        operator.require_calibrated_sdk({"sdk_distribution": "10.50.2"})
