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
from test_key_level_break_production_handoff import forbid_io
from test_broker_registry_exposure_admission import no_external_activity
from test_pr1082_rth_watchlist_continuity import _reset_config


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


@pytest.mark.parametrize('scope_alias', ['epoch_bool', 'client_bool', 'connected_integer'])
def test_native_fee_source_invalid_later_scope_type_latches_conflict_after_current_scope_restored(
        native_execution_client, monkeypatch, scope_alias):
    client = native_execution_client
    # Use the exact small identity values that alias Python bools numerically.
    client.client_id = 1
    _fee_execution(client, clientId=1)
    _fee_report(client)
    first, = client.cached_native_execution_fees(71)
    assert first['report_status'] == 'BOUND_API_REPORT' and not first['conflict']
    if scope_alias == 'epoch_bool':
        assert client._position_connection_epoch == 0
        client._position_connection_epoch = False
    elif scope_alias == 'client_bool':
        client.client_id = True
    else:
        monkeypatch.setattr(client, 'isConnected', lambda: 1)
    _fee_report(client)  # Same payload, invalid type in this receipt's scope.
    client.client_id = 1
    client._position_connection_epoch = 0
    monkeypatch.setattr(client, 'isConnected', lambda: True)
    observation, = client.cached_native_execution_fees(71)
    assert observation['conflict'], 'A malformed later receipt must not alias the first valid scope'
    assert observation['report_status'] == 'UNAVAILABLE' and observation['amount'] is None
    assert 'COMMISSION_REPORT_CONFLICT' in observation['unavailable_reasons']
    assert observation['first_report'] == first['first_report']
    assert observation['net_status'] == 'UNAVAILABLE_FOR_NET'
    assert client.commission_for_order(71) == .01
    _fee_report(client)  # Restoring scope and repeating cannot clear uncertainty.
    repeated, = client.cached_native_execution_fees(71)
    assert repeated['conflict'] and repeated['report_count'] == 3
    assert repeated['first_report'] == first['first_report']
    assert repeated['amount'] is None and repeated['net_status'] == 'UNAVAILABLE_FOR_NET'


# Capture the real native owner at collection, before function-scoped transport
# tripwires. Only the external SDK connection/MemorySocket boundary is synthetic.
_NATIVE_SOURCE_CONNECT = IbkrClient.connect
_NATIVE_SDK_CONNECT = EClient.connect


