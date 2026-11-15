"""Offline ownership evidence, never a positive P02 admission or SDK send."""
from inspect import unwrap
import sys
from threading import Thread

import pytest

from src.core.active_trade_registry import ActiveTrade, ActiveTradeRegistry
from src.execution.execution_providers import OrderSnapshot
from src.execution.post_fill_lifecycle_engine import LifecyclePolicy, PostFillLifecycleEngine, PositionLifecycleState
from test_p02_observable_local_cooldown import (
    NOW, local_component, native_execution_client, no_external_activity, forbid_io, _reset_config,
    _observe, _settle,
)


@pytest.fixture
def owners(local_component, monkeypatch):
    h = local_component()
    h.engine.trade_registry = ActiveTradeRegistry()
    h.engine.post_fill_lifecycle = PostFillLifecycleEngine(run_mode="PAPER",
        execution_provider=h.engine._provider, storage_engine=h.storage)
    h.engine._p02_bind_financial_owners()
    # Existing owner behavior uses synthetic provider results for these ownership
    # checks. They supply no native execution, financial settlement or permission.
    monkeypatch.setattr(h.engine._provider, "place_stop_order",
        lambda **kwargs: {"broker_order_id": "TEST-STOP", "status": "Submitted"})
    monkeypatch.setattr(h.engine._provider, "place_target_order",
        lambda **kwargs: {"broker_order_id": "TEST-TARGET", "status": "Submitted"})
    h.registry = h.engine.trade_registry
    h.protection = h.engine.post_fill_lifecycle
    return h


def _trade(**kwargs):
    return ActiveTrade(symbol="AAPL", trader_type="TEST", entry_tick=1,
        entry_price=10.0, direction="LONG", quantity=1,
        stop_loss_price=9.5, strategy_name="RossMomentum", **kwargs)


def _activate(h, **kwargs):
    return h.protection.activate_trade_management_after_fill(trade_id="owner-roundtrip",
        symbol="AAPL", side="LONG", filled_qty=1, avg_fill_price=10.,
        strategy_id="RossMomentum", stop_loss_price=9.5, take_profit_price=11.,
        preserve_selected_protection=True, **kwargs)


def test_registry_copies_retained_input_and_every_nested_outward_read(owners):
    h = owners
    incoming = _trade(state_history=[{"nested": {"flags": ["original"]}}])
    h.registry.register_trade(incoming)
    incoming.quantity = 99
    incoming.state_history[0]["nested"]["flags"].append("caller")
    first = h.registry.get_trade("AAPL", "TEST")
    assert first.quantity == 1
    assert first.state_history[0]["nested"]["flags"] == ["original"]
    first.state_history[0]["nested"]["flags"].append("read")
    snapshot = h.registry.snapshot()
    snapshot[0].state_history[0]["nested"]["flags"].append("snapshot")
    assert h.registry.get_trade("AAPL", "TEST").state_history[0]["nested"]["flags"] == ["original"]
    assert h.registry._p02_local_supported


def test_registry_internal_mark_closed_updates_actual_owner_and_revisions(owners):
    h = owners
    before = h.registry._p02_local_revision
    h.registry.register_trade(_trade())
    assert h.registry._p02_local_revision >= before + 2
    before = h.registry._p02_local_revision
    h.registry.mark_closed("AAPL", "TEST", 5, 9.5, -.5)
    assert h.registry._p02_local_revision >= before + 2
    assert h.registry.get_trade("AAPL", "TEST").close_price == 9.5
    detached = h.registry.close_all_trades()
    detached[0].state_history[0]["reason"] = "caller"
    assert h.registry.snapshot() == []
    assert h.registry._p02_local_supported


def test_post_fill_input_and_mutation_return_are_detached_recursively(owners):
    h = owners
    session = {"nested": {"flags": ["original"]}}
    result = _activate(h, session_label=session)
    assert result["success"]
    session["nested"]["flags"].append("caller")
    result["trade"]["session_label"]["nested"]["flags"].append("returned")
    result["installed_stop_metadata"]["trigger_price"] = 1.
    trade = h.protection.get_trade("owner-roundtrip")
    assert trade.session_label["nested"]["flags"] == ["original"]
    assert trade.stop.trigger_price == 9.5
    assert h.protection._p02_local_supported


