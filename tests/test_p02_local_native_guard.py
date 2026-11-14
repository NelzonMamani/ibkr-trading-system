"""Default-off native participation; no P02 admission or broker activity."""
from dataclasses import FrozenInstanceError
import threading

import pytest
from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.execution import Execution
from ibapi.order import Order

from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.config.config_resolver import set_config_overrides
from src.ibkr.mutation_audit import snapshot as mutations
from test_p02_observable_local_cooldown import local_component, _settle, ACCOUNT
from test_ibkr_cached_client_access import forbid_io, no_external_activity, _reset_config


@pytest.fixture
def native_execution_client(monkeypatch,tmp_path,no_external_activity):
    # Same existing native component boundary, with audit assertions owned by
    # each test because some controls deliberately attempt refused entry calls.
    monkeypatch.setenv('IBKR_ORDER_ID_STATE_PATH',str(tmp_path/'p02-native-ids.json'))
    client=IbkrClient('offline',0,999,1,'LIVE',True)
    monkeypatch.setattr(client,'isConnected',lambda:True)
    client.nextValidId(71);client.managedAccounts(ACCOUNT)
    yield client
    assert no_external_activity==[]


def _status(client,order_id=71):
    client.orderStatus(order_id,'Submitted',1,1,10.5,0,0,10.5,999,'',0.)


def test_default_native_callbacks_keep_cache_without_local_enrollment(native_execution_client):
    client=native_execution_client
    _status(client)
    assert client.cached_order_status(71)['filled']==1
    assert getattr(client,'_p02_local_ingress',None) is None
    with pytest.raises(RuntimeError,match='NOT_ENROLLED'):client.local_intake_snapshot()
    assert mutations()==dict(place=0,modify=0,cancel=0)


def test_native_initial_dirty_settles_only_through_actual_collector(local_component):
    h=local_component()
    snapshot=h.client.local_intake_snapshot()
    assert len(snapshot.dirty)==1 and snapshot.dirty[0].kind=='BASELINE'
    assert snapshot.dirty[0].finished and not snapshot.inflight
    with pytest.raises(FrozenInstanceError):snapshot.revision=0
    with pytest.raises(FrozenInstanceError):snapshot.dirty[0].failed=False
    with pytest.raises(RuntimeError,match='RECEIPT_UNVERIFIED'):
        h.client.settle_local_intake(snapshot.dirty[0],True)
    assert h.client.local_intake_snapshot()==snapshot
    _settle(h)
    assert h.client.local_intake_snapshot().dirty==()


def test_native_ingress_precedes_existing_account_registration(local_component,monkeypatch):
    import src.ibkr.mutation_audit as audit
    import src.adapters.brokers.ibkr.ibkr_client as native_module
    h=local_component();seen=[]
    for module in (audit,native_module):
        original=module.register_account
        def observed(*args,_original=original,**kwargs):
            snapshot=h.client.local_intake_snapshot()
            seen.append(snapshot)
            assert snapshot.inflight
            return _original(*args,**kwargs)
        monkeypatch.setattr(module,'register_account',observed)
    h.client.managedAccounts(ACCOUNT)
    snapshot=h.client.local_intake_snapshot()
    assert seen and not snapshot.inflight
    tickets=[ticket for ticket in snapshot.dirty if ticket.kind=='managedAccounts']
    assert tickets and all(ticket.finished and ticket.raw_fingerprint for ticket in tickets)
    assert snapshot.accounts==(ACCOUNT,) and snapshot.client_object_id==id(h.client)


def test_native_ingress_precedes_order_cache_publication(local_component,monkeypatch):
    h=local_component();seen=[];original=h.client._observe_order_id
    def observed(order_id):
        seen.append(h.client.local_intake_snapshot())
        assert seen[-1].inflight and 71 not in h.client._order_status
        return original(order_id)
    monkeypatch.setattr(h.client,'_observe_order_id',observed)
    _status(h.client)
    snapshot=h.client.local_intake_snapshot()
    assert seen and not snapshot.inflight
    assert h.client.cached_order_status(71)['filled']==1
    assert any(ticket.kind=='orderStatus' and ticket.finished and ticket.raw_fingerprint for ticket in snapshot.dirty)
    _settle(h)
    assert h.client.local_intake_snapshot().dirty  # Nonempty financial cache is not enrolled.


