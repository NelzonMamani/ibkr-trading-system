import importlib.util
import threading
from datetime import datetime, timezone
from types import SimpleNamespace as NS
import pytest
from ibapi.contract import Contract
from src.core import acquisition

from scripts.certification import quote_transport_diagnostic as payload

class Fake:
    def __init__(self, mode='success'):
        self.mode=mode; self.scans=0; self.requests=[]; self.cancelled=[]
        self._market_events={}; self._lock=threading.Lock(); self.completions=[]
    def is_connected(self):return True
    def resolve_contract(self, symbol):
        assert symbol.startswith('NATURAL_')
        c = Contract()
        c.symbol, c.conId, c.secType, c.currency = symbol, 101 + int(symbol.rsplit('_', 1)[1]), 'STK', 'USD'
        c.primaryExchange = 'NASDAQ'
        return NS(contract=c)
    def reqScannerData(self, sub):
        self.scans+=1
        assert (sub.instrument,sub.locationCode,sub.scanCode,sub.numberOfRows,sub.abovePrice,sub.belowPrice)==('STK','STK.US.MAJOR','TOP_PERC_GAIN',50,1,20)
        rows=[]
        for i in range(3):
            c=Contract();c.symbol='NATURAL_'+str(i);c.secType='STK';c.currency='USD';c.conId=101+i
            rows.append(NS(rank=i,contractDetails=NS(contract=c)))
        if self.mode=='empty': rows=[]
        self.last_scanner_request=dict(completion_status='COMPLETE',end_received=True,
            wait_signalled=True,error=None,connected=True,row_count=len(rows))
        if self.mode=='incomplete':
            self.last_scanner_request.update(completion_status='UNAVAILABLE',end_received=False)
        return rows
    def reqMktData(self,c,**flags):
        assert flags==dict(genericTickList='',snapshot=True,regulatorySnapshot=False)
        self.requests.append((c.symbol,c.conId));req=len(self.requests)
        self._market_events[req]=threading.Event()
        return NS(reqId=req,contract=c,snapshotEnd=self.mode!='missing',brokerErrors=[],
            bid=4.,ask=4.1,last=4.05,close=3.9,volume=100.,
            marketDataType=1,marketDataTypeConfirmed=True,lastTime=datetime.now(timezone.utc))
    def _raise_if_request_id_conflicted(self,req): pass
    def record_quote_completion(self,req,reason):self.completions.append(reason)
    def cancelMktData(self,req):self.cancelled.append(req);self._market_events.pop(req)

@pytest.mark.parametrize('mode,n', [('success',1),('empty',0),('missing',1)])
def test_bounded_acquisition(monkeypatch,mode,n):
    def wait(e, timeout):
        assert timeout == 5
        return mode != 'missing'
    monkeypatch.setattr(acquisition, 'wait_event', wait)
    f=Fake(mode);facts={};r=payload.acquire(f,lambda k,v:facts.update({k:v}))
    assert f.scans==1 and len(f.requests)==n and len(f.cancelled)==n
    assert all(s.startswith('NATURAL_') for s,c in f.requests)
    assert not f._market_events
    assert all('fields' not in q and 'field_presence' in q for q in r['quotes'])
    if mode=='empty':assert r['scan_outcome']=='CONFIRMED_EMPTY' and not r['quotes']
    elif mode=='missing':assert not any(q['diagnostic_fields_available'] for q in r['quotes'])
    else:assert len(r['quotes'])==1 and all(q['diagnostic_fields_available'] for q in r['quotes'])

def test_incomplete_scan_cannot_trigger_quotes(monkeypatch):
    f=Fake('incomplete')
    with pytest.raises(RuntimeError,match='Scanner completion'):
        payload.acquire(f,lambda *a:None)
    assert f.scans==1 and not f.requests

def test_expired_absolute_cap_starts_no_quote(monkeypatch):
    f=Fake(); value=[0.]
    monkeypatch.setattr(acquisition.time,'monotonic',lambda:value[0])
    original=f.reqScannerData
    def scan(sub):
        rows=original(sub);value[0]=26.;return rows
    f.reqScannerData=scan
    with pytest.raises(acquisition.AcquisitionDeadlineExceeded):payload.acquire(f,lambda *a:None)
    assert f.scans==1 and not f.requests


