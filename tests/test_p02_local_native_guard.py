"""Default-off native participation; no P02 admission or broker activity."""
from dataclasses import FrozenInstanceError
import threading

import pytest
from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.execution import Execution
from ibapi.order import Order

_SOURCE_REQ_POSITIONS_MULTI=EClient.reqPositionsMulti
_SOURCE_CANCEL_POSITIONS_MULTI=EClient.cancelPositionsMulti
_SOURCE_REQ_ACCOUNT_SUMMARY=EClient.reqAccountSummary
_SOURCE_CANCEL_ACCOUNT_SUMMARY=EClient.cancelAccountSummary

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


def test_native_financial_occurrence_retains_original_semantics_and_publication(local_component):
    h=local_component()
    _status(h.client)
    ticket=next(row for row in h.client.local_intake_snapshot().dirty if row.kind=='orderStatus')
    _settle(h)
    assert h.client.local_intake_snapshot().dirty  # Existing bounded refusal stays truthful.
    assert ticket.semantic_payload and dict(ticket.publication)=={
        'kind':'orderStatus','cache':'_order_status','order_id':71}
    assert h.client.local_intake_occurrence(ticket) is ticket
    with pytest.raises(FrozenInstanceError):ticket.semantic_payload=()


def _source_request_encoder(h,monkeypatch,on_request,on_cancel):
    client=h.client;requests=[];cancels=[]
    monkeypatch.setattr(client,'serverVersion',lambda:180)
    def send(message):
        fields=message.split('\0');kind=int(fields[0]);request_id=int(fields[2])
        if kind in {74,62}:
            requests.append((kind,request_id))
            assert client.local_intake_snapshot().inflight
            try:on_request(kind,request_id)
            except BaseException:
                import traceback
                traceback.print_exc()
                raise
        elif kind in {75,63}:
            cancels.append((kind,request_id))
            on_cancel(kind,request_id)
        else:pytest.fail('Unexpected synthetic SDK request '+str(kind))
    monkeypatch.setattr(client,'sendMsg',send)
    for name,method in (('reqPositionsMulti',_SOURCE_REQ_POSITIONS_MULTI),
            ('cancelPositionsMulti',_SOURCE_CANCEL_POSITIONS_MULTI),
            ('reqAccountSummary',_SOURCE_REQ_ACCOUNT_SUMMARY),
            ('cancelAccountSummary',_SOURCE_CANCEL_ACCOUNT_SUMMARY)):
        monkeypatch.setattr(client,name,lambda *args,_method=method:_method(client,*args))
    return requests,cancels


def _source_position_contract():
    contract=Contract();contract.conId=123;contract.symbol='JPM'
    contract.secType='STK';contract.currency='USD'
    return contract


def test_native_position_receipt_requires_actual_owner_retirement_and_cancel_return(local_component,monkeypatch):
    import copy
    h=local_component();contract=_source_position_contract()
    def requested(kind,req_id):
        assert kind==74
        h.client.positionMulti(req_id,ACCOUNT,'',contract,0,0.)
        h.client.positionMultiEnd(req_id)
        assert h.client.local_request_completion('POSITIONS_MULTI',req_id) is None
    def cancelled(kind,req_id):
        assert kind==75 and req_id not in h.client._position_queries
        assert h.client.local_request_completion('POSITIONS_MULTI',req_id) is None
    requests,cancels=_source_request_encoder(h,monkeypatch,requested,cancelled)
    result=h.client.position_snapshot(timeout_seconds=.1)
    assert result.status=='COMPLETE' and len(requests)==len(cancels)==1
    req_id=requests[0][1];receipt=h.client.local_request_completion('POSITIONS_MULTI',req_id)
    assert receipt is not None and receipt.source_client is h.client
    assert receipt.retired and receipt.cancellation_returned and receipt.context_id>0
    assert receipt.request_started_at<=receipt.completed_at
    assert receipt.revision_start<receipt.revision_end
    assert tuple(dict(row) for row in receipt.rows)==(dict(account=ACCOUNT,con_id=123,
        symbol='JPM',sec_type='STK',currency='USD',quantity=0,avg_cost=0.),)
    tickets=[h.client.local_intake_occurrence(ticket) for ticket in h.client.local_intake_occurrences()
        if ticket.ticket_id in receipt.callback_ticket_ids]
    assert {ticket.kind for ticket in tickets}=={'positionMulti','positionMultiEnd'}
    assert all(dict(ticket.publication)['context_id']==receipt.context_id for ticket in tickets)
    with pytest.raises(TypeError):receipt.rows[0]['quantity']=1
    with pytest.raises(TypeError):copy.copy(receipt)


