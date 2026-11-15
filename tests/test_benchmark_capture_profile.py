"""Synthetic SDK facts through actual capture/reference/history/quote/ATR owners."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS
import json
import io

import pytest
from ibapi.client import EClient
from ibapi.contract import Contract, ContractDetails

from scripts.certification import pr1040_real_readonly_runtime_observation_adapter as capture
from scripts.certification import pr1090_terminal_observation_supervisor as supervisor
from src.adapters.brokers.ibkr import ibkr_client as native_module
from src.adapters.brokers.ibkr.ibkr_connection_manager import IbkrConnectionManager, IbkrConnectionConfig
from src.adapters.data import historical_data_provider as historical
from src.ibkr import market_data_client as market_module
from src.market_data import reference_resolver as reference_module
from src.market_data.market_data_snapshot_manager import MarketDataSnapshotManager
from src.market_data import market_data_snapshot_manager as snapshot_module
from src.config import config_resolver as cfg
from src.ibkr import shutdown_evidence as shutdown
from test_post_pr1090_market_data_authority import native, native_ticks, source_bound_native_snapshot
from test_history_completion_ownership import prohibit_acquisition_and_mutation
from test_next_session_catalyst import receipt
from test_readonly_reviewed_calendar import owned, scrub
from test_pr1090_evidence_safety import verified_process

NOW = datetime(2026, 11, 16, 14, 50, 5, tzinfo=timezone.utc)
OPEN = NOW.replace(minute=30, second=0)

class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is None else NOW.astimezone(tz)


@pytest.fixture
def component(native, monkeypatch, tmp_path):
    for name in ('FORCE_SESSION','SESSION_OVERRIDE','MARKET_SESSION_OVERRIDE','PR1090_STOP_FILE',
                 'READONLY_BENCHMARK_CAPTURE'):
        monkeypatch.delenv(name, raising=False)
    cfg.set_config_overrides(dict(RUN_MODE='READ_ONLY', RUN_MODE_EFFECTIVE='READ_ONLY',
        IBKR_READONLY_ENABLED=True, IBKR_API_WRITE_ALLOWED=False, IBKR_ORDER_SUBMISSION_ENABLED=False,
        MARKET_SESSION_COVERAGE=json.dumps(receipt('2026-11-13','2026-11-16')),
        MARKET_HOLIDAYS=set(), MARKET_HALF_DAYS=set(), SESSION_PHASE_OVERRIDE=None,
        IBKR_MARKET_DATA_TYPE='LIVE'))
    for module in (capture, native_module, market_module, historical, snapshot_module):
        monkeypatch.setattr(module,'datetime',Clock)
    monkeypatch.setattr(reference_module,'get_us_eastern_now',lambda:NOW.astimezone(reference_module.ZoneInfo('America/New_York')))
    native = native_module.IbkrClient("127.0.0.1",7497,71,0.01,"LIVE",True)
    native.clientId=71
    native._position_connection_epoch=23
    monkeypatch.setattr(native,'isConnected',lambda:True)
    monkeypatch.setattr(native,'is_connected',lambda:True)
    native.managedAccounts('DU000000001')
    sent=[]
    fault=NS(kind=None)
    transport=NS(connected=True)
    monkeypatch.setattr(native,"isConnected",lambda:transport.connected)
    monkeypatch.setattr(native,"is_connected",lambda:transport.connected)
    monkeypatch.setattr(EClient,"disconnect",lambda self:setattr(transport,"connected",False))
    def qualify(self,request_id,requested):
        sent.append(('qualify',requested.symbol))
        supplied=Contract()
        for key,value in dict(symbol=requested.symbol,secType='STK',currency='USD',exchange='SMART',
            primaryExchange='ARCA' if requested.symbol=='SPY' else 'NASDAQ',
            conId=123 if requested.symbol=='SPY' else 456,localSymbol=requested.symbol,tradingClass=requested.symbol).items():
            setattr(supplied,key,value)
        detail=ContractDetails();detail.contract=supplied;detail.longName=requested.symbol+' ETF'
        if fault.kind=='foreign':supplied.symbol='FOREIGN'
        if fault.kind=='missing_type':supplied.secType=''
        if fault.kind=='missing_symbol':supplied.symbol=''
        self.contractDetails(request_id,detail)
        if fault.kind=='ambiguous':self.contractDetails(request_id,detail)
        self.contractDetailsEnd(request_id)
    def history(self,request_id,contract,end,duration,size,what,rth,fmt,streaming,options):
        sent.append(('history',contract.symbol,size,end,duration,rth,fmt))
        if size=='1 day':
            bars=[] if fault.kind=='empty_daily' else [NS(date='20261113',open=99.,high=101.,low=98.,close=100.,volume=1_000_000)]
        else:
            bars=[NS(date=str(int((OPEN+timedelta(minutes=index)).timestamp())),open=100.+index*.01,
                high=100.5+index*.01,low=99.5+index*.01,close=100.+index*.01,volume=1000) for index in range(20)]
            if fault.kind=='forming':bars[-1].date=str(int((NOW.replace(second=0)).timestamp()))
            if fault.kind=='gap':bars.pop(5)
        for bar in bars:self.historicalData(request_id,bar)
        if fault.kind=='interrupt':
            from src.core.acquisition import AcquisitionCancelled
            raise AcquisitionCancelled()
        self.historicalDataEnd(request_id,'raw-start','raw-end')
        if size=='1 day' and fault.kind=='changed_epoch':self._position_connection_epoch += 1
    def quote(self,request_id,contract,*args):
        sent.append(('quote',contract.symbol))
        self.marketDataType(request_id,3 if fault.kind=='delayed' else 1)
        kinds=(66,67,68,75) if fault.kind=='delayed' else (1,2,4,9)
        for kind,value in zip(kinds,(100.18,100.20,100.19,100.0)):
            if fault.kind=="missing_last" and kind==4:continue
            self.tickPrice(request_id,kind,value,None)
        self.tickSize(request_id,74 if fault.kind=='delayed' else 8,10000)
        stamp=NOW+timedelta(seconds=1) if fault.kind=='future' else NOW-timedelta(days=1) if fault.kind=='stale' else NOW
        self.tickString(request_id,45,str(int(stamp.timestamp())))
        self.tickSnapshotEnd(request_id)
    monkeypatch.setattr(EClient,'reqContractDetails',qualify)
    monkeypatch.setattr(EClient,'reqHistoricalData',history)
    monkeypatch.setattr(EClient,'reqMktData',quote)
    monkeypatch.setattr(EClient,'cancelHistoricalData',lambda *args:None)
    manager=IbkrConnectionManager(IbkrConnectionConfig('127.0.0.1',7497,71,1,'LIVE',True))
    def connect_transport():
        # Synthetic connection publication only; no actual connect/manager IO.
        manager._client=native;manager._connected_client_id=71;manager._connection_generation=1
        return native
    monkeypatch.setattr(manager,'_connect_locked',connect_transport)
    monkeypatch.setattr(historical,'get_shared_ibkr_connection_manager',lambda **kw:manager)
    yield NS(manager=manager,native=native,sent=sent,fault=fault,transport=transport,private=tmp_path/'private',shared=tmp_path/'e')
    cfg.set_config_overrides(None)


def run(component):
    return capture.collect_benchmark_capture(manager=component.manager,
        private_directory=component.private,shared_directory=component.shared)


def test_actual_capture_owners_preserve_exact_source_and_measurement(component):
    result=run(component)
    assert result['capture_completed'] and result['retention_complete']
    assert [row['status'] for row in result['assets']]==['MEASUREMENT_RECORDED']*2
    assert [x[:2] for x in component.sent]==[(kind,symbol) for symbol in ('SPY','QQQ')
        for kind in ('qualify','history','history','quote')]
    for symbol in ('SPY','QQQ'):
        daily=json.loads((component.private/(symbol+'-daily.json')).read_bytes())
        assert daily['request_spec']['duration_str']=='25 D'
        assert daily['request_spec']['end_date_time']=='20261116 14:30:00 UTC'
        raw=json.loads((component.private/(symbol+'-raw.json')).read_bytes())
        assert raw['assessed_at']=={'datetime':NOW.isoformat(),'fold':0}
        assert raw['quote_original_diagnostics']['attempts'][0]['label']=='primary'
        assert raw['opening_history']['source_bar_count']==20
        report=json.loads((component.private/(symbol+'-offline-report.json')).read_bytes())
        assert report['classification']=='MARKET_UNVERIFIED' and not report['approved_dataset']
        assert report['sessions'][0]['measurement']['admission']=='UNKNOWN'
        assert report['sessions'][0]['costs_availability']=='UNAVAILABLE'
    public=json.dumps(json.loads((component.shared/'benchmark-capture-summary.json').read_text()))
    assert '100.19' not in public and 'source_facts' not in public and 'raw-start' not in public
    assert component.manager.config.max_client_id_retries==1
    assert not component.native._historical_states


@pytest.mark.parametrize('fault',['forming','gap','delayed','future','stale','missing_last'])
def test_actual_source_refusals_preserve_original_raw_without_favorable_retry(component,fault):
    component.fault.kind=fault
    result=run(component)
    assert result['capture_completed']  # Finite collection completion, not data approval.
    assert all(row['status']=='REFUSED' for row in result['assets'])
    assert len([x for x in component.sent if x[0]=='quote'])==2
    assert len([x for x in component.sent if x[0]=='history'])==4
    assert not list(component.private.glob('*offline-input.json'))
    for symbol in ('SPY','QQQ'):
        assert (component.private/(symbol+'-raw.json')).exists()


def test_size_refusal_stops_requests_and_never_labels_truncated_input_complete(component,monkeypatch):
    monkeypatch.setattr(capture,'BENCHMARK_SOURCE_LIMIT',5000)
    with pytest.raises(capture.BenchmarkCaptureRefused,match='PRIVATE_SIZE_LIMIT'):
        run(component)
    result=json.loads((component.shared/'benchmark-capture-summary.json').read_text())
    assert not result['capture_completed'] and not result['retention_complete']
    assert not any(x[1]=='QQQ' for x in component.sent)
    assert not list(component.private.glob('*offline-input.json'))
    assert json.loads((component.private/'retention-incomplete.json').read_text())['retention_complete'] is False


def test_strict_single_attempt_uses_real_native_quote_owner_once(source_bound_native_snapshot,monkeypatch):
    f=source_bound_native_snapshot
    original=EClient.reqMktData
    def incomplete(self,request_id,contract,*args):
        f.requests.append(contract.symbol)
        self.marketDataType(request_id,3)
        self.tickSnapshotEnd(request_id)
    monkeypatch.setattr(EClient,'reqMktData',incomplete)
    snapshot,quality=f.manager.get_snapshot('AEMD',expected_client=f.native,
        expected_connection_epoch=23,single_attempt=True)
    assert len(f.requests)==1
    assert quality.data_quality_flags and not snapshot.returned_market_data_type=='LIVE'
    assert len(f.wrapper.last_snapshot_debug['attempts'])==1


def test_single_attempt_requires_strict_source_before_any_request(source_bound_native_snapshot):
    f=source_bound_native_snapshot
    with pytest.raises(RuntimeError):f.wrapper.snapshot_stock('AEMD',single_attempt=True)
    assert not f.requests and not f.qualifications


def test_capture_shutdown_profile_cannot_self_declare_weaker_hooks(tmp_path):
    proof=shutdown.ShutdownEvidence(runtime_profile=capture.BENCHMARK_PROFILE)
    proof.record('GRACEFUL_STOP_REQUESTED',completed=True);proof.record('SHUTDOWN_STARTED',completed=True)
    for name in shutdown.BENCHMARK_REQUIRED_HOOKS:proof.attempt(name,lambda:True)
    proof.record('SHUTDOWN_COMPLETE',completed=True);proof.record('TERMINAL_FLUSHED',completed=True)
    payload=proof.payload();payload.update(pid=999999,process_identity=verified_process(lambda:0).runtime_identity)
    (tmp_path/'shutdown_evidence.json').write_text(json.dumps(payload))
    result=shutdown.complete_after_process_exit(tmp_path,verified_process(lambda:0),lambda:True,
        lambda:{'query_completed':True,'disconnected':True},expected_profile=capture.BENCHMARK_PROFILE)
    assert result['passed']
    terminal=json.loads((tmp_path/'terminal_evidence.json').read_text())
    assert not shutdown.validate_terminal(terminal)['passed']
    assert shutdown.validate_terminal(terminal,expected_profile=capture.BENCHMARK_PROFILE)['passed']
    terminal['runtime_profile']='UNKNOWN'
    assert not shutdown.validate_terminal(terminal,expected_profile=capture.BENCHMARK_PROFILE)['passed']


def test_private_pipe_cap_drains_and_marks_incomplete_without_publishing_data(tmp_path,monkeypatch):
    monkeypatch.setenv('READONLY_BENCHMARK_CAPTURE',capture.BENCHMARK_PROFILE)
    monkeypatch.setattr(capture,'BENCHMARK_LOG_LIMIT',32) # Default argument stays bound; explicit sink test below.
    stream=io.StringIO('RAW-QUOTE-123\n'*(100_000))
    errors=[]
    supervisor._capture(stream,tmp_path/'stdout.log',errors)
    assert errors==['RuntimeError'] and (tmp_path/'stdout.log').stat().st_size==512*1024
    assert (tmp_path/'retention-incomplete.json').exists()


@pytest.mark.parametrize('fault',['ambiguous','foreign','missing_type','missing_symbol','empty_daily'])
def test_unqualified_or_empty_reference_never_starts_an_extra_data_route(component,fault):
    component.fault.kind=fault
    result=run(component)
    assert all(row['status']=='REFUSED' for row in result['assets'])
    assert not any(row[0]=='quote' for row in component.sent)
    daily=[row for row in component.sent if row[0]=='history']
    assert len(daily)==(2 if fault=='empty_daily' else 0)
    assert not any(row[2]=='1 min' for row in daily)
    if fault=='empty_daily':
        raw=json.loads((component.private/'SPY-raw.json').read_text())
        assert raw['daily_history']['status']=='COMPLETE_EMPTY'
        assert raw['refused_reference_fallbacks']==[{'dispatched':False,'reason':'FALLBACK_OUTSIDE_CAPTURE_SCOPE'}]


def test_source_epoch_change_refuses_without_reconnect_or_second_asset(component):
    component.fault.kind='changed_epoch'
    with pytest.raises(capture.BenchmarkCaptureRefused):run(component)
    assert not any(row[1]=='QQQ' for row in component.sent)
    assert not any(row[0]=='quote' for row in component.sent)
    raw=json.loads((component.private/'SPY-daily.json').read_text())
    assert raw['status']=='SOURCE_SCOPE_CHANGED' and raw['raw_source_bars']
    assert raw['request_spec']['duration_str']=='25 D'


def test_arbitrary_provider_exception_text_cannot_be_a_public_reason():
    assert capture._benchmark_reason(RuntimeError('PRIVATE_PROVIDER_QUOTE_123'))=='SOURCE_REFUSED'
    assert capture._benchmark_reason(capture.BenchmarkCaptureRefused('PRIVATE_PROVIDER_QUOTE_123'))=='SOURCE_REFUSED'


@pytest.mark.parametrize('argv',[
    ['python','operator','prepare'],
    ['python','-u','natural_readonly_operator.py','prepare'],
    ['python','-m','scripts.certification.pr1090_terminal_observation_supervisor'],
    ['powershell.exe','-File','C:/checkout/scripts/certification/run_natural_readonly_observation.ps1'],
])
def test_known_controller_entrypoints_are_detected_without_launch(argv):
    expected='operator' not in argv
    assert supervisor.is_observation_controller(argv) is expected


def test_offline_input_ceiling_stops_second_asset_and_reports_incomplete_retention(component,monkeypatch):
    monkeypatch.setattr(capture,'BENCHMARK_INPUT_LIMIT',100)
    with pytest.raises(capture.BenchmarkCaptureRefused,match='OFFLINE_BYTES_INVALID'):run(component)
    assert not any(row[1]=='QQQ' for row in component.sent)
    result=json.loads((component.shared/'benchmark-capture-summary.json').read_text())
    assert not result['capture_completed'] and not result['retention_complete']
    assert not list(component.private.glob('*offline-input.json'))
    refusal=json.loads((component.private/'SPY-input-refused.json').read_text())
    assert refusal['bytes']>100 and len(refusal['sha256'])==64


@pytest.mark.parametrize('account',['U000000001','DU000000001,DU000000002',''])
def test_unknown_live_or_ambiguous_account_scope_refuses_before_data(component,account):
    component.native.managedAccounts(account)
    with pytest.raises(capture.BenchmarkCaptureRefused,match='CAPTURE_PAPER_ACCOUNT_SCOPE_UNVERIFIED'):run(component)
    assert not component.sent


@pytest.mark.parametrize('SDK_id',[True,72,None])
def test_sdk_native_identity_must_both_remain_exact71_before_data(component,SDK_id):
    component.native.clientId=SDK_id
    with pytest.raises(capture.BenchmarkCaptureRefused,match='CAPTURE_SOURCE_SCOPE_CHANGED'):run(component)
    assert not component.sent


def test_standalone_capture_flag_cannot_bypass_supervised_operator_admission(monkeypatch):
    for key in ('READONLY_ADMISSION_TOKEN','PR1090_EVIDENCE_DIR','READONLY_BENCHMARK_CAPTURE'):
        monkeypatch.delenv(key,raising=False)
    with pytest.raises(capture.BenchmarkCaptureRefused,match='SUPERVISED_CAPTURE_ADMISSION_REQUIRED'):
        capture.main(['--benchmark-capture'])


def test_capture_rejects_ordinary_scope_overrides_before_any_runtime():
    with pytest.raises(SystemExit):capture.main(['--benchmark-capture','--force'])


def test_bound_daily_refuses_scope_loss_before_dispatch_without_implicit_reconnect(source_bound_native_snapshot,monkeypatch):
    f=source_bound_native_snapshot
    monkeypatch.setattr(f.wrapper,'_resolve_ib_client',lambda:pytest.fail('implicit reconnect'))
    result=f.wrapper._history_request(Contract(),expected_client=f.native,expected_connection_epoch=999,
        endDateTime='',durationStr='25 D',barSizeSetting='1 day',whatToShow='TRADES',useRTH=True,formatDate=1)
    assert result.status=='DISCONNECTED' and result.request_id is None and result.request_spec is None


def test_single_attempt_is_always_fresh_even_with_an_existing_cycle_cache(source_bound_native_snapshot):
    from src.core.acquisition import acquisition_scope
    f=source_bound_native_snapshot
    with acquisition_scope():
        f.wrapper.snapshot_stock('AEMD',expected_client=f.native,expected_connection_epoch=23)
        f.wrapper.snapshot_stock('AEMD',expected_client=f.native,expected_connection_epoch=23,single_attempt=True)
    assert len(f.requests)==2


@pytest.mark.parametrize('selected',[False,True])
def test_actual_profile_environment_and_binding_own_calendar_without_enrolling_ross(owned,selected):
    import os
    before=dict(os.environ);overrides=dict(cfg._CONFIG_OVERRIDES)
    try:
        os.environ['READONLY_BENCHMARK_CAPTURE']='untrusted-ambient'
        owned['benchmark_capture']=selected
        env=scrub(owned,True)
        cfg.set_config_overrides({})
        assert cfg.get_config('ROSS_NEXT_SESSION_CATALYST_ENABLED') is (not selected)
        assert cfg.get_config('NEWS_ENABLED') is (not selected)
        assert cfg.get_config('NEWS_MAINTENANCE_ENABLED') is (not selected)
        assert env.get('READONLY_BENCHMARK_CAPTURE')==('BENCHMARK_CAPTURE_V1' if selected else None)
        assert owned['binding']()['runtime_profile']==('BENCHMARK_CAPTURE_V1' if selected else None)
        assert env['IBKR_HOST']=='127.0.0.1' and env['IBKR_CLIENT_ID']=='71'
    finally:
        os.environ.clear();os.environ.update(before);cfg.set_config_overrides(overrides)


@pytest.mark.parametrize('fault',['interrupt','disconnect_error'])
def test_real_capture_entrypoint_hooks_retain_original_cleanup_failures(component,monkeypatch,tmp_path,fault):
    from src.runtime import process_identity
    from src.adapters.brokers.ibkr import ibkr_connection_manager as manager_module
    output=tmp_path/'owned-root'/'e'/'terminal';output.mkdir(parents=True)
    for key,value in {process_identity.HANDSHAKE_PATH:'synthetic',process_identity.HANDSHAKE_ACK:'synthetic',
            process_identity.HANDSHAKE_NONCE:'synthetic', 'PR1090_EVIDENCE_DIR':str(output),
            'READONLY_ADMISSION_TOKEN':'synthetic', 'READONLY_BENCHMARK_CAPTURE':capture.BENCHMARK_PROFILE,
            'IBKR_HOST':'127.0.0.1','IBKR_PORT':'7497','IBKR_CLIENT_ID':'71',
            'IBKR_MARKET_DATA_TYPE':'LIVE','NEWS_ENABLED':'false','NEWS_MAINTENANCE_ENABLED':'false',
            'MARKET_SESSION_COVERAGE':json.dumps(receipt('2026-11-13','2026-11-16'))}.items():
        monkeypatch.setenv(key,value)
    handshake=[]
    monkeypatch.setattr(process_identity,'publish_runtime_identity',lambda:handshake.append(True))
    monkeypatch.setattr(supervisor,'benchmark_conflict_check',lambda root:{'completed':True,'runtimes':[]})
    monkeypatch.setattr(manager_module,'get_shared_ibkr_connection_manager',lambda **kw:component.manager)
    if fault=='interrupt':component.fault.kind='interrupt'
    else:
        def failed_disconnect(self):raise RuntimeError('PRIVATE_CLEANUP_PROVIDER_DETAIL')
        monkeypatch.setattr(EClient,'disconnect',failed_disconnect)
    status=capture.run_benchmark_capture_entrypoint()
    assert status==2 and handshake==[True]
    proof=json.loads((output/'shutdown_evidence.json').read_text())
    hooks={row['hook']:row for row in proof['hooks']}
    assert hooks['capture_requests.retired']['completed'] is True
    if fault=='interrupt':
        assert hooks['manager_disconnect']['completed'] is True
        assert not component.native._historical_states and not component.transport.connected
        assert not any(x[1]=='QQQ' for x in component.sent)
    else:
        assert hooks['manager_disconnect']['completed'] is False
        assert component.transport.connected
        assert 'PRIVATE_CLEANUP_PROVIDER_DETAIL' not in json.dumps(proof)
        private=json.loads((output.parent.parent/'private'/'capture'/'shutdown-private.json').read_text())
        assert 'PRIVATE_CLEANUP_PROVIDER_DETAIL' in json.dumps(private)


def test_retirement_observation_never_clears_unknown_active_request_state(component):
    component.native._active_market_req_ids.add(999)
    assert not capture._benchmark_capture_requests_retired(component.native)
    assert component.native._active_market_req_ids=={999}


@pytest.mark.parametrize('missing',[None,'ibapi','ib_insync'])
def test_effective_child_dependencies_refuse_before_network_admission(tmp_path,missing):
    import os,sys
    from scripts.certification.readonly_cache_probe import run_cache_probe
    startup=tmp_path/'startup';startup.mkdir()
    package=startup/'yfinance';package.mkdir()
    (package/'__init__.py').write_text('')
    (package/'cache.py').write_text('_readonly_cache_isolated=True\n_readonly_cache_locations=[]\n')
    (startup/'sitecustomize.py').write_text("import sys\ndef no_network(event,args):\n    if event in ('socket.connect','socket.bind','socket.getaddrinfo'):raise AssertionError('Network forbidden')\nsys.addaudithook(no_network)\ndef probe_stage(stage):pass\n")
    if missing:(startup/(missing+'.py')).write_text("raise ModuleNotFoundError('controlled child-only SDK absence')\n")
    evidence=tmp_path/'private-probe';evidence.mkdir()
    child_env=dict(os.environ,PYTHONPATH=os.pathsep.join((str(startup),str(Path(__file__).resolve().parents[1]))),
        PR1108_YFINANCE_CACHE=str(tmp_path/'cache'))
    if missing:
        with pytest.raises(RuntimeError):run_cache_probe(sys.executable,Path(__file__).resolve().parents[1],evidence,
            child_env,require_capture_dependencies=True)
    else:
        result=run_cache_probe(sys.executable,Path(__file__).resolve().parents[1],evidence,
            child_env,require_capture_dependencies=True)
        assert 'CHILD_CAPTURE_DEPENDENCIES_VERIFIED' in result['stdout']
    result=json.loads((evidence/'child-cache-probe.json').read_text())
    assert result['child_exited'] and not result['timed_out']
    assert result['required_capture_dependencies'] and not result['required_news_dependencies']
    assert result['exit_code']==(1 if missing else 0)


@pytest.fixture
def native_profile_audit(monkeypatch,tmp_path):
    """Original Native connect + SDK encoders; transport is memory-only."""
    import socket
    from src.config import runtime_config
    monkeypatch.setattr(runtime_config,'resolve_ibkr_connection',lambda:('127.0.0.1',7497,71,'READ_ONLY'))
    for name in ('connect','create_connection'):
        if hasattr(socket,name):monkeypatch.setattr(socket,name,lambda *a,**k:pytest.fail('No network'))
    monkeypatch.setattr(socket.socket,'connect',lambda *a,**k:pytest.fail('No network'))
    for name in ('placeOrder','cancelOrder','reqGlobalCancel'):
        monkeypatch.setattr(EClient,name,lambda *a,**k:pytest.fail('No order mutation'))
    packets=[];connected={};instances=[]
    state=NS(account='DU000000001',case=None,bootstrap=True,managed_reply='DU000000001')
    def connect(self,host,port,clientId):
        assert (host,port,clientId)==('127.0.0.1',7497,71)
        instances.append(self)
        if state.case=='connect_exception':raise RuntimeError('PRIVATE_CONNECT_DETAIL')
        self.clientId=clientId;connected[id(self)]=True
        if state.case=='changed_after_wait':
            original_wait=self._open_orders_event.wait
            def waited(timeout):
                result=original_wait(timeout)
                self.managedAccounts('DU000000002')
                return result
            self._open_orders_event.wait=waited
    def run(self):
        if state.bootstrap:self.managedAccounts(state.account)
        self.nextValidId(1)
        self._stop_event.wait(2)
    def send(self,message):
        opcode=message.split('\0')[0];packets.append(opcode)
        if opcode=='17':self.managedAccounts(state.managed_reply)
        if opcode=='59' and state.case=='changed_before_query':self.managedAccounts('U000000001')
        if opcode=='59' and state.case=='SDK_id':self.clientId=True
        if opcode=='16':
            if state.case=='query_exception':raise RuntimeError('PRIVATE_QUERY_DETAIL')
            if state.case=='changed_during_query':self.managedAccounts('DU000000002')
            if state.case=='epoch':self._position_connection_epoch+=1
            self.openOrderEnd()
    monkeypatch.setattr(EClient,'connect',connect)
    monkeypatch.setattr(EClient,'run',run)
    monkeypatch.setattr(EClient,'isConnected',lambda self:connected.get(id(self),False))
    monkeypatch.setattr(EClient,'disconnect',lambda self:connected.__setitem__(id(self),False))
    monkeypatch.setattr(EClient,'serverVersion',lambda self:180)
    monkeypatch.setattr(EClient,'sendMsg',send)
    output=tmp_path/'owned-audit-root'/'e'/'terminal';output.mkdir(parents=True)
    source=dict(accounts=['DU000000001'],client_id=71,SDK_client_id=71,connection_epoch=23,
        scope='ORIGINAL_NATIVE_MANAGED_ACCOUNTS')
    commitment=capture.benchmark_private_write(output.parent.parent/'private'/'capture',
        'original-account-scope.json',capture.benchmark_json_bytes(source))
    identity=verified_process(lambda:0).runtime_identity
    proof={'runtime_profile':capture.BENCHMARK_PROFILE,'process_identity':identity,'capture_account_scope':commitment}
    (output/'shutdown_evidence.json').write_text(json.dumps(proof))
    def invoke(**changes):
        return supervisor.final_broker_audit(expected_profile=capture.BENCHMARK_PROFILE,
            capture_evidence=output,expected_runtime_identity=identity,**changes)
    return NS(invoke=invoke,state=state,packets=packets,instances=instances,output=output,
        source=source,proof=proof,identity=identity,connected=connected)


def test_matched_original_paper_scope_uses_one_actual_native_query_and_cleanup(native_profile_audit):
    f=native_profile_audit
    result=f.invoke()
    assert result['query_completed'] and result['disconnected'] and result['end_received']
    assert f.packets.count('16')==1 and f.packets.count('17')==0
    assert len(f.instances)==1 and not f.instances[0]._thread.is_alive()


@pytest.mark.parametrize('account',['U000000001','','DU000000001,DU000000002','DU000000002'])
def test_post_audit_wrong_empty_multiple_or_other_paper_account_never_queries(native_profile_audit,account):
    f=native_profile_audit;f.state.account=account
    result=f.invoke()
    assert not result['query_completed'] and result['disconnected']
    assert f.packets.count('16')==0 and f.packets.count('17')==0
    assert not f.instances[0]._thread.is_alive()


@pytest.mark.parametrize('case',['changed_before_query','SDK_id','changed_during_query','changed_after_wait','epoch','query_exception','connect_exception'])
def test_post_audit_scope_changes_and_exceptions_never_certify_old_scope(native_profile_audit,case):
    f=native_profile_audit;f.state.case=case
    result=f.invoke()
    assert not result['query_completed'] and result['disconnected']
    assert f.packets.count('16')==(1 if case in ('changed_during_query','changed_after_wait','epoch','query_exception') else 0)
    assert f.packets.count('17')==0
    thread=f.instances[0]._thread
    assert thread is None or not thread.is_alive()


@pytest.mark.parametrize('reply',['DU000000001','','DU000000001,DU000000002'])
def test_missing_bootstrap_permits_only_one_bounded_original_managed_account_read(native_profile_audit,reply):
    f=native_profile_audit;f.state.bootstrap=False;f.state.managed_reply=reply
    result=f.invoke()
    assert result['query_completed'] is (reply=='DU000000001') and result['disconnected']
    assert f.packets.count('17')==1 and f.packets.count('16')==(1 if reply=='DU000000001' else 0)


@pytest.mark.parametrize('fault',['missing','corrupt','hash','missing_commitment','identity'])
def test_original_capture_scope_proof_missing_or_changed_refuses_before_connect(native_profile_audit,fault):
    f=native_profile_audit
    path=f.output.parent.parent/'private'/'capture'/'original-account-scope.json'
    if fault=='missing':path.unlink()
    elif fault=='corrupt':path.write_text('{}')
    elif fault=='hash':path.write_bytes(path.read_bytes().replace(b'DU000000001',b'DU000000002'))
    elif fault=='missing_commitment':
        f.proof.pop('capture_account_scope');(f.output/'shutdown_evidence.json').write_text(json.dumps(f.proof))
    else:f.identity={**f.identity,'creation_token':'windows-filetime:999'}
    with pytest.raises((RuntimeError,OSError)):
        supervisor.final_broker_audit(expected_profile=capture.BENCHMARK_PROFILE,capture_evidence=f.output,
            expected_runtime_identity=f.identity)
    assert not f.instances and not f.packets


def test_ordinary_audit_default_keeps_its_existing_behavior(native_profile_audit,monkeypatch):
    f=native_profile_audit;f.state.account='U000000001'
    monkeypatch.delenv('READONLY_BENCHMARK_CAPTURE',raising=False)
    result=supervisor.final_broker_audit()
    assert result['query_completed'] and result['disconnected']
    assert f.packets.count('16')==1 and not f.packets.count('17')


def test_capture_dependency_probe_caps_and_drains_noisy_imports_before_admission(tmp_path):
    import os,sys
    from scripts.certification.readonly_cache_probe import run_cache_probe
    startup=tmp_path/'startup';startup.mkdir();package=startup/'yfinance';package.mkdir()
    (package/'__init__.py').write_text('')
    (package/'cache.py').write_text("print('PRIVATE_DEPENDENCY_DETAIL'*60000,flush=True)\n_readonly_cache_isolated=True\n_readonly_cache_locations=[]\n")
    (startup/'sitecustomize.py').write_text("import sys\ndef no_network(event,args):\n    if event in ('socket.connect','socket.bind','socket.getaddrinfo'):raise AssertionError('Network forbidden')\nsys.addaudithook(no_network)\ndef probe_stage(stage):pass\n")
    evidence=tmp_path/'private-probe';evidence.mkdir()
    child_env=dict(os.environ,PYTHONPATH=os.pathsep.join((str(startup),str(Path(__file__).resolve().parents[1]))),
        PR1108_YFINANCE_CACHE=str(tmp_path/'cache'))
    with pytest.raises(RuntimeError,match='logs incomplete or over limit'):
        run_cache_probe(sys.executable,Path(__file__).resolve().parents[1],evidence,child_env,require_capture_dependencies=True)
    result=json.loads((evidence/'child-cache-probe.json').read_text())
    assert result['child_exited'] and result['exit_code']==0 and not result['timed_out']
    assert result['capture_log_readers_complete'] and not result['retention_complete']
    assert (evidence/'child-cache.stdout.log').stat().st_size==512*1024
    assert (evidence/'child-cache.stderr.log').stat().st_size<=512*1024



def test_actual_profile_finalization_persists_audit_scope_privately_only(native_profile_audit,monkeypatch):
    from test_pr1090_p1_repairs import Process
    f=native_profile_audit
    process=Process([0])
    process.runtime_identity={**f.identity,'argv':['python','-m',
        'scripts.certification.pr1040_real_readonly_runtime_observation_adapter','--benchmark-capture']}
    process.launcher_identity=process.runtime_identity
    proof=shutdown.ShutdownEvidence(runtime_profile=capture.BENCHMARK_PROFILE)
    proof.record('GRACEFUL_STOP_REQUESTED',completed=True);proof.record('SHUTDOWN_STARTED',completed=True)
    for name in shutdown.BENCHMARK_REQUIRED_HOOKS:proof.attempt(name,lambda:True)
    proof.record('SHUTDOWN_COMPLETE',completed=True);proof.record('TERMINAL_FLUSHED',completed=True)
    payload=proof.payload();payload.update(pid=process.pid,process_identity=process.runtime_identity,
        capture_account_scope=f.proof['capture_account_scope'])
    (f.output/'shutdown_evidence.json').write_text(json.dumps(payload))
    monkeypatch.setattr(supervisor,'benchmark_conflict_check',lambda root:{'completed':True,'runtimes':[]})
    private=f.output.parent.parent/'private'/'supervisor';private.mkdir()
    result=supervisor.stop_and_finalize(process,[],[],f.output,expected_profile=capture.BENCHMARK_PROFILE,
        private_output=private,graceful_timeout=.1,terminate_timeout=.1,kill_timeout=.1,reader_timeout=.1)
    assert result==0
    public=json.loads((f.output/'terminal_evidence.json').read_text())
    assert 'private_account_scope' not in public['final_broker_audit']
    private_audit=json.loads((private.parent/'capture'/'final-audit-private.json').read_text())
    assert private_audit['private_account_scope']['observed_accounts']==['DU000000001']
    assert private_audit['query_completed'] and private_audit['disconnected']


@pytest.mark.parametrize('value',['ordinary','£ and 東京'])
def test_existing_cache_optional_bound_writes_exact_checked_bytes_at_boundary(tmp_path,value):
    from src.market_data.reference_resolver import PersistentReferenceCache
    record={'reference_price':100.0,'label':value}
    raw=json.dumps({'conid:123':record},indent=2,sort_keys=True).encode('utf-8')
    path=tmp_path/'cache.json'
    cache=PersistentReferenceCache(path,max_bytes=len(raw))
    cache.put(('conid:123',),record)
    assert path.read_bytes()==raw and path.stat().st_size==len(raw)
    assert b'\r\n' not in raw and cache.get('conid:123',trading_date=None)==record
    assert not list(tmp_path.glob('cache.json.*.tmp'))


def test_existing_cache_one_byte_overflow_opens_no_temp_and_publishes_no_memory(tmp_path,monkeypatch):
    from src.market_data import reference_resolver as owner
    record={'reference_price':100.0,'label':'£'}
    raw=json.dumps({'conid:123':record},indent=2,sort_keys=True).encode('utf-8')
    path=tmp_path/'not-created'/'cache.json'
    cache=owner.PersistentReferenceCache(path,max_bytes=len(raw)-1)
    monkeypatch.setattr(owner.tempfile,'NamedTemporaryFile',lambda **kw:pytest.fail('over-limit temporary opened'))
    with pytest.raises(owner.ReferenceCacheSizeLimitError):cache.put(('conid:123',),record)
    assert not path.parent.exists() and cache.get('conid:123',trading_date=None) is None
    assert cache._store=={}


def test_existing_bounded_cache_failure_preserves_prior_file_and_memory(tmp_path,monkeypatch):
    from src.market_data import reference_resolver as owner
    path=tmp_path/'cache.json';cache=owner.PersistentReferenceCache(path,max_bytes=256)
    cache.put(('conid:123',),{'reference_price':100.0})
    original=path.read_bytes();stored=deepcopy(cache._store)
    with pytest.raises(owner.ReferenceCacheSizeLimitError):
        cache.put(('conid:999',),{'label':'£'*200})
    assert path.read_bytes()==original and cache._store==stored
    assert cache.get('conid:999',trading_date=None) is None
    def no_replace(*args):raise OSError('controlled atomic publication failure')
    monkeypatch.setattr(owner.os,'replace',no_replace)
    with pytest.raises(OSError):cache.put(('conid:123',),{'reference_price':101.0})
    assert path.read_bytes()==original and cache._store==stored
    assert not list(tmp_path.glob('cache.json.*.tmp'))


def test_existing_unbounded_cache_default_keeps_ordinary_behavior(tmp_path):
    from src.market_data.reference_resolver import PersistentReferenceCache
    cache=PersistentReferenceCache(tmp_path/'ordinary.json')
    value={'literal':'x'*(300*1024)}
    cache.put(('ordinary',),value)
    assert cache.max_bytes is None and cache.path.stat().st_size>256*1024
    assert cache.get('ordinary',trading_date=None)==value


@pytest.mark.parametrize('bound',[False,True,0,-1,1.5,'256'])
def test_cache_bound_parameter_is_explicit_positive_integer_only(tmp_path,bound):
    from src.market_data.reference_resolver import PersistentReferenceCache
    with pytest.raises(ValueError):PersistentReferenceCache(tmp_path/'cache.json',max_bytes=bound)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('metadata_size',[9*1024,10*1024,11*1024,12*1024])
def test_original_native_conid_amplification_respects_prewrite_cache_reserve(component,monkeypatch,metadata_size):
    # Same original callback shape as the independent48KiB failure. Scale the
    # reserve to8KiB, so qualification succeeds and DAILY retention reaches the
    # relevant quota boundary; a fixed1MiB reserve would refuse trivially early.
    limit=48*1024
    monkeypatch.setattr(capture,'BENCHMARK_SOURCE_LIMIT',limit)
    monkeypatch.setattr(capture,'BENCHMARK_CACHE_RESERVE',8*1024)
    monkeypatch.setattr(capture,'BENCHMARK_CACHE_LIMIT',2*1024)
    original=component.native.contractDetails
    def supplied(request_id,details):
        details.contract.primaryExchange='X'*metadata_size
        details.contract.conId=int('9'*1500)
        return original(request_id,details)
    monkeypatch.setattr(component.native,'contractDetails',supplied)
    with pytest.raises(capture.BenchmarkCaptureRefused,match='PRIVATE_SIZE_LIMIT'):run(component)
    assert [row[:3] for row in component.sent]==[('qualify','SPY'),('history','SPY','1 day')]
    assert (component.private/'SPY-qualification.json').exists()
    assert not list(component.private.glob('*reference-cache.json'))
    assert not list(component.private.glob('*.tmp'))
    assert sum(path.stat().st_size for path in component.private.rglob('*') if path.is_file())<=limit
    result=json.loads((component.shared/'benchmark-capture-summary.json').read_text())
    assert not result['capture_completed'] and not result['retention_complete']


def test_oversized_original_qualification_is_retained_before_daily_refusal(component,monkeypatch):
    original=component.native.contractDetails
    def supplied(request_id,details):
        details.longName='X'*(capture.BENCHMARK_QUALIFICATION_LIMIT+1)
        return original(request_id,details)
    monkeypatch.setattr(component.native,'contractDetails',supplied)
    with pytest.raises(capture.BenchmarkCaptureRefused,match='QUALIFICATION_METADATA_LIMIT'):run(component)
    assert component.sent==[('qualify','SPY')]
    raw=json.loads((component.private/'SPY-qualification.json').read_text())
    assert raw['qualification']['longName']=='X'*(64*1024+1)
    assert not list(component.private.glob('*reference-cache.json'))


@pytest.mark.parametrize('literal',['2026-11-13'+'Z'*2048,'20261113trailing','20261313','20261131','２０２６１１１３'])
def test_original_daily_date_literal_is_never_trimmed_into_reference_authority(component,monkeypatch,literal):
    original=component.native.historicalData
    def supplied(request_id,bar):
        if bar.date=='20261113':bar.date=literal
        return original(request_id,bar)
    monkeypatch.setattr(component.native,'historicalData',supplied)
    result=run(component)
    assert all(row['reason']=='DAILY_DATE_INVALID' for row in result['assets'])
    assert not any(row[0]=='quote' or (row[0]=='history' and row[2]=='1 min') for row in component.sent)
    assert not list(component.private.glob('*reference-cache.json'))
    raw=json.loads((component.private/'SPY-daily.json').read_text())
    assert raw['raw_source_bars'][0]['date']==literal


def test_actual_reference_cache_limit_stops_capture_without_publishing_cache(component,monkeypatch):
    monkeypatch.setattr(capture,'BENCHMARK_CACHE_LIMIT',256)
    with pytest.raises(capture.BenchmarkCaptureRefused,match='PRIVATE_SIZE_LIMIT'):run(component)
    assert [row[:3] for row in component.sent]==[('qualify','SPY'),('history','SPY','1 day')]
    assert not list(component.private.glob('*reference-cache.json'))
    assert not list(component.private.glob('*.tmp'))
    raw=json.loads((component.private/'SPY-raw.json').read_text())
    assert raw['error']['cause']['type']=='ReferenceCacheSizeLimitError'
    result=json.loads((component.shared/'benchmark-capture-summary.json').read_text())
    assert not result['capture_completed'] and not result['retention_complete']