@pytest.mark.parametrize('stale,missing', [(True, False), (False, True), (True, True)])
def test_completed_live_quote_still_rejects_stale_or_missing_fields(monkeypatch, stale, missing):
    from datetime import timedelta
    f = Fake()
    request = f.reqMktData
    def completed(*args, **kwargs):
        ticker = request(*args, **kwargs)
        if stale:
            ticker.lastTime -= timedelta(seconds=103.076777)
        if missing:
            ticker.bid = ticker.ask = -1  # Actual SDK missing-price sentinel.
        return ticker
    f.reqMktData = completed
    monkeypatch.setattr(acquisition, 'wait_event', lambda event, timeout: True)
    quote = payload.acquire(f, lambda *args: None)['quotes'][0]
    assert quote['snapshot_complete'] and quote['returned_type'] == 'LIVE'
    assert not quote['diagnostic_fields_available']
    assert quote['canonical_qualification'] == 'NOT_PERFORMED'
    assert f.completions == ['snapshot_end'] and not f._market_events


@pytest.mark.parametrize('completed',[True,False])
def test_final_orders_caller_one_audit_whitelist_no_quote_acquisition(monkeypatch,completed):
    from scripts.certification import pr1090_terminal_observation_supervisor as owner
    calls=[];artifacts={};observers=[]
    class Observer:
        def __init__(self,c):self.client=c;self.closed=False;observers.append(self)
        def __enter__(self):return self
        def close(self):self.closed=True
        def snapshot(self):
            assert self.closed
            return {'coverage_verified':True,'absence_claims_valid':True}
    client=object()
    def audit(*,observer_factory):
        calls.append(client);o=observer_factory(client);o.__enter__();o.close()
        return {'query_completed':completed,'disconnected':True,'error':'PRIVATE_PAYLOAD',
                'broker_errors':[{'message':'PRIVATE_PAYLOAD','req_id':999}],
                'timeout_seconds':10,**({'open_orders_count':0} if completed else {})}
    monkeypatch.setattr(owner,'final_broker_audit',audit)
    monkeypatch.setattr(payload,'acquire',lambda *a:pytest.fail('No scanner/quote acquisition'))
    success,proof=payload.final_orders(lambda n,v:artifacts.__setitem__(n,v),Observer)
    assert success==completed and len(calls)==1 and observers[0].client is client
    assert 'PRIVATE_PAYLOAD' not in str(artifacts) and 'broker_errors' not in artifacts['final-order-audit.json']
    assert ('open_orders_count' in artifacts['final-order-audit.json'])==completed
    assert artifacts['final-order-audit.json']['error_present']


def test_final_orders_requires_explicit_tree_before_any_probe(monkeypatch):
    import sys
    monkeypatch.setattr(sys,'argv',['operator','probe','unused','a'*40,'final-orders',''])
    with pytest.raises(RuntimeError,match='explicit reviewed tree'):payload.main()


