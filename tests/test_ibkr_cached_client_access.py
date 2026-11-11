"""Read cached callback facts through the real, non-connecting manager API."""
from types import SimpleNamespace as NS

import pytest
from ibapi.client import EClient

from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.adapters.brokers.ibkr.ibkr_connection_manager import IbkrConnectionConfig, IbkrConnectionManager
from src.config.runtime_config import RunMode
from src.core.active_trade_registry import ActiveTradeRegistry
from src.execution.execution_providers import IbkrExecutionProvider
from src.ibkr.mutation_audit import snapshot as mutations
from test_standalone_pmh_late_fill_protection import forbid_io, no_external_activity, _reset_config


@pytest.mark.parametrize('mode',[RunMode.PAPER,RunMode.READ_ONLY,RunMode.LIVE])
@pytest.mark.parametrize('availability',['present','absent','disconnected'])
def test_cached_read_uses_only_existing_connected_client(monkeypatch,tmp_path,no_external_activity,mode,availability):
    monkeypatch.setenv('IBKR_ORDER_ID_STATE_PATH',str(tmp_path/'synthetic-order-state.json'))
    manager=IbkrConnectionManager(IbkrConnectionConfig('offline',0,999,5,'LIVE',True,mode.value))
    client=IbkrClient('offline',0,999,5,'LIVE',True)
    connected=[availability!='disconnected']
    # Synthetic external connectivity and native callback. Accessor, cache,
    # provider and connection-state owners are not replaced.
    monkeypatch.setattr(client,'isConnected',lambda:connected[0])
    client.orderStatus(71,'Filled',1,0,10.31,0,0,10.31,999,'',0.)
    manager._client=None if availability=='absent' else client
    for name in ('connect','ensure_connected','get_client','_connect_locked'):
        monkeypatch.setattr(manager,name,lambda *a,**kw:pytest.fail('Cache read may not acquire/reconnect'))
    reads=[];read=client.cached_order_status
    def observed(order_id):
        reads.append(order_id)
        return read(order_id)
    monkeypatch.setattr(client,'cached_order_status',observed)
    provider=IbkrExecutionProvider(broker=NS(connection_manager=manager),trade_registry=ActiveTradeRegistry(),run_mode=mode)
    result=provider.cached_order_update('71')
    if availability=='present':
        assert result['filled']==1 and result['avgFillPrice']==10.31
        assert reads==[71] and provider.cached_order_update('999')=={}
        result['filled']=999  # Returned projection cannot mutate callback facts.
        assert provider.cached_order_update('71')['filled']==1
        with pytest.raises(ValueError):provider.cached_order_update('malformed-id')
    else:
        assert result=={} and reads==[]  # Never expose even retained fill facts offline.
    assert manager.existing_client is (None if availability=='absent' else client)
    assert no_external_activity==[] and mutations()==dict(place=0,modify=0,cancel=0)


def test_order_status_preserves_fractional_callback_quantity(monkeypatch,tmp_path,no_external_activity):
    monkeypatch.setenv('IBKR_ORDER_ID_STATE_PATH',str(tmp_path/'fractional-order-state.json'))
    client=IbkrClient('offline',0,999,5,'LIVE',True)
    client.orderStatus(71,'Submitted',1.5,.5,10.31,0,0,10.31,999,'',0.)
    cached=client.cached_order_status(71)
    assert cached['filled']==1.5 and cached['remaining']==.5
    assert no_external_activity==[] and mutations()==dict(place=0,modify=0,cancel=0)


@pytest.fixture
def native_execution_client(monkeypatch,tmp_path,no_external_activity):
    monkeypatch.setenv('IBKR_ORDER_ID_STATE_PATH',str(tmp_path/'native-execution-state.json'))
    for name in ('connect','reqExecutions','placeOrder','cancelOrder','reqGlobalCancel'):
        monkeypatch.setattr(EClient,name,lambda *a,**k:pytest.fail('Passive execution facts must not dispatch'))
    client=IbkrClient('offline',0,999,5,'LIVE',True)
    monkeypatch.setattr(client,'isConnected',lambda:True)
    client.nextValidId(71)
    client.managedAccounts('SYNTHETIC_TEST')
    yield client
    assert no_external_activity==[] and mutations()==dict(place=0,modify=0,cancel=0)


def _native_execution(**changes):
    from decimal import Decimal
    values=dict(execId='synthetic.execution.1',time='20261111 09:35:05 UTC',
        orderId=71,acctNumber='SYNTHETIC_TEST',clientId=999,side='BOT',
        shares=Decimal('1'),price=10.53,cumQty=Decimal('1'),avgPrice=10.53)
    values.update(changes)
    return NS(**values)