def native_commission_decoder_source(client, monkeypatch, *, account='SYNTHETIC_TEST',
                                     constructor_frames=(), clock=None):
    import queue
    import socket
    import threading
    from ibapi import comm
    from ibapi.connection import Connection
    from ibapi.decoder import Decoder
    from ibapi.reader import EReader
    from src.adapters.brokers.ibkr import ibkr_client as native_module
    if clock is not None:
        monkeypatch.setattr(native_module, 'datetime', clock)
    if not client.port:
        client.port = 1  # Explicit memory-only endpoint; no socket connect occurs.
    packets = queue.Queue()
    progress = threading.Condition()
    state = NS(processed=0, closed=False, reader=None, decoder=None, connection=None,
        constructor_queued=threading.Event(), sent=[])
    def encoded(fields):
        return comm.make_msg(''.join(comm.make_field(value.decode('ascii') if isinstance(value, bytes) else value)
            for value in fields))
    constructor_frames = tuple(constructor_frames)
    constructor_bodies = {comm.read_msg(encoded(fields))[1] for fields in constructor_frames}
    queued = set()
    put = client.msg_queue.put
    def observed_put(value, *args, **kwargs):
        out = put(value, *args, **kwargs)
        if value in constructor_bodies:
            queued.add(value)
            if queued == constructor_bodies:
                state.constructor_queued.set()
        return out
    monkeypatch.setattr(client.msg_queue, 'put', observed_put)
    class MemorySocket:
        def recv(self, size):
            try:
                payload = packets.get(timeout=1)
            except queue.Empty:
                raise socket.timeout()
            return b'' if payload is None else payload
        def close(self):
            packets.put(None)
        def send(self, payload):
            from ibapi.message import OUT
            state.sent.append(payload)
            if payload.startswith(b'API\0'):
                return len(payload)  # Actual SDK protocol negotiation.
            size, body, rest = comm.read_msg(payload)
            assert body and not rest and size == len(body)
            message_id = int(comm.read_fields(body)[0])
            assert message_id in (OUT.START_API, OUT.REQ_MARKET_DATA_TYPE), 'Unexpected SDK/provider dispatch'
            if message_id == OUT.START_API:
                for fields in ([9, 1, 71], [15, 1, account], *constructor_frames):
                    packets.put(encoded(fields))
                if constructor_frames:
                    assert state.constructor_queued.wait(2), 'SDK reader did not queue constructor frame'
            return len(payload)
    def memory_connect(connection):
        assert connection.host == client.host and connection.port == client.port
        connection.socket = MemorySocket()
        state.connection = connection
        # The actual EClient.connect consumes this real SDK handshake frame,
        # sets clientId/connstate/version and constructs its decoder and EReader.
        packets.put(comm.make_msg('151\00020261111 18:00:00 UTC\0'))
    def loop_received():
        with progress:
            state.processed += 1
            progress.notify_all()
    initial_queue = client.msg_queue
    monkeypatch.setattr(EClient, 'connect', _NATIVE_SDK_CONNECT)
    monkeypatch.setattr(Connection, 'connect', memory_connect)
    monkeypatch.setattr(client, 'msgLoopRec', loop_received)
    def close():
        if state.closed:
            return
        state.closed = True
        # SDK reset clears reader/connection attributes. Capture every actual
        # worker even when connect failed after creating it but before return.
        reader = state.reader or client.reader
        worker = client._thread
        try:
            client.disconnect()
        finally:
            packets.put(None)
            for owned, label in ((reader, 'reader'), (worker, 'decoder worker')):
                if owned is not None:
                    if owned.ident is not None:
                        owned.join(2)
                    assert not owned.is_alive(), 'Synthetic SDK ' + label + ' leaked'
    def deliver_frame(fields):
        with progress:
            before = state.processed
            packets.put(encoded(fields))
            assert progress.wait_for(lambda: state.processed > before, timeout=2), 'SDK decoder did not finish the frame'
    def deliver_commission_frame(exec_id, amount=0, currency='USD', *, empty=False):
        deliver_frame([59, 1, exec_id, '' if empty else amount, currency, '', '', 0])
    state.deliver_frame, state.deliver_commission_frame, state.close = deliver_frame, deliver_commission_frame, close
    try:
        _NATIVE_SOURCE_CONNECT(client)
        state.reader, state.decoder = client.reader, client.decoder
        with progress:
            assert progress.wait_for(lambda: state.processed >= 2 + len(constructor_frames), timeout=2)
        assert client.wrapper is client and client.decoder is state.decoder
        assert client.reader is state.reader and client.msg_queue is initial_queue
        return state
    except BaseException:
        close()
        raise


def test_native_explicit_zero_uses_first_actual_decoder_and_constructor_queue(monkeypatch, tmp_path, no_external_activity):
    from decimal import Decimal
    monkeypatch.setenv('IBKR_ORDER_ID_STATE_PATH', str(tmp_path / 'wire-zero-order-ids.json'))
    client = IbkrClient('offline', 1, 999, 2, 'LIVE', True)
    source = native_commission_decoder_source(client, monkeypatch,
        constructor_frames=([59, 1, 'constructor.unowned', 0, 'USD', '', '', 0],))
    try:
        _fee_execution(client)
        source.deliver_commission_frame('fee.1')
        row, = client.cached_native_execution_fees(71)
        assert row['report_status'] == 'BOUND_API_REPORT' and row['amount'] == Decimal(0)
        first = row['first_report']
        assert first['commission_field_present'] is True
        assert first['commission_presence_source'] == 'IBKR_SDK_DECODER'
        assert first['commission_decoder_schema'] == 'IBAPI_9_81_1_POST1_COMMISSION_8_FIELDS'
        assert first['commission_client_object_id'] == id(client)
        assert first['commission_decoder_object_id'] == id(client.decoder)
        assert first['commission_decoder_epoch'] == client._position_connection_epoch
        assert first['commission_decoder_generation'] == 1
        assert first['commission_decoder_thread_id'] == client._thread.ident
        assert row['net_status'] == 'UNAVAILABLE_FOR_NET' and client.commission_for_order(71) == 0
    finally:
        source.close()


