"""Synthetic component evidence for the separate P02 local cooldown policy.

Real canonical journal and native callback owners participate. These observations
never certify broker-history coverage or authorize Core/native P02 admission.
"""
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace as NS

import pytest

from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import RunMode
from src.core.active_trade_registry import ActiveTradeRegistry
from src.core.engines.trade_lifecycle_engine import TradeLifecycleEngine
from src.execution.execution_engine import ExecutionEngine
from src.execution.execution_providers import IbkrExecutionProvider
from src.storage.storage_engine import StorageEngine
from test_ibkr_cached_client_access import (
    native_execution_client, _native_contract, _native_execution,
    forbid_io, no_external_activity, _reset_config,
)
from test_trade_lifecycle_engine import _native_event, _apply_native, _p02_cooldown_identity


NOW = datetime(2026, 10, 20, 13, 35, tzinfo=timezone.utc)
ACCOUNT = "SYNTHETIC_TEST"
P02 = "StatisticalIntradayMomentum"


@pytest.fixture
def local_component(isolated_runtime_schema, native_execution_client, monkeypatch):
    """Existing owner component, deliberately outside Core entry/admission."""
    set_config_overrides(dict(RUN_MODE="PAPER", RUN_MODE_EFFECTIVE="PAPER",
        PERSISTENCE_ENABLED=True, PERSISTENCE_BACKEND="sqlite",
        PERSISTENCE_SQLITE_PATH=str(isolated_runtime_schema), PERSIST_FLUSH_EACH_CYCLE=True))
    opened = []

    def create(*, enrolled=True, client=None):
        client = client or native_execution_client
        storage = StorageEngine(**({"local_cooldown_mode": "PAPER"} if enrolled else {}))
        opened.append(storage)
        lifecycle = TradeLifecycleEngine(storage)
        manager = NS(existing_client=client)
        provider = IbkrExecutionProvider(broker=NS(connection_manager=manager),
            trade_registry=ActiveTradeRegistry(), run_mode=RunMode.PAPER)
        engine = ExecutionEngine.__new__(ExecutionEngine)
        engine.run_mode = RunMode.PAPER
        engine._native_orders = {}
        engine._native_loaded = False
        engine._native_state = None
        engine._native_quarantined = False
        engine._failsafe_block_new_entries = False
        engine._storage_engine = storage
        engine._trade_lifecycle_engine = lifecycle
        engine._provider = provider
        engine.relationship_manager = None
        if enrolled:
            engine.enable_p02_local_cooldown(account=ACCOUNT, client=client)
        return NS(engine=engine, lifecycle=lifecycle, storage=storage,
            client=client, manager=manager, identity=_p02_cooldown_identity())

    def close(h):
        h.storage.shutdown()
        opened.remove(h.storage)
    create.close = close
    yield create
    for storage in reversed(opened):
        storage.shutdown()
    set_config_overrides(None)


def _entry(h, *, identifier="local-entry", timestamp=NOW, quantity=1, root="LOCAL-P02"):
    """Only the actual strict canonical owner computes financial metadata."""
    event, binding = _native_event(identifier, "ENTRY_FILL", quantity, 10.5,
        timestamp=timestamp.isoformat(), root=root)
    binding.update(strategy=P02, client_id=h.client.client_id,
        connection_epoch=h.client._position_connection_epoch)
    trade = h.lifecycle.get_trade(root)
    _apply_native(h.lifecycle, event, binding, trade.quantity_open if trade is not None else 0)
    return event, binding


def _settle(h):
    # No replacement collector/result: actual existing Core-facing fill drain.
    assert h.engine.collect_relationship_updates() == []