def _native_contract(**changes):
    values=dict(symbol='JPM',conId=123,secType='STK')
    values.update(changes)
    return NS(**values)


def test_native_execution_cache_is_passive_immutable_callback_evidence(native_execution_client):
    from datetime import datetime,timezone
    from decimal import Decimal
    client=native_execution_client
    execution=_native_execution();contract=_native_contract()
    client.execDetails(-1,contract,execution)
    rows=client.cached_native_executions(71)
    assert len(rows)==1 and rows[0]['execId']==execution.execId
    assert rows[0]['account']=='SYNTHETIC_TEST' and rows[0]['clientId']==999
    assert rows[0]['orderId']==71 and rows[0]['conId']==123
    assert rows[0]['symbol']=='JPM' and rows[0]['secType']=='STK' and rows[0]['side']=='BOT'
    assert rows[0]['shares']==rows[0]['cumQty']==Decimal('1')
    assert rows[0]['price']==rows[0]['avgPrice']==Decimal('10.53')
    assert rows[0]['connection_epoch']==client._position_connection_epoch
    assert rows[0]['time']=='20261111 09:35:05 UTC'
    assert rows[0]['timestamp_utc']==datetime(2026,11,11,9,35,5,tzinfo=timezone.utc)
    with pytest.raises(TypeError):rows[0]['price']=999
    execution.price=999;execution.time='bad';contract.symbol='OTHER'
    assert dict(client.cached_native_executions(71)[0])==dict(rows[0])
    assert client.cached_native_executions(999)==()


def test_native_execution_cache_history_queries_cannot_supply_or_clear_live_facts(native_execution_client,monkeypatch):
    client=native_execution_client
    live=_native_execution();client.execDetails(-1,_native_contract(),live)
    before=client.cached_native_executions(71)
    def history(req_id,native_filter):
        client.execDetails(req_id,_native_contract(),_native_execution(execId='legacy.history',price=11.))
        client.execDetailsEnd(req_id)
    monkeypatch.setattr(client,'reqExecutions',history)  # Synthetic external send only.
    assert client.executions(timeout_seconds=1)
    assert client.cached_native_executions(71)==before
    client.execDetails(987654,_native_contract(),_native_execution(execId='unowned.history'))
    assert client.cached_native_executions(71)==before
    # Existing history request owns a separate order; still no native authority.
    def other(req_id,native_filter):
        client.execDetails(req_id,_native_contract(),_native_execution(orderId=72,execId='legacy.other'))
        client.execDetailsEnd(req_id)
    monkeypatch.setattr(client,'reqExecutions',other)
    client.executions(timeout_seconds=1)
    assert client.cached_native_executions(72)==()


def test_native_execution_cache_dedupes_and_orders_real_execution_rows(native_execution_client):
    from decimal import Decimal
    client=native_execution_client
    first=_native_execution()
    second=_native_execution(execId='synthetic.execution.2',time='20261111 09:35:06 UTC',
        price=10.55,cumQty=Decimal('2'),avgPrice=10.54)
    client.execDetails(-1,_native_contract(),second)
    client.execDetails(-1,_native_contract(),first)
    client.execDetails(-1,_native_contract(),first)
    rows=client.cached_native_executions(71)
    assert [row['execId'] for row in rows]==[first.execId,second.execId]
    assert [row['cumQty'] for row in rows]==[Decimal('1'),Decimal('2')]
    assert rows[1]['timestamp_utc']>rows[0]['timestamp_utc']


@pytest.mark.parametrize('changes',[{'price':10.54},{'time':'20261111 09:35:06 UTC'},
    {'acctNumber':'OTHER_ACCOUNT'},{'clientId':998},{'orderId':72}])
def test_native_execution_cache_conflicting_duplicates_remain_unavailable(native_execution_client,changes):
    client=native_execution_client
    client.execDetails(-1,_native_contract(),_native_execution())
    client.execDetails(-1,_native_contract(),_native_execution(**changes))
    with pytest.raises(ValueError,match='NATIVE_EXECUTION_DUPLICATE_CONFLICT'):
        client.cached_native_executions(71)
    # No last-writer-wins repair of the conflicted evidence.
    client.execDetails(-1,_native_contract(),_native_execution())
    with pytest.raises(ValueError,match='NATIVE_EXECUTION_DUPLICATE_CONFLICT'):
        client.cached_native_executions(71)


@pytest.mark.parametrize('changes,contract_changes',[
    ({'execId':''},{}),({'time':None},{}),({'shares':True},{}),({'shares':float('nan')},{}),
    ({'price':float('inf')},{}),({'cumQty':.5},{}),({'acctNumber':''},{}),
    ({'clientId':True},{}),({'side':'BUY'},{}),({}, {'conId':0}),({}, {'secType':'OPT'})])
