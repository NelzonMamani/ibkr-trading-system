"""Synthetic callbacks only: active Core initialization -> native snapshot -> reconciliation."""
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import pytest
from ibapi.client import EClient

from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.adapters.brokers.ibkr.ibkr_connection_manager import IbkrConnectionConfig, IbkrConnectionManager
from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import RunMode
from src.core import orchestrator as core_module
from src.core.managers import connection_manager as manager_module
from src.core.managers.connection_manager import ConnectionManager
from src.core.orchestrator import CoreOrchestrator
from src.core.acquisition import AcquisitionCancelled, AcquisitionDeadlineExceeded, acquisition_scope
from src.execution.execution_engine import ExecutionEngine


@pytest.fixture(autouse=True)
def no_transport_or_mutations(monkeypatch, tmp_path):
    monkeypatch.setenv('IBKR_ORDER_ID_STATE_PATH', str(tmp_path/'order-state.json'))
    monkeypatch.delenv('PR1090_STOP_FILE', raising=False)
    set_config_overrides({'RUN_MODE':'READ_ONLY','RUN_MODE_EFFECTIVE':'READ_ONLY',
        'EXECUTION_ENABLED':False,'IBKR_FALLBACK_ENABLED':False,'SCANNER_DATA_SOURCE':'IBKR'})
    violations=[]
    def forbidden(*args, **kwargs):
        violations.append('forbidden transport/mutation/submission')
        raise AssertionError('No network, broker connection/inquiry, mutation or execution')
    for name in ('connect','reqPositions','cancelPositions','reqPositionsMulti','cancelPositionsMulti',
                 'reqAllOpenOrders','reqOpenOrders','placeOrder','cancelOrder','reqGlobalCancel'):
        monkeypatch.setattr(EClient, name, forbidden)
    for name in ('connect','placeOrder','cancelOrder','reqGlobalCancel'):
        monkeypatch.setattr(IbkrClient,name,forbidden)
    monkeypatch.setattr(ExecutionEngine, 'execute_trade', forbidden)
    monkeypatch.setattr(CoreOrchestrator, 'attach_broker_position_from_recovery', forbidden)
    yield
    set_config_overrides(None)
    assert not violations


@pytest.fixture
def chain(monkeypatch):
    events=[];requests=[];cancelled=[];connected=[True]
    native=IbkrClient('offline',0,999,5,'LIVE',True)
    native._managed_accounts=['SYNTHETIC_ACCOUNT']
    native._position_transport_available=True
    monkeypatch.setattr(native,'is_connected',lambda:connected[0])
    monkeypatch.setattr(native,'isConnected',lambda:connected[0])
    monkeypatch.setattr(native,'cancelPositionsMulti',lambda req:cancelled.append(req))
    # The native transport is fixture-connected; Core and facade initialization
    # remain real. Any attempt to create a real broker connection is forbidden.
    shared=IbkrConnectionManager(IbkrConnectionConfig('offline',0,999,5,'LIVE',True))
    shared._client=native
    manager=ConnectionManager(RunMode.READ_ONLY)
    monkeypatch.setattr(manager_module,'get_shared_ibkr_connection_manager',lambda:shared)
    ensure=manager.ensure_connected
    def initialize():
        events.append('initialize')
        ensure()
        assert manager.get_ibkr_client(False) is native
    monkeypatch.setattr(manager,'ensure_connected',initialize)
    assert manager.get_ibkr_client(False) is None
    core=CoreOrchestrator.__new__(CoreOrchestrator)
    core.run_mode=RunMode.READ_ONLY;core.connection_manager=manager
    core.trade_registry=NS(snapshot=lambda:[])
    core.execution_engine=NS(_relationship_orders_asof=None)
    core.trade_management_engine=None
    core._latest_position_truth_snapshot=None;core._degraded=False
    core._resolve_fill_authority_cycle=lambda:{'execution_stalled':False,'stalled_symbols':[]}
    core._resolve_lifecycle_authority_cycle=lambda:{}
    core._startup_recovery_allows_strategy_execution=lambda:False
    core._trace_halt=lambda **kwargs:events.append('connectivity_failure')
    real_reconcile=core_module.reconcile_position_truth
    def reconcile(**kwargs):
        events.append('reconcile')
        return real_reconcile(**kwargs)
    monkeypatch.setattr(core_module,'reconcile_position_truth',reconcile)
    def request(req,account,model):
        assert manager.get_ibkr_client(False) is native
        events.append('snapshot');requests.append(req)
        native.positionMultiEnd(req)
    monkeypatch.setattr(native,'reqPositionsMulti',request)
    return NS(core=core,manager=manager,shared=shared,native=native,events=events,
              requests=requests,cancelled=cancelled,connected=connected)