def _observe(h, *, at=NOW, context="p02-component-occurrence"):
    # Public SQL-backed inspection itself participates in the source revision.
    # Check legacy UNKNOWN before issuing the new version-bound observation.
    old = h.lifecycle.p02_entry_cooldown_snapshot(account=ACCOUNT, identity=h.identity,
        run_mode="PAPER", assessed_at=at)
    assert old["eligible"] is False and old["coverage"] == "UNKNOWN"
    value = h.engine.observe_p02_local_cooldown(identity=h.identity,
        context_fingerprint=context, assessed_at=at)
    assert value["policy"] == "P02_OBSERVABLE_LOCAL_COOLDOWN_V1"
    assert value["basis"] == "OBSERVABLE_LOCAL_STATE"
    assert value["coverage"] == "UNKNOWN" and value["broker_history_complete"] is False
    assert value["admission_authorized"] is value.admission_authorized is False
    return value


def test_local_policy_requires_explicit_storage_and_execution_enrollment(local_component):
    h = local_component(enrolled=False)
    assert not h.storage.local_cooldown_state()["enrolled"]
    with pytest.raises(RuntimeError, match="P02_LOCAL_STORAGE_NOT_ENROLLED"):
        h.engine.enable_p02_local_cooldown(account=ACCOUNT, client=h.client)
    with pytest.raises(RuntimeError, match="P02_LOCAL_OBSERVATION_UNAVAILABLE"):
        _observe(h)


def test_empty_local_evidence_is_immutable_and_never_admission(local_component):
    h = local_component()
    before = _observe(h)
    assert not before["available"] and not before.local_condition_satisfied
    assert "P02_LOCAL_INTAKE_NOT_SETTLED" in before["findings"]
    _settle(h)
    assert h.storage.fetch_trade_lifecycle_events() == []
    value = _observe(h)
    assert value["available"] and value.local_condition_satisfied
    assert value["timing"] == "EMPTY_LOCAL" and value["entries"] == ()
    with pytest.raises(TypeError):
        value.details["local_condition_satisfied"] = False
    with pytest.raises(FrozenInstanceError):
        value.context_fingerprint = "different"
    assert h.engine.revalidate_p02_local_cooldown(value, assessed_at=NOW)
    for stage in ("PROPOSAL", "RISK", "FINAL_NATIVE_ENTRY"):
        assert not h.engine.revalidate_p02_local_cooldown(value, assessed_at=NOW, stage=stage)


def test_public_journal_read_invalidates_previous_local_observation(local_component):
    h = local_component()
    _settle(h)
    prior = _observe(h)
    assert prior.local_condition_satisfied
    assert h.storage.fetch_trade_lifecycle_events() == []
    assert not h.engine.revalidate_p02_local_cooldown(prior, assessed_at=NOW)
    fresh = _observe(h)
    assert fresh.local_condition_satisfied and fresh.source_version != prior.source_version
    assert h.engine.revalidate_p02_local_cooldown(fresh, assessed_at=NOW)


@pytest.mark.parametrize("change", ["effective_mode", "execution_environment"])
def test_changed_runtime_mode_or_environment_invalidates_local_observation(
        local_component, monkeypatch, change):
    from src.config import config_resolver
    h = local_component()
    _settle(h)
    prior = _observe(h)
    assert prior.local_condition_satisfied
    if change == "effective_mode":
        set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES,
            RUN_MODE="LIVE", RUN_MODE_EFFECTIVE="LIVE"))
    else:
        monkeypatch.setenv("EXECUTION_ENV", "NOT_TEST")
    assert not h.engine.revalidate_p02_local_cooldown(prior, assessed_at=NOW)
    current = h.engine.observe_p02_local_cooldown(identity=h.identity,
        context_fingerprint=prior.context_fingerprint, assessed_at=NOW)
    assert not current["available"] and not current.local_condition_satisfied
    assert current.admission_authorized is False