@pytest.mark.parametrize('fault',['cancel_error','late_callback','wrong_scope','fractional','mutated_sdk'])
def test_native_legacy_complete_position_result_cannot_fabricate_cleanup_receipt(local_component,monkeypatch,fault):
    h=local_component();contract=_source_position_contract()
    def requested(kind,req_id):
        h.client.positionMulti(req_id,ACCOUNT,'',contract,.5 if fault=='fractional' else 0,0.)
        h.client.positionMultiEnd(req_id)
        if fault=='mutated_sdk':contract.symbol='MUTATED_AFTER_CALLBACK'
    def cancelled(kind,req_id):
        if fault=='cancel_error':raise OSError('synthetic cancellation did not return')
        if fault=='late_callback':h.client.positionMultiEnd(req_id)
        if fault=='wrong_scope':h.client.managedAccounts('OTHER_SYNTHETIC')
    requests,cancels=_source_request_encoder(h,monkeypatch,requested,cancelled)
    result=h.client.position_snapshot(timeout_seconds=.1)
    assert result.status=='COMPLETE' and len(requests)==len(cancels)==1
    assert h.client.local_request_completion('POSITIONS_MULTI',requests[0][1]) is None
    assert h.client.local_intake_snapshot().dirty


def test_native_currency_receipt_binds_actual_strict_context_and_cleanup(local_component,monkeypatch):
    h=local_component()
    def requested(kind,req_id):
        assert kind==62
        h.client.accountSummary(req_id,ACCOUNT,'CashBalance','12.34','USD')
        h.client.accountSummaryEnd(req_id)
    def cancelled(kind,req_id):
        assert kind==63
        assert 'account_currency_query' not in h.client._request_context_by_req_id[req_id]
    requests,cancels=_source_request_encoder(h,monkeypatch,requested,cancelled)
    result=h.client.account_currency_snapshot(expected_account=ACCOUNT,timeout_seconds=.1)
    assert result.status=='COMPLETE' and result.currency=='USD' and len(requests)==len(cancels)==1
    receipt=h.client.local_request_completion('ACCOUNT_CURRENCY_STRICT',result.request_id)
    assert receipt is not None and receipt.currency=='USD' and receipt.tags==('CashBalance',)
    assert receipt.completed_at==result.completed_at and receipt.account==ACCOUNT
    tickets=[ticket for ticket in h.client.local_intake_occurrences() if ticket.ticket_id in receipt.callback_ticket_ids]
    assert {ticket.kind for ticket in tickets}=={'accountSummary','accountSummaryEnd'}
    assert all(dict(ticket.publication)['context_id']==receipt.context_id for ticket in tickets)


def _source_execution(identifier='source-execution',price=10.5):
    execution=Execution();execution.orderId=71;execution.clientId=999
    execution.acctNumber=ACCOUNT;execution.execId=identifier;execution.side='BOT'
    execution.shares=1;execution.cumQty=1;execution.price=price;execution.avgPrice=price
    execution.time='20261115 13:35:00 UTC'
    return execution


def test_native_semantics_remain_frozen_after_sdk_object_mutation_and_reject_copies(local_component):
    from dataclasses import replace
    h=local_component();contract=_source_position_contract();execution=_source_execution()
    h.client.execDetails(-1,contract,execution)
    ticket=next(row for row in h.client.local_intake_snapshot().dirty if row.kind=='execDetails')
    original=ticket.semantic_payload
    snapshot=h.client.local_financial_cache_snapshot()
    assert dict(ticket.publication)==dict(kind='execDetails',cache='_exec_details_by_order',
        order_id=71,execution_id=execution.execId,request_id=-1)
    execution.price=99.
    changed=h.client.local_financial_cache_snapshot()
    assert ticket.semantic_payload is original
    assert changed['executions_snapshot']!=snapshot['executions_snapshot']
    assert changed['native_executions']==snapshot['native_executions']
    with pytest.raises(RuntimeError,match='OCCURRENCE_UNAVAILABLE'):
        h.client.local_intake_occurrence(replace(ticket))
    with pytest.raises(RuntimeError,match='SEMANTIC_SOURCE_REQUIRED'):
        h.client._local_intake_fingerprint(ticket,'caller-hash',semantic_payload=('caller',))
    with pytest.raises(RuntimeError,match='PUBLICATION_SOURCE_REQUIRED'):
        h.client._publish_local_intake('execDetails',cache='caller')
    assert ticket in h.client.local_intake_occurrences()