def pipeline(x):
    now=datetime.now(timezone.utc)
    return x.core._run_manager_pipeline(cycle_started_at=now,ny_time=now,uk_time=now,session_phase='RTH_MID')


def retired(x):
    assert not x.native._position_queries
    assert 'POSITIONS_MULTI' not in x.native._request_type_by_req_id.values()


def test_active_manager_initializes_before_authoritative_empty_snapshot(chain):
    x=chain
    assert pipeline(x) is False  # Stop fixture after real position/recovery owners.
    assert x.events==['initialize','snapshot','reconcile']
    snapshot=x.core._latest_position_truth_snapshot
    assert snapshot.snapshot_status=='HEALTHY' and not snapshot.broker_positions
    assert not x.core._latest_position_truth_verdict.block_new_entries
    assert len(x.requests)==1 and x.cancelled==x.requests
    assert x.manager.optional_client is x.shared.get_market_data_client()
    assert not hasattr(x.manager.optional_client,'position_snapshot')  # Never a list/facade fallback.
    retired(x)


def test_stop_inside_owned_snapshot_propagates_and_cleans_up(chain,monkeypatch):
    x=chain;stop=[False]
    def request(req,*args):
        x.requests.append(req);stop[0]=True
    monkeypatch.setattr(x.native,'reqPositionsMulti',request)
    with pytest.raises(AcquisitionCancelled),acquisition_scope(lambda:stop[0]):
        x.native.position_snapshot(timeout_seconds=0)
        pytest.fail('Position snapshot returned after stop instead of propagating it')
    assert x.cancelled==x.requests and len(x.requests)==1
    retired(x)


def set_mode(x, mode):
    x.core.run_mode=mode;x.manager.run_mode=mode
    set_config_overrides({'RUN_MODE':mode.value,'RUN_MODE_EFFECTIVE':mode.value,
        'EXECUTION_ENABLED':mode==RunMode.LIVE,'IBKR_FALLBACK_ENABLED':False,'SCANNER_DATA_SOURCE':'IBKR'})


@pytest.mark.parametrize('mode',[RunMode.READ_ONLY,RunMode.PAPER,RunMode.LIVE])
def test_initialized_nonempty_snapshot_reaches_reconciliation_and_global_veto(chain,monkeypatch,mode,capsys):
    x=chain;set_mode(x,mode)
    positions={f'SYNTH_{i}':(.25 if i%2 else -.5) for i in range(5)}
    def request(req,account,model):
        x.events.append('snapshot');x.requests.append(req)
        for con_id,(symbol,quantity) in enumerate(positions.items(),1):
            x.native.positionMulti(req,account,model,NS(symbol=symbol,conId=con_id),quantity,10)
        x.native.positionMultiEnd(req)
    monkeypatch.setattr(x.native,'reqPositionsMulti',request)
    assert pipeline(x) is False
    snapshot=x.core._latest_position_truth_snapshot;v=x.core._latest_position_truth_verdict
    assert x.events==['initialize','snapshot','reconcile']
    assert {s:p.quantity for s,p in snapshot.broker_positions.items()}==positions
    assert len(snapshot.mismatches)==v.critical_mismatch_count==5 and v.block_new_entries
    assert CoreOrchestrator._apply_position_truth_entry_guard([NS(symbol='UNRELATED')],v)==[]
    assert 'POSITION_TRUTH_BLOCK_NEW_ENTRIES' in capsys.readouterr().out
    assert x.cancelled==x.requests and len(x.requests)==1
    retired(x)