def test_coherent_foreign_journal_change_invalidates_historical_local_observation(local_component):
    import sqlite3
    prior = local_component()
    entry, _ = _entry(prior, identifier="foreign-prior-entry", root="FOREIGN-PRIOR-P02",
        timestamp=NOW - timedelta(seconds=300))
    exit_event, binding = _native_event("foreign-prior-exit", "STOP_EXIT", 1, 10.25,
        native_id=72, root=entry.lifecycle_trade_id, timestamp=(NOW - timedelta(seconds=290)).isoformat())
    binding.update(strategy=P02, client_id=prior.client.client_id,
        connection_epoch=prior.client._position_connection_epoch)
    _apply_native(prior.lifecycle, exit_event, binding, 1)
    local_component.close(prior)
    client = IbkrClient("offline", 0, 999, 5, "LIVE", True)
    client.isConnected = lambda: True
    client.managedAccounts(ACCOUNT)
    client.nextValidId(71)
    current = local_component(client=client)
    assert current.lifecycle.get_trade(entry.lifecycle_trade_id) is None
    _settle(current)
    original = _observe(current)
    assert original["available"] and original.local_condition_satisfied
    revision = current.storage.local_cooldown_state()["revision"]
    changed_timestamp = (datetime.fromisoformat(entry.timestamp) + timedelta(seconds=1)).isoformat()
    foreign = sqlite3.connect(current.storage.sqlite_path)
    try:
        foreign.execute("UPDATE trade_lifecycle_events SET timestamp=? WHERE event_id=?",
            (changed_timestamp, entry.event_id))
        foreign.execute("UPDATE trade_lifecycle_trades SET opened_at=? WHERE lifecycle_trade_id=?",
            (changed_timestamp, entry.lifecycle_trade_id))
        foreign.commit()
    finally:
        foreign.close()
    assert current.storage.local_cooldown_state()["revision"] == revision
    assert not current.engine.revalidate_p02_local_cooldown(original, assessed_at=NOW)
    fresh = current.engine.observe_p02_local_cooldown(identity=current.identity,
        context_fingerprint=original.context_fingerprint, assessed_at=NOW)
    assert fresh["available"] and fresh.local_condition_satisfied
    assert fresh["last_entry_at"] == changed_timestamp
    assert fresh["journal_fingerprint"] != original["journal_fingerprint"]
    assert fresh.admission_authorized is False


@pytest.mark.parametrize("seconds,satisfied", [(119.999, False), (120, True), (120.001, True)])
def test_actual_entry_original_time_controls_exact_local_boundary(local_component, seconds, satisfied):
    h = local_component()
    event, _ = _entry(h)
    _settle(h)
    rows = h.storage.fetch_trade_lifecycle_events()
    value = _observe(h, at=NOW + timedelta(seconds=seconds))
    assert value["available"] and value.local_condition_satisfied is satisfied
    assert value["timing"] == ("ELAPSED" if satisfied else "ACTIVE")
    assert value["duration_seconds"] == 120 and value["last_entry_at"] == event.timestamp
    assert value["expires_at"] == (NOW + timedelta(seconds=120)).isoformat()
    assert len(value["entries"]) == 1 and value["entries"][0]["execution_id"] == event.execution_id
    assert h.storage.fetch_trade_lifecycle_events() == rows


def test_partial_duplicate_and_late_entry_use_latest_original_fill_time(local_component):
    h = local_component()
    first, binding = _entry(h)
    second, _ = _entry(h, identifier="local-entry-second", timestamp=NOW + timedelta(seconds=30))
    _apply_native(h.lifecycle, first, binding, 2)
    late, _ = _entry(h, identifier="local-entry-late", timestamp=NOW - timedelta(seconds=10))
    _settle(h)
    value = _observe(h, at=NOW + timedelta(seconds=120))
    assert value["available"] and not value.local_condition_satisfied
    assert value["last_entry_at"] == second.timestamp
    assert {row["execution_id"] for row in value["entries"]} == {
        first.execution_id, second.execution_id, late.execution_id}
    assert len(h.storage.fetch_trade_lifecycle_events()) == 3
    assert h.lifecycle.get_trade("LOCAL-P02").quantity_open == 3
    boundary = _observe(h, at=NOW + timedelta(seconds=150))
    assert boundary["available"] and boundary.local_condition_satisfied


