"""Synthetic audit callbacks only; no socket, broker inquiry or mutation is allowed."""
from types import SimpleNamespace as NS

import pytest
from ibapi.client import EClient
from ibapi.decoder import Decoder
from ibapi.message import IN

from scripts.certification import pr1090_terminal_observation_supervisor as supervisor
from src.adapters.brokers.ibkr import ibkr_client as native
from src.config import runtime_config
from src.execution.execution_engine import ExecutionEngine


@pytest.fixture(autouse=True)
def hard_guard(monkeypatch, tmp_path):
    monkeypatch.setenv('IBKR_ORDER_ID_STATE_PATH', str(tmp_path/'synthetic-order-state.json'))
    violations = []
    def forbidden(*args, **kwargs):
        violations.append(True)
        raise AssertionError('No real connect, broker request, mutation or execution')
    for name in ('connect', 'reqAllOpenOrders', 'reqOpenOrders', 'reqPositions',
                 'reqPositionsMulti', 'reqHistoricalData', 'reqMktData', 'reqScannerSubscription',
                 'reqContractDetails', 'reqAccountSummary', 'reqExecutions',
                 'placeOrder', 'cancelOrder', 'reqGlobalCancel'):
        monkeypatch.setattr(EClient, name, forbidden)
    for name in ('connect', 'placeOrder', 'cancelOrder', 'reqGlobalCancel', 'submit_order'):
        monkeypatch.setattr(native.IbkrClient, name, forbidden)
    monkeypatch.setattr(ExecutionEngine, 'execute_trade', forbidden)
    monkeypatch.setattr(runtime_config, 'resolve_ibkr_connection', lambda:('offline',0,999,'READ_ONLY'))
    yield
    assert not violations


@pytest.fixture
def audits(monkeypatch):
    original = native.IbkrClient
    clients = []
    def build(scenario):
        c = original('offline', 0, 999, 10, 'DELAYED', True)
        assert c.wrapper is c  # Actual SDK callback owner, not an adapter.
        c.connected = False
        c.alive = False
        c.sent = 0
        c.waits = []
        c.closed = False
        c._thread = NS(is_alive=lambda:c.alive)
        event = c._open_orders_event
        def connect():
            c.connected = scenario != 'not_connected'
            c.alive = scenario != 'no_reader'
            event.set()  # Pre-query stale completion MUST be cleared.
        def dispatch():
            c.sent += 1
            assert not event.is_set()
            if scenario == 'dispatch_error':
                raise RuntimeError('Synthetic dispatch failure')
        def wait(timeout):
            c.waits.append(timeout)
            assert timeout == 10  # No wait extension or retry.
            if scenario == 'partial':
                c.openOrder(1, NS(symbol='SYNTH'), NS(), NS(status='Submitted'))
            if scenario == 'error':
                c.error(-1, 321, 'Synthetic query rejection')
            if scenario in {'empty', 'populated', 'disconnect_end', 'reader_exit_end'}:
                if scenario == 'populated':
                    c.openOrder(1, NS(symbol='SYNTH'), NS(), NS(status='Submitted'))
                # Dispatch through the installed SDK decoder into native wrapper.
                Decoder(c, 151).interpret([str(IN.OPEN_ORDER_END).encode(), b'1'])
            if scenario == 'disconnect_end':
                c.connected = False
                c.connectionClosed()
            if scenario == 'reader_exit_end':
                c.alive = False
            if callable(scenario):
                scenario(c)
            return event.is_set()
        def disconnect():
            c.closed = True
            c.connected = c.alive = False
        monkeypatch.setattr(c, 'connect', connect)
        monkeypatch.setattr(c, 'is_connected', lambda:c.connected)
        monkeypatch.setattr(c, 'reqAllOpenOrders', dispatch)
        monkeypatch.setattr(c, 'disconnect', disconnect)
        monkeypatch.setattr(event, 'wait', wait)
        return c
    def run(scenario):
        c = build(scenario)
        clients.append(c)
        monkeypatch.setattr(native, 'IbkrClient', lambda **kwargs:c)
        result = supervisor.final_broker_audit()
        assert c.closed and result['disconnected']
        return c, result
    return run


@pytest.mark.parametrize('scenario,count',[('empty',0),('populated',1)])
def test_completed_native_decoder_inventory(audits,scenario,count):
    c,r = audits(scenario)
    assert r['query_completed'] and r['end_received'] and r['open_orders_count'] == count
    assert c.sent == 1 and c.waits == [10]


@pytest.mark.parametrize('scenario',['not_connected','no_reader','disconnect_end','reader_exit_end'])
def test_inactive_transport_cannot_certify_final_inventory(audits,scenario):
    c,r = audits(scenario)
    assert not r['query_completed'] and 'open_orders_count' not in r
    assert c.sent == int(scenario.endswith('_end'))
    assert c.waits == ([10] if c.sent else [])


