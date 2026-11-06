"""Scoped owner faults around the real joined standalone PMH admission."""
from copy import deepcopy
from datetime import timedelta

import pytest

from test_standalone_pmh_late_fill_protection import (
    late_pmh, acknowledge, teardown_unsent_fixture, reassessment, lifecycle,
    _reset_config, forbid_io, no_external_activity,
)


def processor(h):
    return lambda r:h.core._apply_execution_results_to_trade_management([r])


def collect(h):
    return h.core.execution_engine.collect_relationship_updates(result_processor=processor(h))


@pytest.mark.parametrize('fault',['symbol','account','side','client_order_id','orderId','missing_counts',
    'fractional','negative','oversize','nan_price','missing_price','unknown_status','inconsistent_terminal',
    'retained_symbol','retained_native','retained_mode','retained_decision','duplicate'])
def test_bad_native_update_rejects_before_effects(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    h=late_pmh(reassessment,monkeypatch,tmp_path)
    try:
        request=acknowledge(h,capsys);engine=h.core.execution_engine
        h.facts[71]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.31)
        if fault in {'symbol','account','side','client_order_id','orderId'}:h.facts[71][fault]='UNRELATED'
        if fault=='missing_counts':h.facts[71].pop('filled')
        if fault=='fractional':h.facts[71]['filled']=.5
        if fault=='negative':h.facts[71]['filled']=-1
        if fault=='oversize':h.facts[71]['filled']=2
        if fault=='nan_price':h.facts[71]['avgFillPrice']=float('nan')
        if fault=='missing_price':h.facts[71].pop('avgFillPrice')
        if fault=='unknown_status':h.facts[71]['status']='UNKNOWN'
        if fault=='inconsistent_terminal':h.facts[71]['remaining']=1
        order=engine._native_orders[request.client_order_id]
        if fault.startswith('retained_'):
            key={'retained_symbol':'symbol','retained_native':'broker_order_id','retained_mode':'mode','retained_decision':'decision_id'}[fault]
            order[key]='CHANGED'
        if fault=='duplicate':engine._native_orders['duplicate']=deepcopy(order)
        with pytest.raises((ValueError,RuntimeError)):collect(h)
        assert not engine.position_records and not h.stop_requests and not h.core.trade_registry.snapshot()
        assert engine.capital_authority.total_used_exposure==0 and engine.capital_authority.total_reserved_capital==pytest.approx(10.3)
        assert len(h.sent_native)==1
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('stage',['before_mutation','after_allocation','after_capital','after_accounting','after_processor','completion_write'])
def test_native_interruption_quarantines_without_replay(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,stage):
    h=late_pmh(reassessment,monkeypatch,tmp_path)
    try:
        request=acknowledge(h,capsys);engine=h.core.execution_engine
        h.facts[71]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.31)
        h.native_quantity[0]=1;h.native_open_orders.clear()
        def fail():raise RuntimeError('controlled native processing interruption')
        if stage=='before_mutation':
            original=engine._save_native_orders
            def save():
                if engine._native_orders[request.client_order_id].get('cached_update_in_progress'):fail()
                return original()
            monkeypatch.setattr(engine,'_save_native_orders',save)
        elif stage in {'after_allocation','after_capital','after_accounting'}:
            name={'after_allocation':'_convert_strategy_allocation_for_fill','after_capital':'_convert_capital_for_fill','after_accounting':'_record_fill_and_position'}[stage]
            original=getattr(engine,name)
            def interrupted(*a,**kw):original(*a,**kw);fail()
            monkeypatch.setattr(engine,name,interrupted)
        elif stage=='completion_write':
            original=engine._save_native_orders
            def save():
                order=engine._native_orders[request.client_order_id]
                if order['filled']==1 and not order.get('cached_update_in_progress'):fail()
                return original()
            monkeypatch.setattr(engine,'_save_native_orders',save)
        callback=processor(h)
        if stage=='after_processor':
            def interrupted(value):callback(value);fail()
            process=interrupted
        else:process=callback
        with pytest.raises(RuntimeError):engine.collect_relationship_updates(result_processor=process)
        counts=(engine.capital_authority.total_used_exposure,len(engine.position_records),len(h.stop_requests),len(h.sent_native))
        with pytest.raises(RuntimeError):collect(h)
        assert counts==(engine.capital_authority.total_used_exposure,len(engine.position_records),len(h.stop_requests),len(h.sent_native))
        assert engine._native_quarantined or engine._native_orders[request.client_order_id].get('cached_update_in_progress')
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('status',['Cancelled','Rejected','Inactive'])
def test_authoritative_zero_fill_terminal_releases_only_reservations(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,status):
    h=late_pmh(reassessment,monkeypatch,tmp_path)
    try:
        request=acknowledge(h,capsys);engine=h.core.execution_engine
        h.facts[71]=dict(status=status,filled=0,remaining=1)
        collect(h);collect(h)
        assert engine._native_orders[request.client_order_id]['terminal']
        assert engine.capital_authority.total_reserved_capital==0
        assert not engine.strategy_allocation_authority.active_reservations
        assert not engine.position_records and not h.stop_requests
    finally:teardown_unsent_fixture(h,no_external_activity)


