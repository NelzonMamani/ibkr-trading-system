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


def _fee_execution(client, *, exec_id='fee.1', order_id=71, side='BOT', currency='USD', **changes):
    from ibapi.contract import Contract
    from ibapi.execution import Execution
    contract = Contract()
    for key, value in vars(_native_contract(currency=currency)).items():
        setattr(contract, key, value)
    execution = Execution()
    for key, value in vars(_native_execution(execId=exec_id, orderId=order_id, side=side, **changes)).items():
        setattr(execution, key, value)
    client.execDetails(-1, contract, execution)
    return contract, execution


def _fee_report(client, *, exec_id='fee.1', amount=.01, currency='USD'):
    from ibapi.commission_report import CommissionReport
    report = CommissionReport()
    report.execId, report.commission, report.currency = exec_id, amount, currency
    client.commissionReport(report)
    return report


@pytest.mark.parametrize('side', ['BOT', 'SLD'])
def test_native_fee_source_observes_actual_execution_currency_without_net_enrollment(native_execution_client, side):
    from decimal import Decimal
    client = native_execution_client
    contract, execution = _fee_execution(client, side=side)
    financial_before = client.cached_native_executions(71)
    report = _fee_report(client)
    observation, = client.cached_native_execution_fees(71)
    assert observation['report_status'] == 'BOUND_API_REPORT'
    assert observation['net_status'] == 'UNAVAILABLE_FOR_NET'
    assert observation['execution']['execId'] == 'fee.1'
    assert observation['execution']['side'] == side
    assert observation['execution']['account'] == 'SYNTHETIC_TEST'
    assert observation['execution']['clientId'] == 999
    assert observation['execution']['connection_epoch'] == client._position_connection_epoch
    assert observation['execution']['conId'] == 123 and observation['execution']['symbol'] == 'JPM'
    assert observation['execution_currency'] == observation['report_currency'] == 'USD'
    assert observation['amount'] == Decimal('.01')
    assert observation['first_report']['received_at'].tzinfo is not None
    assert observation['source'] == 'IBKR_COMMISSION_REPORT'
    assert observation['report_count'] == 1 and not observation['conflict']
    assert client.cached_native_executions(71) == financial_before
    assert 'currency' not in financial_before[0]  # Existing financial contract unchanged.
    assert client.commission_for_order(71) == .01
    contract.currency = 'EUR'
    execution.acctNumber = 'OTHER'
    report.currency, report.commission = 'GBP', 1000
    assert client.cached_native_execution_fees(71) == (observation,)
    with pytest.raises(TypeError):
        observation['amount'] = Decimal('100')
    with pytest.raises(TypeError):
        observation['first_report']['currency'] = 'GBP'
    with pytest.raises(TypeError):
        observation['execution']['account'] = 'OTHER'


@pytest.mark.parametrize('amount,reason', [
    (None, 'COMMISSION_AMOUNT_UNAVAILABLE'), (True, 'COMMISSION_AMOUNT_UNAVAILABLE'),
    ('0.01', 'COMMISSION_AMOUNT_UNAVAILABLE'), (float('nan'), 'NONFINITE_COMMISSION'),
    (float('inf'), 'NONFINITE_COMMISSION'), (-float('inf'), 'NONFINITE_COMMISSION'),
    (0., 'ZERO_COMMISSION_WIRE_PRESENCE_UNAVAILABLE'), (-0., 'ZERO_COMMISSION_WIRE_PRESENCE_UNAVAILABLE'),
    (-.01, 'NEGATIVE_COMMISSION_POLICY_UNADOPTED'),
])
def test_native_fee_source_never_defaults_unsupported_amount_to_usable_zero(native_execution_client, amount, reason):
    client = native_execution_client
    _fee_execution(client)
    _fee_report(client, amount=amount)
    observation, = client.cached_native_execution_fees(71)
    assert observation['report_status'] == 'UNAVAILABLE' and observation['amount'] is None
    assert reason in observation['unavailable_reasons']
    assert observation['net_status'] == 'UNAVAILABLE_FOR_NET'
    # The supported legacy projection keeps its original numeric conventions.
    legacy = client.commission_for_order(71)
    if amount is None:
        assert legacy is None
    elif isinstance(amount, float) and amount != amount:
        assert legacy != legacy
    else:
        assert legacy == round(float(amount), 2)


