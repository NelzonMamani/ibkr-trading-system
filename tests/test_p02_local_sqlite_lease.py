"""Synthetic original-connection fencing; no trading or history-completeness claim."""
from __future__ import annotations

import copy
import sqlite3
import threading

import pytest

from src.config import config_resolver
from src.storage.sqlite_store import SQLiteStore, _LocalCooldownFence


@pytest.fixture
def store(tmp_path,monkeypatch):
    previous=dict(config_resolver._CONFIG_OVERRIDES)
    monkeypatch.setenv('EXECUTION_ENV','TEST')
    config_resolver.set_config_overrides(dict(previous,RUN_MODE='PAPER',RUN_MODE_EFFECTIVE='PAPER'))
    value=SQLiteStore(str(tmp_path/'local.sqlite3'),local_cooldown_mode='PAPER')
    value.initialize_schema()
    try:
        yield value
    finally:
        state=value._local_cooldown
        if state.lease is not None:
            state.lease.close()
        value.close()
        config_resolver.set_config_overrides(previous or None)


def test_default_connection_remains_raw_and_not_enrolled(tmp_path):
    value=SQLiteStore(str(tmp_path/'default.sqlite3'))
    try:
        assert type(value.connection) is sqlite3.Connection
        assert not value.local_cooldown_state()['enrolled']
        with pytest.raises(RuntimeError,match='NOT_ENROLLED'):
            value.acquire_local_cooldown_fence()
    finally:value.close()


def test_actual_fence_reads_immutable_journal_and_restores_original_connection(store):
    facade=store.connection
    before=store.local_cooldown_state()['revision']
    timeout=facade.execute('PRAGMA busy_timeout').fetchall()[0][0]
    before=store.local_cooldown_state()['revision']
    lease=store.acquire_local_cooldown_fence(expected_revision=before)
    assert type(lease) is _LocalCooldownFence and lease.owner is store and lease.revision==before
    assert lease.validate()
    evidence=lease.read_committed_accounting()
    assert evidence['events']==evidence['trades']==evidence['native_states']==()
    assert evidence['relationship_states']==()
    with pytest.raises(TypeError):evidence['events']=()
    assert store.local_cooldown_state()['revision']==before
    lease.close();lease.close()
    assert not lease.validate() and store.connection is facade
    assert facade.execute('PRAGMA busy_timeout').fetchall()[0][0]==timeout
    assert facade.execute('PRAGMA query_only').fetchall()[0][0]==0
    assert not facade.in_transaction
    with store.acquire_local_cooldown_fence() as second:
        assert second.validate()


def test_fence_materializes_real_current_and_prior_accounting_rows(store):
    from src.storage.sqlite_store import now_iso
    for number in (1,2):
        run='RUN'+str(number)
        store.insert_run(dict(run_id=run,run_mode='PAPER',effective_run_mode='PAPER',event_replay_mode='CYCLE'))
        store.upsert_trade_lifecycle_trade(dict(lifecycle_trade_id='ROOT'+str(number),run_id=run,
            symbol='JPM',side='LONG',strategy_name='StatisticalIntradayMomentum',status='OPEN',
            quantity_open=1,quantity_closed=0,entry_avg_price=10.5,gross_realized_pnl=0.,
            source_execution_ids_json="['EXEC"+str(number)+"']",created_at=now_iso()))
        store.insert_trade_lifecycle_events([dict(event_id='EVENT'+str(number),run_id=run,
            lifecycle_trade_id='ROOT'+str(number),symbol='JPM',side='LONG',event_type='ENTRY_FILL',
            quantity=1,price=10.5,timestamp='2026-11-14T14:00:00+00:00',execution_id='EXEC'+str(number))])
    with store.acquire_local_cooldown_fence() as lease:
        result=lease.read_committed_accounting()
        assert [row['event_id'] for row in result['events']]==['EVENT1','EVENT2']
        assert {row['run_id'] for row in result['trades']}=={'RUN1','RUN2'}
        with pytest.raises(TypeError):result['events'][0]['quantity']=99


