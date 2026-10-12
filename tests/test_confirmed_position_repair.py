from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
import threading

import pytest

from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.config.runtime_config import RunMode
from src.core.orchestrator import CoreOrchestrator
from src.execution.position_truth import (PositionTruthConfig, collect_broker_position_snapshot,
    collect_system_position_snapshot, reconcile_position_truth)
from src.ibkr.position_snapshot import BrokerPositionResult, PositionRows


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv('IBKR_ORDER_ID_STATE_PATH', str(tmp_path / 'order-id.json'))
    c = IbkrClient('offline', 0, 123, 1, 'LIVE', True)
    c._managed_accounts = ['TEST']
    c._position_transport_available = True
    c.is_connected = lambda: True
    c.cancelPositionsMulti = lambda req: None
    return c


def collect(client):
    return collect_broker_position_snapshot(client, as_of=datetime.now(timezone.utc),
        config=PositionTruthConfig(True, RunMode.READ_ONLY))


def verdict(collection, system=None):
    return reconcile_position_truth(collection, system or {},
        as_of=datetime.now(timezone.utc), live_broker_mode=True)


@pytest.mark.parametrize('quantity', [0, 0.1, -0.1, 1.25, -1.25])
def test_complete_and_signed_fractional(client, quantity):
    def response(req, account, model):
        if quantity:
            client.positionMulti(req, account, model, NS(symbol='AAPL', conId=1), quantity, 10)
        client.positionMultiEnd(req)
    client.reqPositionsMulti = response
    rows = collect(client)
    assert rows.status == 'COMPLETE'
    system = collect_system_position_snapshot([NS(symbol='AAPL', quantity=abs(quantity),
        direction='SHORT' if quantity < 0 else 'LONG')], as_of=datetime.now(timezone.utc))
    snapshot, v = verdict(rows, system)
    assert v.healthy
    if quantity:
        assert rows['AAPL'].quantity == quantity
        assert verdict(rows)[1].block_new_entries
    else:
        assert not rows


@pytest.mark.parametrize('kind', ['missing', 'legacy', 'partial', 'failed', 'timeout', 'disconnected', 'wrong', 'stale', 'unscoped'])
def test_unavailable_never_flat_or_complete(client, kind):
    now = datetime.now(timezone.utc)
    if kind == 'missing':
        client = None
    elif kind == 'legacy':
        client = NS(positions=lambda: [])
    elif kind in {'stale', 'unscoped'}:
        client = NS(position_snapshot=lambda: BrokerPositionResult((), 'COMPLETE',
            None if kind == 'unscoped' else 'TEST', now-timedelta(seconds=100)))
    else:
        def response(req, account, model):
            if kind == 'failed':
                raise RuntimeError('offline')
            client.positionMulti(req, 'OTHER' if kind == 'wrong' else account, model,
                NS(symbol='AAPL', conId=1), 0.1, 10)
            if kind == 'disconnected':
                client.connectionClosed()
            elif kind not in {'timeout', 'partial'}:
                client.positionMultiEnd(req)
        client.reqPositionsMulti = response
        original = client.position_snapshot
        client.position_snapshot = lambda: original(timeout_seconds=0.001)
    snapshot, v = verdict(collect(client))
    assert snapshot.snapshot_status == 'UNKNOWN'
    assert not v.healthy and v.block_new_entries and v.require_reconciliation
    assert not v.block_exits


def test_late_rows_and_end_cannot_certify_new_query(client):
    ids = []
    client.reqPositionsMulti = lambda req, *args: ids.append(req)
    assert client.position_snapshot(0).status == 'TIMEOUT'
    old = ids[0]
    def second(req, account, model):
        client.positionMulti(old, account, model, NS(symbol='OLD', conId=1), 10, 1)
        client.positionMultiEnd(old)
        client.positionEnd()  # legacy subscription is also uncorrelated
    client.reqPositionsMulti = second
    assert client.position_snapshot(0).status == 'TIMEOUT'
    assert not client._position_queries


def test_disconnect_after_end_invalidates_completion(client):
    def response(req, *args):
        client.positionMultiEnd(req)
        client.connectionClosed()
    client.reqPositionsMulti = response
    assert client.position_snapshot().status == 'DISCONNECTED'