def test_nonterminal_then_terminal_full_one_share_applies_once(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h=late_pmh(reassessment,monkeypatch,tmp_path)
    try:
        request=acknowledge(h,capsys);engine=h.core.execution_engine
        h.facts[71]=dict(status='Submitted',filled=1,remaining=0,avgFillPrice=10.31)
        h.native_quantity[0]=1;h.native_open_orders.clear()
        collect(h)
        assert not engine._native_orders[request.client_order_id]['terminal']
        h.facts[71]['status']='Filled'
        collect(h);collect(h)
        assert engine._native_orders[request.client_order_id]['terminal']
        assert engine.capital_authority.total_used_exposure==10.31
        assert h.manager.snapshot_positions()['JPM'].quantity==1 and len(h.stop_requests)==1
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('change',['account','client','mode','stale','unknown'])
def test_scope_change_cannot_apply_cached_effect(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,change):
    from types import SimpleNamespace as NS
    from src.config.runtime_config import RunMode
    h=late_pmh(reassessment,monkeypatch,tmp_path)
    try:
        acknowledge(h,capsys);engine=h.core.execution_engine
        h.facts[71]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.31)
        account,client,stamp=engine._native_scope
        if change=='account':engine.bind_native_order_scope(account='OTHER',client=client,as_of=stamp)
        if change=='client':engine._provider.broker.connection_manager.optional_client=NS()
        if change=='mode':engine.run_mode=RunMode.READ_ONLY
        if change=='stale':engine.bind_native_order_scope(account=account,client=client,as_of=stamp-timedelta(minutes=2))
        if change=='unknown':engine.bind_native_order_scope(account=None,client=client,as_of=stamp)
        with pytest.raises((ValueError,RuntimeError)):collect(h)
        assert not engine.position_records and not h.stop_requests and len(h.sent_native)==1
        assert engine.capital_authority.total_used_exposure==0
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('response',['pending','timeout','exception','missing_id'])
def test_submission_uncertainty_retains_reservation_and_never_resubmits(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,response):
    h=late_pmh(reassessment,monkeypatch,tmp_path)
    try:
        broker=h.core.execution_engine._provider.broker;original=broker.place_order
        def external(request):
            result=original(request)
            if response=='exception':raise OSError('synthetic lost submission reply')
            result.status='PendingSubmit' if response=='pending' else ('TIMED_OUT' if response=='timeout' else 'Submitted')
            if response!='pending':result.ibkr_order_id=None
            result.retry_scheduled=True;result.next_retry_tick=100
            return result
        monkeypatch.setattr(broker,'place_order',external)
        assert h.core.run_once();capsys.readouterr();h.life.clock.current+=timedelta(seconds=11)
        assert h.core.run_once();capsys.readouterr()
        engine=h.core.execution_engine
        for _ in range(2):
            h.life.clock.current+=timedelta(seconds=1);assert h.core.run_once();capsys.readouterr()
        assert len(h.sent_native)==1 and not engine.position_records and not h.stop_requests
        assert engine.capital_authority.total_reserved_capital==pytest.approx(10.3)
        assert not h.manager.snapshot_positions()
        assert not h.execution_results[0].submission_confirmed()
        assert engine.pending_book.due_orders(1000)==[]
    finally:teardown_unsent_fixture(h,no_external_activity)