@pytest.mark.parametrize('operation',['write','cached_write','commit','rollback','script','close','cursor_write'])
def test_public_operation_refuses_before_delegation_and_invalidates_lease(store,operation):
    connection=store.connection
    connection.execute('CREATE TABLE probe(value)').close()
    sql='INSERT INTO probe VALUES(?)'
    if operation=='cached_write':
        connection.execute(sql,(1,)).close();connection.commit()
    cursor=connection.cursor()
    lease=store.acquire_local_cooldown_fence()
    actions={
        'write':lambda:connection.execute(sql,(2,)),
        'cached_write':lambda:connection.execute(sql,(2,)),
        'commit':connection.commit,'rollback':connection.rollback,
        'script':lambda:connection.executescript('COMMIT; INSERT INTO probe VALUES(2);'),
        'close':connection.close,'cursor_write':lambda:cursor.execute(sql,(2,)),
    }
    with pytest.raises(RuntimeError,match='DURING_LEASE'):actions[operation]()
    assert not lease.validate()
    lease.close()
    rows=connection.execute('SELECT value FROM probe').fetchall()
    assert [row[0] for row in rows]==([1] if operation=='cached_write' else [])
    assert store.local_cooldown_state()['uncertain']
    with pytest.raises(RuntimeError):store.acquire_local_cooldown_fence()


@pytest.mark.parametrize('name',['blobopen','backup','deserialize','set_authorizer','set_progress_handler',
    'set_trace_callback','create_function','create_aggregate','create_window_function','create_collation',
    'enable_load_extension','load_extension','setconfig','setlimit'])
def test_unsupported_api_is_sticky_without_invoking_it(store,name):
    with pytest.raises(RuntimeError,match='UNSUPPORTED_CONNECTION_API'):
        getattr(store.connection,name)
    assert not store.local_cooldown_state()['supported']
    with pytest.raises(RuntimeError):store.acquire_local_cooldown_fence()


@pytest.mark.parametrize('name,value',[('row_factory',lambda *args:None),('text_factory',bytes),
    ('autocommit',True),('isolation_level',None)])
def test_configuration_setters_refuse_before_native_descriptor(store,name,value):
    with pytest.raises(RuntimeError,match='CONFIGURATION'):setattr(store.connection,name,value)
    assert store.local_cooldown_state()['uncertain']


def test_no_raw_escape_or_custom_factory_or_transfer(store):
    cursor=store.connection.cursor()
    assert cursor.connection is store.connection
    with pytest.raises(TypeError):sqlite3.Connection.execute(store.connection,'SELECT 1')
    with pytest.raises(TypeError):sqlite3.Cursor.execute(cursor,'SELECT 1')
    with pytest.raises(TypeError):copy.copy(store.connection)
    with pytest.raises(TypeError):copy.deepcopy(cursor)
    calls=[]
    with pytest.raises(RuntimeError,match='CUSTOM_CURSOR_FACTORY'):
        store.connection.cursor(factory=lambda *args:calls.append(args))
    assert calls==[]


def test_preexisting_returning_vm_refuses_fence_without_rolling_back_its_work(store):
    connection=store.connection
    connection.execute('CREATE TABLE probe(value)').close()
    connection.executemany('INSERT INTO probe VALUES(?)',[(1,),(2,)]).close();connection.commit()
    cursor=connection.execute('WITH witness AS(SELECT 1) UPDATE probe SET value=value+10 RETURNING value')
    assert not connection.in_transaction
    with pytest.raises(RuntimeError,match='FENCE_UNAVAILABLE'):store.acquire_local_cooldown_fence()
    assert [row[0] for row in cursor.fetchall()]==[11,12]
    cursor.close()
    with store.acquire_local_cooldown_fence() as lease:assert lease.validate()
    assert [row[0] for row in connection.execute('SELECT value FROM probe').fetchall()]==[11,12]


def test_pending_transaction_is_not_committed_or_rolled_back_by_acquisition(store):
    store.connection.execute('CREATE TABLE probe(value)').close()
    store.connection.execute('INSERT INTO probe VALUES(1)').close()
    assert store.connection.in_transaction
    with pytest.raises(RuntimeError):store.acquire_local_cooldown_fence()
    assert store.connection.in_transaction
    store.connection.rollback()
    assert store.connection.execute('SELECT value FROM probe').fetchall()==[]