@pytest.mark.parametrize('shutdown_error', [False, True])
def test_final_orders_operator_filesystem_sealing_no_acquisition_or_operator_write(monkeypatch,tmp_path,capsys,shutdown_error):
    """Run existing operator phases with stub audit result and hard I/O tripwires.

    Only platform/offline-entry checks are modeled; all acquisition entry points
    remain forbidden. This is synthetic packaging proof, not a broker receipt.
    """
    import os,shutil,json,zipfile
    from pathlib import Path
    from scripts.certification import pr1090_terminal_observation_supervisor as safety
    from src.config import system_config
    from src.ibkr import read_only_guard
    from src.adapters.brokers.ibkr import ibkr_client
    original_class=ibkr_client.IbkrClient
    class NoClient:
        submit_order=original_class.submit_order
        def __init__(self,*a,**kw):pytest.fail('No diagnostic/second client in operator caller')
    monkeypatch.setattr(ibkr_client,'IbkrClient',NoClient)
    monkeypatch.setattr(payload,'acquire',lambda *a:pytest.fail('No scanner/quote activity'))
    root=tmp_path/'run';repo=root/'s';evidence=root/'e';evidence.mkdir(parents=True);repo.mkdir()
    source=Path(payload.__file__).resolve().parents[2]
    for name in ('src/config/config_registry.py','scripts/certification/pr1040_real_readonly_runtime_observation_adapter.py'):
        target=repo/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/name,target)
    original=tmp_path/'original-order-state.json';original.write_text('PRIVATE_OPERATOR_CANARY')
    env=dict(os.environ,IBKR_ORDER_ID_STATE_PATH=str(original))
    monkeypatch.setattr(payload,'os',NS(name='nt',environ=env,chdir=lambda *a:None))
    import sys as actual_sys
    monkeypatch.setattr(actual_sys,'stdout',actual_sys.stdout)
    monkeypatch.setattr(actual_sys,'stderr',actual_sys.stderr)
    class SysView(NS):
        @property
        def stdout(self):return actual_sys.stdout
        @stdout.setter
        def stdout(self,value):actual_sys.stdout=value
        @property
        def stderr(self):return actual_sys.stderr
        @stderr.setter
        def stderr(self,value):actual_sys.stderr=value
    fake_sys=SysView(argv=['operator','probe',str(root),'a'*40,'final-orders','b'*40],
                version_info=(3,13,3),path=[],modules={'sitecustomize':NS()})
    monkeypatch.setattr(payload,'sys',fake_sys)
    monkeypatch.setattr(payload.subprocess,'check_output',lambda *a,**kw:('b'*40+'\n').encode())
    monkeypatch.setattr(payload,'manifest',lambda repo:{'tracked':'c'*64})
    pins=[]
    monkeypatch.setattr(safety,'require_clean_certification_worktree',lambda pin:pins.append(pin))
    monkeypatch.setattr(safety,'runtime_inventory',lambda:{'completed':True,'runtimes':[]})
    monkeypatch.setattr(system_config,'get_current_market_session',lambda:'RTH')
    monkeypatch.setattr(read_only_guard,'get_ibkr_readonly_enabled',lambda:True)
    calls=[]
    def audit(put,observer_factory=None):
        calls.append(True)
        put('final-order-audit.json',{'query_completed':False,'end_received':False,'timeout_seconds':10})
        proof={'coverage_verified':True,'absence_claims_valid':True}
        if shutdown_error:
            from src.ibkr.transport_diagnostic import TransportDiagnostic, _Socket
            diagnostic = observer_factory(NS())
            class PrivateSocket:
                def close(self):
                    raise OSError(9, 'PRIVATE_SHUTDOWN_ACCOUNT_ORDER_ADDRESS')
                def recv(self, size):
                    raise OSError(9, 'PRIVATE_SHUTDOWN_ACCOUNT_ORDER_ADDRESS')
            proxy = _Socket(PrivateSocket(), diagnostic)
            diagnostic.audit_finalization()
            with pytest.raises(OSError): proxy.close()
            with pytest.raises(OSError): proxy.recv(4096)
            proof = diagnostic.snapshot()
            assert proof['counters']['recv_exceptions'] == 1
        put('transport-diagnostic.json',proof)
        return False,proof
    monkeypatch.setattr(payload,'final_orders',audit)
    from src.ibkr import evidence_safety
    original_scan=evidence_safety.scan_artifacts
    late=[False]
    def scan(directory):
        if not late[0]:
            late[0]=True
            print('PRIVATE_LATE_ORDER_SYMBOL_ID')  # Synthetic late callback after observer scope.
        return original_scan(directory)
    monkeypatch.setattr(evidence_safety,'scan_artifacts',scan)
    assert payload.main()==(1 if shutdown_error else 2)  # Preserve receive failures and incomplete audit.
    captured=capsys.readouterr()
    (evidence/'probe-process.stdout.log').write_text(captured.out)
    (evidence/'probe-process.stderr.log').write_text(captured.err)
    assert 'PRIVATE_LATE_ORDER_SYMBOL_ID' not in captured.out+captured.err
    report=json.loads((evidence/'result.json').read_text())
    assert report['scope']=='FINAL_ORDERS_DIAGNOSTIC_ONLY' and report['status']==('FAIL' if shutdown_error else 'DIAGNOSTIC_ONLY')
    assert report['source_state']==report['operator_state']=='PASS' and not report['scanner_attempted']
    assert calls==[True] and pins==['a'*40,'a'*40]
    assert original.read_text()=='PRIVATE_OPERATOR_CANARY'
    for phase in ('package','seal'):
        fake_sys.argv[1]=phase
        assert payload.main()==0
    archive=root/'final-orders-diagnostic-upload.zip'
    with zipfile.ZipFile(archive) as z:
        assert all(b'PRIVATE_OPERATOR_CANARY' not in z.read(n) and b'PRIVATE_LATE_ORDER_SYMBOL_ID' not in z.read(n)
                   and b'PRIVATE_SHUTDOWN_ACCOUNT_ORDER_ADDRESS' not in z.read(n) for n in z.namelist())
        assert not any('state' in n or n.startswith('quote-trace') for n in z.namelist())
    assert calls==[True]  # Packaging is filesystem only, never another audit.