def test_restart_and_second_writer_cannot_replay_retained_native_state(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    import os,subprocess,sys
    h=late_pmh(reassessment,monkeypatch,tmp_path)
    try:
        acknowledge(h,capsys);engine=h.core.execution_engine;storage=h.core.storage_engine
        namespace='execution.native_orders.v1:PAPER'
        before=storage.fetch_management_state(namespace)
        with pytest.raises(RuntimeError,match='CONFLICT'):
            storage.store_execution_order_state(namespace,{'version':1,'orders':{}},expected=None)
        assert storage.fetch_management_state(namespace)==before
        script='''
import sqlite3,sys
from types import SimpleNamespace as NS
from src.storage.storage_engine import StorageEngine
from src.execution.execution_engine import ExecutionEngine
from src.config.runtime_config import RunMode
s=StorageEngine.__new__(StorageEngine);s.enabled=True;s.backend='sqlite'
s._store=NS(connection=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True))
e=ExecutionEngine.__new__(ExecutionEngine);e._storage_engine=s;e.run_mode=RunMode.PAPER
e._native_loaded=False;e._native_state=None;e._native_orders={};e._native_quarantined=False
try:e._load_native_orders()
except RuntimeError as exc:assert str(exc)=='NATIVE_ORDER_RESTART_RECONCILIATION_REQUIRED'
else:raise AssertionError('restored request resumed')
assert e._native_quarantined and e._failsafe_block_new_entries
s._store.connection.close()
print('READ_ONLY_RESTART_BLOCKED')
'''
        result=subprocess.run([sys.executable,'-c',script,storage.sqlite_path],env=dict(os.environ),capture_output=True,text=True,timeout=15)
        assert result.returncode==0,result.stderr
        assert 'READ_ONLY_RESTART_BLOCKED' in result.stdout
        assert storage.fetch_management_state(namespace)==before
        assert not engine.position_records and not h.stop_requests
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('failure',['rejected','missing','wrong_quantity','query_error'])
def test_unverified_protection_quarantines_applied_fill_without_replay(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,failure):
    h=late_pmh(reassessment,monkeypatch,tmp_path)
    try:
        request=acknowledge(h,capsys);engine=h.core.execution_engine;broker=engine._provider.broker
        stop=broker.place_stop_order
        if failure=='rejected':monkeypatch.setattr(broker,'place_stop_order',lambda **kw:dict(status='Rejected',broker_order_id=None))
        else:
            def external(**kw):
                out=stop(**kw)
                if failure=='missing':h.native_open_orders.clear()
                if failure=='wrong_quantity':h.native_open_orders[-1].order.totalQuantity=2
                return out
            monkeypatch.setattr(broker,'place_stop_order',external)
        if failure=='query_error':
            def unavailable():raise OSError('synthetic inventory unavailable')
            monkeypatch.setattr(broker,'open_orders',unavailable)
        h.facts[71]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.31)
        with pytest.raises((RuntimeError,OSError)):collect(h)
        assert engine.capital_authority.total_used_exposure==10.31
        assert engine._native_orders[request.client_order_id].get('cached_update_in_progress')
        calls=len(h.stop_requests)
        with pytest.raises(RuntimeError):collect(h)
        assert len(h.stop_requests)==calls
    finally:teardown_unsent_fixture(h,no_external_activity)