def test_timeout_end_cannot_complete(client):
    client.reqPositionsMulti = lambda req, *args: client.positionMultiEnd(req)
    assert client.position_snapshot(0).status == 'TIMEOUT'


def test_legacy_subscription_not_cancelled_or_overwritten(client):
    client._positions_snapshot = {'KNOWN': NS(position=.1)}
    client.reqPositionsMulti = lambda req, *args: client.positionMultiEnd(req)
    client.cancelPositions = lambda: pytest.fail('legacy subscription cancelled')
    assert client.positions() == []
    assert client._positions_snapshot['KNOWN'].position == .1


def test_real_handoff_and_downstream_unknown_preserves_exposure(client):
    from src.core.managers.connection_manager import ConnectionManager
    manager = ConnectionManager(RunMode.READ_ONLY)
    manager._ibkr_connection_manager = NS(existing_client=client, get_client=lambda: pytest.fail("unexpected reconnect"))
    manager._client = NS()  # actual market-data facade has no positions method
    client.reqPositionsMulti = lambda req, account, model: (
        client.positionMulti(req, account, model, NS(symbol='AAPL', conId=1), .1, 10),
        client.positionMultiEnd(req))
    calls = []
    engine = NS(_relationship_orders_asof=None)
    o = CoreOrchestrator.__new__(CoreOrchestrator)
    o.run_mode = RunMode.READ_ONLY
    o.connection_manager = manager
    o.trade_registry = NS(snapshot=lambda: [])
    o.execution_engine = engine
    o.trade_management_engine = NS(_relationship_plans={}, reconcile_broker_snapshot=lambda **kw: calls.append(kw))
    o._latest_position_truth_snapshot = None
    o._degraded = False
    assert o._resolve_position_truth_cycle(as_of=datetime.now(timezone.utc)).block_new_entries
    client.is_connected = lambda: False
    v = o._resolve_position_truth_cycle(as_of=datetime.now(timezone.utc))
    assert not v.healthy and v.block_new_entries
    assert o._latest_position_truth_snapshot.broker_positions['AAPL'].quantity == .1
    assert calls[-1]['complete'] is False
    assert CoreOrchestrator._apply_position_truth_entry_guard([NS(symbol='AAPL')], v) == []


def test_passive_unknown_does_not_erase_or_reconcile(monkeypatch):
    from src.execution import order_router as router
    known = router.IbkrPositionTruth(symbol='AAPL', quantity=.1)
    monkeypatch.setattr(router, '_IBKR_POSITIONS_BY_SYMBOL', {'AAPL': known})
    monkeypatch.setattr(router, '_RECONCILED_POSITIONS_OK', 0)
    monkeypatch.setattr(router, '_RECON_RESYNC_NEEDED', False)
    _, _, rows = router._normalize_ibkr_truth(([], [], PositionRows(available=False)))
    router._run_passive_position_reconciliation(positions=rows)
    assert router._IBKR_POSITIONS_BY_SYMBOL['AAPL'].quantity == .1
    assert router._RECONCILED_POSITIONS_OK == 0 and router._RECON_RESYNC_NEEDED