def test_native_zero_source_rejects_sdk_report_class_replaced_after_install(monkeypatch, tmp_path, no_external_activity):
    from ibapi import decoder as sdk_decoder
    from ibapi.commission_report import CommissionReport
    from decimal import Decimal
    monkeypatch.setenv('IBKR_ORDER_ID_STATE_PATH', str(tmp_path / 'wire-zero-class-ids.json'))
    client = IbkrClient('offline', 1, 999, 2, 'LIVE', True)
    source = native_commission_decoder_source(client, monkeypatch)
    class UnsupportedReport(CommissionReport):
        @property
        def commission(self):
            return 0.0
        @commission.setter
        def commission(self, value):
            self.projected_from = value
    try:
        _fee_execution(client)
        with monkeypatch.context() as changed:
            changed.setattr(sdk_decoder, 'CommissionReport', UnsupportedReport)
            source.deliver_commission_frame('fee.1', amount=.01)
        row, = client.cached_native_execution_fees(71)
        assert row['report_status'] == 'UNAVAILABLE' and row['amount'] is None
        assert row['first_report']['commission_field_present'] is None
        assert row['net_status'] == 'UNAVAILABLE_FOR_NET'
        # Restoring an unsupported SDK capability is not automatic rearming.
        _fee_execution(client, exec_id='fee.2', cumQty=Decimal('2'))
        source.deliver_commission_frame('fee.2')
        assert client.cached_native_execution_fees(71)[1]['report_status'] == 'UNAVAILABLE'
    finally:
        source.close()


@pytest.fixture
def native_wire_zero_source(monkeypatch, tmp_path, no_external_activity):
    monkeypatch.setenv('IBKR_ORDER_ID_STATE_PATH', str(tmp_path / 'native-wire-source-ids.json'))
    client = IbkrClient('offline', 1, 999, 2, 'LIVE', True)
    source = native_commission_decoder_source(client, monkeypatch)
    try:
        yield client, source
    finally:
        source.close()


@pytest.mark.parametrize('changed', ['epoch', 'decoder', 'client_id', 'clientId', 'reader', 'msg_queue', 'conn'])
def test_native_zero_source_observed_owner_loss_cannot_rearm(native_wire_zero_source, changed):
    client, source = native_wire_zero_source
    _fee_execution(client)
    source.deliver_commission_frame('fee.1')
    assert client.cached_native_execution_fees(71)[0]['report_status'] == 'BOUND_API_REPORT'
    # Observe loss through the real source accessor, then restore the exact
    # original objects/scope. A past unavailable owner is not a fresh enrollment.
    name = '_position_connection_epoch' if changed == 'epoch' else changed
    original = getattr(client, name)
    setattr(client, name, original + 1 if changed in ('epoch', 'client_id', 'clientId')
            else None if changed == 'conn' else NS())
    try:
        assert client.cached_native_execution_fees(71)[0]['report_status'] == 'UNAVAILABLE'
    finally:
        setattr(client, name, original)
    assert client.cached_native_execution_fees(71)[0]['report_status'] == 'UNAVAILABLE'
    source.deliver_commission_frame('fee.1')
    assert client.cached_native_execution_fees(71)[0]['report_status'] == 'UNAVAILABLE'


