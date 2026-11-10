"""Synthetic external callbacks/wire; genuine qualification/rule/completion owners."""
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone, timedelta
from decimal import Decimal, localcontext
from threading import Event, Thread
from types import SimpleNamespace as NS
import pytest
from ibapi.client import EClient
from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from test_ibkr_reference_names import contract


def price_client(monkeypatch, *, route='SMART', mode='complete', bands=((0,.005),(1.02,.03),(10.25,.05))):
    from ibapi.contract import ContractDetails
    client=IbkrClient('127.0.0.1',7497,999,3,'LIVE',True)
    monkeypatch.setattr(client,'is_connected',lambda:True)
    monkeypatch.setattr(client,'isConnected',lambda:True)
    monkeypatch.setattr(client,'serverVersion',lambda:200)
    details=ContractDetails();details.contract=contract();details.longName='Synthetic only'
    details.validExchanges='SMART,NASDAQ';details.marketRuleIds='26,27'
    def qualify(req_id,c):
        client.contractDetails(req_id,details);client.contractDetailsEnd(req_id)
    monkeypatch.setattr(client,'reqContractDetails',qualify)
    c=contract();client.qualifyContracts(c)
    wire=[]
    def send(message):
        wire.append(message)
        if mode=='complete':client.marketRule(26 if route=='SMART' else 27,[NS(lowEdge=e,increment=i) for e,i in bands])
        if mode=='error':client.error(-1,503,'synthetic unsupported market rule')
    monkeypatch.setattr(client,'sendMsg',send)
    return client,c,details,wire


def test_real_sdk_encoding_completed_immutable_scoped_bands(monkeypatch):
    client,c,detail,wire=price_client(monkeypatch)
    result=client.price_rule_snapshot(c,route='SMART')
    assert result.status=='COMPLETE' and result.rule_id==26 and result.qualification_request>0
    assert len(wire)==1 and str(wire[0]).endswith('26\x00')
    assert result.bands==((Decimal(0),Decimal('.005')),(Decimal('1.02'),Decimal('.03')),(Decimal('10.25'),Decimal('.05')))
    assert client.validate_price_rule(result,c,route='SMART',observed_at=datetime.now(timezone.utc),max_age_seconds=3)
    detail.marketRuleIds='99,99'  # End-owned frozen rows, not live mutable SDK objects.
    assert client.price_rule_snapshot(c,route='SMART') is result and len(wire)==1
    client.marketRule(26,[NS(lowEdge=e,increment=i) for e,i in ((0,.005),(1.02,.03),(10.25,.05))])
    assert client.price_rule_snapshot(c,route='SMART') is result
    with pytest.raises(FrozenInstanceError):result.status='COMPLETE'
    assert not client.validate_price_rule(replace(result),c,route='SMART',observed_at=datetime.now(timezone.utc),max_age_seconds=3)
    assert not client.validate_price_rule(result,c,route='NASDAQ',observed_at=datetime.now(timezone.utc),max_age_seconds=3)
    assert not client.validate_price_rule(result,c,route='SMART',observed_at=result.completed_at+timedelta(seconds=4),max_age_seconds=3)
    assert not client.validate_price_rule(result,c,route='SMART',observed_at=result.completed_at-timedelta(seconds=1),max_age_seconds=3)
    with pytest.raises(RuntimeError,match='unowned'):client.reqMarketRule(26)


@pytest.mark.parametrize('value,expected',[(.991,'.995'),(.999,'1.000'),(1.02,'1.02'),(10.249,'10.25'),(10.30,'10.30')])
def test_exact_grid_and_band_crossing(monkeypatch,value,expected):
    client,c,_,_=price_client(monkeypatch)
    rule=client.price_rule_snapshot(c,route='SMART')
    with localcontext() as ctx:
        ctx.prec=3  # Exact integer-ratio normalization must not inherit decimal rounding.
        assert rule.normalize_long_stop(value,original_stop='.5',effective_stop='.6',bid='12')==Decimal(expected)


@pytest.mark.parametrize('bad',[(('.1','.01'),),((0,0),),((0,.01),(1,.05),(.5,.01)),((0,True),),((0,float('nan')),),()])
def test_malformed_bands_deny(monkeypatch,bad):
    client,c,_,_=price_client(monkeypatch,bands=bad)
    assert client.price_rule_snapshot(c,route='SMART').status=='MALFORMED'