def test_complete_matching_snapshot_uses_existing_system_reconciliation(chain,monkeypatch):
    x=chain
    x.core.trade_registry=NS(snapshot=lambda:[NS(symbol='SYNTH',quantity=1.25,direction='LONG')])
    def request(req,account,model):
        x.requests.append(req)
        x.native.positionMulti(req,account,model,NS(symbol='SYNTH',conId=123),1.25,10)
        x.native.positionMultiEnd(req)
    monkeypatch.setattr(x.native,'reqPositionsMulti',request)
    pipeline(x)
    assert x.core._latest_position_truth_verdict.healthy
    assert x.core._latest_position_truth_snapshot.matched_symbols==['SYNTH']
    assert x.cancelled==x.requests
    retired(x)


@pytest.mark.parametrize('kind',['missing_interface','list_only','partial','timeout','error','disconnect'])
def test_initialized_connection_is_not_snapshot_completion(chain,monkeypatch,kind):
    x=chain
    if kind=='missing_interface':
        monkeypatch.setattr(x.native,'position_snapshot',None)
        monkeypatch.setattr(x.native,'positions',lambda:pytest.fail('No legacy positions/list adapter'))
    elif kind=='list_only':
        monkeypatch.setattr(x.native,'position_snapshot',lambda:[])
    else:
        original=x.native.position_snapshot
        monkeypatch.setattr(x.native,'position_snapshot',lambda:original(timeout_seconds=0))
        def request(req,account,model):
            x.requests.append(req)
            if kind=='partial':
                x.native.positionMulti(req,account,model,NS(symbol='SYNTH',conId=123),5,10)
            if kind=='error':x.native.error(req,321,'Synthetic position rejection')
            if kind=='disconnect':x.native.connectionClosed()
        monkeypatch.setattr(x.native,'reqPositionsMulti',request)
    pipeline(x)
    snapshot=x.core._latest_position_truth_snapshot;v=x.core._latest_position_truth_verdict
    assert x.events[0]=='initialize' and x.events[-1]=='reconcile'
    assert snapshot.snapshot_status=='UNKNOWN' and not snapshot.broker_positions and not snapshot.system_positions
    assert not v.healthy and v.block_new_entries and v.require_reconciliation
    assert snapshot.broker_positions.status=={'missing_interface':'UNAVAILABLE','list_only':'UNAVAILABLE',
        'partial':'TIMEOUT','timeout':'TIMEOUT','error':'FAILED','disconnect':'DISCONNECTED'}[kind]
    assert len(x.requests)==(0 if kind in {'missing_interface','list_only'} else 1)
    if kind!='disconnect':assert x.cancelled==x.requests
    else:assert not x.cancelled  # Never cancel into a disconnected/replaced session.
    retired(x)


@pytest.mark.parametrize('mode',[RunMode.READ_ONLY,RunMode.PAPER,RunMode.LIVE])
def test_failed_initialization_cannot_query_stale_client_or_refresh_relationships(chain,monkeypatch,mode):
    x=chain;set_mode(x,mode)
    def failed():
        x.events.append('initialize');raise RuntimeError('Synthetic initialization failure')
    monkeypatch.setattr(x.manager,'ensure_connected',failed)
    monkeypatch.setattr(x.manager,'get_ibkr_client',lambda *a,**kw:pytest.fail('Cannot use client after failed initialization'))
    x.core.trade_management_engine=NS(_relationship_plans={'SYNTH':object()},reconcile_broker_snapshot=lambda **kw:
        x.events.append('relationship_incomplete') if kw['complete'] is False else pytest.fail('False complete'))
    x.core.execution_engine.refresh_relationship_order_snapshot=lambda:pytest.fail('No reconnect/query through relationship refresh')
    assert pipeline(x) is False
    assert x.events==['initialize','connectivity_failure','reconcile','relationship_incomplete']
    assert x.core._latest_position_truth_snapshot.snapshot_status=='UNKNOWN'
    assert x.core._latest_position_truth_verdict.block_new_entries and not x.requests
    retired(x)