@pytest.mark.parametrize('first_kind,later_kind', [
    ('wire', 'wire'), ('wire', 'direct'), ('wire', 'empty'),
    ('direct', 'wire'), ('empty', 'wire'),
])
def test_native_zero_source_retains_first_authority_without_false_economic_conflict(
        native_wire_zero_source, first_kind, later_kind):
    client, source = native_wire_zero_source
    _fee_execution(client)
    def report(kind):
        if kind == 'direct':
            _fee_report(client, amount=0.)
        else:
            source.deliver_commission_frame('fee.1', empty=kind == 'empty')
    report(first_kind)
    before = client.cached_native_execution_fees(71)[0]
    report(later_kind)
    row, = client.cached_native_execution_fees(71)
    assert row['report_count'] == 2 and not row['conflict']
    assert row['first_report'] == before['first_report']
    assert row['report_status'] == ('BOUND_API_REPORT' if first_kind == 'wire' else 'UNAVAILABLE')
    assert row['net_status'] == 'UNAVAILABLE_FOR_NET' and client.commission_for_order(71) == 0
    assert row['first_report']['commission_field_present'] is (
        True if first_kind == 'wire' else False if first_kind == 'empty' else None)


def test_native_zero_source_uses_one_report_object_once_after_sdk_logging(
        monkeypatch, native_wire_zero_source):
    from ibapi import utils
    client, source = native_wire_zero_source
    for number in (1, 2, 3):
        _fee_execution(client, exec_id=f'fee.{number}', cumQty=number)
    sdk_debug = utils.logger.debug
    injected = []
    def reentrant_log(*args, **kwargs):
        if not injected and len(args) >= 3 and args[1] is float and args[2] == b'0':
            injected.append('SDK logging')
            _fee_report(client, exec_id='fee.2', amount=0.)
        return sdk_debug(*args, **kwargs)
    monkeypatch.setattr(utils.logger, 'debug', reentrant_log)
    def reentrant_listener(payload):
        if payload.get('event_type') == 'commissionReport' and payload['execId'] == 'fee.1':
            report = payload['commissionReport']
            report.execId = 'fee.3'
            client.commissionReport(report)  # Same SDK object, witness already consumed.
    client.register_reconciliation_callback(reentrant_listener)
    source.deliver_commission_frame('fee.1')
    rows = {row['execution']['execId']: row for row in client.cached_native_execution_fees(71)}
    assert injected == ['SDK logging']
    assert rows['fee.1']['report_status'] == 'BOUND_API_REPORT'
    for exec_id in ('fee.2', 'fee.3'):
        assert rows[exec_id]['report_status'] == 'UNAVAILABLE'
        assert rows[exec_id]['first_report']['commission_field_present'] is None
    # No forwarding token survives the delegated SDK handler or listener.
    assert getattr(client._commission_decoder_proxy.local, 'forward', None) is None


def test_native_zero_source_delegates_the_same_immutable_field_values(
        monkeypatch, native_wire_zero_source):
    from ibapi import utils
    client, source = native_wire_zero_source
    _fee_execution(client)
    interpret = client.decoder.interpret
    captured = []
    def mutable_interpret(fields):
        mutable = list(fields)
        captured.append(mutable)
        return interpret(mutable)
    monkeypatch.setattr(client.decoder, 'interpret', mutable_interpret)
    sdk_debug = utils.logger.debug
    parsed_commission = []
    def mutate_during_decode(*args, **kwargs):
        if len(args) >= 3 and args[1] is int and args[2] == b'1':
            captured[-1][3] = b''  # After witness snapshot; before SDK reads commission.
        if len(args) >= 3 and args[1] is float and not parsed_commission:
            parsed_commission.append(args[2])
        return sdk_debug(*args, **kwargs)
    monkeypatch.setattr(utils.logger, 'debug', mutate_during_decode)
    source.deliver_commission_frame('fee.1')
    assert captured[-1][3] == b'' and parsed_commission == [b'0']
    row, = client.cached_native_execution_fees(71)
    assert row['report_status'] == 'BOUND_API_REPORT'
    assert row['first_report']['commission_field_present'] is True