def test_native_duplicate_occurrences_keep_distinct_receipts_without_dedup_cache_deletion(local_component):
    h=local_component();contract=_source_position_contract();execution=_source_execution()
    h.client.execDetails(-1,contract,execution);h.client.execDetails(-1,contract,execution)
    tickets=[row for row in h.client.local_intake_occurrences() if row.kind=='execDetails']
    assert len(tickets)==2 and tickets[0].ticket_id!=tickets[1].ticket_id
    assert tickets[0].semantic_payload==tickets[1].semantic_payload
    assert len(h.client.cached_native_executions(71))==1
    assert len(h.client._exec_details_by_order[71])==len(h.client._executions_snapshot)==2
    assert all(ticket.finished and not ticket.failed for ticket in tickets)


def test_native_changed_duplicate_remains_conflicting_and_nonfinite_occurrence_fails(local_component):
    h=local_component();contract=_source_position_contract()
    h.client.execDetails(-1,contract,_source_execution())
    h.client.execDetails(-1,contract,_source_execution(price=10.6))
    with pytest.raises(ValueError,match='DUPLICATE_CONFLICT'):h.client.cached_native_executions(71)
    bad=_source_execution('nonfinite');bad.price=float('nan')
    h.client.execDetails(-1,contract,bad)
    tickets=[row for row in h.client.local_intake_occurrences() if row.kind=='execDetails']
    assert tickets[-1].finished and tickets[-1].failed and tickets[-1].semantic_payload is None
    assert len(h.client.local_intake_snapshot().dirty)>=3


@pytest.mark.parametrize('fault',['cancel_error','late_callback','empty_end'])
def test_native_currency_cleanup_or_unowned_end_never_issues_receipt(local_component,monkeypatch,fault):
    h=local_component()
    def requested(kind,req_id):
        if fault!='empty_end':h.client.accountSummary(req_id,ACCOUNT,'CashBalance','0','USD')
        h.client.accountSummaryEnd(req_id)
    def cancelled(kind,req_id):
        if fault=='cancel_error':raise OSError('synthetic currency cleanup error')
        if fault=='late_callback':h.client.accountSummaryEnd(req_id)
    requests,cancels=_source_request_encoder(h,monkeypatch,requested,cancelled)
    result=h.client.account_currency_snapshot(expected_account=ACCOUNT,timeout_seconds=.1)
    assert len(requests)==len(cancels)==1
    assert result.status=={'cancel_error':'CLEANUP_UNCONFIRMED','late_callback':'COMPLETE',
        'empty_end':'MISSING_CURRENCY'}[fault]
    assert h.client.local_request_completion('ACCOUNT_CURRENCY_STRICT',result.request_id) is None


def test_native_new_request_is_inflight_before_first_callback_and_is_released(local_component,monkeypatch):
    h=local_component();entered,release=threading.Event(),threading.Event();results=[];errors=[]
    contract=_source_position_contract()
    def requested(kind,req_id):
        entered.set()
        assert release.wait(2)
        h.client.positionMulti(req_id,ACCOUNT,'',contract,0,0.)
        h.client.positionMultiEnd(req_id)
    requests,cancels=_source_request_encoder(h,monkeypatch,requested,lambda *args:None)
    before=h.client.local_intake_snapshot()
    def run():
        try:results.append(h.client.position_snapshot(timeout_seconds=.5))
        except BaseException as exc:errors.append(exc)
    worker=threading.Thread(target=run);worker.start()
    try:
        assert entered.wait(2)
        current=h.client.local_intake_snapshot()
        assert current.revision>before.revision and current.inflight
        assert h.client.local_request_completion('POSITIONS_MULTI',requests[0][1]) is None
        with pytest.raises(RuntimeError,match='CACHE_BUSY'):h.client.local_financial_cache_snapshot()
    finally:
        release.set();worker.join(3)
        assert not worker.is_alive()
    assert not errors and results[0].status=='COMPLETE'
    assert h.client.local_request_completion('POSITIONS_MULTI',requests[0][1]) is not None
    assert len(requests)==len(cancels)==1