def test_forged_processed_marker_does_not_bypass_owner(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from src.models.execution_result import ExecutionResult
    h=late_pmh(reassessment,monkeypatch,tmp_path)
    try:
        request=acknowledge(h,capsys);engine=h.core.execution_engine
        forged=ExecutionResult(symbol='JPM',trader_type=request.trader_type,attempted=True,status='Filled',
            rationale='synthetic forged transport marker',direction='SELL',filled_quantity=2,remaining_quantity=0,
            average_fill_price=10.31,client_order_id=request.client_order_id,ibkr_order_id=999)
        forged._native_effect_processed=True
        with pytest.raises(ValueError):h.core._apply_execution_results_to_trade_management([forged])
        assert not engine.position_records and not h.manager.snapshot_positions() and not h.stop_requests
        assert engine.capital_authority.total_used_exposure==0
    finally:teardown_unsent_fixture(h,no_external_activity)


def test_restored_request_blocks_before_new_reservation_even_without_scope(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from copy import copy
    h=late_pmh(reassessment,monkeypatch,tmp_path)
    try:
        acknowledge(h,capsys);engine=h.core.execution_engine
        restored=copy(engine);restored._native_loaded=False;restored._native_state=None
        restored._native_orders={};restored._native_scope=None;restored._native_quarantined=False
        before=list(h.reserves)
        from src.execution.execution_engine import ExecutionEngine
        result=ExecutionEngine.execute_trade(restored,h.evaluated[0][2])
        assert not result.attempted and 'NATIVE_ORDER_RECOVERY' in result.rationale
        assert h.reserves==before and len(h.sent_native)==1
        assert restored._native_quarantined
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('error',['stop','deadline'])
def test_stop_before_callback_has_no_effects_and_preserves_owned_request(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,error):
    from src.core.acquisition import AcquisitionCancelled,AcquisitionDeadlineExceeded
    from src.execution import execution_engine as execution_module
    h=late_pmh(reassessment,monkeypatch,tmp_path)
    try:
        acknowledge(h,capsys);engine=h.core.execution_engine
        h.facts[71]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.31)
        def halted():raise (AcquisitionCancelled if error=='stop' else AcquisitionDeadlineExceeded)()
        monkeypatch.setattr(execution_module,'checkpoint',halted)
        with pytest.raises(AcquisitionCancelled if error=='stop' else AcquisitionDeadlineExceeded):collect(h)
        assert not engine.position_records and not h.stop_requests
        assert engine.capital_authority.total_reserved_capital==pytest.approx(10.3)
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('error',['stop','deadline'])
def test_interruption_after_actual_processor_retains_quarantine(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,error):
    from src.core.acquisition import AcquisitionCancelled,AcquisitionDeadlineExceeded
    h=late_pmh(reassessment,monkeypatch,tmp_path)
    try:
        acknowledge(h,capsys);engine=h.core.execution_engine
        h.facts[71]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.31)
        h.native_quantity[0]=1;h.native_open_orders.clear()
        def interrupted(result):
            processor(h)(result)
            raise (AcquisitionCancelled if error=='stop' else AcquisitionDeadlineExceeded)()
        with pytest.raises(AcquisitionCancelled if error=='stop' else AcquisitionDeadlineExceeded):
            engine.collect_relationship_updates(result_processor=interrupted)
        assert engine.capital_authority.total_used_exposure==10.31 and len(h.stop_requests)==1
        with pytest.raises(RuntimeError):collect(h)
        assert engine.capital_authority.total_used_exposure==10.31 and len(h.stop_requests)==1
    finally:teardown_unsent_fixture(h,no_external_activity)


