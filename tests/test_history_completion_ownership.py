"""Synthetic transport only: actual native/MD/provider/resolver history owners."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import pytest
from ibapi.client import EClient
from ibapi.contract import Contract
from src.adapters.brokers.ibkr import ibkr_client as native
from src.ibkr.market_data_client import MarketDataClient, HistoricalDataResult, HistoricalVolumeResult
from src.core.acquisition import (AcquisitionCancelled, AcquisitionDeadlineExceeded,
    acquisition_scope, historical_enrichment_attempt, HISTORY_ATTEMPT_MAX_REQUESTS)
from src.scanner.providers.ibkr_provider import IbkrScannerProvider
from src.market_data.reference_resolver import CanonicalReferenceResolver, PersistentReferenceCache
from src.market_data.candidate_identity import CandidateIdentity


def confirmed(bars=()):
    return HistoricalDataResult('COMPLETE_BARS' if bars else 'COMPLETE_EMPTY',tuple(bars),True)


def contract(conid=123):
    c=Contract();c.symbol='SYNTH';c.conId=conid;c.primaryExchange='NASDAQ'
    c.exchange='SMART';c.currency='USD';c.secType='STK';c.localSymbol='SYNTH';c.tradingClass='SCM'
    return c


@pytest.fixture(autouse=True)
def prohibit_acquisition_and_mutation(monkeypatch,tmp_path):
    monkeypatch.setenv('IBKR_ORDER_ID_STATE_PATH',str(tmp_path/'isolated-order-state.json'))
    monkeypatch.delenv('PR1090_STOP_FILE',raising=False)
    def forbidden(*a,**kw):raise AssertionError('No network, broker mutation or execution submission')
    for method in ['connect','reqHistoricalData','cancelHistoricalData','placeOrder','cancelOrder','reqGlobalCancel']:
        monkeypatch.setattr(EClient,method,forbidden)
    from src.execution.execution_engine import ExecutionEngine
    monkeypatch.setattr(ExecutionEngine,'execute_trade',forbidden)


@pytest.fixture
def owner(monkeypatch):
    c=native.IbkrClient('127.0.0.1',7497,999,5,'LIVE',True)
    monkeypatch.setattr(c,'isConnected',lambda:True)
    monkeypatch.setattr(c,'is_connected',lambda:True)
    class Clock:
        value=0.;on_wait=None
        def monotonic(self):return self.value
        def sleep(self,seconds):
            self.value+=seconds
            if self.on_wait:self.on_wait()
    clock=Clock()
    class Event:
        flag=False
        def set(self):self.flag=True
        def is_set(self):return self.flag
        def wait(self,seconds):
            if not self.flag:
                clock.value+=seconds
                if clock.on_wait:clock.on_wait()
            return self.flag
    monkeypatch.setattr(native,'time',clock)
    monkeypatch.setattr(native,'threading',NS(Event=Event))
    sent=[];cancel=[]
    monkeypatch.setattr(EClient,'cancelHistoricalData',lambda self,req:cancel.append(req))
    def send(self,req,*args):sent.append(req)
    monkeypatch.setattr(EClient,'reqHistoricalData',send)
    return NS(client=c,clock=clock,sent=sent,cancel=cancel)


def retired(c):
    assert not c._historical_states and not c._historical_data and not c._historical_events
    assert 'HISTORICAL_DATA' not in c._request_type_by_req_id.values()


@pytest.mark.parametrize('kind',['bars','empty','partial','timeout','error','disconnect','send_error'])
def test_native_only_end_can_confirm_history(owner,monkeypatch,kind):
    o=owner;c=o.client;bar=NS(date='20261027',close=10.,volume=100)
    def send(self,req,*args):
        o.sent.append(req)
        if kind in {'bars','partial','disconnect'}:c.historicalData(req,bar)
        if kind in {'bars','empty'}:c.historicalDataEnd(req,'original-start','original-end')
        if kind=='error':c.error(req,162,'Synthetic history error')
        if kind=='disconnect':c.connectionClosed()
        if kind=='send_error':raise RuntimeError('Synthetic send failure')
    monkeypatch.setattr(EClient,'reqHistoricalData',send)
    result=c.reqHistoricalData(contract())
    expected={'bars':'COMPLETE_BARS','empty':'COMPLETE_EMPTY','partial':'TIMEOUT','timeout':'TIMEOUT',
              'error':'ERROR','disconnect':'DISCONNECTED','send_error':'ERROR'}[kind]
    assert result.status==expected and result.completed==(kind in {'bars','empty'})
    assert result.end_received==(kind in {'bars','empty'})
    assert len(result)==(1 if kind=='bars' else 0)
    if kind=='bars':assert result[0] is bar and result[0].date=='20261027'
    if kind=='partial':assert result.partial_count==1 and o.clock.value==5
    assert o.cancel==([] if kind in {'bars','empty','disconnect'} else o.sent)
    req=result.request_id;retired(c)
    c.historicalData(req,bar);c.historicalDataEnd(req,'late','late')
    retired(c)  # Late callbacks cannot recreate rows/events or confer authority.


@pytest.mark.parametrize('before_send',[True,False])
def test_stop_propagates_and_retires_even_if_sdk_cancel_raises(owner,monkeypatch,before_send):
    o=owner
    def bad_cancel(self,req):o.cancel.append(req);raise RuntimeError('Synthetic cancellation failure')
    monkeypatch.setattr(EClient,'cancelHistoricalData',bad_cancel)
    with pytest.raises(AcquisitionCancelled),acquisition_scope(lambda:before_send or o.clock.value>=.2):
        o.client.reqHistoricalData(contract())
    retired(o.client)
    assert o.cancel==([] if before_send else o.sent)


def test_disconnect_between_registration_and_dispatch_never_sends(owner,monkeypatch):
    c=owner.client;once=[]
    def checkpoint():
        if not once:once.append(True);c.connectionClosed()
    monkeypatch.setattr(native,'checkpoint',checkpoint)
    result=c.reqHistoricalData(contract())
    assert result.status=='DISCONNECTED' and owner.sent==[] and owner.cancel==[]
    retired(c)


def test_raw_ids_cannot_replace_active_or_retired_owners(owner,monkeypatch):
    c=owner.client
    def send(self,req,*args):
        owner.sent.append(req)
        with pytest.raises(RuntimeError,match='used or retired'):
            c.reqHistoricalData(req,contract())
        c.historicalDataEnd(req,'','')
    monkeypatch.setattr(EClient,'reqHistoricalData',send)
    result=c.reqHistoricalData(200,contract())
    assert result.status=='COMPLETE_EMPTY' and owner.sent==[200]
    retired(c);c._request_context_by_req_id.clear()
    with pytest.raises(RuntimeError,match='used or retired'):c.reqHistoricalData(200,contract())
    c.historicalData(200,NS(close=99));c.historicalDataEnd(200,'','');retired(c)
    allocated=c._next_req_id()
    assert c.reqHistoricalData(allocated,contract()).completed


def test_request_order_ambiguity_preserved_without_cancelling_ambiguous_id(owner,monkeypatch):
    c=owner.client
    def send(self,req,*args):
        owner.sent.append(req)
        c._order_state_registry[req]={}
        c._mark_request_id_conflict(req)
    # Use the established callback entry to discover a real order ownership ID.
    from ibapi.order import Order
    from ibapi.order_state import OrderState
    def send(self,req,*args):
        owner.sent.append(req)
        c.openOrder(req,contract(),Order(),OrderState())
    monkeypatch.setattr(EClient,'reqHistoricalData',send)
    with pytest.raises(RuntimeError,match='ambiguous|conflict|Conflicting|Ambiguous'):
        c.reqHistoricalData(contract())
    assert owner.cancel==[];retired(c)


@pytest.fixture
def chain(owner,monkeypatch,tmp_path):
    c=owner.client
    md=MarketDataClient(connection_manager=NS(get_client=lambda:c),allow_direct_connection=False);md.ib=c
    provider=object.__new__(IbkrScannerProvider);provider.market_data_client=md
    monkeypatch.setattr(provider,'_qualify_identity_contract',lambda identity:contract())
    monkeypatch.setattr(provider,'qualifyContracts',lambda *args:[contract()])
    monkeypatch.setattr(provider,'_qualified_contract_for_symbol',lambda symbol:contract())
    monkeypatch.setattr(provider,'get_quote',lambda *a,**kw:NS(volume=2000,close=9.))
    resolver=CanonicalReferenceResolver(PersistentReferenceCache(tmp_path/'reference.json'))
    identity=CandidateIdentity.from_mapping({'symbol':'SYNTH','conId':123,'exchange':'SMART','primaryExchange':'NASDAQ'})
    return NS(md=md,provider=provider,resolver=resolver,identity=identity,owner=owner)


@pytest.mark.parametrize('outcome',['empty','bars','timeout','error'])
def test_actual_provider_resolver_chain_deduplicates_only_this_attempt(chain,monkeypatch,outcome):
    x=chain;o=x.owner;c=o.client;requests=[]
    def send(self,req,con,end,duration,size,what,rth,*args):
        requests.append((con.conId,end,duration,size,what,rth));o.sent.append(req)
        if outcome=='bars' and not rth:c.historicalData(req,NS(date='20261027',close=10.,volume=100))
        if outcome in {'empty','bars'}:c.historicalDataEnd(req,'','')
        if outcome=='error':c.error(req,162,'Synthetic failure')
    monkeypatch.setattr(EClient,'reqHistoricalData',send)
    def run():
        with historical_enrichment_attempt() as scope:
            stats=x.provider.get_intraday_stats('SYNTH')
            result=x.resolver.resolve(identity=x.identity,provider=x.provider,session_label='RTH_MID',
                current_volume=2000,intraday_avg_volume_20d=stats.average_daily_volume_20d,
                intraday_history_end_received=stats.historical_end_received,current_last_price=10.,
                rth_open_price=9.,rth_close_price=9.,ibkr_change_pct=None,persisted_pct_change=None)
            same=x.resolver.resolve(identity=x.identity,provider=x.provider,session_label='RTH_MID',
                current_volume=2000,intraday_avg_volume_20d=stats.average_daily_volume_20d,
                intraday_history_end_received=stats.historical_end_received,current_last_price=10.,
                rth_open_price=9.,rth_close_price=9.,ibkr_change_pct=None,persisted_pct_change=None)
            assert same is result
            assert result.historical_outcome==({'empty':'COMPLETE_EMPTY','bars':'COMPLETE_BARS','timeout':'TIMEOUT','error':'ERROR'}[outcome])
            if outcome=='bars':assert stats.average_daily_volume_20d==result.avg_volume_20d==100
            else:assert stats.average_daily_volume_20d is None and result.avg_volume_20d is None
            count=len(requests)
            assert count in (2,4)
        assert not scope
    run();per_attempt=4 if outcome in {'empty','bars'} else 2
    assert len(requests)==len(set(requests))==per_attempt
    first=list(requests);requests.clear();run()
    assert requests==first and len(requests)==per_attempt  # no persistent negative/positive history cache


def test_exact_identity_durations_and_bounded_inflight_reservation(chain,monkeypatch):
    x=chain;c=x.owner.client;requests=[];nested=[]
    def send(self,req,con,*args):
        requests.append((con.conId,args))
        if len(requests)==1:
            nested.append(x.md.daily_bars_from_history(con,lookback_days=20,use_rth=False))
        c.historicalDataEnd(req,'','')
    monkeypatch.setattr(EClient,'reqHistoricalData',send)
    with historical_enrichment_attempt() as scope:
        x.md.daily_bars_from_history(contract(),lookback_days=20,use_rth=False)
        assert nested[0].status=='IN_PROGRESS' and len(requests)==1
        result=x.md.daily_bars_from_history(contract(),lookback_days=25,use_rth=False)
        assert result.completed
        x.md.daily_bars_from_history(contract(456),lookback_days=25,use_rth=False)
        assert len({r[0] for r in requests})==2
        assert {r[1][1] for r in requests}>={'20 D','25 D'}
    assert not scope


def test_unwitnessed_sdk_list_never_becomes_usable_history(chain,monkeypatch):
    x=chain
    monkeypatch.setattr(x.owner.client,'reqHistoricalData',lambda *a,**kw:[NS(date='20261027',close=999,volume=999)])
    result=x.md.daily_bars_from_history(contract())
    assert result.status=='UNVERIFIED' and not result
    monkeypatch.setattr(x.provider,'get_daily_bars',lambda *a,**kw:[NS(date='20261027',close=999,volume=999)])
    result=x.resolver._request_historical_daily_bars(x.provider,x.identity,session_label='RTH_MID')
    assert result.status=='UNVERIFIED' and not result
    monkeypatch.setattr(x.provider,'get_average_daily_volume',lambda *a,**kw:(999,20))
    volume=x.resolver._provider_adv20_fallback(x.provider,x.identity)
    assert isinstance(volume,HistoricalVolumeResult) and volume.history.status=='UNVERIFIED' and tuple(volume)==(None,None)


def test_attempt_storage_is_bounded_without_eviction_or_late_repopulation(chain,monkeypatch):
    import contextvars
    x=chain;c=x.owner.client;sent=[]
    def send(self,req,*args):sent.append(req);c.historicalDataEnd(req,'','')
    monkeypatch.setattr(EClient,'reqHistoricalData',send)
    with historical_enrichment_attempt() as scope:
        inherited=contextvars.copy_context()
        for n in range(HISTORY_ATTEMPT_MAX_REQUESTS):
            assert x.md.daily_bars_from_history(contract(1000+n),use_rth=False).completed
        assert len(scope)==len(sent)==HISTORY_ATTEMPT_MAX_REQUESTS
        assert x.md.daily_bars_from_history(contract(9999),use_rth=False).status=='ATTEMPT_CAPACITY'
        assert x.md.daily_bars_from_history(contract(1000),use_rth=False).reused
        assert len(sent)==HISTORY_ATTEMPT_MAX_REQUESTS
    assert not scope and scope.closed
    late=inherited.run(lambda:x.md.daily_bars_from_history(contract(1000),use_rth=False))
    assert late.status=='ATTEMPT_CLOSED' and not scope and len(sent)==HISTORY_ATTEMPT_MAX_REQUESTS
    assert x.md.daily_bars_from_history(contract(1000),use_rth=False).completed
    assert len(sent)==HISTORY_ATTEMPT_MAX_REQUESTS+1


@pytest.mark.parametrize('kind',['complete','empty','error','unwitnessed','cancel','disconnect'])
@pytest.mark.parametrize('raise_errors',[False,True])
def test_real_insync_wrapper_requires_end_and_retires_container(monkeypatch,kind,raise_errors):
    from ib_insync import IB, BarData
    async def run():
        ib=IB();ib.RaiseRequestErrors=raise_errors
        monkeypatch.setattr(ib.client,'getReqId',lambda:99)
        monkeypatch.setattr(ib,'isConnected',lambda:kind!='disconnect')
        original_keys=set(vars(ib.wrapper));cancel=[]
        def send(req,*args):
            if kind not in {'empty','unwitnessed','cancel','disconnect'}:
                ib.wrapper.historicalData(req,BarData(date='20261027',close=10,volume=100))
            if kind in {'complete','empty'}:ib.wrapper.historicalDataEnd(req,'','')
            if kind=='error':ib.wrapper.error(req,162,'Synthetic history error')
            if kind=='unwitnessed':ib.wrapper._endReq(req)
            if kind=='disconnect':ib.wrapper.connectionClosed()
        monkeypatch.setattr(ib.client,'reqHistoricalData',send)
        monkeypatch.setattr(ib.client,'cancelHistoricalData',lambda req:cancel.append(req))
        md=MarketDataClient(connection_manager=NS(),allow_direct_connection=False)
        call=md._cancellable_insync_history(ib,contract(),endDateTime='',durationStr='25 D',
            barSizeSetting='1 day',whatToShow='TRADES',useRTH=True,formatDate=1)
        task=asyncio.create_task(call)
        if kind=='cancel':
            await asyncio.sleep(0);task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
        else:
            result=await task
            expected={'complete':'COMPLETE_BARS','empty':'COMPLETE_EMPTY','error':'ERROR','unwitnessed':'UNVERIFIED','disconnect':'DISCONNECTED'}[kind]
            assert result.status==expected and bool(result)==(kind=='complete')
        assert 99 not in ib.wrapper._results and 99 not in ib.wrapper._futures and 99 not in ib.wrapper._reqId2Contract
        assert 'historicalDataEnd' not in vars(ib.wrapper) and 'error' not in vars(ib.wrapper)
        assert '_ross_history_completion' not in vars(ib.wrapper)
        ib.wrapper.historicalData(99,BarData(date='20261027',close=20,volume=200))
        assert 99 not in ib.wrapper._results
        assert cancel==([] if kind in {'complete','empty','disconnect'} else [99])
    asyncio.run(run())


def test_first_bar_waits_for_later_end_and_late_end_cannot_confirm(owner,monkeypatch):
    c=owner.client
    def send(self,req,*args):
        owner.sent.append(req);c.historicalData(req,NS(date='20261027',close=10,volume=100))
    monkeypatch.setattr(EClient,'reqHistoricalData',send)
    owner.clock.on_wait=lambda:c.historicalDataEnd(owner.sent[-1],'','') if owner.clock.value>=.2 else None
    result=c.reqHistoricalData(contract())
    assert result.completed and len(result)==1 and owner.clock.value>=.2
    retired(c)
    owner.clock.on_wait=None
    result=c.reqHistoricalData(contract())
    assert result.status=='TIMEOUT' and not result
    c.historicalDataEnd(result.request_id,'late','late')
    assert result.status=='TIMEOUT';retired(c)


@pytest.mark.parametrize('partial',[False,True])
def test_insync_timeout_does_not_accept_partial_bars(monkeypatch,partial):
    from ib_insync import IB, BarData
    from src.ibkr import market_data_client as module
    async def run():
        ib=IB();monkeypatch.setattr(ib.client,'getReqId',lambda:42)
        def send(req,*args):
            if partial:ib.wrapper.historicalData(req,BarData(date='20261027',close=10,volume=100))
        monkeypatch.setattr(ib.client,'reqHistoricalData',send)
        cancel=[];monkeypatch.setattr(ib.client,'cancelHistoricalData',lambda req:cancel.append(req))
        async def expired(future,timeout):
            assert timeout==60
            raise asyncio.TimeoutError
        monkeypatch.setattr(module.asyncio,'wait_for',expired)
        md=MarketDataClient(connection_manager=NS(),allow_direct_connection=False)
        result=await md._cancellable_insync_history(ib,contract(),endDateTime='',durationStr='25 D',
            barSizeSetting='1 day',whatToShow='TRADES',useRTH=True,formatDate=1)
        assert result.status=='TIMEOUT' and not result and result.partial_count==int(partial)
        assert cancel==[42] and not ib.wrapper._results and not ib.wrapper._futures
    asyncio.run(run())


def test_insync_overlapping_owners_restore_hooks_without_touching_foreign_request(monkeypatch):
    from ib_insync import IB
    async def run():
        ib=IB();seq=iter([100,101]);monkeypatch.setattr(ib.client,'getReqId',lambda:next(seq))
        monkeypatch.setattr(ib.client,'reqHistoricalData',lambda *a:None)
        cancel=[];monkeypatch.setattr(ib.client,'cancelHistoricalData',lambda req:cancel.append(req))
        foreign=ib.wrapper.startReq(77,contract(),container=[])
        md=MarketDataClient(connection_manager=NS(),allow_direct_connection=False)
        def operation():return md._cancellable_insync_history(ib,contract(),endDateTime='',durationStr='25 D',
            barSizeSetting='1 day',whatToShow='TRADES',useRTH=True,formatDate=1)
        first=asyncio.create_task(operation());second=asyncio.create_task(operation())
        await asyncio.sleep(0)
        assert set(ib.wrapper._ross_history_completion['owners'])=={100,101}
        ib.wrapper.historicalDataEnd(100,'','');assert (await first).completed
        assert 'historicalDataEnd' in vars(ib.wrapper) and not foreign.done()
        ib.wrapper.historicalDataEnd(101,'','');assert (await second).completed
        assert 'historicalDataEnd' not in vars(ib.wrapper) and 'error' not in vars(ib.wrapper)
        assert not foreign.done() and set(ib.wrapper._results)=={77} and cancel==[]
        foreign.cancel();ib.wrapper._endReq(77)
    asyncio.run(run())


@pytest.mark.parametrize('outcome',['empty','bars','timeout'])
@pytest.mark.parametrize('quote_close',[9.,None])
def test_actual_scanner_cycle_projects_reference_without_second_history_attempt(chain,monkeypatch,tmp_path,outcome,quote_close):
    from dataclasses import replace
    import json
    from src.scanner import scanner_runner as ross
    from src.scanner.providers.base import QuoteData
    from src.scanner.scanner_contract import scanner_request_from_policy
    from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy
    from src.config.config_resolver import set_config_overrides
    x=chain;p=x.provider;c=x.owner.client;requests=[]
    set_config_overrides({'RUN_MODE':'READ_ONLY','RUN_MODE_EFFECTIVE':'READ_ONLY','SCANNER_DATA_SOURCE':'IBKR',
        'SCANNER_MODE':'LIVE_READONLY','EXECUTION_ENABLED':False,'NEWS_ENABLED':False,'IBKR_FALLBACK_ENABLED':False})
    monkeypatch.setattr(ross,'_PERSISTENT_PROVIDER',None)
    ross.reset_scanner_runtime_state(clear_persistent_provider=True)
    monkeypatch.setattr(ross,'_REFERENCE_RESOLVER',x.resolver)
    monkeypatch.setattr(p,'connect',lambda:None);monkeypatch.setattr(p,'disconnect',lambda:None)
    monkeypatch.setattr(p,'get_top_gainers',lambda *a,**kw:['SYNTH'])
    monkeypatch.setattr(p,'get_float',lambda *a:5_000_000)
    monkeypatch.setattr(p,'get_quote',lambda *a,**kw:QuoteData(symbol='SYNTH',bid=10.99,ask=11.01,last=11.,vwap=11.,
        open=9.,high=11.5,low=9.,close=quote_close,change_percent=None,volume=2_000_000,
        timestamp_utc=datetime.now(timezone.utc).isoformat(),timestamp_source='LAST_TRADE',data_quality_flags=()))
    p.last_scan_details={'symbol_details':{'SYNTH':{'conId':123,'exchange':'SMART','primaryExchange':'NASDAQ',
        'localSymbol':'SYNTH','tradingClass':'SCM','currency':'USD'}},'returned_rows':1}
    cache=tmp_path/'float.json';cache.write_text(json.dumps({'SYNTH':{'float_value':5_000_000,
        'float_source':'SYNTHETIC','float_asof':datetime.now(timezone.utc).isoformat()}}))
    monkeypatch.setattr(ross,'_resolve_float_cache_path',lambda:cache)
    def send(self,req,con,end,duration,size,what,rth,*args):
        requests.append((con.conId,end,duration,size,what,rth))
        if outcome=='bars' and not rth:c.historicalData(req,NS(date='20261027',close=9.,volume=100_000))
        if outcome!='timeout':c.historicalDataEnd(req,'','')
    monkeypatch.setattr(EClient,'reqHistoricalData',send)
    policy=replace(RossMomentumPolicy().stock_selection,top_gainers_n=1,max_symbols_per_cycle=1,watchlist_limit_k=1,focus_limit_m=1)
    try:
        result=ross.run_scanner_cycle(mode='READONLY',policy=policy,provider=p,disconnect_provider=False,
            scanner_request=scanner_request_from_policy(policy,strategy_name='ross_momentum'),
            forced_session_label='RTH_MID',forced_session_source='SYNTHETIC_OFFLINE_HISTORY_CONTROL')
        assert result is not None
        assert len(requests)==len(set(requests))==(2 if outcome=='timeout' else 4),requests
        assert {'20 D','25 D'}=={row[2] for row in requests}
    finally:
        ross.reset_scanner_runtime_state(clear_persistent_provider=True);set_config_overrides(None)


def test_raw_streaming_history_cancels_owned_subscription_after_initial_end(owner,monkeypatch):
    c=owner.client
    def send(self,req,*args):
        owner.sent.append(req);c.historicalData(req,NS(date='20261027',close=10,volume=100));c.historicalDataEnd(req,'','')
    monkeypatch.setattr(EClient,'reqHistoricalData',send)
    result=c.reqHistoricalData(100,contract(),'','25 D','1 day','TRADES',1,1,True,[])
    assert result.completed and len(result)==1 and owner.cancel==[100]
    retired(c);c.historicalData(100,NS(date='20261028',close=11,volume=200));retired(c)


def test_insync_retirement_does_not_finish_or_cancel_replacement_future(monkeypatch):
    from ib_insync import IB
    async def run():
        ib=IB();monkeypatch.setattr(ib.client,'getReqId',lambda:42)
        monkeypatch.setattr(ib.client,'reqHistoricalData',lambda *a:None)
        cancelled=[];monkeypatch.setattr(ib.client,'cancelHistoricalData',lambda req:cancelled.append(req))
        md=MarketDataClient(connection_manager=NS(),allow_direct_connection=False)
        task=asyncio.create_task(md._cancellable_insync_history(ib,contract(),endDateTime='',durationStr='25 D',
            barSizeSetting='1 day',whatToShow='TRADES',useRTH=True,formatDate=1))
        await asyncio.sleep(0)
        old=ib.wrapper._futures[42]
        replacement=asyncio.get_running_loop().create_future();rows=[];other=contract(456)
        ib.wrapper._futures[42]=replacement;ib.wrapper._results[42]=rows;ib.wrapper._reqId2Contract[42]=other
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert not replacement.done() and ib.wrapper._futures[42] is replacement
        assert ib.wrapper._results[42] is rows and ib.wrapper._reqId2Contract[42] is other
        assert cancelled==[]
        replacement.cancel();ib.wrapper._endReq(42)
    asyncio.run(run())


def test_cached_history_revalidates_request_ownership(chain,monkeypatch):
    from ibapi.order import Order
    from ibapi.order_state import OrderState
    x=chain;c=x.owner.client;sent=[]
    def send(self,req,*args):sent.append(req);c.historicalData(req,NS(date='20261027',close=10,volume=100));c.historicalDataEnd(req,'','')
    monkeypatch.setattr(EClient,'reqHistoricalData',send)
    with historical_enrichment_attempt():
        first=x.md.daily_bars_from_history(contract(),use_rth=False)
        assert first.completed
        c.openOrder(first.request_id,contract(),Order(),OrderState())
        again=x.md.daily_bars_from_history(contract(),use_rth=False)
        assert again.status=='REQUEST_ID_CONFLICT' and not again and len(sent)==1


@pytest.mark.parametrize('status',['TIMEOUT','ERROR','CANCELLED','DISCONNECTED','COMPLETE_EMPTY'])
def test_derived_volume_never_exposes_unavailable_or_empty_history(chain,monkeypatch,status):
    history=HistoricalDataResult(status,end_received=status=='COMPLETE_EMPTY')
    malformed=HistoricalVolumeResult(999,20,history)
    assert tuple(malformed)==(None,None)
    monkeypatch.setattr(chain.provider,'_average_daily_volume',lambda *a:(999,20))
    stats=chain.provider.get_intraday_stats('SYNTH')
    assert stats.average_daily_volume_20d is None and stats.historical_end_received is None