@pytest.mark.parametrize('unsupported', ['extra_field', 'distribution'])
def test_native_zero_source_unsupported_capability_never_rearms(
        monkeypatch, tmp_path, no_external_activity, unsupported):
    from src.adapters.brokers.ibkr import ibkr_client as native_module
    monkeypatch.setenv('IBKR_ORDER_ID_STATE_PATH', str(tmp_path / 'unsupported-wire-source.json'))
    client = IbkrClient('offline', 1, 999, 2, 'LIVE', True)
    with monkeypatch.context() as capability:
        if unsupported == 'distribution':
            capability.setattr(native_module, '_sdk_distribution_version', lambda _: 'unsupported')
        source = native_commission_decoder_source(client, monkeypatch)
    try:
        _fee_execution(client)
        fields = [59, 1, 'fee.1', 0, 'USD', '', '', 0]
        if unsupported == 'extra_field':
            fields.append('unsupported')
        source.deliver_frame(fields)
        assert client.cached_native_execution_fees(71)[0]['report_status'] == 'UNAVAILABLE'
        _fee_execution(client, exec_id='fee.2', cumQty=2)
        source.deliver_commission_frame('fee.2')
        assert client.cached_native_execution_fees(71)[1]['report_status'] == 'UNAVAILABLE'
        # Source witness absence preserves legacy positive direct callbacks.
        _fee_execution(client, exec_id='fee.3', cumQty=3)
        _fee_report(client, exec_id='fee.3')
        assert client.cached_native_execution_fees(71)[2]['report_status'] == 'BOUND_API_REPORT'
    finally:
        source.close()


def test_native_zero_proxy_forwards_other_callbacks_without_replacing_native_wrapper(
        native_wire_zero_source):
    from ibapi.decoder import Decoder
    from ibapi.message import IN
    client, source = native_wire_zero_source
    assert client.wrapper is client
    assert client.decoder.wrapper is not client
    assert client.decoder.msgId2handleInfo is not Decoder.msgId2handleInfo
    assert client.decoder.msgId2handleInfo[IN.OPEN_ORDER_END] is Decoder.msgId2handleInfo[IN.OPEN_ORDER_END]
    assert client._managed_accounts == ['SYNTHETIC_TEST']
    assert not client._open_orders_event.is_set()
    source.deliver_frame([53, 1])  # Actual SDK generic callback dispatch.
    assert client._open_orders_event.is_set()
    assert client.wrapper is client


@pytest.mark.parametrize('transition', ['managedAccounts', 'connectionClosed'])
def test_native_zero_source_actual_scope_transition_cannot_rearm(native_wire_zero_source, transition):
    client, source = native_wire_zero_source
    _fee_execution(client)
    source.deliver_commission_frame('fee.1')
    assert client.cached_native_execution_fees(71)[0]['report_status'] == 'BOUND_API_REPORT'
    if transition == 'managedAccounts':
        source.deliver_frame([15, 1, 'OTHER_ACCOUNT'])
        source.deliver_frame([15, 1, 'SYNTHETIC_TEST'])
    else:
        client.connectionClosed()
    assert client.cached_native_execution_fees(71)[0]['report_status'] == 'UNAVAILABLE'


@pytest.mark.parametrize('early_call', ['config_only', 'failed_sdk_attempt'])
def test_native_zero_source_first_actual_sdk_attempt_scope(
        monkeypatch, tmp_path, no_external_activity, early_call):
    from ibapi.connection import Connection
    monkeypatch.setenv('IBKR_ORDER_ID_STATE_PATH', str(tmp_path / 'early-sdk-scope.json'))
    client = IbkrClient('offline', 1, 999, 2, 'LIVE', True)
    if early_call == 'config_only':
        client.port = 0
        with pytest.raises(RuntimeError, match='INVALID_RETRY_CONFIGURATION'):
            _NATIVE_SOURCE_CONNECT(client)
        assert client._commission_connection_attempts == 0
        client.port = 1
    else:
        with monkeypatch.context() as boundary:
            boundary.setattr(EClient, 'connect', _NATIVE_SDK_CONNECT)
            def external_failure(connection):
                raise RuntimeError('synthetic external connect failure')
            boundary.setattr(Connection, 'connect', external_failure)
            with pytest.raises(RuntimeError, match='synthetic external connect failure'):
                _NATIVE_SOURCE_CONNECT(client)
        assert client._commission_connection_attempts == 1
    source = native_commission_decoder_source(client, monkeypatch)
    try:
        _fee_execution(client)
        source.deliver_commission_frame('fee.1')
        row, = client.cached_native_execution_fees(71)
        assert row['report_status'] == ('BOUND_API_REPORT' if early_call == 'config_only' else 'UNAVAILABLE')
        assert client._commission_connection_attempts == (1 if early_call == 'config_only' else 2)
        assert row['net_status'] == 'UNAVAILABLE_FOR_NET'
    finally:
        source.close()