def test_current_and_prior_run_entries_share_original_local_timing(local_component):
    prior = local_component()
    first, _ = _entry(prior, identifier="prior-entry", root="PRIOR-P02",
        timestamp=NOW - timedelta(seconds=300))
    exit_event, binding = _native_event("prior-exit", "STOP_EXIT", 1, 10.25,
        native_id=72, root="PRIOR-P02", timestamp=(NOW - timedelta(seconds=290)).isoformat())
    binding.update(strategy=P02, client_id=prior.client.client_id,
        connection_epoch=prior.client._position_connection_epoch)
    _apply_native(prior.lifecycle, exit_event, binding, 1)
    previous_run = prior.storage.run_id
    local_component.close(prior)
    client = IbkrClient("offline", 0, 999, 5, "LIVE", True)
    client.isConnected = lambda: True
    client.managedAccounts(ACCOUNT)
    client.nextValidId(71)
    current = local_component(client=client)
    assert current.storage.run_id != previous_run
    latest, _ = _entry(current, identifier="current-entry", root="CURRENT-P02")
    _settle(current)
    value = _observe(current, at=NOW + timedelta(seconds=120))
    assert value["available"] and value.local_condition_satisfied
    assert value["last_entry_at"] == latest.timestamp
    assert {row["execution_id"] for row in value["entries"]} == {first.execution_id, latest.execution_id}
    assert {row["run_id"] for row in value["entries"]} == {previous_run, current.storage.run_id}
    assert len(current.storage.fetch_trade_lifecycle_events()) == 1
    assert current.lifecycle.get_trade("PRIOR-P02") is None


@pytest.mark.parametrize("callback", ["execution", "status", "error"])
def test_unclassified_actual_native_callback_keeps_local_intake_veto(local_component, callback):
    h = local_component()
    _settle(h)
    prior = _observe(h)
    assert prior.local_condition_satisfied
    if callback == "execution":
        h.client.execDetails(-1, _native_contract(conId=123, currency="USD"),
            _native_execution(clientId=h.client.client_id, time=NOW.isoformat()))
    elif callback == "status":
        h.client.orderStatus(71, "Submitted", 0, 1, 0., 0, 0, 0., h.client.client_id, "", 0.)
    else:
        h.client.error(71, 321, "Synthetic unresolved execution-source error")
    _settle(h)
    value = _observe(h)
    assert not value["available"] and not value.local_condition_satisfied
    assert "P02_LOCAL_INTAKE_NOT_SETTLED" in value["findings"]
    assert not h.engine.revalidate_p02_local_cooldown(prior, assessed_at=NOW)
    assert h.storage.fetch_trade_lifecycle_events() == []


@pytest.mark.parametrize("damage", ["missing_native_identity", "conflicting_price", "future_entry"])
def test_incomplete_or_conflicting_journal_never_satisfies_local_policy(local_component, damage):
    h = local_component()
    _entry(h, timestamp=NOW + timedelta(seconds=1) if damage == "future_entry" else NOW)
    if damage == "missing_native_identity":
        row = h.storage.fetch_trade_lifecycle_events()[0]
        metadata = json.loads(row["payload_json"])
        metadata["native_identity"].pop("con_id")
        h.storage._store.connection.execute("UPDATE trade_lifecycle_events SET payload_json=? WHERE event_id=?",
            (json.dumps(metadata), row["event_id"]))
        h.storage._store.connection.commit()
    elif damage == "conflicting_price":
        h.storage._store.connection.execute("UPDATE trade_lifecycle_events SET price=99")
        h.storage._store.connection.commit()
    _settle(h)
    value = _observe(h)
    assert not value["available"] and not value.local_condition_satisfied
    assert value["findings"]