def test_exact_provider_order_snapshot_is_copied_before_public_reconciliation(owners):
    h = owners
    _activate(h)
    metadata = dict(side="SELL", quantity=1, native_quantity=1, stop_price=9.5,
        limit_price=None, trade_id="owner-roundtrip", order_ref="PROTECT|owner-roundtrip",
        con_id=123, account="SYNTHETIC_TEST", client_id=h.client.client_id,
        nested={"flags": ["original"]})
    stop = OrderSnapshot("TEST-STOP", "AAPL", "Submitted", "STP", "owner-roundtrip", metadata)
    target = OrderSnapshot("TEST-TARGET", "AAPL", "Submitted", "LMT", "owner-roundtrip",
        dict(side="SELL", quantity=1, limit_price=11., trade_id="owner-roundtrip"))
    original_code = unwrap(PostFillLifecycleEngine.reconcile_orders).__code__
    captured = []
    def trace(frame, event, arg):
        if event == "call" and frame.f_code is original_code:
            # The original public operation must receive a private field copy,
            # before retained caller metadata can change during its processing.
            received = frame.f_locals["broker_orders"][0]
            assert type(received) is OrderSnapshot and received is not stop
            assert received.metadata is not metadata
            captured.append(received)
            metadata["stop_price"] = 1.
            metadata["nested"]["flags"].append("caller")
        return trace
    previous_trace = sys.gettrace()
    sys.settrace(trace)
    try:
        result = h.protection.reconcile_orders([stop, target], repair=False)
    finally:
        sys.settrace(previous_trace)
    assert captured[0].metadata["stop_price"] == 9.5
    assert captured[0].metadata["nested"]["flags"] == ["original"]
    assert result["findings"] == [] and not result["block_new_entries"]
    assert h.protection.get_trade("owner-roundtrip").stop.trigger_price == 9.5
    assert h.protection._p02_local_supported


@pytest.mark.parametrize("custom", ["subclass", "metadata_hook"])
def test_custom_provider_order_snapshot_input_still_taints_without_copy_hooks(owners, custom):
    h = owners
    class Hook:
        def __deepcopy__(self, memo):
            pytest.fail("custom provider input must not run a deepcopy hook")
    class CustomOrderSnapshot(OrderSnapshot):
        def __deepcopy__(self, memo):
            pytest.fail("custom snapshot subclass must not run a deepcopy hook")
    cls = CustomOrderSnapshot if custom == "subclass" else OrderSnapshot
    metadata = {"side": "SELL", "quantity": 1}
    if custom == "metadata_hook":
        metadata["unknown"] = Hook()
    result = h.protection.reconcile_orders([
        cls("foreign", "AAPL", "Submitted", "STP", metadata=metadata)], repair=False)
    assert result["orphan_orders"] == ["foreign"]
    assert not h.protection._p02_local_supported


def test_post_fill_trade_stop_target_events_and_pending_exit_reads_do_not_alias(owners):
    h = owners
    _activate(h)
    # Existing public management produces the owned pending exit dictionary.
    intents = h.protection.evaluate_trade_management(trade_id="owner-roundtrip", current_price=9.)
    # A source fixture covers this nested field without invoking any additional
    # management action or claiming that synthetic state supplies local evidence.
    h.protection._trades["owner-roundtrip"].selected_exit_pending = {"nested": {"flags": ["original"]}}
    trade = h.protection.get_trade("owner-roundtrip")
    assert trade.selected_exit_pending is not None
    trade.stop.trigger_price = 1.
    trade.target.trigger_price = 100.
    trade.failure_flags.append("caller")
    trade.take_profit_events.append({"caller": [1]})
    trade.selected_exit_pending["caller"] = [1]
    intents[0]["caller"] = [1]
    snapshot = h.protection.snapshot()
    snapshot["owner-roundtrip"]["selected_exit_pending"]["snapshot"] = [1]
    again = h.protection.get_trade("owner-roundtrip")
    assert again.stop.trigger_price == 9.5 and again.target.trigger_price == 11.
    assert "caller" not in again.failure_flags
    assert not any("caller" in event for event in again.take_profit_events)
    assert "caller" not in again.selected_exit_pending and "snapshot" not in again.selected_exit_pending


