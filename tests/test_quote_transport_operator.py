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
        return NS(reqId=req,snapshotEnd=self.mode!='missing',brokerErrors=[],
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