def test_native_malformed_and_ignored_callbacks_finish_but_remain_dirty(local_component):
    h=local_component()
    with pytest.raises(ValueError):_status(h.client,'malformed-order')
    contract=Contract();contract.symbol='JPM';contract.conId=123
    execution=Execution();execution.orderId=71;execution.execId='ignored-source'
    h.client.execDetails(999999,contract,execution)
    snapshot=h.client.local_intake_snapshot()
    assert not snapshot.inflight
    bad=[ticket for ticket in snapshot.dirty if ticket.kind=='orderStatus']
    ignored=[ticket for ticket in snapshot.dirty if ticket.kind=='execDetails']
    assert bad and all(ticket.finished and ticket.failed for ticket in bad)
    assert ignored and all(ticket.finished and ticket.raw_fingerprint for ticket in ignored)
    assert not h.client._exec_details_by_order
    _settle(h)
    assert h.client.local_intake_snapshot().dirty


def test_native_listener_failure_keeps_raw_cache_and_unsettled_intake(local_component):
    h=local_component()
    def fail(payload):raise RuntimeError('Synthetic listener failure')
    before=h.client.local_intake_snapshot()
    h.client.register_execution_callback(fail,internal_reconciliation=True)
    registered=h.client.local_intake_snapshot()
    assert fail in h.client._execution_callbacks and registered.revision>before.revision
    registration=[ticket for ticket in registered.dirty if ticket.kind=='register_execution_callback']
    assert registration and all(ticket.finished and ticket.failed for ticket in registration)
    # Unsupported callback fingerprinting still forwards the real registration.
    _status(h.client)
    snapshot=h.client.local_intake_snapshot()
    assert not snapshot.inflight and h.client.cached_order_status(71)['filled']==1
    tickets=[ticket for ticket in snapshot.dirty if ticket.kind=='orderStatus']
    assert tickets and all(ticket.finished and ticket.failed for ticket in tickets)
    with pytest.raises(RuntimeError,match='NOT_SETTLEABLE'):
        h.client.settle_local_intake(tickets[0],True)


def test_native_callback_never_waits_for_engine_gate(local_component):
    h=local_component();gate=h.engine._p02_local['gate'];errors=[]
    assert gate.acquire(blocking=False)
    def callback():
        try:_status(h.client)
        except BaseException as exc:errors.append(exc)
    thread=threading.Thread(target=callback)
    try:
        thread.start();thread.join(timeout=2)
        assert not thread.is_alive() and not errors
        assert h.client.cached_order_status(71)['filled']==1
    finally:
        gate.release();thread.join(timeout=2)
    assert not h.client.local_intake_snapshot().inflight


def test_native_snapshot_fails_fast_when_ingress_bookkeeping_is_busy(local_component):
    h=local_component();lock=h.client._p02_local_ingress['lock']
    assert lock.acquire(blocking=False)
    try:
        with pytest.raises(RuntimeError,match='INGRESS_BUSY'):h.client.local_intake_snapshot()
    finally:lock.release()


def test_native_same_numeric_rebind_cannot_restore_old_revision(local_component):
    h=local_component();before=h.client.local_intake_snapshot()
    h.client.client_id=1000;h.client.client_id=999
    after=h.client.local_intake_snapshot()
    assert after.client_id==before.client_id and after.revision>before.revision
    assert any(ticket.kind=='SET_client_id' for ticket in after.dirty)
    _settle(h)
    assert h.client.local_intake_snapshot().dirty


@pytest.mark.parametrize('enrolled',[False,True])
def test_native_refused_direct_entry_keeps_audit_and_readonly_gate(local_component,enrolled):
    h=local_component(enrolled=enrolled)
    contract=Contract();order=Order()
    with pytest.raises(RuntimeError,match='read-only|read.only|Execution disabled'):
        h.client.placeOrder(71,contract,order)
    assert mutations()==dict(place=1,modify=0,cancel=0)


def test_native_enrolled_unguarded_entry_refuses_before_sdk(local_component):
    h=local_component()
    set_config_overrides(dict(RUN_MODE='PAPER',RUN_MODE_EFFECTIVE='PAPER',EXECUTION_ENABLED=True,
        EXECUTION_ENABLED_EFFECTIVE=True,IBKR_READONLY_ENABLED=False))
    h.client.readonly_enabled=False
    with pytest.raises(RuntimeError,match='UNGUARDED_NATIVE_ENTRY'):
        h.client.placeOrder(71,Contract(),Order())
    assert mutations()==dict(place=1,modify=0,cancel=0)


def _entry_arguments():
    contract=Contract();contract.symbol='JPM';contract.conId=123
    contract.secType='STK';contract.exchange='SMART';contract.currency='USD'
    order=Order();order.action='BUY';order.orderType='MKT';order.totalQuantity=1
    order.account=ACCOUNT
    return contract,order