def test_live_volume_probe_keeps_raw_callback_outside_general_artifacts(monkeypatch):
    f = Fake()
    def wait(event, timeout):
        assert timeout == 12
        return True
    monkeypatch.setattr(acquisition, 'wait_event', wait)
    now = datetime.now(timezone.utc).isoformat()
    raw = {
        'source': 'IBKR_NATIVE_TICK_SIZE', 'sdk_distribution': '9.81.1.post1',
        'session_basis': 'IBKR_CURRENT_TRADING_DAY_CUMULATIVE',
        'security_type': 'STK', 'currency': 'USD', 'primary_exchange': 'NASDAQ',
        'market_data_status': 'LIVE', 'tick_type': 8, 'con_id': 101, 'client_id': 71,
        'server_version': 157, 'connection_epoch': 0, 'request_id': 1,
        'market_timestamp_utc': now, 'received_at_utc': now, 'raw_value': 39018,
        'unit': 'UNKNOWN',
    }
    f.snapshot_volume_evidence = lambda ticker: raw
    f.reqHistoricalData = lambda *args, **kwargs: NS(
        volume_basis={'unit': 'UNKNOWN'}, raw_source_bars=({'date': '20261019', 'volume': 81234},),
    )
    regular, private = {}, {}
    observation = payload.acquire(f, regular.__setitem__, put_private=private.__setitem__, requested_type='LIVE')
    assert private == {
        'native-volume.json': raw,
        'volume-probe.json': {'watchlist': raw, 'history': {'unit': 'UNKNOWN', 'bars': [['20261019', 81234]]}},
    }
    assert observation['native_volume_sample_status'] == 'LIVE_TICK8_CAPTURED_UNITS_UNVERIFIED'
    assert observation['quotes'][0]['requested_type'] == 'LIVE'
    assert '39018' not in repr(regular)
    assert not f._market_events