def test_native_request_receipt_never_renews_time_and_epoch_change_revokes_it(local_component,monkeypatch):
    h=local_component();contract=_source_position_contract()
    def requested(kind,req_id):
        h.client.positionMulti(req_id,ACCOUNT,'',contract,0,0.)
        h.client.positionMultiEnd(req_id)
    requests,cancels=_source_request_encoder(h,monkeypatch,requested,lambda *args:None)
    result=h.client.position_snapshot(timeout_seconds=.1)
    receipt=h.client.local_request_completion('POSITIONS_MULTI',requests[0][1])
    assert receipt.completed_at==result.completed_at
    assert h.client.local_request_completion('POSITIONS_MULTI',requests[0][1]) is receipt
    h.client._position_connection_epoch+=1
    assert h.client.local_request_completion('POSITIONS_MULTI',requests[0][1]) is None


def test_native_failed_request_without_callbacks_stays_dirty_without_replacing_prior_receipt(local_component,monkeypatch):
    h=local_component();contract=_source_position_contract()
    def requested(kind,req_id):
        h.client.positionMulti(req_id,ACCOUNT,'',contract,0,0.)
        h.client.positionMultiEnd(req_id)
    requests,cancels=_source_request_encoder(h,monkeypatch,requested,lambda *args:None)
    assert h.client.position_snapshot(timeout_seconds=.1).status=='COMPLETE'
    previous=h.client.local_request_completion('POSITIONS_MULTI',requests[0][1])
    def failed_request(*args):raise OSError('synthetic request failed before any callback')
    _source_request_encoder(h,monkeypatch,failed_request,lambda *args:None)
    assert h.client.position_snapshot(timeout_seconds=.1).status=='FAILED'
    dirty=h.client.local_intake_snapshot().dirty
    assert any(ticket.kind=='POSITIONS_MULTI' and ticket.finished and ticket.failed for ticket in dirty)
    assert h.client.local_request_completion('POSITIONS_MULTI',requests[0][1]) is previous
    monkeypatch.setattr(h.client,'isConnected',lambda:False)
    assert h.client.local_request_completion('POSITIONS_MULTI',requests[0][1]) is None


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


def test_native_enrollment_refuses_callback_already_running_before_bind(
        local_component,native_execution_client,monkeypatch):
    client=native_execution_client;entered=threading.Event();release=threading.Event();errors=[]
    original=client._observe_order_id
    def blocked(order_id):
        entered.set();assert release.wait(timeout=3)
        return original(order_id)
    monkeypatch.setattr(client,'_observe_order_id',blocked)
    def callback():
        try:client.orderStatus(43000,'Submitted',0,1,0,0,0,0,999,'',0)
        except BaseException as exc:errors.append(exc)
    worker=threading.Thread(target=callback)
    try:
        worker.start();assert entered.wait(timeout=2)
        assert getattr(client,'_p02_local_ingress',None) is None
        with pytest.raises(RuntimeError,match='P02_LOCAL_NATIVE_.*'):
            local_component()
        assert getattr(client,'_p02_local_ingress',None) is None
    finally:
        release.set();worker.join(timeout=3)
    assert not worker.is_alive() and not errors
    assert client.cached_order_status(43000)['remaining']==1


def test_native_lifetime_is_visible_before_bound_intake_registration(local_component,monkeypatch):
    from test_p02_observable_local_cooldown import NOW
    h=local_component();_settle(h)
    initial=h.engine.observe_p02_local_cooldown(identity=h.identity,
        context_fingerprint='before-registration',assessed_at=NOW)
    assert initial.local_condition_satisfied and not initial.admission_authorized
    entered=threading.Event();release=threading.Event();errors=[]
    original=h.client.begin_local_intake
    def blocked(kind):
        entered.set();assert release.wait(timeout=3)
        return original(kind)
    monkeypatch.setattr(h.client,'begin_local_intake',blocked)
    def callback():
        try:h.client.orderStatus(43000,'Submitted',0,1,0,0,0,0,999,'',0)
        except BaseException as exc:errors.append(exc)
    worker=threading.Thread(target=callback)
    try:
        worker.start();assert entered.wait(timeout=2)
        snapshot=h.client.local_intake_snapshot()
        assert snapshot.inflight and all(identifier<0 for identifier in snapshot.inflight)
        assert snapshot.dirty==()  # No bound ticket exists yet; lifetime still vetoes.
        _settle(h)
        value=h.engine.observe_p02_local_cooldown(identity=h.identity,
            context_fingerprint='paused-before-registration',assessed_at=NOW)
        assert not value.local_condition_satisfied and not value['available']
        assert 'P02_LOCAL_INTAKE_NOT_SETTLED' in value['findings']
    finally:
        release.set();worker.join(timeout=3)
    assert not worker.is_alive() and not errors
    assert not h.client.local_intake_snapshot().inflight
    assert h.client.cached_order_status(43000)['remaining']==1