def _allow_synthetic_refused_entry(client):
    set_config_overrides(dict(RUN_MODE='PAPER',RUN_MODE_EFFECTIVE='PAPER',EXECUTION_ENABLED=True,
        EXECUTION_ENABLED_EFFECTIVE=True,IBKR_READONLY_ENABLED=False))
    client.readonly_enabled=False


def test_native_enrolled_preparation_does_not_erase_intervening_actual_callback(
        local_component,monkeypatch):
    from datetime import datetime,timezone
    h=local_component();_allow_synthetic_refused_entry(h.client)
    original=h.client.reserve_order_id;hooks=[];reserved=[]
    contract,order=_entry_arguments()
    def actual_callback_after_reservation():
        order_id=original();reserved.append(order_id)
        execution=Execution();execution.orderId=order_id;execution.execId='during-id-preparation'
        execution.acctNumber=ACCOUNT;execution.clientId=999;execution.side='BOT'
        execution.shares=execution.cumQty=1;execution.price=execution.avgPrice=10.5
        execution.time=datetime.now(timezone.utc).isoformat()
        h.client.execDetails(-1,contract,execution)
        return order_id
    monkeypatch.setattr(h.client,'reserve_order_id',actual_callback_after_reservation)
    def never_ready(*args):
        hooks.append(args);raise RuntimeError('PREP_BOUNDARY')
    with pytest.raises(RuntimeError,match='PREP_BOUNDARY|CACHE_OCCUPIED'):
        h.client.submit_order(contract,order,before_submit=never_ready)
    rows=h.client.cached_native_executions(reserved[0])
    assert len(rows)==1 and rows[0]['execId']=='during-id-preparation'
    assert not hooks
    assert mutations()==dict(place=1,modify=0,cancel=0)


@pytest.mark.parametrize('case',['component_consumed','wrapper_refusal','readonly_refusal','callback_before_entry','mutated_arguments','mutated_side'])
def test_native_component_lease_is_one_shot_and_lexically_abandoned(
        local_component,monkeypatch,case):
    from src.execution.execution_engine import _P02LocalEntryLease
    h=local_component();_settle(h);_allow_synthetic_refused_entry(h.client)
    contract,order=_entry_arguments();leases=[];fences=[]
    def component_hook(order_id,native_contract,native_order):
        # Real owner gate and SAME real storage fence. There is no prepared risk
        # success, native bridge enrollment or positive SDK delegation here.
        gate=h.engine._p02_local['gate']
        assert gate.acquire(blocking=False)
        try:
            fence=h.storage.acquire_local_cooldown_fence(run_mode='PAPER',
                expected_revision=h.storage.local_cooldown_state()['revision'])
            fences.append(fence)
            snapshot=h.client.local_intake_snapshot()
            lease=_P02LocalEntryLease(h.engine,fence,h.engine._p02_native_version(snapshot),
                order_id,native_contract,native_order)
            leases.append(lease)
            if case=='wrapper_refusal':
                def refused(*args):raise RuntimeError('Synthetic wrapper refusal')
                monkeypatch.setattr(h.client,'placeOrder',refused)
            elif case=='readonly_refusal':h.client.readonly_enabled=True
            elif case=='callback_before_entry':h.client.openOrderEnd()
            elif case=='mutated_arguments':native_order.totalQuantity=2
            elif case=='mutated_side':native_order.action='SELL'
            return lease
        except BaseException:
            if fences:fences[-1].close()
            gate.release()
            raise
    with pytest.raises(RuntimeError,match='BRIDGE_NOT_ADOPTED|wrapper refusal|read-only|UNSETTLED_INGRESS|LEASE_STALE'):
        h.client.submit_order(contract,order,before_submit=component_hook)
    assert len(leases)==len(fences)==1
    lease=leases[0]
    assert lease.closed and not lease.admission_authorized
    assert lease.phase==('CONSUMED' if case=='component_consumed' else 'ABORTED')
    assert not h.engine._p02_local['gate'].locked() and not fences[0].validate()
    assert not h.storage._store.connection.in_transaction
    lease.abort()  # Idempotent issuer cleanup never rearms or releases twice.
    assert not h.engine._p02_local['gate'].locked()
    assert h.client._p02_local_ingress['thread'].submit is None
    assert mutations()==dict(place=1,modify=0,cancel=0)
    assert h.storage.fetch_trade_lifecycle_events()==[]
    assert h.client._order_status=={} and not any(h.client._exec_details_by_order.values())