def test_disconnected_followup_keeps_prior_exposure_unknown_not_empty(chain,monkeypatch):
    x=chain
    def request(req,account,model):
        x.requests.append(req)
        x.native.positionMulti(req,account,model,NS(symbol='SYNTH',conId=123),.25,10)
        x.native.positionMultiEnd(req)
    monkeypatch.setattr(x.native,'reqPositionsMulti',request)
    pipeline(x)
    def failed():raise RuntimeError('Synthetic connection loss')
    monkeypatch.setattr(x.manager,'ensure_connected',failed)
    pipeline(x)
    snapshot=x.core._latest_position_truth_snapshot
    assert snapshot.snapshot_status=='UNKNOWN' and snapshot.broker_positions['SYNTH'].quantity==.25
    assert x.core._latest_position_truth_verdict.block_new_entries
    assert len(x.requests)==1


def test_sim_never_initializes_or_queries_broker(chain,monkeypatch):
    x=chain;set_mode(x,RunMode.SIM)
    monkeypatch.setattr(x.manager,'ensure_connected',lambda:pytest.fail('SIM must not initialize broker'))
    monkeypatch.setattr(x.manager,'get_ibkr_client',lambda *a,**kw:pytest.fail('SIM must not query broker'))
    assert pipeline(x) is False
    assert not x.events and not x.requests and x.core._latest_position_truth_verdict.healthy


@pytest.mark.parametrize('kind',['stop','deadline'])
def test_initialization_control_flow_is_not_converted_to_connectivity_failure(chain,monkeypatch,kind):
    x=chain;error=AcquisitionCancelled if kind=='stop' else AcquisitionDeadlineExceeded
    def abort():
        x.events.append('initialize');raise error()
    monkeypatch.setattr(x.manager,'ensure_connected',abort)
    with pytest.raises(error):pipeline(x)
    assert x.events==['initialize'] and x.core._latest_position_truth_snapshot is None
    assert not x.requests and not x.cancelled


def test_stop_before_initialization_does_not_query_or_reconcile(chain):
    x=chain;stop=[False]
    with pytest.raises(AcquisitionCancelled),acquisition_scope(lambda:stop[0]):
        stop[0]=True;pipeline(x)
        pytest.fail('Stopped pipeline returned')
    assert not x.events and x.core._latest_position_truth_snapshot is None
    assert not x.requests and not x.cancelled


def test_stop_between_registration_and_dispatch_retires_without_sending_or_cancelling(chain,monkeypatch):
    x=chain;stop=[False];register=x.native._register_request
    def registering(*args):
        register(*args);stop[0]=True
    monkeypatch.setattr(x.native,'_register_request',registering)
    with pytest.raises(AcquisitionCancelled),acquisition_scope(lambda:stop[0]):
        x.native.position_snapshot()
        pytest.fail('Stopped snapshot returned')
    assert not x.requests and not x.cancelled
    retired(x)


@pytest.mark.parametrize("error",[AcquisitionCancelled,AcquisitionDeadlineExceeded])
def test_snapshot_control_flow_propagates_despite_owned_cancel_failure(chain,monkeypatch,error):
    x=chain
    def request(req,*args):
        x.requests.append(req);raise error()
    def cancel(req):
        x.cancelled.append(req);raise RuntimeError('Synthetic cancellation transport failure')
    monkeypatch.setattr(x.native,'reqPositionsMulti',request)
    monkeypatch.setattr(x.native,'cancelPositionsMulti',cancel)
    with pytest.raises(error):x.native.position_snapshot()
    assert x.cancelled==x.requests and len(x.requests)==1
    retired(x)