def test_native_zero_source_helper_releases_reader_after_preworker_failure(
        monkeypatch, tmp_path, no_external_activity):
    monkeypatch.setenv('IBKR_ORDER_ID_STATE_PATH', str(tmp_path / 'helper-failure-ids.json'))
    client = IbkrClient('offline', 1, 999, 2, 'LIVE', True)
    readers = []
    def fail_install():
        readers.append(client.reader)
        assert client.reader.is_alive() and client._thread is None
        raise RuntimeError('synthetic preworker hook failure')
    monkeypatch.setattr(client, '_install_commission_decoder_witness', fail_install)
    with pytest.raises(RuntimeError, match='synthetic preworker hook failure'):
        native_commission_decoder_source(client, monkeypatch)
    assert len(readers) == 1 and not readers[0].is_alive()
    assert not client.is_connected() and client._thread is None


@pytest.mark.parametrize('unsupported', ['nonbytes', 'wrong_thread'])
def test_native_zero_source_rejects_non_native_decoder_dispatch(
        monkeypatch, native_wire_zero_source, unsupported):
    client, source = native_wire_zero_source
    _fee_execution(client)
    if unsupported == 'nonbytes':
        interpret = client.decoder.interpret
        def text_field(fields):
            changed = list(fields)
            changed[3] = '0'
            return interpret(changed)
        with monkeypatch.context() as wrong_fields:
            wrong_fields.setattr(client.decoder, 'interpret', text_field)
            source.deliver_commission_frame('fee.1')
    else:
        # Real parser and object, but not the enrolled native decoder worker.
        client.decoder.interpret((b'59', b'1', b'fee.1', b'0', b'USD', b'', b'', b'0'))
    assert client.cached_native_execution_fees(71)[0]['report_status'] == 'UNAVAILABLE'
    _fee_execution(client, exec_id='fee.2', cumQty=2)
    source.deliver_commission_frame('fee.2')
    assert client.cached_native_execution_fees(71)[1]['report_status'] == 'UNAVAILABLE'
    assert client.commission_for_order(71) == 0


def test_native_zero_source_frame_cannot_be_reused_by_reentrant_wrapper_callback(
        native_wire_zero_source):
    from ibapi.commission_report import CommissionReport
    client, source = native_wire_zero_source
    _fee_execution(client)
    _fee_execution(client, exec_id='fee.2', cumQty=2)
    def wrapper_reentry(payload):
        if payload.get('event_type') == 'commissionReport' and payload['execId'] == 'fee.1':
            unrelated = CommissionReport()
            unrelated.execId, unrelated.commission, unrelated.currency = 'fee.2', 0., 'USD'
            client.decoder.wrapper.commissionReport(unrelated)
    client.register_reconciliation_callback(wrapper_reentry)
    source.deliver_commission_frame('fee.1')
    actual, unrelated = client.cached_native_execution_fees(71)
    assert actual['report_status'] == 'BOUND_API_REPORT'
    assert unrelated['report_status'] == 'UNAVAILABLE'
    assert unrelated['first_report']['commission_field_present'] is None