def test_missing_committed_entry_chain_cannot_become_empty_local_clearance(local_component):
    h = local_component()
    event, _ = _entry(h)
    assert h.lifecycle.get_trade(event.lifecycle_trade_id).quantity_open == 1
    assert len(h.storage.fetch_trade_lifecycle_events()) == 1
    # Deleting the child events preserves the existing foreign-key protection
    # and leaves the actual committed trade snapshot as evidence of the gap.
    h.storage._store.connection.execute("DELETE FROM trade_lifecycle_events")
    h.storage._store.connection.commit()
    _settle(h)
    value = _observe(h, at=NOW + timedelta(seconds=120))
    assert not value["available"] and not value.local_condition_satisfied, value.details
    assert value["findings"]
    assert h.lifecycle.get_trade(event.lifecycle_trade_id).quantity_open == 1
    assert h.storage.fetch_trade_lifecycle_events() == []
    snapshot = h.storage._store.connection.execute(
        "SELECT quantity_open FROM trade_lifecycle_trades WHERE lifecycle_trade_id=?",
        (event.lifecycle_trade_id,)).fetchone()
    assert snapshot["quantity_open"] == 1


@pytest.mark.parametrize("uncertain", [False, True])
def test_pending_or_uncertain_canonical_intake_remains_vetoed(local_component, uncertain):
    h = local_component()
    _entry(h)
    event, binding = _native_event("pending-p02", "ENTRY_FILL", 1, 10.5, root="PENDING-P02")
    binding.update(strategy=P02, client_id=h.client.client_id,
        connection_epoch=h.client._position_connection_epoch)
    h.lifecycle.require_native_feedback(event.metadata["feedback_id"], binding)
    if uncertain:
        h.lifecycle.mark_native_feedback_uncertain(event.metadata["feedback_id"], "SYNTHETIC_ACCOUNTING_UNKNOWN")
    _settle(h)
    value = _observe(h, at=NOW + timedelta(seconds=120))
    assert not value["available"] and not value.local_condition_satisfied
    assert "P02_LOCAL_ACCOUNTING_PENDING_OR_UNCERTAIN" in value["findings"]


def test_actual_owner_mutation_invalidates_prior_observation(local_component):
    h = local_component()
    _settle(h)
    prior = _observe(h)
    assert prior.local_condition_satisfied
    _entry(h)
    assert not h.engine.revalidate_p02_local_cooldown(prior, assessed_at=NOW)
    _settle(h)
    changed = _observe(h, at=NOW + timedelta(seconds=120))
    assert changed.local_condition_satisfied
    assert changed.source_version != prior.source_version
    assert not h.engine.revalidate_p02_local_cooldown(prior, assessed_at=NOW + timedelta(seconds=120))


@pytest.mark.parametrize("scope_change", ["account", "client"])
def test_actual_callback_scope_change_cannot_reuse_local_observation(local_component, scope_change):
    h = local_component()
    _settle(h)
    prior = _observe(h)
    assert prior.local_condition_satisfied
    if scope_change == "account":
        h.client.managedAccounts("OTHER_SYNTHETIC_ACCOUNT")
    else:
        replacement = IbkrClient("offline", 0, h.client.client_id, 5, "LIVE", True)
        replacement.isConnected = lambda: True
        replacement.managedAccounts(ACCOUNT)
        h.manager.existing_client = replacement
    changed = _observe(h)
    assert not changed["available"] and not changed.local_condition_satisfied
    assert not h.engine.revalidate_p02_local_cooldown(prior, assessed_at=NOW)


def test_failed_journal_acquisition_does_not_return_local_clearance(local_component, monkeypatch):
    h = local_component()
    _settle(h)
    prior = _observe(h)
    assert prior.local_condition_satisfied
    def failed_read(**kwargs):
        raise OSError("Synthetic local journal acquisition failure")
    monkeypatch.setattr(h.storage, "acquire_local_cooldown_fence", failed_read)
    with pytest.raises(OSError, match="Synthetic local journal"):
        _observe(h)
    with pytest.raises(OSError, match="Synthetic local journal"):
        h.engine.revalidate_p02_local_cooldown(prior, assessed_at=NOW)