@pytest.mark.parametrize('history_complete', [True, False])
@pytest.mark.parametrize('automatic', [True, False])
def test_live_volume_probe_uses_exact_contract_and_keeps_paired_sources_private(monkeypatch, history_complete, automatic):
    f = Fake()
    monkeypatch.setattr(acquisition, 'wait_event', lambda event, timeout: True)
    symbol = 'SYNTH'
    contract = Contract()
    contract.symbol, contract.conId, contract.secType, contract.currency = symbol, 123, 'STK', 'USD'
    def resolve(requested):
        assert requested == symbol
        from copy import copy
        resolved = copy(contract)
        resolved.primaryExchange = 'NASDAQ'
        return NS(contract=resolved)
    f.resolve_contract = resolve
    scan = f.reqScannerData
    def completed_scan(subscription):
        scan(subscription)  # Retain the existing bounded query contract assertion.
        f.last_scanner_request['row_count'] = 1
        return [NS(rank=0, contractDetails=NS(contract=contract))]
    f.reqScannerData = completed_scan
    quote_targets = []
    quote = f.reqMktData
    def snapshot(target, **flags):
        quote_targets.append(target)
        return quote(target, **flags)
    f.reqMktData = snapshot
    now = datetime.now(timezone.utc).isoformat()
    watch = {
        'source': 'IBKR_NATIVE_TICK_SIZE', 'sdk_distribution': '9.81.1.post1',
        'session_basis': 'IBKR_CURRENT_TRADING_DAY_CUMULATIVE', 'security_type': 'STK',
        'currency': 'USD', 'primary_exchange': 'NASDAQ', 'market_data_status': 'LIVE', 'tick_type': 8,
        'con_id': 123, 'client_id': 71, 'server_version': 157, 'connection_epoch': 0, 'request_id': 1,
        'market_timestamp_utc': now, 'received_at_utc': now, 'raw_value': 39018, 'unit': 'UNKNOWN',
    }
    f.snapshot_volume_evidence = lambda ticker: watch
    history_calls = []
    def history(target, **parameters):
        assert target is quote_targets[0]
        assert (target.symbol, target.conId) == (symbol, 123)
        assert parameters == dict(durationStr='20 D', barSizeSetting='1 day',
                                  whatToShow='TRADES', useRTH=1, formatDate=1)
        history_calls.append(target)
        return NS(volume_basis={'unit': 'UNKNOWN'} if history_complete else None,
                  raw_source_bars=({'date': '20261019', 'volume': 81234},))
    f.reqHistoricalData = history

    regular, private = {}, {}
    outcome = payload.acquire(f, regular.__setitem__, put_private=private.__setitem__,
                              requested_type='LIVE', volume_symbol=None if automatic else symbol)
    assert f.scans == int(automatic) and f.requests == [(symbol, 123)]
    assert history_calls == quote_targets and len(history_calls) == 1
    assert f.cancelled == [1] and not f._market_events
    assert '39018' not in repr(regular) and '81234' not in repr(regular)
    if history_complete:
        assert private['volume-probe.json'] == {
            'watchlist': watch, 'history': {'unit': 'UNKNOWN', 'bars': [['20261019', 81234]]},
        }
    else:
        assert 'volume-probe.json' not in private
        assert outcome['native_volume_sample_status'] == 'PAPER_RELEASE_VOLUME_HISTORICAL_PROBE_UNVERIFIED'


@pytest.mark.parametrize('mode', ['empty', 'incomplete'])
def test_automatic_live_volume_requires_completed_nonempty_scanner_before_any_quote_or_history(monkeypatch, mode):
    f = Fake(mode)
    f.reqHistoricalData = lambda *a, **k: pytest.fail('No historical request without selected live source')
    f.snapshot_volume_evidence = lambda *a: pytest.fail('No volume sample without selected source')
    private = {}
    if mode == 'incomplete':
        with pytest.raises(RuntimeError, match='Scanner completion'):
            payload.acquire(f, lambda *a: None, put_private=private.__setitem__, requested_type='LIVE')
    else:
        outcome = payload.acquire(f, lambda *a: None, put_private=private.__setitem__, requested_type='LIVE')
        assert outcome['scan_outcome'] == 'CONFIRMED_EMPTY' and not outcome['selected']
    assert f.scans == 1 and not f.requests and not f.cancelled and not private