@pytest.mark.parametrize('raw_amount,report_currency', [('0', 'USD'), ('.01', 'USD'), ('', 'USD'), ('0', 'EUR')])
def test_native_zero_source_logging_cannot_borrow_another_raw_execution_or_cost(
        monkeypatch, native_wire_zero_source, raw_amount, report_currency):
    from ibapi import utils
    from ibapi.commission_report import CommissionReport
    client, source = native_wire_zero_source
    _fee_execution(client)
    _fee_execution(client, exec_id='fee.2', cumQty=2, currency=report_currency)
    debug = utils.logger.debug
    injected = []
    def before_sdk_report(*args, **kwargs):
        if not injected and len(args) >= 3 and args[1] is int and args[2] == b'1':
            unrelated = CommissionReport()
            unrelated.execId, unrelated.commission, unrelated.currency = 'fee.2', 0., report_currency
            client.decoder.wrapper.commissionReport(unrelated)
            injected.append(client.cached_native_execution_fees(71)[1]['report_status'])
        return debug(*args, **kwargs)
    monkeypatch.setattr(utils.logger, 'debug', before_sdk_report)
    source.deliver_frame([59, 1, 'fee.1', raw_amount, 'USD', '', '', 0])
    actual, unrelated = client.cached_native_execution_fees(71)
    assert injected == ['UNAVAILABLE'] and unrelated['report_status'] == 'UNAVAILABLE'
    assert unrelated['first_report']['commission_field_present'] is None
    assert actual['report_status'] == ('UNAVAILABLE' if raw_amount == '' else 'BOUND_API_REPORT')


@pytest.mark.parametrize('raw_amount', ['.01', '', '0.00', '-0.0', '0e0'])
def test_native_zero_source_same_execution_proxy_cannot_invent_an_explicit_zero(
        monkeypatch, native_wire_zero_source, raw_amount):
    from ibapi import utils
    from ibapi.commission_report import CommissionReport
    client, source = native_wire_zero_source
    _fee_execution(client)
    debug = utils.logger.debug
    seen = []
    def before_sdk_report(*args, **kwargs):
        if not seen and len(args) >= 3 and args[1] is int and args[2] == b'1':
            fake = CommissionReport()
            fake.execId, fake.commission, fake.currency = 'fee.1', 0., 'USD'
            client.decoder.wrapper.commissionReport(fake)
            row, = client.cached_native_execution_fees(71)
            seen.append(row['report_status'])
        return debug(*args, **kwargs)
    monkeypatch.setattr(utils.logger, 'debug', before_sdk_report)
    source.deliver_frame([59, 1, 'fee.1', raw_amount, 'USD', '', '', 0])
    assert seen == ['UNAVAILABLE']
    assert client.cached_native_execution_fees(71)[0]['report_status'] == 'UNAVAILABLE'


@pytest.mark.parametrize('raw_amount', ['0', '0.0'])
def test_native_zero_source_equivalent_proxy_report_corroborates_the_same_actual_frame(
        monkeypatch, native_wire_zero_source, raw_amount):
    from ibapi import utils
    from ibapi.commission_report import CommissionReport
    client, source = native_wire_zero_source
    _fee_execution(client)
    debug = utils.logger.debug
    seen = []
    def before_sdk_report(*args, **kwargs):
        if not seen and len(args) >= 3 and args[1] is int and args[2] == b'1':
            same_fact = CommissionReport()
            same_fact.execId, same_fact.commission, same_fact.currency = 'fee.1', 0., 'USD'
            client.decoder.wrapper.commissionReport(same_fact)
            row, = client.cached_native_execution_fees(71)
            seen.append(row['report_status'])
        return debug(*args, **kwargs)
    monkeypatch.setattr(utils.logger, 'debug', before_sdk_report)
    source.deliver_frame([59, 1, 'fee.1', raw_amount, 'USD', '', '', 0])
    row, = client.cached_native_execution_fees(71)
    assert seen == ['UNAVAILABLE'] and row['report_status'] == 'BOUND_API_REPORT'
    assert row['report_count'] == 1 and not row['conflict']
    assert row['first_report']['commission_field_present'] is True
    assert row['latest_report'] == row['first_report']  # Published once after SDK return.
    assert row['net_status'] == 'UNAVAILABLE_FOR_NET'