def test_native_execution_cache_rejects_malformed_facts(native_execution_client,changes,contract_changes):
    client=native_execution_client
    client.execDetails(-1,_native_contract(**contract_changes),_native_execution(**changes))
    with pytest.raises(ValueError,match='NATIVE_EXECUTION'):
        client.cached_native_executions(71)


@pytest.mark.parametrize('raw,expected',[
    ('2026-11-11T09:35:05Z','2026-11-11T09:35:05+00:00'),
    ('2026-11-11T04:35:05-05:00','2026-11-11T09:35:05+00:00'),
    ('20261111  09:35:05 UTC','2026-11-11T09:35:05+00:00'),
    ('20261111 04:35:05 US/Eastern','2026-11-11T09:35:05+00:00'),
    ('20260711 05:35:05 America/New_York','2026-07-11T09:35:05+00:00'),
    ('2026-11-11 09:35:05 GMT','2026-11-11T09:35:05+00:00')])
def test_native_execution_time_requires_explicit_instant(raw,expected):
    assert IbkrClient.normalize_native_execution_time(raw).isoformat()==expected


@pytest.mark.parametrize('raw',[None,'','2026-11-11','2026-11-11T09:35:05',
    '20261111 09:35:05','20261111 09:35:05 UNKNOWN','20261111 09:35:05 EST',
    '20261111 09:35:05 Missing/Zone','20261101 01:30:00 America/New_York',
    '20260308 02:30:00 America/New_York',True,12345])
def test_native_execution_time_never_invents_timezone_or_receipt(raw):
    with pytest.raises(ValueError,match='NATIVE_EXECUTION_TIME_UNAVAILABLE'):
        IbkrClient.normalize_native_execution_time(raw)


@pytest.mark.parametrize('filled,remaining',[(True,0),(float('nan'),0),(float('inf'),0),(1,.5)])
def test_order_status_preserves_invalid_quantity_for_native_validation(native_execution_client,filled,remaining,monkeypatch):
    import math
    client=native_execution_client
    emitted=[];monkeypatch.setattr(client,'_emit_execution_callback',emitted.append)
    client.orderStatus(71,'Submitted',filled,remaining,10.53,0,0,10.53,999,'',0.)
    cached=client.cached_order_status(71)
    if isinstance(filled,float) and math.isnan(filled):
        assert math.isnan(cached['filled']) and math.isnan(emitted[0]['filled'])
    else:
        assert cached['filled'] is filled and emitted[0]['filled'] is filled
    assert cached['remaining']==remaining and emitted[0]['remaining']==remaining


def test_native_execution_cache_does_not_rebase_callback_epoch(native_execution_client,monkeypatch):
    client=native_execution_client
    epoch=client._position_connection_epoch
    observe=client._observe_order_id
    def disconnect_after_identity(order_id):
        observe(order_id)
        client.error(-1,1100,'synthetic upstream connection loss')
    monkeypatch.setattr(client,'_observe_order_id',disconnect_after_identity)
    client.execDetails(-1,_native_contract(),_native_execution())
    assert client._position_connection_epoch>epoch
    # These are retained inspection facts, not permission in the new epoch.
    assert client.cached_native_executions(71)[0]['connection_epoch']==epoch


def test_native_execution_time_accepts_aware_datetime_only():
    from datetime import datetime,timedelta,timezone
    stamp=datetime(2026,11,11,4,35,5,tzinfo=timezone(timedelta(hours=-5)))
    assert IbkrClient.normalize_native_execution_time(stamp)==stamp.astimezone(timezone.utc)
    with pytest.raises(ValueError,match='NATIVE_EXECUTION_TIME_UNAVAILABLE'):
        IbkrClient.normalize_native_execution_time(stamp.replace(tzinfo=None))


@pytest.mark.parametrize('raw',['0001-01-01T00:00:00+14:00','99991231 23:59:59 America/New_York'])
def test_native_execution_time_overflow_is_unavailable(raw):
    with pytest.raises(ValueError,match='NATIVE_EXECUTION_TIME_UNAVAILABLE'):
        IbkrClient.normalize_native_execution_time(raw)


def test_native_execution_cache_rejects_request_order_identity_conflict(native_execution_client):
    client=native_execution_client
    req_id=client._next_req_id()
    client._register_request(req_id,'HISTORICAL')
    client.execDetails(-1,_native_contract(),_native_execution(orderId=req_id))
    with pytest.raises(ValueError,match='NATIVE_EXECUTION_IDENTITY_CONFLICT'):
        client.cached_native_executions(req_id)