def test_native_unbound_lifetime_metadata_is_bounded_and_unknown_intake_sticky(
        native_execution_client,local_component):
    client=native_execution_client;state=client._p02_source_lifetime
    before=state['revision']
    for _ in range(5):client.execDetails(999999,Contract(),Execution())
    assert state['revision']>before and state['operations']=={}
    assert state['tickets']=={} and state['origins']=={} and not state['inflight']
    assert state['supported'] is False and state['unsupported']=='PREBIND_execDetails'
    assert getattr(client,'_p02_local_ingress',None) is None
    assert client._exec_details_by_order=={}
    with pytest.raises(RuntimeError,match='P02_LOCAL_NATIVE_LIFETIME_UNAVAILABLE'):
        local_component(client=client)
    assert client._p02_source_lifetime is state and not state['supported']


def test_native_prebind_critical_rebind_cannot_be_laundered_by_restoring_value(
        native_execution_client,local_component):
    client=native_execution_client;state=client._p02_source_lifetime;revision=state['revision']
    client.client_id=1000;client.client_id=999
    assert state['revision']>revision and not state['operations']
    assert state['unsupported']=='PREBIND_SET_client_id'
    with pytest.raises(RuntimeError,match='P02_LOCAL_NATIVE_LIFETIME_UNAVAILABLE'):
        local_component(client=client)
    assert client.client_id==999 and state is client._p02_source_lifetime


def test_native_reinitialization_never_resets_original_lifetime(native_execution_client,local_component):
    client=native_execution_client;state=client._p02_source_lifetime;revision=state['revision']
    client.__init__('offline',0,999,1,'LIVE',True)
    assert client._p02_source_lifetime is state and state['revision']>revision
    assert not state['supported'] and state['unsupported']=='NATIVE_REINITIALIZATION'
    with pytest.raises(RuntimeError,match='P02_LOCAL_NATIVE_LIFETIME_UNAVAILABLE'):
        local_component(client=client)


def test_native_missing_constructor_metadata_cannot_enroll(local_component):
    from src.core.engines.trade_lifecycle_engine import TradeLifecycleEngine
    from src.storage.storage_engine import StorageEngine
    legacy=IbkrClient.__new__(IbkrClient)
    legacy.client_id=999;legacy._position_connection_epoch=0
    legacy._managed_accounts=[ACCOUNT];legacy._execution_callbacks=[]
    legacy._stop_event=threading.Event();legacy.isConnected=lambda:True
    assert getattr(legacy,'_p02_source_lifetime',None) is None
    h=local_component(enrolled=False,client=legacy)
    storage=StorageEngine(local_cooldown_mode='PAPER')
    try:
        h.engine._storage_engine=storage;h.engine._trade_lifecycle_engine=TradeLifecycleEngine(storage)
        assert storage.local_cooldown_state()['supported']
        with pytest.raises(RuntimeError,match='P02_LOCAL_NATIVE_ENROLLMENT_UNAVAILABLE'):
            h.engine.enable_p02_local_cooldown(account=ACCOUNT,client=legacy)
        assert getattr(legacy,'_p02_source_lifetime',None) is None
        assert getattr(legacy,'_p02_local_ingress',None) is None
    finally:storage.shutdown()


def test_native_failed_bound_intake_registration_remains_dirty(local_component,monkeypatch):
    h=local_component();_settle(h)
    def failed(kind):raise RuntimeError('Synthetic failure before bound-ticket registration')
    monkeypatch.setattr(h.client,'begin_local_intake',failed)
    with pytest.raises(RuntimeError,match='before bound-ticket'):
        _status(h.client)
    snapshot=h.client.local_intake_snapshot()
    assert not snapshot.inflight
    assert any(ticket.kind=='orderStatus' and ticket.finished and ticket.failed
        for ticket in snapshot.dirty)
    assert h.client._order_status=={}
    _settle(h)
    assert h.client.local_intake_snapshot().dirty


def test_native_lifetime_uses_real_primitives_with_existing_history_event_seam(
        native_execution_client,monkeypatch):
    from types import SimpleNamespace
    import src.adapters.brokers.ibkr.ibkr_client as native_module
    client=native_execution_client
    monkeypatch.setattr(native_module,'threading',SimpleNamespace(Event=threading.Event))
    _status(client)
    assert client.cached_order_status(71)['filled']==1
    assert client._p02_source_lifetime['operations']=={}
    assert client._p02_source_lifetime['tickets']=={}
    assert getattr(client,'_p02_local_ingress',None) is None