def test_external_selected_unit_submitter_taints_before_actual_handles_escape(owners):
    h = owners
    seen = []
    def submit(trade, leg):
        assert not h.protection._p02_local_supported
        seen.append((trade, leg))
        leg.broker_order_id = "TEST-UNIT"
    result = h.protection.activate_trade_management_after_fill(trade_id="unit",
        symbol="AAPL", side="LONG", filled_qty=1, avg_fill_price=10.,
        strategy_id="RossMomentum", stop_loss_price=9.5,
        preserve_selected_protection=True, selected_stop_units=True, unit_stop_submitter=submit)
    assert result["success"] and seen
    detached_trade = h.protection.get_trade("unit")
    leg = h.protection.selected_unit_leg(detached_trade, broker_order_id="TEST-UNIT")
    leg.trigger_price = 1.
    detached_trade.stop_legs[0].stop_price_revision = {"caller": [1]}
    assert h.protection.get_trade("unit").stop_legs[0].trigger_price == 9.5
    assert h.protection.get_trade("unit").stop_legs[0].stop_price_revision is None


@pytest.mark.parametrize("owner_name,method,args", [
    ("registry", "register_trade", (_trade(),)),
    ("protection", "set_startup_recovery_complete", (True,)),
])
def test_owner_mutation_invalidates_observation_and_participates_in_same_gate(
        owners, owner_name, method, args):
    h = owners
    _settle(h)
    prior = _observe(h)
    assert prior.local_condition_satisfied
    owner = getattr(h, owner_name)
    before = owner._p02_local_revision
    getattr(owner, method)(*args)
    assert owner._p02_local_revision > before
    assert not h.engine.revalidate_p02_local_cooldown(prior, assessed_at=NOW)
    state = h.engine._p02_local
    assert state["gate"].acquire(blocking=False)
    token = h.engine._p02_begin_read_frame()
    try:
        with pytest.raises(RuntimeError, match="P02_LOCAL_OWNER_BUSY"):
            getattr(owner, method)(*args)
    finally:
        h.engine._p02_end_read_frame(token)
        state["gate"].release()


def test_same_context_from_other_thread_cannot_borrow_owner_frame(owners):
    h = owners
    state = h.engine._p02_local
    errors = []
    with h.engine._p02_owner_mutation(h.engine, "test-held-frame"):
        def mutate():
            try:
                h.registry.register_trade(_trade())
            except RuntimeError as exc:
                errors.append(str(exc))
        thread = Thread(target=mutate)
        thread.start()
        thread.join(timeout=2)
        assert not thread.is_alive()
    assert errors == ["P02_LOCAL_OWNER_BUSY"]
    assert h.registry.snapshot() == []


@pytest.mark.parametrize("owner_kind", ["registry", "protection"])
@pytest.mark.parametrize("history", ["read", "mutate", "prepopulated", "unknown", "custom"])
def test_financial_binding_refuses_used_prepopulated_unknown_or_custom_owner(
        local_component, owner_kind, history):
    h = local_component()
    if owner_kind == "registry":
        cls = ActiveTradeRegistry
        owner = cls.__new__(cls) if history == "unknown" else cls()
        if history == "read": owner.snapshot()
        if history == "mutate": owner.unregister_trade("AAPL", "TEST")
        if history == "prepopulated": owner._active_trades.append(_trade())
        if history == "custom": owner.snapshot = lambda: []
        h.engine.trade_registry = owner
    else:
        cls = PostFillLifecycleEngine
        owner = cls.__new__(cls) if history == "unknown" else cls("PAPER")
        if history == "read": owner.get_trade("absent")
        if history == "mutate": owner.set_startup_recovery_complete(True)
        if history == "prepopulated": owner._pending_exit_requests["foreign"] = {}
        if history == "custom": owner.get_trade = lambda trade_id: None
        h.engine.post_fill_lifecycle = owner
    with pytest.raises(RuntimeError, match="P02_LOCAL_.*_OWNER_UNAVAILABLE"):
        owner.bind_p02_local_authority(h.engine)