def test_native_fee_source_rejects_exact_finite_sdk_unset_amount(native_execution_client):
    import math
    from ibapi.common import UNSET_DOUBLE
    client = native_execution_client
    _fee_execution(client)
    assert math.isfinite(UNSET_DOUBLE)
    _fee_report(client, amount=UNSET_DOUBLE)
    observation, = client.cached_native_execution_fees(71)
    assert observation['report_status'] == 'UNAVAILABLE'
    assert 'SDK_UNSET_COMMISSION' in observation['unavailable_reasons']
    assert observation['amount'] is None and observation['net_status'] == 'UNAVAILABLE_FOR_NET'
    assert client.commission_for_order(71) == UNSET_DOUBLE


@pytest.mark.parametrize('fee_currency', ['', 'BASE', None, 'usd', ' USD', 'USD ', 'US', 'USDT', 'EUR'])
def test_native_fee_source_retains_currency_without_default_or_conversion(native_execution_client, fee_currency):
    client = native_execution_client
    _fee_execution(client)
    _fee_report(client, currency=fee_currency)
    observation, = client.cached_native_execution_fees(71)
    reason = 'COMMISSION_CURRENCY_MISMATCH' if fee_currency == 'EUR' else 'COMMISSION_CURRENCY_UNAVAILABLE'
    assert reason in observation['unavailable_reasons']
    assert observation['amount'] is None and observation['net_status'] == 'UNAVAILABLE_FOR_NET'
    assert observation['report_currency'] == fee_currency
    assert observation['execution_currency'] == 'USD'
    assert client.commission_for_order(71) == .01


@pytest.mark.parametrize('instrument_currency', ['', 'BASE', None, 'usd', 'CAD'])
def test_native_fee_source_requires_observed_matching_execution_currency(native_execution_client, instrument_currency):
    client = native_execution_client
    _fee_execution(client, currency=instrument_currency)
    before = client.cached_native_executions(71)
    _fee_report(client)
    observation, = client.cached_native_execution_fees(71)
    reason = 'COMMISSION_CURRENCY_MISMATCH' if instrument_currency == 'CAD' else 'EXECUTION_CURRENCY_UNAVAILABLE'
    assert reason in observation['unavailable_reasons']
    assert observation['amount'] is None and observation['net_status'] == 'UNAVAILABLE_FOR_NET'
    assert client.cached_native_executions(71) == before


def test_native_fee_source_conflicting_currency_does_not_change_financial_dedupe(native_execution_client):
    client = native_execution_client
    _fee_execution(client)
    before = client.cached_native_executions(71)
    _fee_execution(client, currency='EUR')  # Exact financial duplicate, contradictory new metadata.
    _fee_report(client)
    assert client.cached_native_executions(71) == before
    observation, = client.cached_native_execution_fees(71)
    assert 'EXECUTION_CURRENCY_CONFLICT' in observation['unavailable_reasons']
    assert observation['net_status'] == 'UNAVAILABLE_FOR_NET'
    assert client.commission_for_order(71) == .02  # Existing legacy duplicate-row sum preserved.


def test_native_fee_source_pending_report_waits_for_actual_native_execution(native_execution_client):
    client = native_execution_client
    _fee_report(client)
    assert client.cached_native_execution_fees(71) == () and client.commission_for_order(71) is None
    _fee_execution(client)
    observation, = client.cached_native_execution_fees(71)
    assert observation['report_status'] == 'BOUND_API_REPORT' and observation['report_count'] == 1
    assert observation['execution']['account'] == 'SYNTHETIC_TEST'
    assert observation['execution']['side'] == 'BOT'
    assert observation['net_status'] == 'UNAVAILABLE_FOR_NET'


def test_native_fee_source_missing_report_is_not_a_zero_fee(native_execution_client):
    client = native_execution_client
    _fee_execution(client)
    observation, = client.cached_native_execution_fees(71)
    assert observation['report_status'] == 'UNAVAILABLE'
    assert observation['reason'] == 'MISSING_COMMISSION_REPORT'
    assert observation['amount'] is observation['first_report'] is None
    assert observation['report_count'] == 0 and client.commission_for_order(71) is None


def test_native_fee_source_mixed_reports_do_not_certify_a_complete_order(native_execution_client):
    from decimal import Decimal
    client = native_execution_client
    _fee_execution(client)
    _fee_execution(client, exec_id='fee.2', cumQty=Decimal('2'))
    _fee_report(client)
    observations = client.cached_native_execution_fees(71)
    assert len(observations) == 2
    assert [row['report_status'] for row in observations] == ['BOUND_API_REPORT', 'UNAVAILABLE']
    assert observations[1]['reason'] == 'MISSING_COMMISSION_REPORT'
    assert all(row['net_status'] == 'UNAVAILABLE_FOR_NET' for row in observations)
    assert client.commission_for_order(71) == .01  # ANY found is the retained legacy behavior.


