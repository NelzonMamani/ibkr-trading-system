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