@pytest.mark.parametrize('fault',['missing','duplicate_route','length','wrong_conid','wrong_route','bool_conid'])
def test_qualification_metadata_is_not_inferred(monkeypatch,fault):
    client,c,detail,wire=price_client(monkeypatch)
    if fault=='missing':detail.marketRuleIds=''
    if fault=='duplicate_route':detail.validExchanges='SMART,SMART'
    if fault=='length':detail.marketRuleIds='26'
    if fault=='wrong_conid':detail.contract.conId=888
    if fault=='bool_conid':detail.contract.conId=True;c.conId=1
    client.qualifyContracts(contract())
    assert client.price_rule_snapshot(c,route='NYSE' if fault=='wrong_route' else 'SMART').status=='UNAVAILABLE'
    assert wire==[]


def test_timeout_late_error_epoch_and_unsolicited_never_rearm(monkeypatch):
    client,c,_,wire=price_client(monkeypatch,mode='hold')
    timed=client.price_rule_snapshot(c,route='SMART',timeout_seconds=0)
    assert timed.status=='TIMEOUT'
    client.marketRule(26,[NS(lowEdge=0,increment=.01)])
    assert client.price_rule_snapshot(c,route='SMART') is timed and len(wire)==1
    client._invalidate_position_queries()
    client.qualifyContracts(contract())
    assert client.price_rule_snapshot(c,route='SMART').status=='RULE_ID_REUSE_DENIED' and len(wire)==1
    other,c,_,other_wire=price_client(monkeypatch,mode='error')
    assert other.price_rule_snapshot(c,route='SMART').status=='ERROR'
    other.marketRule(26,[NS(lowEdge=0,increment=.01)])
    assert other.price_rule_snapshot(c,route='SMART').status=='ERROR' and len(other_wire)==1
    fresh,c,_,sent=price_client(monkeypatch)
    fresh.marketRule(26,[NS(lowEdge=0,increment=.01)])
    assert fresh.price_rule_snapshot(c,route='SMART').status=='RULE_ID_REUSE_DENIED' and sent==[]


def test_concurrent_admission_duplicate_conflict_and_disconnect(monkeypatch):
    client,c,_,wire=price_client(monkeypatch,mode='hold')
    entered=Event();release=Event();results=[];errors=[]
    def blocked_send(message):
        wire.append(message);entered.set()  # No lock/wait here: real owner releases before waiting.
    monkeypatch.setattr(client,'sendMsg',blocked_send)
    def query():
        try:results.append(client.price_rule_snapshot(c,route='SMART'))
        except BaseException as error:errors.append(error)
    thread=Thread(target=query)
    try:
        thread.start();assert entered.wait(3)
        assert client.price_rule_snapshot(c,route='SMART').status=='PENDING' and len(wire)==1
        client.marketRule(27,[NS(lowEdge=0,increment=.01)])
        client.marketRule(26,[NS(lowEdge=0,increment=.005)])
        thread.join(3);assert not thread.is_alive() and not errors
        result=results[0];assert result.status=='COMPLETE'
        client.marketRule(26,[NS(lowEdge=0,increment=.01)])
        assert client.price_rule_snapshot(c,route='SMART').status=='CONFLICTED'
        assert not client.validate_price_rule(result,c,route='SMART',observed_at=datetime.now(timezone.utc),max_age_seconds=3)
        client._invalidate_position_queries()
        assert not client.validate_price_rule(result,c,route='SMART',observed_at=datetime.now(timezone.utc),max_age_seconds=3)
    finally:
        release.set();client._invalidate_position_queries();thread.join(3)
        assert not thread.is_alive()


def test_blocked_sdk_send_does_not_hold_invalidation_lock(monkeypatch):
    client,c,_,wire=price_client(monkeypatch,mode='hold')
    entered=Event();release=Event();result=[]
    def send(message):
        wire.append(message);entered.set()
        assert release.wait(3)
    monkeypatch.setattr(client,'sendMsg',send)
    thread=Thread(target=lambda:result.append(client.price_rule_snapshot(c,route='SMART')))
    try:
        thread.start();assert entered.wait(3)
        client._invalidate_position_queries()  # Must not wait for transport.
    finally:
        release.set();thread.join(3)
        assert not thread.is_alive()
    assert result[0].status=='DISCONNECTED' and len(wire)==1


@pytest.mark.parametrize('bands',[((0,.01),(1,.03)),((0,.01),(1,.02),(1,.05))])
def test_ambiguous_grid_origin_or_duplicate_band_denies(monkeypatch,bands):
    client,c,_,_=price_client(monkeypatch,bands=bands)
    assert client.price_rule_snapshot(c,route='SMART').status=='MALFORMED'