@pytest.mark.parametrize('missing', ['handler', 'python_code', 'message_id', 'handle_info'])
def test_native_zero_optional_sdk_capability_preserves_cold_legacy_import(tmp_path, missing):
    import os
    import subprocess
    import sys
    code = r'''
import socket, sys
from ibapi import decoder
from ibapi.message import IN
if sys.argv[1] == 'handler':
    del decoder.Decoder.processCommissionReportMsg
elif sys.argv[1] == 'python_code':
    decoder.Decoder.processCommissionReportMsg = len
elif sys.argv[1] == 'message_id':
    del IN.COMMISSION_REPORT
else:
    del decoder.HandleInfo
# No external transport even if a compatibility regression tries to acquire it.
def forbidden(*args, **kwargs):
    raise AssertionError('cold capability check attempted transport')
socket.socket.connect = forbidden
socket.create_connection = forbidden
from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from ibapi.contract import Contract
from ibapi.execution import Execution
from ibapi.commission_report import CommissionReport
client = IbkrClient('offline', 0, 999, 2, 'LIVE', True)
client._install_commission_decoder_witness()
assert client._commission_zero_disabled
contract, execution = Contract(), Execution()
contract.symbol, contract.conId = 'SYNTH', 123
execution.execId, execution.orderId = 'legacy.1', 71
client.execDetails(-1, contract, execution)
report = CommissionReport()
report.execId, report.commission, report.currency = 'legacy.1', .01, 'USD'
client.commissionReport(report)
assert client.commission_for_order(71) == .01
assert client.wrapper is client
print('LEGACY_IMPORT_CALLBACK_OK_ZERO_DISABLED')
'''
    env = dict(os.environ, IBKR_ORDER_ID_STATE_PATH=str(tmp_path / 'optional-sdk-ids.json'))
    result = subprocess.run([sys.executable, '-c', code, missing], capture_output=True,
        text=True, timeout=10, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'LEGACY_IMPORT_CALLBACK_OK_ZERO_DISABLED' in result.stdout


def test_native_zero_source_rejects_pending_zero_when_sdk_parse_does_not_complete(
        monkeypatch, native_wire_zero_source):
    from ibapi import utils
    from ibapi.commission_report import CommissionReport
    client, source = native_wire_zero_source
    _fee_execution(client)
    debug = utils.logger.debug
    seen = []
    def during_decode(*args, **kwargs):
        if not seen and len(args) >= 3 and args[1] is int and args[2] == b'1':
            seen.append('entered parser')
            pending = CommissionReport()
            pending.execId, pending.commission, pending.currency = 'fee.1', 0., 'USD'
            client.decoder.wrapper.commissionReport(pending)
            seen.append(client.cached_native_execution_fees(71)[0]['report_status'])
        return debug(*args, **kwargs)
    monkeypatch.setattr(utils.logger, 'debug', during_decode)
    with pytest.raises(AssertionError, match='SDK decoder did not finish the frame'):
        source.deliver_frame([59, 1, 'fee.1', 0, 'USD', '', 'invalid-yield', 0])
    assert seen == ['entered parser', 'UNAVAILABLE']
    assert client.cached_native_execution_fees(71)[0]['report_status'] == 'UNAVAILABLE'


def test_native_zero_source_scope_loss_after_normal_parse_preserves_legacy_callback(
        monkeypatch, native_wire_zero_source):
    client, source = native_wire_zero_source
    _fee_execution(client)
    proxy = client.decoder.wrapper
    callback = proxy.commissionReport
    def actual_callback_then_scope_loss(report):
        callback(report)  # The actual SDK report is staged until normal return.
        client.connectionClosed()  # Real callback owner invalidates the epoch.
    monkeypatch.setattr(proxy, 'commissionReport', actual_callback_then_scope_loss)
    source.deliver_commission_frame('fee.1')
    assert client.commission_for_order(71) == 0.0
    row, = client.cached_native_execution_fees(71)
    assert row['report_status'] == 'UNAVAILABLE' and row['amount'] is None
    assert row['first_report']['commission_field_present'] is None
    assert row['net_status'] == 'UNAVAILABLE_FOR_NET'