def test_concurrent_queries_only_accept_their_own_end(client):
    barrier = threading.Barrier(2)
    ids = []
    lock = threading.Lock()
    def request(req, account, model):
        with lock:
            ids.append(req)
        barrier.wait(timeout=2)
        client.positionMulti(req, account, model, NS(symbol=f'S{req}', conId=req), req+.1, 10)
        client.positionMultiEnd(req)
    client.reqPositionsMulti = request
    results = []
    threads = [threading.Thread(target=lambda: results.append(client.position_snapshot(2))) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(3)
        assert not t.is_alive()
    assert len(results) == 2 and len(set(ids)) == 2
    assert all(r.status == 'COMPLETE' and len(r.rows) == 1 for r in results)
    assert {r.rows[0].symbol for r in results} == {f'S{i}' for i in ids}


def test_query_error_and_connectivity_loss_fail_closed(client):
    client.reqPositionsMulti = lambda req, *args: client.error(req, 321, 'test rejection')
    assert client.position_snapshot().status == 'FAILED'
    client.reqPositionsMulti = lambda req, *args: client.error(-1, 1100, 'test loss')
    assert client.position_snapshot().status == 'DISCONNECTED'
    assert client.position_snapshot().status == 'DISCONNECTED'


def test_multiple_accounts_have_no_implicit_primary_scope(client):
    client._managed_accounts = ['TEST', 'OTHER']
    client.reqPositionsMulti = lambda *args: pytest.fail('ambiguous account requested')
    assert client.position_snapshot().status == 'ACCOUNT_SCOPE_UNAVAILABLE'


@pytest.mark.parametrize('quantity', [.1, -.1])
def test_downstream_preserves_fractional_truth(monkeypatch, quantity):
    from src.execution import order_router as router
    monkeypatch.setattr(router, '_IBKR_POSITIONS_BY_SYMBOL', {})
    monkeypatch.setattr(router, '_RUNTIME_ORDERS', {})
    router._sync_ibkr_positions_from_snapshot([NS(symbol='AAPL', position=quantity)])
    assert router._IBKR_POSITIONS_BY_SYMBOL['AAPL'].quantity == quantity


@pytest.mark.parametrize('action,side', [('ENTER','LONG'), ('ADD','LONG'), ('REENTER','LONG'), ('ENTER','SHORT')])
def test_actual_router_blocks_new_risk_when_position_truth_unknown(monkeypatch, action, side):
    from src.execution import order_router as router
    monkeypatch.setattr(router, '_fetch_ibkr_truth', lambda *args: ([], [], PositionRows(available=False)))
    monkeypatch.setattr(router, '_RUNTIME_ORDERS', {})
    monkeypatch.setattr(router, '_IBKR_POSITIONS_BY_SYMBOL', {})
    events = router.execute_intents(mode_value='PAPER', decisions=[NS(symbol='AAPL', intent_id='test',
        approved_quantity=1, entry_price=10, side=side, action=action, available_funds=100,
        order_value=10, risk_allowed=True, decision='ALLOW')])
    assert len(events) == 1
    assert events[0].action == 'BLOCKED' and events[0].event_type == 'POSITION_TRUTH_UNAVAILABLE'


def test_unknown_truth_keeps_explicit_exit_route(monkeypatch):
    from src.execution import order_router as router
    monkeypatch.setattr(router, '_fetch_ibkr_truth', lambda *args: ([], [], PositionRows(available=False)))
    monkeypatch.setattr(router, '_RUNTIME_ORDERS', {})
    monkeypatch.setattr(router, '_IBKR_POSITIONS_BY_SYMBOL', {})
    # Stop at the existing exit route before any simulated or broker submission.
    class ReachedExitRoute(Exception):
        pass
    def reached(**kwargs):
        raise ReachedExitRoute()
    monkeypatch.setattr(router, '_create_execution_truth', reached)
    with pytest.raises(ReachedExitRoute):
        router.execute_intents(mode_value='PAPER', decisions=[NS(symbol='AAPL', intent_id='exit',
            approved_quantity=1, entry_price=10, side='SHORT', action='EXIT', available_funds=100,
            order_value=10, risk_allowed=True, decision='ALLOW')])


@pytest.mark.parametrize('quantity', [.1, -.1])
def test_repeated_external_fraction_never_becomes_flat(monkeypatch, capsys, quantity):
    from src.execution import order_router as router
    monkeypatch.setattr(router, '_IBKR_POSITIONS_BY_SYMBOL', {})
    monkeypatch.setattr(router, '_RUNTIME_ORDERS', {})
    monkeypatch.setattr(router, '_BROKER_POSITION_LAST_QTY_BY_SYMBOL', {})
    for _ in range(2):
        router._run_passive_position_reconciliation(positions=PositionRows(
            [NS(symbol='AAPL', position=quantity)], available=True))
        assert router._IBKR_POSITIONS_BY_SYMBOL['AAPL'].quantity == quantity
        assert router.runtime_lifecycle_snapshot()['open_position_count'] == 1
    assert 'verdict=POSITION_CLOSED_ALIGNED' not in capsys.readouterr().out


def test_completed_query_stale_before_consumption(client, monkeypatch):
    import src.adapters.brokers.ibkr.ibkr_client as module
    base = datetime.now(timezone.utc)
    times = iter([base, base + timedelta(seconds=100)])
    monkeypatch.setattr(module, 'datetime', NS(now=lambda *args: next(times)))
    client.reqPositionsMulti = lambda req, *args: client.positionMultiEnd(req)
    assert client.position_snapshot().status == 'STALE'


def test_account_scope_change_after_end_invalidates_result(client):
    def request(req, *args):
        client.positionMultiEnd(req)
        client._managed_accounts = ['OTHER']
    client.reqPositionsMulti = request
    assert client.position_snapshot().status == 'WRONG_ACCOUNT'


def test_collection_expiring_before_reconciliation_blocks(client):
    client.reqPositionsMulti = lambda req, *args: client.positionMultiEnd(req)
    collection = collect(client)
    collection.completed_at -= timedelta(seconds=100)
    snapshot, v = verdict(collection)
    assert snapshot.snapshot_status == 'UNKNOWN' and v.block_new_entries


def test_query_error_not_downgraded_to_unknown_market_warning(client):
    def request(req, *args):
        client.error(req, 300, 'test missing request')
        client.positionMultiEnd(req)
    client.reqPositionsMulti = request
    assert client.position_snapshot().status == 'FAILED'


@pytest.mark.parametrize('quantity', [None, float('nan'), float('inf'), 'invalid'])
def test_invalid_query_quantity_never_complete(client, quantity):
    def request(req, account, model):
        client.positionMulti(req, account, model, NS(symbol='AAPL', conId=1), quantity, 10)
        client.positionMultiEnd(req)
    client.reqPositionsMulti = request
    assert client.position_snapshot().status == 'FAILED'


@pytest.mark.parametrize('code', [103, 201, 321])
def test_position_query_errors_do_not_compete_with_order_callback_owner(client, code):
    client.nextValidId(1)
    order_id = client.reserve_order_id()
    client._order_status_events[order_id] = threading.Event()
    client._order_status[order_id] = {'status': 'Submitted'}
    def request(req, *args):
        assert req != order_id
        client.error(req if code == 321 else order_id, code, 'test rejection')
        client.positionMultiEnd(req)
    client.reqPositionsMulti = request
    result = client.position_snapshot()
    assert result.status == ('FAILED' if code == 321 else 'COMPLETE')
    assert bool(client._order_errors.get(order_id)) == (code != 321)
    assert client._order_status_events[order_id].is_set() == (code != 321)
    assert client._order_status[order_id]['status'] == 'Submitted'


@pytest.mark.parametrize('recovery_code', [1101, 1102])
def test_upstream_recovery_allows_fresh_query_without_reconnecting(client, recovery_code):
    ids=[]
    def interrupted(req, account, model):
        ids.append(req)
        client.error(-1, 1100, 'test upstream loss')
        client.error(-1, recovery_code, 'test upstream restored')
        client.positionMultiEnd(req)
    client.reqPositionsMulti=interrupted
    assert client.position_snapshot().status == 'DISCONNECTED'
    def fresh(req, account, model):
        client.positionMultiEnd(ids[0])
        client.positionMulti(req, account, model, NS(symbol='AAPL', conId=1), .1, 10)
        client.positionMultiEnd(req)
    client.reqPositionsMulti=fresh
    result=client.position_snapshot()
    assert result.status == 'COMPLETE' and result.rows[0].position == .1
    assert client._managed_accounts == ['TEST']


@pytest.mark.parametrize('quantity', [.1, -.1, 1.25, -1.25, 1])
def test_real_recovery_never_adopts_preexisting_inventory(client, quantity):
    from src.core.active_trade_registry import ActiveTradeRegistry
    from src.execution.recovery_engine import build_recovery_plan, apply_recovery_actions
    def response(req, account, model):
        client.positionMulti(req, account, model, NS(symbol='AAPL', conId=1), quantity, 10)
        client.positionMultiEnd(req)
    client.reqPositionsMulti = response
    snapshot, v=verdict(collect(client))
    registry=ActiveTradeRegistry()
    o=CoreOrchestrator.__new__(CoreOrchestrator)
    o._latest_position_truth_snapshot=snapshot
    o.trade_registry=registry
    plan=build_recovery_plan(snapshot,v,{'execution_stalled':False})
    assert plan.manual_required_count == 1 and plan.auto_actions_count == 0
    apply_recovery_actions(plan,o)
    assert registry.snapshot() == []
    assert snapshot.broker_positions['AAPL'].quantity == quantity and v.block_new_entries


def test_retained_auto_attach_plan_cannot_adopt_inventory():
    from src.execution.recovery_engine import RecoveryAction, RecoveryPlan, apply_recovery_actions
    action=RecoveryAction('AAPL','ATTACH_BROKER_POSITION','WARNING',False,True,'legacy')
    plan=RecoveryPlan([action],0,1,1,0,'legacy')
    apply_recovery_actions(plan,NS(attach_broker_position_from_recovery=lambda **_: pytest.fail('auto adoption')))


def test_order_id_callback_does_not_restore_lost_position_transport(client):
    client.error(-1, 1100, 'test upstream loss')
    client.nextValidId(1234)
    client.reqPositionsMulti=lambda req, *args: client.positionMultiEnd(req)
    assert client.position_snapshot().status == 'DISCONNECTED'
    client.error(-1,1102,'test upstream restored')
    assert client.position_snapshot().status == 'COMPLETE'


def test_unknown_position_truth_keeps_recovery_plan_blocked():
    from src.execution.recovery_engine import build_recovery_plan
    snapshot, v=verdict(collect(None))
    plan=build_recovery_plan(snapshot,v,{'execution_stalled':False})
    assert plan.manual_required_count == 1 and plan.auto_actions_count == 0
    assert 'blocked=True' in plan.summary
    assert plan.actions[0].action_type == 'FLAG_POSITION_TRUTH_UNAVAILABLE'


def test_request_order_ids_are_disjoint_even_after_query_retirement(client):
    client.nextValidId(100)
    order = client.reserve_order_id()
    client._order_status_events[order] = threading.Event()
    issued = []
    def request(req, *args):
        issued.append(req)
        during = client.reserve_order_id()
        assert during != req and during > order
        client._order_status_events[during] = threading.Event()
        # An arbitrary order error reaches its existing owner even while the
        # position query is active; no code whitelist or broker submission.
        client.error(during, 103, 'test duplicate order id')
        assert client._order_errors[during][0] == 103
        assert client._order_status_events[during].is_set()
        client.positionMultiEnd(req)
    client.reqPositionsMulti = request
    assert client.position_snapshot().status == 'COMPLETE'
    after = client.reserve_order_id()
    assert after > issued[-1] and after not in issued
    req_after = client._next_req_id()
    assert req_after > after and req_after not in client._order_status_events


@pytest.mark.parametrize('mode', [RunMode.READ_ONLY, RunMode.PAPER])
def test_manager_exposes_existing_test_client_and_truth_is_unknown(mode):
    from src.core.managers.connection_manager import ConnectionManager
    manager=ConnectionManager(mode)
    manager.connect()  # supported TEST factory; no socket or broker connection
    client=manager.get_ibkr_client(ensure_connected=False)
    assert client is manager._ibkr_connection_manager.get_client()
    o=CoreOrchestrator.__new__(CoreOrchestrator)
    o.run_mode=mode
    o.connection_manager=manager
    o.trade_registry=NS(snapshot=lambda:[])
    o.execution_engine=NS(_relationship_orders_asof=None)
    o.trade_management_engine=None
    o._latest_position_truth_snapshot=None
    o._degraded=False
    v=o._resolve_position_truth_cycle(as_of=datetime.now(timezone.utc))
    assert not v.healthy and v.block_new_entries
    assert o._latest_position_truth_snapshot.snapshot_status == 'UNKNOWN'


def test_request_order_allocation_is_unique_under_concurrency(client):
    client.nextValidId(1)
    barrier=threading.Barrier(2)
    results=[]
    def allocate(method):
        barrier.wait(timeout=2)
        results.extend(method() for _ in range(20))
    threads=[threading.Thread(target=allocate,args=(method,))
             for method in (client._next_req_id,client.reserve_order_id)]
    for t in threads:t.start()
    for t in threads:
        t.join(3)
        assert not t.is_alive()
    assert len(results)==40 and len(set(results))==40


def _raw_request(client, method, req):
    contract=NS(symbol='AAPL',secType='STK',exchange='SMART',currency='USD',conId=1)
    if method=='reqMktData':
        client.reqMktData(req,contract,'',True,False,[])
    else:
        client.reqHistoricalData(req,contract,'','1 D','1 min','TRADES',1,1,False,[])


@pytest.mark.parametrize('method', ['reqMktData','reqHistoricalData'])
def test_raw_request_ids_advance_shared_order_boundary(client, monkeypatch, method):
    from ibapi.client import EClient
    sent=[]
    monkeypatch.setattr(EClient,method,lambda *args,**kwargs:sent.append(args[1]))
    client.nextValidId(100)
    _raw_request(client,method,100)
    order=client.reserve_order_id()
    assert sent==[100] and order>100
    client.error(order,103,'test duplicate order')
    event=(client._market_events if method=='reqMktData' else client._historical_events)[100]
    assert not event.is_set()
    assert client._order_errors[order][0]==103 and client._order_status_events[order].is_set()


@pytest.mark.parametrize('method', ['reqMktData','reqHistoricalData'])
def test_raw_request_cannot_claim_reserved_order_id(client, monkeypatch, method):
    from ibapi.client import EClient
    monkeypatch.setattr(EClient,method,lambda *args,**kwargs:pytest.fail('ambiguous request dispatched'))
    client.nextValidId(100)
    order=client.reserve_order_id()
    with pytest.raises(RuntimeError,match='already reserved for an order'):
        _raw_request(client,method,order)
    assert order not in client._market_events and order not in client._historical_events
    assert order not in client._request_type_by_req_id
    client.error(order,103,'test order rejected')
    assert client._order_status_events[order].is_set()


def test_explicit_request_registration_and_order_reservation_share_lock(client):
    client.nextValidId(100)
    barrier=threading.Barrier(2)
    result={}
    def request():
        barrier.wait(timeout=2)
        try:
            client._register_request(100,'HISTORICAL_DATA')
            result['request']=100
        except RuntimeError:
            result['request_rejected']=True
    def order():
        barrier.wait(timeout=2)
        result['order']=client.reserve_order_id()
    threads=[threading.Thread(target=request),threading.Thread(target=order)]
    for t in threads:t.start()
    for t in threads:
        t.join(3)
        assert not t.is_alive()
    assert result['order'] != result.get('request')
    assert (result['order']==100 and result.get('request_rejected')) or result['order']>100


def _discovered_order(client, kind, order_id):
    contract=NS(symbol='AAPL')
    if kind=='openOrder':
        client.openOrder(order_id,contract,NS(orderType='STP',tif='DAY',outsideRth=True),NS(status='Submitted'))
    elif kind=='orderStatus':
        client.orderStatus(order_id,'Submitted',0,1,0,0,0,0,0,'',0)
    else:
        client.execDetails(900,contract,NS(orderId=order_id,execId='fixture',shares=1,price=10,time='fixture'))


@pytest.mark.parametrize('kind', ['openOrder','orderStatus','execDetails'])
def test_callback_discovered_order_ids_cannot_be_claimed_by_requests(client,kind):
    client.nextValidId(100)
    _discovered_order(client,kind,150)
    with pytest.raises(RuntimeError,match='already reserved for an order'):
        client._register_request(150,'HISTORICAL_DATA')
    assert client.reserve_order_id()>150
    assert client._next_req_id()>150
    client.error(150,103,'test rejection for observed order')
    assert client._order_errors[150][0]==103
    assert client._order_status_events[150].is_set()
    assert 150 not in client._historical_events


def test_order_discovered_during_position_query_invalidates_ambiguous_query(client):
    def request(req, *args):
        _discovered_order(client,'openOrder',req)
        client.positionMultiEnd(req)
    client.reqPositionsMulti=request
    assert client.position_snapshot().status=='FAILED'


@pytest.mark.parametrize('kind', ['MARKET_DATA','HISTORICAL_DATA','CONTRACT_DETAILS',
    'SCANNER_DATA','ACCOUNT_SUMMARY','EXECUTIONS','POSITIONS_MULTI'])
def test_discovered_collision_retires_every_request_owner(client,kind):
    req=150
    client._register_request(req,kind)
    event=threading.Event()
    event_maps={'MARKET_DATA':client._market_events,'HISTORICAL_DATA':client._historical_events,
        'CONTRACT_DETAILS':client._contract_events,'SCANNER_DATA':client._scanner_events,
        'ACCOUNT_SUMMARY':client._account_summary_events}
    if kind in event_maps:event_maps[kind][req]=event
    client._historical_data[req]=[NS(close=42)]
    client._contract_details[req]=[NS(contract=NS(symbol='AAPL',conId=1))]
    client._scanner_rows[req]=[NS(symbol='AAPL')]
    client._account_summary_rows[req]={'AvailableFunds':'100'}
    client._market_data[req]={'last':42}
    ticker=client._build_ticker(NS(symbol='AAPL'))
    ticker.last=42;ticker.snapshotEnd=True
    client._ticker_by_req_id[req]=ticker
    client._active_market_req_ids.add(req)
    if kind=='EXECUTIONS':
        client._executions_event.clear();client._executions_snapshot=[NS(orderId=1)]
    if kind=='POSITIONS_MULTI':
        client._position_queries[req]={'event':event,'status':'PARTIAL'}
    _discovered_order(client,'openOrder',req)
    assert req not in client._request_type_by_req_id
    assert client._request_id_conflicted(req)
    assert req not in client._historical_data and req not in client._contract_details
    assert req not in client._scanner_rows and req not in client._account_summary_rows
    assert req not in client._market_data and req not in client._active_market_req_ids
    assert not ticker.snapshotEnd and ticker.last is None
    if kind in event_maps:assert event.is_set() and req not in event_maps[kind]
    if kind=='EXECUTIONS':assert client._executions_event.is_set() and not client._executions_snapshot
    if kind=='POSITIONS_MULTI':assert event.is_set() and client._position_queries[req]['status']=='FAILED'
    client.error(req,321,'test ambiguous request error')
    client.error(req,103,'test ambiguous order error')
    assert req not in client._order_errors and not client._order_status_events[req].is_set()
    assert client._broker_error_events[-1]['code']==103  # diagnostic retained, not misassigned
    # Genuine typed order facts remain authoritative; late request data cannot return.
    client.orderStatus(req,'Submitted',0,1,0,0,0,0,0,'',0)
    assert client._order_status[req]['status']=='Submitted'
    client.historicalData(req,NS(close=99));client.historicalDataEnd(req,'','')
    client.contractDetails(req,NS(contract=NS(symbol='AAPL',conId=1)));client.contractDetailsEnd(req)
    client.accountSummary(req,'TEST','AvailableFunds','100','USD');client.accountSummaryEnd(req)
    client.scannerData(req,1,NS(contract=NS(symbol='AAPL')),'','','','');client.scannerDataEnd(req)
    assert req not in client._historical_data and req not in client._contract_details
    assert req not in client._scanner_rows and req not in client._account_summary_rows
    client._request_context_by_req_id.clear()  # bounded context eviction does not undo quarantine
    client.error(req,321,'test late error after metadata eviction')
    assert req not in client._order_errors
    assert client._order_status[req]['status']=='Submitted'


@pytest.mark.parametrize('kind', ['HISTORICAL_DATA','CONTRACT_DETAILS','SCANNER_DATA',
                                  'ACCOUNT_SUMMARY','EXECUTIONS'])
def test_colliding_read_interfaces_raise_unavailable(client,monkeypatch,kind):
    from ibapi.client import EClient
    def discover(req,*args):_discovered_order(client,'openOrder',req)
    if kind=='HISTORICAL_DATA':
        monkeypatch.setattr(EClient,'reqHistoricalData',lambda self,req,*args:discover(req))
        call=lambda:client.reqHistoricalData(NS(symbol='AAPL'))
    elif kind=='CONTRACT_DETAILS':
        client.reqContractDetails=discover
        call=lambda:client.resolve_contract('AAPL')
    elif kind=='SCANNER_DATA':
        client.reqScannerSubscription=discover
        client.cancelScannerSubscription=lambda *args:None
        call=lambda:client.reqScannerData(NS())
    elif kind=='ACCOUNT_SUMMARY':
        client.reqAccountSummary=discover;client.cancelAccountSummary=lambda *args:None
        call=client.get_account_summary
    else:
        client.reqExecutions=discover
        call=client.executions
    with pytest.raises(RuntimeError,match='ownership is ambiguous'):call()


def test_colliding_market_snapshot_cannot_supply_cached_quote_authority(client,monkeypatch):
    from ibapi.client import EClient
    client.resolve_contract=lambda *args:NS(contract=NS(symbol='AAPL',conId=1))
    monkeypatch.setattr(EClient,'reqMktData',lambda self,req,*args:_discovered_order(client,'openOrder',req))
    monkeypatch.setattr(EClient,'cancelMktData',lambda *args:None)
    with pytest.raises(RuntimeError,match='ownership is ambiguous'):client.get_market_snapshot('AAPL')