@pytest.mark.parametrize('scenario',['no_end','partial','error','dispatch_error'])
def test_incomplete_and_error_outcomes_stay_unknown(audits,scenario):
    c,r = audits(scenario)
    assert not r['query_completed'] and 'open_orders_count' not in r
    assert c.sent == 1
    if scenario == 'error':
        assert r['broker_errors'][-1]['code'] == 321


def test_late_old_callback_cannot_complete_new_audit(audits):
    old,first = audits('no_end')
    assert not first['query_completed']
    def late(new):
        old.openOrderEnd()
        old.openOrder(2, NS(symbol='SYNTH'), NS(), NS(status='Submitted'))
        assert old._open_orders_event.is_set()
        assert not new._open_orders_event.is_set() and not new._open_orders_snapshot
    new,second = audits(late)
    assert old is not new and old.wrapper is old and new.wrapper is new
    assert not second['query_completed'] and 'open_orders_count' not in second


def test_opt_in_observer_uses_actual_audit_client_once_and_cannot_supply_completion(monkeypatch,audits):
    from src.core import acquisition
    # Keep the fixture's immediate synthetic wait while checking the real owner's
    # opt-in stop-aware wait receives exactly the unchanged ten-second bound.
    waits=[]
    monkeypatch.setattr(acquisition,'wait_event',lambda event,timeout:waits.append(timeout) or event.wait(timeout))
    seen=[]
    class Observer:
        def __init__(self,c):seen.append(c);self.entered=False;self.closed=False
        def __enter__(self):self.entered=True;return self
        def close(self):self.closed=True
    original=supervisor.final_broker_audit
    observers=[]
    def factory(c):
        o=Observer(c);observers.append(o);return o
    monkeypatch.setattr(supervisor,'final_broker_audit',lambda:original(observer_factory=factory))
    c,r=audits('no_end')
    assert seen==[c] and c.sent==1 and waits==[10]
    assert observers[0].entered and observers[0].closed
    assert not r['query_completed'] and 'open_orders_count' not in r


def test_order_audit_observer_close_failure_does_not_rewrite_authority(monkeypatch,audits):
    from src.core import acquisition
    monkeypatch.setattr(acquisition,'wait_event',lambda event,timeout:event.wait(timeout))
    original=supervisor.final_broker_audit
    class Observer:
        def __enter__(self):return self
        def close(self):raise RuntimeError('PRIVATE_PAYLOAD')
    monkeypatch.setattr(supervisor,'final_broker_audit',lambda:original(observer_factory=lambda c:Observer()))
    c,r=audits('empty')
    assert r['query_completed'] and r['open_orders_count']==0 and r['disconnected']
    assert r['observer_cleanup_error_type']=='RuntimeError' and c.sent==1


def test_opt_in_audit_propagates_stop_and_still_disconnects(monkeypatch):
    from src.core import acquisition
    clients=[]
    class Client:
        def __init__(self,**kw):
            clients.append(self);self.connected=False;self.sent=0
            self._thread=NS(is_alive=lambda:self.connected)
            self._open_orders_snapshot={};self._open_orders_event=NS(clear=lambda:None)
        def connect(self):self.connected=True
        def is_connected(self):return self.connected
        def reqAllOpenOrders(self):self.sent+=1
        def disconnect(self):self.connected=False
    class Observer:
        closed=False
        def __enter__(self):return self
        def close(self):self.closed=True
    o=Observer()
    monkeypatch.setattr(native,'IbkrClient',Client)
    def stop(*args):raise acquisition.AcquisitionCancelled()
    monkeypatch.setattr(acquisition,'wait_event',stop)
    with pytest.raises(acquisition.AcquisitionCancelled):supervisor.final_broker_audit(observer_factory=lambda c:o)
    assert clients[0].sent==1 and not clients[0].connected and o.closed


@pytest.mark.parametrize('fails', [False, True])
def test_audit_owned_finalization_seam_precedes_cleanup_without_changing_authority(monkeypatch, audits, fails):
    from src.core import acquisition
    monkeypatch.setattr(acquisition, 'wait_event', lambda event, timeout: event.wait(timeout))
    original = supervisor.final_broker_audit
    seen = []
    class Observer:
        def __init__(self, client):
            self.client = client
        def __enter__(self):
            return self
        def audit_finalization(self):
            assert self.client.sent == 1 and not self.client.closed
            assert self.client._open_orders_event.is_set()
            seen.append('finalization')
            if fails:
                raise RuntimeError('PRIVATE_FINALIZATION_PAYLOAD')
        def close(self):
            assert self.client.closed
            seen.append('observer_close')
    monkeypatch.setattr(supervisor, 'final_broker_audit', lambda: original(observer_factory=Observer))
    c, result = audits('empty')
    assert seen == ['finalization', 'observer_close']
    assert result['query_completed'] and result['open_orders_count'] == 0 and result['disconnected']
    assert c.sent == 1 and c.waits == [10]
    assert ('observer_cleanup_error_type' in result) == fails