def test_native_public_snapshot_cannot_finish_live_callback(local_component,monkeypatch):
    h=local_component();entered=threading.Event();release=threading.Event();errors=[]
    original=h.client._observe_order_id
    def blocked(order_id):
        entered.set()
        assert release.wait(timeout=2)
        return original(order_id)
    monkeypatch.setattr(h.client,'_observe_order_id',blocked)
    def callback():
        try:_status(h.client)
        except BaseException as exc:errors.append(exc)
    thread=threading.Thread(target=callback)
    try:
        thread.start();assert entered.wait(timeout=2)
        snapshot=h.client.local_intake_snapshot()
        ticket=next(ticket for ticket in snapshot.dirty if ticket.kind=='orderStatus')
        with pytest.raises(RuntimeError,match='TICKET_INVALID'):
            h.client.finish_local_intake(ticket,'RETURNED')
        with pytest.raises(RuntimeError,match='TICKET_INVALID'):
            h.client.finish_local_intake(object(),'RETURNED')
        assert h.client.local_intake_snapshot().inflight
    finally:
        release.set();thread.join(timeout=2)
    assert not thread.is_alive() and not errors
    assert not h.client.local_intake_snapshot().inflight
    assert h.client.cached_order_status(71)['filled']==1


def test_native_consumed_component_lease_cannot_be_reused_in_new_submission(local_component):
    from src.execution.execution_engine import _P02LocalEntryLease
    h=local_component();_settle(h);_allow_synthetic_refused_entry(h.client)
    contract,order=_entry_arguments();leases=[]
    def first_hook(order_id,native_contract,native_order):
        assert h.engine._p02_local['gate'].acquire(blocking=False)
        fence=h.storage.acquire_local_cooldown_fence(run_mode='PAPER',
            expected_revision=h.storage.local_cooldown_state()['revision'])
        lease=_P02LocalEntryLease(h.engine,fence,
            h.engine._p02_native_version(h.client.local_intake_snapshot()),order_id,native_contract,native_order)
        leases.append(lease);return lease
    with pytest.raises(RuntimeError,match='BRIDGE_NOT_ADOPTED'):
        h.client.submit_order(contract,order,before_submit=first_hook)
    lease=leases[0]
    assert lease.phase=='CONSUMED' and lease.closed
    with pytest.raises(RuntimeError,match='LEASE_STALE'):
        h.client.submit_order(contract,order,before_submit=lambda *args:lease)
    assert lease.phase=='CONSUMED' and lease.closed
    assert not h.engine._p02_local['gate'].locked() and not h.storage._store.connection.in_transaction
    assert mutations()==dict(place=2,modify=0,cancel=0)


def test_mutation_audit_counts_distinct_reentrant_native_commands():
    from src.ibkr.mutation_audit import instrument_mutation
    set_config_overrides(dict(RUN_MODE='PAPER',RUN_MODE_EFFECTIVE='PAPER',EXECUTION_ENABLED=True,
        EXECUTION_ENABLED_EFFECTIVE=True,IBKR_READONLY_ENABLED=False))
    calls=[]
    class SDK:
        readonly_enabled=False
        def placeOrder(self,orderId,contract,order):
            calls.append(orderId)
            if orderId==71:self.placeOrder(72,contract,order)
    class Native(SDK):
        def placeOrder(self,orderId,contract,order):
            return super().placeOrder(orderId,contract,order)
    instrument_mutation(SDK,'placeOrder');instrument_mutation(Native,'placeOrder')
    Native().placeOrder(71,None,None)
    assert calls==[71,72]
    assert mutations()==dict(place=2,modify=0,cancel=0)


def test_native_local_entry_guard_preserves_existing_sell_sdk_boundary(local_component):
    h=local_component();_allow_synthetic_refused_entry(h.client)
    contract,order=_entry_arguments();order.action='SELL'
    # Retain the existing hard SDK refusal. Reaching it proves this ENTRY-only
    # seam did not replace the protection path; no SDK body/send is permitted.
    with pytest.raises(pytest.fail.Exception,match='network/broker/mutation forbidden'):
        h.client.placeOrder(99,contract,order)
    assert mutations()==dict(place=1,modify=0,cancel=0)