@pytest.mark.parametrize('failure', ['stale', 'future', 'delayed', 'missing_end', 'missing_fields'])
def test_automatic_live_volume_never_pairs_history_for_unqualified_quote(monkeypatch, failure):
    from datetime import timedelta
    f = Fake('missing' if failure == 'missing_end' else 'success')
    request = f.reqMktData
    def quote(*args, **kwargs):
        ticker = request(*args, **kwargs)
        ticker.received = datetime.now(timezone.utc)
        if failure == 'stale':
            ticker.lastTime -= timedelta(seconds=103)
        elif failure == 'future':
            ticker.lastTime += timedelta(seconds=103)
        elif failure == 'delayed':
            ticker.marketDataType = 3
        elif failure == 'missing_fields':
            ticker.bid = -1
        return ticker
    f.reqMktData = quote
    def evidence(ticker):
        return {
            'source': 'IBKR_NATIVE_TICK_SIZE', 'sdk_distribution': '9.81.1.post1',
            'session_basis': 'IBKR_CURRENT_TRADING_DAY_CUMULATIVE', 'security_type': 'STK',
            'currency': 'USD', 'primary_exchange': 'NASDAQ',
            'market_data_status': 'DELAYED' if failure == 'delayed' else 'LIVE', 'tick_type': 8,
            'con_id': 101, 'client_id': 71, 'server_version': 157, 'connection_epoch': 0, 'request_id': 1,
            'market_timestamp_utc': ticker.lastTime.isoformat(), 'received_at_utc': ticker.received.isoformat(),
            'raw_value': 39018, 'unit': 'UNKNOWN',
        }
    f.snapshot_volume_evidence = evidence
    f.reqHistoricalData = lambda *a, **k: pytest.fail('Invalid volume must not start historical acquisition')
    monkeypatch.setattr(acquisition, 'wait_event', lambda event, timeout: failure != 'missing_end')
    private = {}
    outcome = payload.acquire(f, lambda *a: None, put_private=private.__setitem__, requested_type='LIVE')
    assert f.scans == 1 and len(f.requests) == 1 and f.cancelled == [1] and not f._market_events
    assert outcome['native_volume_sample_status'] != 'LIVE_TICK8_CAPTURED_UNITS_UNVERIFIED'
    assert 'native-volume.json' in private and 'volume-probe.json' not in private


@pytest.mark.parametrize('profile', ['quotes', 'final-orders', 'live-volume'])
@pytest.mark.parametrize('session', ['PRE', 'RTH', 'AH', 'OVN', 'CLOSED'])
def test_normal_session_admission_is_premarket_only_for_live_volume(profile, session):
    admitted = session == 'RTH' or (profile == 'live-volume' and session == 'PRE')
    if admitted:
        payload.require_diagnostic_session(profile, session)
    else:
        with pytest.raises(RuntimeError, match='Normal configured .* required; no override'):
            payload.require_diagnostic_session(profile, session)


def test_live_volume_profile_accepts_automatic_selection_without_symbol_before_probe(monkeypatch, tmp_path):
    import sys
    # Packaging is explicitly forbidden and performs no acquisition. Reaching
    # this guard proves optional-symbol argument validation accepted the profile.
    (tmp_path / 's').mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, 'path', list(sys.path))
    monkeypatch.setattr(sys, 'argv', ['operator', 'package', str(tmp_path), 'a' * 40, 'live-volume', 'b' * 40])
    with pytest.raises(RuntimeError, match='laptop-private'):
        payload.main()


def _sdk_scanner_row():
    """Decode the scanner schema installed on the laptop, without a socket."""
    from ibapi.decoder import Decoder
    from importlib.metadata import version
    assert version('ibapi') == '9.81.1.post1'
    rows, ends = [], []
    wrapper = NS(
        scannerData=lambda req, rank, details, *rest: rows.append(NS(rank=rank, contractDetails=details)),
        scannerDataEnd=ends.append,
    )
    fields = ['20', '3', '71', '1',  # Message, version, request and row count.
              '0', '123', 'SYNTH', 'STK', '', '0', '', 'NASDAQ', 'USD',
              'SYNTH', 'NASDAQ', 'NMS', '', '', '', '']
    Decoder(wrapper, 157).processScannerDataMsg(iter(item.encode() for item in fields))
    assert ends == [71] and len(rows) == 1
    assert rows[0].contractDetails.contract.primaryExchange == ''
    return rows[0]


