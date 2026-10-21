"""Offline callbacks only: no socket, broker, provider, or runtime launch."""
from types import SimpleNamespace as NS
import pytest
from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
import src.adapters.brokers.ibkr.ibkr_client as module


@pytest.mark.parametrize('response', ['empty','rows','missing','wrong_id','error','partial','late_end'])
def test_scanner_requires_matching_end_marker(monkeypatch,response,capsys):
    client=IbkrClient('offline',0,123,0,'LIVE',True)
    client.is_connected=lambda:True
    cancellations=[]
    client.cancelScannerSubscription=lambda req:cancellations.append(req)
    def deliver(req,*args):
        if response in {'rows','partial'}:
            client.scannerData(req,0,NS(contract=NS(symbol='FIXTURE')),'','','','')
        if response in {'empty','rows'}:client.scannerDataEnd(req)
        if response=='wrong_id':client.scannerDataEnd(req+1)
        if response=='error':client.error(req,321,'controlled rejection')
    client.reqScannerSubscription=deliver
    if response=='late_end':
        # Matching end arrives as an expired wait returns: it cannot revive success.
        def expired_wait(event,timeout):
            client.scannerDataEnd(next(iter(client._scanner_events)))
            return False
        monkeypatch.setattr(module,'wait_event',expired_wait)
    if response in {'empty','rows'}:
        rows=client.reqScannerData(NS(scanCode='FIXTURE',locationCode='FIXTURE'))
        assert len(rows)==int(response=='rows')
    else:
        with pytest.raises((TimeoutError,RuntimeError)):
            client.reqScannerData(NS(scanCode='FIXTURE',locationCode='FIXTURE'))
    receipt=client.last_scanner_request
    assert receipt['end_received']==(response in {'empty','rows','late_end'})
    if response=='late_end':assert not receipt['wait_signalled']
    assert len(cancellations)==1
    assert not client._scanner_events and not client._scanner_rows
    assert '[IBKR][SCANNER_RESULT]' in capsys.readouterr().out
    # Late callbacks cannot create rows after cancellation.
    client.scannerData(cancellations[0],0,NS(contract=NS(symbol='LATE')),'','','','')
    assert not client._scanner_rows