@pytest.mark.parametrize('error',[AcquisitionCancelled,AcquisitionDeadlineExceeded])
def test_actual_core_collector_chain_propagates_snapshot_control_flow(chain,monkeypatch,error):
    x=chain
    def request(req,*args):
        x.requests.append(req);x.events.append('snapshot');raise error()
    monkeypatch.setattr(x.native,'reqPositionsMulti',request)
    with pytest.raises(error):
        pipeline(x)
        pytest.fail('Core swallowed acquisition control flow')
    assert x.events==['initialize','snapshot'] and x.core._latest_position_truth_snapshot is None
    assert x.cancelled==x.requests and len(x.requests)==1
    retired(x)


def test_failed_live_initialization_reconciles_unavailable_then_halts_before_management(chain,monkeypatch):
    x=chain;set_mode(x,RunMode.LIVE)
    def failed():raise RuntimeError('Synthetic connection loss')
    monkeypatch.setattr(x.manager,'ensure_connected',failed)
    x.core._startup_recovery_allows_strategy_execution=lambda:True
    x.core._run_position_management_tick=lambda *args:pytest.fail('LIVE management after failed initialization')
    x.core._autonomous_recovery_allows_new_entries=lambda **kw:False
    assert pipeline(x) is False
    assert x.core._latest_position_truth_snapshot.snapshot_status=='UNKNOWN'
    assert x.core._latest_position_truth_verdict.block_new_entries and not x.requests


def test_disconnect_between_registration_and_dispatch_retires_without_wire_work(chain,monkeypatch):
    x=chain;register=x.native._register_request
    def registering(*args):
        register(*args);x.native.connectionClosed()
    monkeypatch.setattr(x.native,'_register_request',registering)
    assert x.native.position_snapshot().status=='DISCONNECTED'
    assert not x.requests and not x.cancelled
    retired(x)


@pytest.mark.parametrize('error',[AcquisitionCancelled,AcquisitionDeadlineExceeded])
@pytest.mark.parametrize('cleanup_fails',[False,True])
def test_shared_initialization_owner_retires_unpublished_client_and_preserves_control_flow(monkeypatch,error,cleanup_fails):
    from src.adapters.brokers.ibkr import ibkr_connection_manager as owner_module
    created=[];cleaned=[]
    class SyntheticClient:
        def __init__(self,**kwargs):created.append(self)
        def connect(self):raise error()  # Pure local lifecycle simulation; real connects forbidden.
        def disconnect(self):
            cleaned.append(self)
            if cleanup_fails:raise RuntimeError("Synthetic cleanup failure")
        def is_connected(self):return False
    monkeypatch.setattr(owner_module,'IbkrClient',SyntheticClient)
    owner=IbkrConnectionManager(IbkrConnectionConfig('offline',7497,999,5,'LIVE',True,max_client_id_retries=1))
    with pytest.raises(error):owner.ensure_connected()
    assert created==cleaned and len(created)==1
    assert owner.existing_client is None and not owner.is_connected()


def test_shared_owner_only_retries_configured_conflict_after_cleaning_local_attempt(monkeypatch):
    from src.adapters.brokers.ibkr import ibkr_connection_manager as owner_module
    created=[];cleaned=[]
    class SyntheticClient:
        def __init__(self,client_id,**kwargs):
            self.client_id=client_id;self.connected=False;created.append(self)
        def connect(self):
            if self.client_id==999:raise RuntimeError('client id 999 already in use')
            self.connected=True
        def disconnect(self):cleaned.append(self);self.connected=False
        def is_connected(self):return self.connected
    monkeypatch.setattr(owner_module,'IbkrClient',SyntheticClient)
    owner=IbkrConnectionManager(IbkrConnectionConfig('offline',7497,999,5,'LIVE',True,max_client_id_retries=2))
    current=owner.ensure_connected()
    assert [c.client_id for c in created]==[999,1000] and cleaned==created[:1]
    assert current is owner.ensure_connected() is owner.existing_client
    assert cleaned==created[:1]  # No cleanup of the successfully published owner.
    owner.disconnect()
    assert cleaned==created and owner.existing_client is None