def test_final_commit_lost_reply_and_failed_quarantine_write_never_replays(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h=late_pmh(reassessment,monkeypatch,tmp_path)
    try:
        request=acknowledge(h,capsys);engine=h.core.execution_engine
        h.facts[71]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.31)
        h.native_quantity[0]=1;h.native_open_orders.clear()
        save=engine._save_native_orders;committed=[False]
        def lose_reply():
            order=engine._native_orders[request.client_order_id]
            if committed[0]:raise OSError('synthetic quarantine persistence unavailable')
            save()
            if order['filled']==1 and not order.get('cached_update_in_progress'):
                committed[0]=True
                raise OSError('synthetic lost final commit acknowledgement')
        monkeypatch.setattr(engine,'_save_native_orders',lose_reply)
        with pytest.raises(OSError):collect(h)
        durable=h.core.storage_engine.fetch_management_state('execution.native_orders.v1:PAPER')
        assert durable['orders'][request.client_order_id]['filled']==1
        assert not durable['orders'][request.client_order_id].get('cached_update_in_progress')
        assert engine._native_quarantined
        with pytest.raises(RuntimeError):collect(h)
        assert engine.capital_authority.total_used_exposure==10.31 and len(h.stop_requests)==1
    finally:teardown_unsent_fixture(h,no_external_activity)


def test_storage_failure_before_dispatch_prevents_transport(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h=late_pmh(reassessment,monkeypatch,tmp_path)
    try:
        def unavailable(*a,**kw):raise OSError('synthetic durable request write unavailable')
        monkeypatch.setattr(h.core.storage_engine,'store_execution_order_state',unavailable)
        assert h.core.run_once();capsys.readouterr();h.life.clock.current+=timedelta(seconds=11)
        assert not h.core.run_once();capsys.readouterr()
        assert h.sent_native==[] and h.stop_requests==[]
        assert h.core.execution_engine.capital_authority.total_used_exposure==0
        assert h.core.execution_engine._native_quarantined
    finally:teardown_unsent_fixture(h,no_external_activity)


class NativeProviderManagerInterfaceMissing(AssertionError):
    """Separate adapter API blocker; this owner repair must not hide it."""


@pytest.mark.xfail(strict=True,raises=NativeProviderManagerInterfaceMissing,
    reason='existing provider uses optional_client; actual IbkrConnectionManager exposes existing_client')
def test_real_manager_shape_reaches_existing_provider_cached_read(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h=late_pmh(reassessment,monkeypatch,tmp_path,canonical_manager=True)
    try:
        request=acknowledge(h,capsys);engine=h.core.execution_engine
        h.facts[71]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.31)
        h.native_quantity[0]=1;h.native_open_orders.clear()
        try:collect(h)
        except AttributeError as error:
            assert 'optional_client' in str(error)
            assert h.reads_native==[] and not engine.position_records and h.stop_requests==[]
            assert engine.capital_authority.total_reserved_capital==pytest.approx(10.3)
            assert engine._native_quarantined and engine._native_orders[request.client_order_id]['quarantine']
            raise NativeProviderManagerInterfaceMissing('real manager/provider cached-read API mismatch') from error
        assert h.reads_native==[71] and len(engine.position_records)==1
    finally:teardown_unsent_fixture(h,no_external_activity)


def test_contradictory_fill_after_terminal_cleanup_is_retained_not_replayed(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h=late_pmh(reassessment,monkeypatch,tmp_path)
    try:
        request=acknowledge(h,capsys);engine=h.core.execution_engine
        h.facts[71]=dict(status='Cancelled',filled=0,remaining=1)
        collect(h)
        assert engine.capital_authority.total_reserved_capital==0
        h.facts[71]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.31)
        with pytest.raises(ValueError):collect(h)
        order=engine._native_orders[request.client_order_id]
        assert order['unresolved_update']['filled']==1 and order['unresolved_update']['avgFillPrice']==10.31
        assert engine._native_quarantined and not engine.position_records and not h.stop_requests
        assert engine.capital_authority.total_used_exposure==0
    finally:teardown_unsent_fixture(h,no_external_activity)
