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