def test_auto_volume_qualifies_real_sdk_scanner_contract_before_live_quote(monkeypatch):
    from copy import copy
    f = Fake()
    row = _sdk_scanner_row()
    source = row.contractDetails.contract
    original_scan = f.reqScannerData
    def scan(subscription):
        original_scan(subscription)
        f.last_scanner_request['row_count'] = 1
        return [row]
    f.reqScannerData = scan
    calls = []
    def resolve(symbol):
        assert symbol == source.symbol
        calls.append('qualify')
        resolved = copy(source)
        resolved.primaryExchange = 'NASDAQ'
        return NS(contract=resolved)
    f.resolve_contract = resolve
    request = f.reqMktData
    def quote(contract, **flags):
        calls.append('quote')
        assert contract.conId == source.conId and contract.symbol == source.symbol
        return request(contract, **flags)
    f.reqMktData = quote
    def evidence(ticker):
        now = datetime.now(timezone.utc).isoformat()
        return {
            'source': 'IBKR_NATIVE_TICK_SIZE', 'sdk_distribution': '9.81.1.post1',
            'session_basis': 'IBKR_CURRENT_TRADING_DAY_CUMULATIVE',
            'security_type': ticker.contract.secType, 'currency': ticker.contract.currency,
            'primary_exchange': ticker.contract.primaryExchange, 'symbol': ticker.contract.symbol,
            'market_data_status': 'LIVE', 'tick_type': 8, 'con_id': ticker.contract.conId,
            'client_id': 71, 'server_version': 157, 'connection_epoch': 0, 'request_id': 1,
            'market_timestamp_utc': now, 'received_at_utc': now, 'raw_value': 39018, 'unit': 'UNKNOWN',
        }
    f.snapshot_volume_evidence = evidence
    def history(contract, **parameters):
        calls.append('history')
        assert contract.conId == source.conId and contract.primaryExchange == 'NASDAQ'
        return NS(volume_basis={'unit': 'UNKNOWN'}, raw_source_bars=({'date': '20261019', 'volume': 81234},))
    f.reqHistoricalData = history
    monkeypatch.setattr(acquisition, 'wait_event', lambda *args: True)
    regular, private = {}, {}
    result = payload.acquire(f, regular.__setitem__, put_private=private.__setitem__, requested_type='LIVE')
    assert result['native_volume_sample_status'] == 'LIVE_TICK8_CAPTURED_UNITS_UNVERIFIED'
    assert calls == ['qualify', 'quote', 'history'] and f.scans == 1 and f.cancelled == [1]
    assert private['volume-probe.json']['watchlist']['primary_exchange'] == 'NASDAQ'
    assert source.primaryExchange == '' and source.exchange == 'NASDAQ'


@pytest.mark.parametrize('field,value', [
    ('conId', 124), ('conId', 123.0), ('symbol', 'OTHER'), ('secType', 'OPT'),
    ('currency', 'CAD'), ('primaryExchange', 'NYSE'), ('localSymbol', 'OTHER'),
    ('tradingClass', 'OTHER'),
])
def test_auto_volume_rejects_qualification_identity_changes_without_trying_another_row(monkeypatch, field, value):
    from copy import copy
    f = Fake()
    row = _sdk_scanner_row()
    source = row.contractDetails.contract
    if field == 'primaryExchange':
        source.primaryExchange = 'NASDAQ'  # Preserve listing identity when a scanner supplies it.
    original_scan = f.reqScannerData
    def scan(subscription):
        fallback_rows = original_scan(subscription)
        f.last_scanner_request['row_count'] = 2
        # A second valid candidate must never replace a failed first selection.
        return [row, fallback_rows[-1]]
    f.reqScannerData = scan
    resolved_symbols = []
    def resolve(symbol):
        resolved_symbols.append(symbol)
        resolved = copy(source)
        resolved.primaryExchange = 'NASDAQ'
        setattr(resolved, field, value)
        return NS(contract=resolved)
    f.resolve_contract = resolve
    f.reqHistoricalData = lambda *a, **k: pytest.fail('No history after mismatched qualification')
    private = {}
    with pytest.raises(RuntimeError, match='CONTRACT_MISMATCH'):
        payload.acquire(f, lambda *a: None, put_private=private.__setitem__, requested_type='LIVE')
    assert f.scans == 1 and resolved_symbols == ['SYNTH']
    assert not f.requests and not f.cancelled and not private


@pytest.mark.parametrize('primary_exchange', ['', 'LSE'])
def test_auto_volume_requires_supported_qualified_primary_exchange_before_quote(primary_exchange):
    from copy import copy
    f = Fake()
    resolve = f.resolve_contract
    symbols = []
    def qualify(symbol):
        symbols.append(symbol)
        resolved = copy(resolve(symbol).contract)
        resolved.primaryExchange = primary_exchange
        return NS(contract=resolved)
    f.resolve_contract = qualify
    with pytest.raises(RuntimeError, match='CONTRACT_UNSUPPORTED'):
        payload.acquire(f, lambda *a: None, put_private=lambda *a: None, requested_type='LIVE')
    assert f.scans == 1 and symbols == ['NATURAL_0'] and not f.requests