def test_native_bound_reinitialization_invalidates_snapshot_without_resetting_cache(local_component):
    from test_p02_observable_local_cooldown import NOW
    h=local_component();_settle(h)
    old=h.engine.observe_p02_local_cooldown(identity=h.identity,
        context_fingerprint='before-bound-reinitialization',assessed_at=NOW)
    assert old.local_condition_satisfied and not old.admission_authorized
    state=h.client._p02_source_lifetime;cache=h.client._order_status
    with pytest.raises(RuntimeError,match='REINITIALIZATION_UNSUPPORTED'):
        h.client.__init__('offline',0,999,1,'LIVE',True)
    assert h.client._p02_source_lifetime is state and h.client._order_status is cache
    assert state['supported'] is False and state['ready'] is False
    with pytest.raises(RuntimeError,match='LIFETIME_UNAVAILABLE'):
        h.client.local_intake_snapshot()
    with pytest.raises(RuntimeError,match='LIFETIME_UNAVAILABLE'):
        h.engine.revalidate_p02_local_cooldown(old,assessed_at=NOW)
    assert not h.engine._p02_local['gate'].locked()


@pytest.mark.parametrize('case,expected_ids,expected_counts', [
    ('direct', [71], dict(place=1,modify=0,cancel=0)),
    ('shim', [71], dict(place=1,modify=0,cancel=0)),
    ('twice', [71,71], dict(place=1,modify=1,cancel=0)),
    ('callback_same', [71,71], dict(place=1,modify=1,cancel=0)),
    ('callback_other', [72,71], dict(place=2,modify=0,cancel=0)),
    ('callback_raises', [71], dict(place=1,modify=1,cancel=0)),
    ('reentrant_native', [72,71], dict(place=2,modify=0,cancel=0)),
    ('cross_client', [71,71], dict(place=2,modify=0,cancel=0)),
    ('changed_order', [71], dict(place=1,modify=1,cancel=0)),
    ('guard_changed', [], dict(place=1,modify=0,cancel=0)),
])
def test_native_sdk_receipt_counts_only_exact_selected_delegation(
        monkeypatch,case,expected_ids,expected_counts):
    from src.ibkr.mutation_audit import delegate_sdk_place_order, instrument_mutation
    set_config_overrides(dict(RUN_MODE='PAPER',RUN_MODE_EFFECTIVE='PAPER',EXECUTION_ENABLED=True,
        EXECUTION_ENABLED_EFFECTIVE=True,IBKR_READONLY_ENABLED=False))
    calls=[]
    class SDK:
        readonly_enabled=False
        def placeOrder(self,orderId,contract,order):
            calls.append((self,orderId,contract,order))
    class Native(SDK):
        def placeOrder(self,orderId,contract,order):
            return delegate_sdk_place_order(self,saved_sdk,super().placeOrder,
                orderId,contract,order)
    instrument_mutation(SDK,'placeOrder')
    saved_sdk=SDK.placeOrder
    instrument_mutation(Native,'placeOrder')
    client,other=Native(),SDK()
    contract,order=object(),object()
    def shim(self,orderId,contract,order):
        if case in {'callback_same','callback_other','callback_raises'}:
            def callback():
                saved_sdk(self,72 if case=='callback_other' else orderId,contract,order)
            callback()
            if case=='callback_raises':
                raise RuntimeError('synthetic shim abort after distinct callback')
        if case=='reentrant_native' and orderId==71:
            self.placeOrder(72,contract,order)
        if case=='cross_client':
            saved_sdk(other,orderId,contract,order)
        if case=='guard_changed':
            self.readonly_enabled=True
        result=saved_sdk(self,orderId,contract,object() if case=='changed_order' else order)
        if case=='twice':
            saved_sdk(self,orderId,contract,order)
        return result
    if case!='direct':
        monkeypatch.setattr(SDK,'placeOrder',shim)
    if case in {'callback_raises','guard_changed'}:
        with pytest.raises(RuntimeError,match='synthetic shim abort|read-only'):
            client.placeOrder(71,contract,order)
    else:
        client.placeOrder(71,contract,order)
    assert [row[1] for row in calls]==expected_ids
    assert mutations()==expected_counts
    import src.ibkr.mutation_audit as audit
    assert getattr(audit._local,'delegations',())==()