def test_shared_owner_cannot_retry_over_unknown_failed_client_cleanup(monkeypatch):
    from src.adapters.brokers.ibkr import ibkr_connection_manager as owner_module
    created=[];cleaned=[]
    class SyntheticClient:
        def __init__(self,**kwargs):created.append(self)
        def connect(self):raise RuntimeError('client id 999 already in use')
        def disconnect(self):cleaned.append(self);raise RuntimeError('Synthetic cleanup failure')
        def is_connected(self):return False
    monkeypatch.setattr(owner_module,'IbkrClient',SyntheticClient)
    owner=IbkrConnectionManager(IbkrConnectionConfig('offline',7497,999,5,'LIVE',True,max_client_id_retries=2))
    with pytest.raises(RuntimeError,match='SYSTEM NOT SAFE'):owner.ensure_connected()
    assert created==cleaned and len(created)==1 and owner.existing_client is None


@pytest.mark.parametrize('error',[AcquisitionCancelled,AcquisitionDeadlineExceeded])
def test_initialization_abort_uses_native_reader_cleanup_without_real_connection(monkeypatch,error):
    from src.adapters.brokers.ibkr import ibkr_connection_manager as owner_module
    created=[];closed=[];joined=[];failure=error()
    class SyntheticReader:
        alive=True
        def is_alive(self):return self.alive
        def join(self,timeout):joined.append(timeout);self.alive=False
    class SyntheticNative(IbkrClient):
        def __init__(self,**kwargs):super().__init__(**kwargs);created.append(self)
        def connect(self):self._thread=SyntheticReader();raise failure
    monkeypatch.setattr(owner_module,'IbkrClient',SyntheticNative)
    monkeypatch.setattr(EClient,'disconnect',lambda self:closed.append(self))
    owner=IbkrConnectionManager(IbkrConnectionConfig('offline',7497,999,5,'LIVE',True,max_client_id_retries=1))
    with pytest.raises(error) as caught:owner.ensure_connected()
    assert caught.value is failure
    assert created==closed and len(created)==1 and joined==[2]
    native=created[0]
    assert native._stop_event.is_set() and not native._thread.is_alive()
    assert not native._position_queries and not native._historical_states
    assert owner.existing_client is None


@pytest.mark.parametrize('stage',['handshake_return','account_resolution'])
@pytest.mark.parametrize('control',['stop','deadline'])
def test_shared_initialization_rechecks_control_before_and_after_account_resolution(monkeypatch,stage,control):
    from src.adapters.brokers.ibkr import ibkr_connection_manager as owner_module
    from src.core import acquisition
    created=[];cleaned=[];account_calls=[];stop=[False];seconds=[0.]
    monkeypatch.setattr(acquisition,'time',NS(monotonic=lambda:seconds[0]))
    def abort():
        if control=='stop':stop[0]=True
        else:seconds[0]=61.
    class SyntheticClient:
        def __init__(self,**kwargs):self.connected=False;created.append(self)
        def connect(self):
            self.connected=True
            if stage=='handshake_return':abort()
        def get_primary_account(self):
            account_calls.append(True)
            if stage=='account_resolution':abort()
            return 'SYNTHETIC_ACCOUNT'
        def disconnect(self):self.connected=False;cleaned.append(self)
        def is_connected(self):return self.connected
    monkeypatch.setattr(owner_module,'IbkrClient',SyntheticClient)
    owner=IbkrConnectionManager(IbkrConnectionConfig('offline',7497,999,5,'LIVE',True,max_client_id_retries=1))
    error=AcquisitionCancelled if control=='stop' else AcquisitionDeadlineExceeded
    with pytest.raises(error),acquisition_scope(lambda:stop[0]),acquisition.acquisition_deadline(60.):
        owner.ensure_connected()
        pytest.fail('Initialization returned after control flow became pending')
    assert created==cleaned and len(created)==1 and owner.existing_client is None
    assert len(account_calls)==int(stage=='account_resolution')