def test_mutation_audit_keeps_distinct_client_commands_separate():
    from src.ibkr.mutation_audit import instrument_mutation
    set_config_overrides(dict(RUN_MODE='PAPER',RUN_MODE_EFFECTIVE='PAPER',EXECUTION_ENABLED=True,
        EXECUTION_ENABLED_EFFECTIVE=True,IBKR_READONLY_ENABLED=False))
    calls=[];second=[]
    class SDK:
        readonly_enabled=False
        def placeOrder(self,orderId,contract,order):
            calls.append((self,orderId))
            if orderId==71:second[0].placeOrder(72,contract,order)
    class Native(SDK):
        def placeOrder(self,orderId,contract,order):
            return super().placeOrder(orderId,contract,order)
    instrument_mutation(SDK,'placeOrder');instrument_mutation(Native,'placeOrder')
    first=Native();second.append(Native())
    first.placeOrder(71,None,None)
    assert calls==[(first,71),(second[0],72)]
    assert mutations()==dict(place=2,modify=0,cancel=0)


@pytest.mark.parametrize('name,args',[
    ('completedOrdersEnd',()),('positionMultiEnd',(404,)),('accountUpdateMultiEnd',(404,)),
    ('connectAck',()),('accountUpdateMulti',(404,ACCOUNT,'','CashBalance','1','USD')),
])
def test_native_inherited_account_order_callbacks_are_observed_even_when_ignored(local_component,name,args):
    h=local_component();before=h.client.local_intake_snapshot()
    getattr(h.client,name)(*args)
    after=h.client.local_intake_snapshot()
    assert after.revision>before.revision and not after.inflight
    tickets=[ticket for ticket in after.dirty if ticket.kind==name]
    assert tickets and all(ticket.finished and ticket.raw_fingerprint for ticket in tickets)
    _settle(h)
    assert any(ticket.kind==name for ticket in h.client.local_intake_snapshot().dirty)


def test_mutation_audit_callback_cannot_borrow_submit_delegation():
    from src.ibkr.mutation_audit import instrument_mutation
    set_config_overrides(dict(RUN_MODE='PAPER',RUN_MODE_EFFECTIVE='PAPER',EXECUTION_ENABLED=True,
        EXECUTION_ENABLED_EFFECTIVE=True,IBKR_READONLY_ENABLED=False))
    calls=[]
    class SDK:
        readonly_enabled=False
        def placeOrder(self,orderId,contract,order):calls.append(orderId)
    class Native(SDK):
        def placeOrder(self,orderId,contract,order):
            return super().placeOrder(orderId,contract,order)
        def submit_order(self,contract,order,*,before_submit=None):
            if before_submit is not None:before_submit(71,contract,order)
            self.placeOrder(71,contract,order)
    instrument_mutation(SDK,'placeOrder');instrument_mutation(Native,'placeOrder')
    instrument_mutation(Native,'submit_order')
    client=Native()
    def callback(orderId,contract,order):
        client.placeOrder(72,contract,order)
        raise RuntimeError('Synthetic callback raised before original SDK entry')
    with pytest.raises(RuntimeError,match='callback raised'):
        client.submit_order(None,None,before_submit=callback)
    assert calls==[72]
    assert mutations()==dict(place=2,modify=0,cancel=0)


def test_native_unenrolled_buy_keeps_existing_forbidden_sdk_boundary(local_component):
    h=local_component(enrolled=False);_allow_synthetic_refused_entry(h.client)
    contract,order=_entry_arguments()
    assert getattr(h.client,'_p02_local_ingress',None) is None
    with pytest.raises(pytest.fail.Exception,match='network/broker/mutation forbidden'):
        h.client.placeOrder(99,contract,order)
    assert mutations()==dict(place=1,modify=0,cancel=0)


def test_native_initial_local_enrollment_refuses_preexisting_callback_owner(local_component):
    from src.core.engines.trade_lifecycle_engine import TradeLifecycleEngine
    from src.storage.storage_engine import StorageEngine
    h=local_component(enrolled=False)
    # Real initially enrolled storage isolates callback ownership as the veto;
    # the original fixture's ordinary store remains under its normal teardown.
    storage=StorageEngine(local_cooldown_mode='PAPER')
    try:
        h.engine._storage_engine=storage
        h.engine._trade_lifecycle_engine=TradeLifecycleEngine(storage)
        assert storage.local_cooldown_state()['supported']
        def existing_owner(payload):pass
        h.client.register_execution_callback(existing_owner)
        with pytest.raises(RuntimeError,match='P02_LOCAL_ENROLLMENT_UNAVAILABLE'):
            h.engine.enable_p02_local_cooldown(account=ACCOUNT,client=h.client)
        assert h.client._execution_callbacks==[existing_owner]
        assert getattr(h.engine,'_p02_local',None) is None
        assert getattr(h.client,'_p02_local_ingress',None) is None
        assert mutations()==dict(place=0,modify=0,cancel=0)
    finally:storage.shutdown()