@pytest.mark.parametrize('changed', ['amount', 'currency', 'scope'])
def test_native_fee_source_conflicts_latch_while_legacy_latest_value_is_preserved(native_execution_client, changed):
    client = native_execution_client
    _fee_execution(client)
    _fee_report(client)
    before, = client.cached_native_execution_fees(71)
    if changed == 'scope':
        client._position_connection_epoch += 1
    _fee_report(client, amount=.02 if changed == 'amount' else .01,
        currency='EUR' if changed == 'currency' else 'USD')
    observation, = client.cached_native_execution_fees(71)
    assert observation['conflict'] and observation['report_count'] == 2
    assert 'COMMISSION_REPORT_CONFLICT' in observation['unavailable_reasons']
    assert observation['first_report'] == before['first_report']
    assert client.commission_for_order(71) == (.02 if changed == 'amount' else .01)
    _fee_report(client)  # Matching original fields cannot clear a prior conflict.
    repeated, = client.cached_native_execution_fees(71)
    assert repeated['conflict'] and repeated['report_count'] == 3
    assert repeated['net_status'] == 'UNAVAILABLE_FOR_NET' and repeated['amount'] is None


def test_native_fee_source_repeated_same_payload_does_not_renew_first_receipt_or_conflict(native_execution_client, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from src.adapters.brokers.ibkr import ibkr_client as native_module
    clock = NS(now=datetime(2026, 11, 11, 17, 0, tzinfo=timezone.utc))
    class ReceiptClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.now if tz is None else clock.now.astimezone(tz)
    monkeypatch.setattr(native_module, 'datetime', ReceiptClock)
    client = native_execution_client
    _fee_execution(client)
    _fee_report(client)
    first, = client.cached_native_execution_fees(71)
    clock.now += timedelta(seconds=20)
    _fee_report(client)
    repeated, = client.cached_native_execution_fees(71)
    assert repeated['report_status'] == 'BOUND_API_REPORT' and not repeated['conflict']
    assert repeated['report_count'] == 2 and repeated['first_report'] == first['first_report']
    assert repeated['latest_report']['received_at'] > first['first_report']['received_at']
    assert repeated['first_report']['received_at'] != repeated['execution']['timestamp_utc']


def test_native_fee_source_freezes_primitives_before_sdk_listener_can_mutate(native_execution_client):
    client = native_execution_client
    _fee_execution(client)
    def listener(payload):
        report = payload.get('commissionReport')
        if report is not None:
            report.commission, report.currency = 5000, 'EUR'
    client.register_reconciliation_callback(listener)
    report = _fee_report(client)
    assert report.commission == 5000 and report.currency == 'EUR'
    observation, = client.cached_native_execution_fees(71)
    assert observation['report_status'] == 'BOUND_API_REPORT'
    assert observation['first_report']['currency'] == 'USD'
    assert client.commission_for_order(71) == .01


@pytest.mark.parametrize('fault', ['execution_other_client', 'execution_other_account', 'current_client',
    'current_epoch', 'stopped', 'disconnected', 'account_scope', 'reception_disconnected', 'report_old_epoch'])
def test_native_fee_source_current_and_reception_scope_cannot_be_upgraded(native_execution_client, monkeypatch, fault):
    client = native_execution_client
    if fault == 'report_old_epoch':
        _fee_report(client)
        client._invalidate_position_queries()
        client.nextValidId(72)
        client.managedAccounts('SYNTHETIC_TEST')
        _fee_execution(client)
    else:
        _fee_execution(client, **({'clientId': 123} if fault == 'execution_other_client'
            else {'acctNumber': 'OTHER'} if fault == 'execution_other_account' else {}))
        if fault == 'reception_disconnected':
            monkeypatch.setattr(client, 'isConnected', lambda: False)
        _fee_report(client)
        if fault == 'reception_disconnected':
            monkeypatch.setattr(client, 'isConnected', lambda: True)
        elif fault == 'current_client':
            client.client_id = 123
        elif fault == 'current_epoch':
            client._invalidate_position_queries()
        elif fault == 'stopped':
            client._stop_event.set()
        elif fault == 'disconnected':
            monkeypatch.setattr(client, 'isConnected', lambda: False)
        elif fault == 'account_scope':
            client.managedAccounts('OTHER')
    observation, = client.cached_native_execution_fees(71)
    assert observation['report_status'] == 'UNAVAILABLE' and observation['amount'] is None
    assert any('SCOPE' in reason or 'EPOCH' in reason or 'CONNECTION' in reason
        for reason in observation['unavailable_reasons'])
    assert observation['net_status'] == 'UNAVAILABLE_FOR_NET'
    assert client.commission_for_order(71) == .01


def test_native_fee_source_legacy_history_and_unowned_callbacks_cannot_supply_execution_binding(native_execution_client):
    client = native_execution_client
    req_id = client._next_req_id()
    client._register_request(req_id, 'EXECUTIONS')
    client.execDetails(req_id, _native_contract(currency='USD'), _native_execution(execId='fee.1'))
    client.execDetailsEnd(req_id)
    _fee_report(client)
    assert client.cached_native_executions(71) == ()
    assert client.cached_native_execution_fees(71) == ()
    assert client.commission_for_order(71) == .01  # Historical legacy sum is not native authority.
    client.execDetails(999999, _native_contract(currency='USD'), _native_execution(execId='unowned'))
    _fee_report(client, exec_id='unowned')
    assert client.cached_native_execution_fees(71) == ()


def test_native_fee_source_legacy_float_seed_remains_unscoped_even_after_report(native_execution_client):
    client = native_execution_client
    _fee_execution(client)
    client._commission_by_exec_id['fee.1'] = .01  # Old private cache format, no source witness.
    observation, = client.cached_native_execution_fees(71)
    assert observation['reason'] == 'LEGACY_COMMISSION_UNSCOPED' and observation['first_report'] is None
    assert client.commission_for_order(71) == .01
    _fee_report(client)
    refreshed, = client.cached_native_execution_fees(71)
    assert refreshed['report_status'] == 'UNAVAILABLE'
    assert 'LEGACY_COMMISSION_UNSCOPED' in refreshed['unavailable_reasons']
    assert client.commission_for_order(71) == .01


def test_native_fee_source_invalid_callback_preserves_legacy_numeric_projection(native_execution_client):
    client = native_execution_client
    _fee_execution(client)
    _fee_report(client)
    with pytest.raises(ValueError):
        _fee_report(client, amount='not-numeric')
    observation, = client.cached_native_execution_fees(71)
    assert observation['report_status'] == 'UNAVAILABLE' and observation['conflict']
    assert observation['latest_report']['amount'] is None
    assert client.commission_for_order(71) == .01


def test_native_fee_source_missing_amount_does_not_replace_prior_legacy_amount(native_execution_client):
    client = native_execution_client
    _fee_execution(client)
    _fee_report(client)
    _fee_report(client, amount=None)
    observation, = client.cached_native_execution_fees(71)
    assert observation['report_status'] == 'UNAVAILABLE' and observation['conflict']
    assert observation['latest_report']['amount'] is None
    assert client.commission_for_order(71) == .01


def test_native_fee_source_does_not_rebase_a_callback_across_epoch_before_execution_binding(native_execution_client, monkeypatch):
    from src.adapters.brokers.ibkr import ibkr_client as native_module
    client = native_execution_client
    received_epoch = client._position_connection_epoch
    original_print = print
    crossed = []
    def diagnostic_boundary(*args, **kwargs):
        if args and 'event=commissionReport' in str(args[0]):
            monkeypatch.setattr(native_module, 'print', original_print)
            crossed.append(received_epoch)
            # Real existing source callbacks model another owner interleaving
            # after this old report entered, before its processing continues.
            client.connectionClosed()
            client.error(-1, 1101, 'synthetic restored upstream scope')
            client.managedAccounts('SYNTHETIC_TEST')
            client.nextValidId(72)
        original_print(*args, **kwargs)
    monkeypatch.setattr(native_module, 'print', diagnostic_boundary, raising=False)
    _fee_report(client)  # Before any native execution is available to bind it.
    assert crossed == [received_epoch] and client._position_connection_epoch > received_epoch
    _fee_execution(client)
    observation, = client.cached_native_execution_fees(71)
    assert observation['execution']['connection_epoch'] == client._position_connection_epoch
    assert observation['first_report']['connection_epoch'] == received_epoch
    assert observation['report_status'] == 'UNAVAILABLE' and observation['amount'] is None
    assert 'COMMISSION_REPORT_SCOPE_UNAVAILABLE' in observation['unavailable_reasons']
    assert client.commission_for_order(71) == .01