def test_other_connection_writer_is_excluded_and_timeout_is_zero(store):
    peer=sqlite3.connect(store.path,timeout=0)
    try:
        with store.acquire_local_cooldown_fence() as lease:
            with pytest.raises(sqlite3.OperationalError,match='locked'):peer.execute('BEGIN IMMEDIATE')
            assert lease.validate()
        peer.execute('BEGIN IMMEDIATE')
        with pytest.raises(sqlite3.OperationalError,match='locked'):store.acquire_local_cooldown_fence()
        assert not store._local_cooldown.raw.in_transaction
    finally:peer.rollback();peer.close()


def test_wrong_thread_and_connection_replacement_are_unavailable(store):
    outcomes=[]
    def call():
        try:store.acquire_local_cooldown_fence()
        except RuntimeError as exc:outcomes.append(str(exc))
    worker=threading.Thread(target=call);worker.start();worker.join(timeout=2)
    assert not worker.is_alive() and outcomes
    with pytest.raises(RuntimeError,match='CONNECTION_REPLACEMENT'):store.connection=object()
    assert store.local_cooldown_state()['uncertain']


def test_fenced_materialization_cannot_invoke_process_global_parameter_adapter(store):
    before=dict(sqlite3.adapters);calls=[]
    def unexpected(value):
        calls.append(value)
        raise AssertionError('Custom binding callback entered fenced materialization')
    try:
        sqlite3.register_adapter(str,unexpected)
        with store.acquire_local_cooldown_fence() as lease:
            assert lease.read_committed_accounting()['events']==()
            assert lease.validate()
        assert calls==[]
    finally:
        sqlite3.adapters.clear();sqlite3.adapters.update(before)


@pytest.mark.parametrize('known_run',[False,True])
def test_only_fenced_native_progress_is_enriched_with_real_run_provenance(store,known_run):
    if known_run:
        store.insert_run(dict(run_id='NATIVE-RUN',run_mode='PAPER',effective_run_mode='PAPER',event_replay_mode='CYCLE'))
    store.store_execution_order_state('execution.native_orders.v1:PAPER',
        dict(version=1,mode='PAPER',orders={}),expected=None,run_id='NATIVE-RUN' if known_run else None)
    with store.acquire_local_cooldown_fence() as lease:
        row=lease.read_committed_accounting()['native_states'][0]
        assert row['run_metadata_present']==int(known_run)
        assert row['effective_run_mode']==('PAPER' if known_run else None)
    ordinary=store.fetch_committed_lifecycle_accounting(run_mode='PAPER')['native_states'][0]
    assert set(ordinary)=={'transition_id','reason'}


@pytest.mark.parametrize('fault',['mode','environment','actual_config'])
def test_explicit_enrollment_is_test_paper_only_before_open(tmp_path,monkeypatch,fault):
    previous=dict(config_resolver._CONFIG_OVERRIDES)
    monkeypatch.setenv('EXECUTION_ENV','PAPER' if fault=='environment' else 'TEST')
    config_resolver.set_config_overrides(dict(previous,RUN_MODE='READ_ONLY' if fault=='actual_config' else 'PAPER',
        RUN_MODE_EFFECTIVE='READ_ONLY' if fault=='actual_config' else 'PAPER'))
    path=tmp_path/'not-created.sqlite3'
    try:
        with pytest.raises(RuntimeError,match='TEST_PAPER_ENROLLMENT'):
            SQLiteStore(str(path),local_cooldown_mode='LIVE' if fault=='mode' else 'PAPER')
        assert not path.exists()
    finally:config_resolver.set_config_overrides(previous or None)


def test_plain_backup_source_cannot_access_opaque_destination(store):
    source=sqlite3.connect(':memory:')
    try:
        source.execute('CREATE TABLE source_only(value)')
        with store.acquire_local_cooldown_fence() as lease:
            with pytest.raises(TypeError):source.backup(store.connection,pages=1,sleep=0)
            assert lease.validate() and lease.read_committed_accounting()['events']==()
    finally:source.close()


@pytest.mark.parametrize('phase',['before_acquire','during_lease'])
def test_enrollment_configuration_change_cannot_keep_an_old_fence(store,phase):
    lease=store.acquire_local_cooldown_fence() if phase=='during_lease' else None
    config_resolver.set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES,
        RUN_MODE='READ_ONLY',RUN_MODE_EFFECTIVE='READ_ONLY'))
    if lease is None:
        with pytest.raises(RuntimeError,match='ENROLLMENT_CHANGED'):store.acquire_local_cooldown_fence()
    else:
        assert not lease.validate()
        lease.close()