@pytest.mark.parametrize('expired', [False, True])
def test_auto_volume_qualification_failure_or_deadline_starts_no_quote(monkeypatch, expired):
    f = Fake()
    clock = [0.0]
    monkeypatch.setattr(acquisition.time, 'monotonic', lambda: clock[0])
    resolve = f.resolve_contract
    calls = []
    def qualify(symbol):
        calls.append(symbol)
        if not expired:
            raise RuntimeError('Synthetic contract lookup failure')
        result = resolve(symbol)
        clock[0] = 26.0
        return result
    f.resolve_contract = qualify
    expected = acquisition.AcquisitionDeadlineExceeded if expired else RuntimeError
    with pytest.raises(expected):
        payload.acquire(f, lambda *a: None, put_private=lambda *a: None, requested_type='LIVE')
    assert f.scans == 1 and calls == ['NATURAL_0'] and not f.requests and not f._market_events


def test_regular_quote_profile_does_not_add_volume_contract_resolution(monkeypatch):
    f = Fake()
    f.resolve_contract = lambda *a: pytest.fail('Qualification is limited to the private volume profile')
    monkeypatch.setattr(acquisition, 'wait_event', lambda *args: True)
    result = payload.acquire(f, lambda *a: None)
    assert f.scans == 1 and len(f.requests) == 1 and result['quotes'][0]['diagnostic_fields_available']


def test_broker_error_facts_are_numeric_bounded_and_exclude_private_payloads():
    errors = [{"code": code, "message": "PRIVATE_BROKER_ACCOUNT_ORDER_TEXT"} for code in range(40)]
    errors += [{"code": 3}, {"code": True}, {"code": "354"}, {"code": 2**31},
               {"code": -(2**31)-1}, {"message": "PRIVATE_MALFORMED_TEXT"}, "PRIVATE_UNSTRUCTURED"]
    facts = payload.broker_error_facts(errors)
    assert facts == {
        "broker_error_count": 47, "broker_error_codes": list(range(32)),
        "broker_error_codes_truncated": True, "broker_error_codes_unavailable": False,
    }
    assert "PRIVATE" not in repr(facts) and "message" not in facts
    assert payload.broker_error_facts([]) == {
        "broker_error_count": 0, "broker_error_codes": [],
        "broker_error_codes_truncated": False, "broker_error_codes_unavailable": False,
    }
    assert payload.broker_error_facts([{"message": "PRIVATE"}])["broker_error_codes_unavailable"]


def test_live_volume_broker_failure_exports_codes_without_qualifying_or_starting_history(monkeypatch):
    f = Fake()
    request = f.reqMktData
    def rejected(*args, **kwargs):
        ticker = request(*args, **kwargs)
        ticker.snapshotEnd = False
        ticker.bid = ticker.ask = ticker.close = ticker.volume = None
        ticker.brokerErrors = [{"code": 354, "message": "PRIVATE_ENTITLEMENT_TEXT", "account": "PRIVATE_ACCOUNT"}]
        return ticker
    f.reqMktData = rejected
    f.snapshot_volume_evidence = lambda ticker: None
    f.reqHistoricalData = lambda *args, **kwargs: pytest.fail("No history after broker error")
    monkeypatch.setattr(acquisition, "wait_event", lambda *args: True)
    regular, private = {}, {}
    result = payload.acquire(f, regular.__setitem__, requested_type="LIVE", put_private=private.__setitem__)
    quote = result["quotes"][0]
    assert quote["broker_error_codes"] == [354] and quote["broker_error_count"] == 1
    assert quote["completion_reason"] == "broker_error" and not quote["snapshot_complete"]
    assert not quote["diagnostic_fields_available"]
    assert result["native_volume_sample_status"] == "ROSS_VOLUME_EVIDENCE_MISSING"
    assert private == {"native-volume.json": None}
    assert "PRIVATE" not in repr(regular) + repr(private)
    assert f.scans == 1 and len(f.requests) == 1 and f.cancelled == [1]
    assert f.completions == ["broker_error"] and not f._market_events