@pytest.mark.parametrize("owner_name", ["registry", "protection"])
def test_financial_owner_cannot_rebind_or_export_source_frame(owners, owner_name):
    h = owners
    owner = getattr(h, owner_name)
    with pytest.raises(RuntimeError, match="P02_LOCAL_.*_OWNER_UNAVAILABLE"):
        owner.bind_p02_local_authority(h.engine)
    with pytest.raises(RuntimeError, match="P02_LOCAL_.*_FRAME_UNAVAILABLE"):
        owner._p02_local_source_frame()
    with h.engine._p02_owner_mutation(h.engine, "caller-holds-frame"):
        with pytest.raises(RuntimeError, match="P02_LOCAL_.*_FRAME_UNAVAILABLE"):
            owner._p02_local_source_frame()


def test_custom_retained_field_never_runs_deepcopy_hook_for_authority(owners):
    h = owners
    class Hook:
        def __deepcopy__(self, memo):
            pytest.fail("custom deepcopy hook must not participate in owner authority")
    incoming = _trade(state_history=[{"unknown": Hook()}])
    h.registry.register_trade(incoming)
    assert not h.registry._p02_local_supported
    with pytest.raises(RuntimeError, match="P02_LOCAL_UNSUPPORTED_OWNER_VALUE"):
        h.registry.snapshot()


def test_custom_post_fill_input_taints_before_storage_without_copy_hooks(owners):
    h = owners
    class Hook:
        def __deepcopy__(self, memo):
            pytest.fail("unknown post-fill field must never execute a copy hook")
    with pytest.raises(RuntimeError, match="P02_LOCAL_UNSUPPORTED_OWNER_VALUE"):
        _activate(h, session_label=Hook())
    assert not h.protection._p02_local_supported
    # Factual activation was retained before its unsafe outward payload refused.
    assert "owner-roundtrip" in h.protection._trades
    with pytest.raises(RuntimeError, match="P02_LOCAL_UNSUPPORTED_OWNER_VALUE"):
        h.protection.snapshot()


@pytest.mark.parametrize("owner_kind", ["registry", "protection"])
def test_reinitializing_used_owner_cannot_reset_constructor_lifetime(local_component, owner_kind):
    h = local_component()
    if owner_kind == "registry":
        owner = ActiveTradeRegistry()
        owner.snapshot()
        owner.__init__()
        h.engine.trade_registry = owner
    else:
        owner = PostFillLifecycleEngine("PAPER")
        owner.snapshot()
        owner.__init__("PAPER")
        h.engine.post_fill_lifecycle = owner
    with pytest.raises(RuntimeError, match="P02_LOCAL_.*_OWNER_UNAVAILABLE"):
        owner.bind_p02_local_authority(h.engine)


def test_retained_constructor_policy_cannot_become_authoritative(local_component):
    h = local_component()
    policy = LifecyclePolicy()
    owner = PostFillLifecycleEngine("PAPER", policy=policy)
    h.engine.post_fill_lifecycle = owner
    with pytest.raises(RuntimeError, match="P02_LOCAL_POST_FILL_OWNER_UNAVAILABLE"):
        owner.bind_p02_local_authority(h.engine)


def test_direct_private_mutation_helper_taints_local_authority(owners):
    h = owners
    _activate(h)
    detached = h.protection.get_trade("owner-roundtrip")
    h.protection._transition(detached, PositionLifecycleState.EXIT_PENDING, "external helper")
    assert not h.protection._p02_local_supported
    assert h.protection.get_trade("owner-roundtrip").state != PositionLifecycleState.EXIT_PENDING


def test_unenrolled_registry_retains_existing_public_object_semantics():
    registry = ActiveTradeRegistry()
    incoming = _trade()
    registry.register_trade(incoming)
    assert registry.get_trade("AAPL", "TEST") is incoming
    assert registry.snapshot()[0] is incoming
