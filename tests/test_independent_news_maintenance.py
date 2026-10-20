"""Broker-free concurrency receipts. All acquisition transports below are fixtures."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import subprocess
import sys
import threading
import time

import pytest

from test_news_catalyst_lifecycle_audit import lifecycle

from src.core.acquisition import checkpoint
from src.news.evidence_store import CanonicalNewsEvidenceStore
from src.news.feed_pool import SharedFeedPool
from src.news.maintenance import NewsMaintenance, request_key
from src.news.news_intelligence_contract import NewsBatchResult,NewsCandidate,NewsEvidence,NewsRequest,RetrievalDiagnostics,RetrievalPolicy
from src.news.news_intelligence_service import CanonicalNewsIntelligenceService
from src.scanner import scanner_runner as ross
from src.strategies.ross_momentum.policy.catalyst_lifecycle import evidence_handoff,revalidate_handoff


def fact(symbol, title=None, age=60):
    return NewsEvidence(symbol=symbol,evidence_id=f'{symbol}:{title or "event"}',
        headline=title or f'{symbol} reports earnings beat',published_at=datetime.now(timezone.utc)-timedelta(seconds=age),
        provider='rss_batch',source_tier='operational_query')


def until(predicate, timeout=4):
    deadline=time.monotonic()+timeout
    while not predicate():
        if time.monotonic()>deadline:raise AssertionError('controlled deadline exceeded')
        time.sleep(.005)


@pytest.fixture
def store(tmp_path):
    return CanonicalNewsEvidenceStore(tmp_path/'canonical.json',prep_artifact_loader=lambda:{})


def test_thread_writers_merge_and_readers_never_see_partial_json(store):
    store.write({'SEED':(fact('SEED'),)})
    stop=threading.Event();errors=[]
    def reader():
        while not stop.is_set():
            try:json.loads(store.cache_path.read_text())
            except Exception as exc:errors.append(exc)
    thread=threading.Thread(target=reader);thread.start()
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes=list(pool.map(lambda i:CanonicalNewsEvidenceStore(store.cache_path).write({f'S{i}':(fact(f'S{i}'),)}),range(24)))
        assert not any(row['cache_write_failed'] for row in outcomes)
    finally:stop.set();thread.join(2)
    assert not errors and not thread.is_alive()
    symbols=json.loads(store.cache_path.read_text())['news_intelligence']['symbols']
    assert len(symbols)==25 and 'SEED' in symbols


def test_process_writers_share_same_owner(store):
    code="""import sys
from src.news.evidence_store import CanonicalNewsEvidenceStore
from src.news.news_intelligence_contract import NewsEvidence
from pathlib import Path
s=CanonicalNewsEvidenceStore(Path(sys.argv[1]))
for i in range(8):
 r=s.write({sys.argv[2]+str(i):(NewsEvidence(symbol=sys.argv[2]+str(i),headline='fixture'),)})
 assert not r['cache_write_failed'],r
"""
    children=[subprocess.Popen([sys.executable,'-c',code,str(store.cache_path),prefix],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for prefix in ('A','B','C')]
    for child in children:
        out,err=child.communicate(timeout=20)
        assert child.returncode==0,(out,err)
    assert len(json.loads(store.cache_path.read_text())['news_intelligence']['symbols'])==24


@pytest.mark.parametrize('corrupt',['{corrupt','[]','null','{"news_intelligence":[]}'])
def test_corrupt_or_failed_publication_preserves_previous_bytes(store,monkeypatch,corrupt):
    import src.news.store_owner as module
    store.write({'JPM':(fact('JPM'),)})
    original=store.cache_path.read_bytes()
    monkeypatch.setattr(module.os,'replace',lambda *args:(_ for _ in ()).throw(OSError('fixture publish failure')))
    assert store.write({'EGG':(fact('EGG'),)})['cache_write_failed']
    assert store.cache_path.read_bytes()==original
    assert not list(store.cache_path.parent.glob('*.tmp'))
    store.cache_path.write_text(corrupt)
    assert store.write({'EGG':(fact('EGG'),)})['cache_write_failed']
    assert store.cache_path.read_text()==corrupt


def test_research_writer_cannot_evict_ross_positive_or_retained_veto(store):
    request=ross._ross_news_request()
    positive=fact('JPM');offering=fact('JPM','JPM announces offering',age=7*3600)
    store.write({'JPM':(positive,offering)},request)
    handoff=evidence_handoff('JPM',(positive,),NewsCandidate('JPM'),acquisition_health='healthy',acquisition_reason='fixture')
    for i in range(8):
        store.write({'JPM':(fact('JPM',f'JPM market roundup {i}',age=i),)},NewsRequest(max_evidence_per_symbol=2))
    bucket=json.loads(store.cache_path.read_text())['news_intelligence']['symbols']['JPM']
    assert any(row['evidence_id']==positive.evidence_id for row in bucket['evidence'])
    assert any(row['evidence_id']==offering.evidence_id for row in bucket['evidence'])
    decision=revalidate_handoff('JPM',handoff,store=store)
    assert not decision['qualified'] and decision['dilution_veto']


def factory(store, release, calls, *, failing=()):
    class Provider:
        provider_id='fixture'
        def get_news(self,candidates,request,policy):
            symbol=candidates[0].symbol;calls.append(symbol)
            while symbol=='SLOW' and not release.is_set():
                checkpoint();release.wait(.01)
            if symbol in failing:raise OSError('controlled source failure')
            return NewsBatchResult(candidates=tuple(candidates),request=request,evidence_by_symbol={symbol:(fact(symbol),)},
                diagnostics=RetrievalDiagnostics(provider_available=True,retrieval_status='available'))
    return lambda:CanonicalNewsIntelligenceService(evidence_store=store,retrieval_provider=Provider())


def test_incremental_first_result_precedes_slow_batch_completion_and_dedup(store):
    release=threading.Event();calls=[]
    owner=NewsMaintenance(store=store,service_factory=factory(store,release,calls),capacity=4)
    request=NewsRequest(max_evidence_per_symbol=5);policy=RetrievalPolicy(refresh_interval_seconds=120,total_budget_seconds=8)
    candidates=(NewsCandidate('SLOW'),NewsCandidate('FAST'))
    start=time.monotonic()
    try:
        assert owner.submit(candidates,request,policy)==2
        assert owner.submit(candidates,request,policy)==0
        until(lambda:bool(store.read((NewsCandidate('FAST'),)).evidence_by_symbol['FAST']))
        first=time.monotonic()-start
        assert not release.is_set() and 'SLOW' in calls
        assert not store.read((NewsCandidate('SLOW'),)).evidence_by_symbol['SLOW']
        time.sleep(.03);release.set()
        until(lambda:owner.snapshot()['completed']==2)
        complete=time.monotonic()-start
        assert first<complete
        assert sorted(calls)==['FAST','SLOW']
        assert owner.snapshot()['tracked']==2 and owner.snapshot()['deduplicated']==2
        print(f'SYNTHETIC_MAINTENANCE_TIMING first_usable={first:.6f}s batch_complete={complete:.6f}s (fixture waits, not live speed)')
    finally:release.set();assert owner.close(2)


def test_bounded_queue_priority_fairness_and_identity_exclusion(store):
    owner=NewsMaintenance(store=store,capacity=8,workers=1)
    request=NewsRequest();policy=RetrievalPolicy()
    # Keep dispatch deterministic without starting real worker threads.
    owner.threads=[threading.current_thread()]
    candidates=[NewsCandidate(f'A{i}') for i in range(7)]+[NewsCandidate('OLD')]
    assert owner.submit(candidates,request,policy)==8
    assert owner.submit((NewsCandidate('OVER'),),request,policy)==0
    owner.set_active([f'A{i}' for i in range(7)],())
    selected=[]
    for _ in range(4):
        item=owner._take();selected.append(item.candidate.symbol);item.running=False;item.due=float('inf')
    assert selected[-1]=='OLD' and owner.snapshot()['rejected_full']==1
    duplicate=replace(candidates[4],priority_rank=99,price=17)
    assert request_key(duplicate,request,policy)==request_key(candidates[4],request,policy)
    # Different requests for the same issuer cannot execute concurrently.
    first=next(item for item in owner.work.values() if item.candidate.symbol=='A4');first.running=True
    owner.capacity=9
    assert owner.submit((duplicate,),replace(request,lookback_seconds=3600),policy)==1
    assert owner._take().candidate.symbol!='A4'


def test_shutdown_cancels_slow_acquisition_and_joins_owned_workers(store):
    release=threading.Event();calls=[]
    owner=NewsMaintenance(store=store,service_factory=factory(store,release,calls),workers=1)
    owner.submit((NewsCandidate('SLOW'),),NewsRequest(),RetrievalPolicy(total_budget_seconds=8))
    until(lambda:bool(calls))
    start=time.monotonic()
    assert owner.close(2)
    assert time.monotonic()-start<2 and owner.snapshot()['alive_workers']==0
    assert not store.cache_path.exists()  # Cancellation is not an unavailable refresh write.
    assert owner.submit((NewsCandidate('AFTER'),),NewsRequest(),RetrievalPolicy())==0


def test_failure_does_not_block_other_issuer_and_keeps_old_evidence(store):
    release=threading.Event();calls=[]
    old=fact('BAD');store.write({'BAD':(old,)})
    owner=NewsMaintenance(store=store,service_factory=factory(store,release,calls,failing={'BAD'}),workers=2)
    try:
        owner.submit((NewsCandidate('BAD'),NewsCandidate('GOOD')),NewsRequest(),RetrievalPolicy(refresh_mode='force_refresh'))
        until(lambda:owner.snapshot()['completed']==2 and owner.snapshot()['failed']==1)
        assert store.read((NewsCandidate('BAD'),)).evidence_by_symbol['BAD'][0].published_at==old.published_at
        assert store.read((NewsCandidate('GOOD'),)).evidence_by_symbol['GOOD']
    finally:assert owner.close(2)


def test_shared_feeds_singleflight_limits_backoff_and_bounded_cache():
    pool=SharedFeedPool(limit=2,capacity=2,ttl=60,failure_backoff=60)
    calls=[];lock=threading.Lock();active=0;maximum=0
    def loader(timeout):
        nonlocal active,maximum
        with lock:active+=1;maximum=max(maximum,active);calls.append(timeout)
        time.sleep(.03)
        with lock:active-=1
        return {'feed':'fixture','error':None}
    with ThreadPoolExecutor(max_workers=8) as workers:
        results=list(workers.map(lambda _:pool.fetch('same',1,loader),range(8)))
    assert len(calls)==1 and sum(row['transport_cache_hit'] for row in results)==7
    with ThreadPoolExecutor(max_workers=6) as workers:
        list(workers.map(lambda i:pool.fetch(str(i),1,loader),range(6)))
    assert maximum<=2 and len(pool.cache)<=2
    bad=lambda timeout:{'feed':None,'error':OSError('fixture')}
    pool.fetch('bad',1,bad)
    assert pool.fetch('bad',1,lambda timeout:pytest.fail('backoff not reused'))['error'] is not None


def test_scanner_reads_incremental_results_without_acquisition_wait(store):
    from src.config.config_resolver import set_config_overrides
    set_config_overrides({'ROSS_ISSUER_QUERY_ENABLED':True})
    release=threading.Event();calls=[]
    owner=NewsMaintenance(store=store,service_factory=factory(store,release,calls))
    try:
        start=time.monotonic()
        ross._enrich_news_context(['FAST','SLOW'],'IBKR',news_maintenance=owner)
        assert time.monotonic()-start<1
        until(lambda:bool(store.read((NewsCandidate('FAST'),)).evidence_by_symbol['FAST']))
        contexts,_=ross._enrich_news_context(['FAST','SLOW'],'IBKR',news_maintenance=owner)
        assert contexts['FAST']['ross_catalyst_valid']
        assert not contexts['SLOW']['ross_catalyst_valid']
        assert calls.count('FAST')==1 and not release.is_set()
    finally:
        release.set();assert owner.close(2)
        set_config_overrides({})


@pytest.mark.parametrize('complete',[True,False])
def test_runtime_shutdown_records_owned_cleanup_and_preserves_required_hooks(monkeypatch,complete):
    from src.config.config_resolver import set_config_overrides
    from src.core.orchestrator import CoreOrchestrator
    from src.core.stop_controller import StopMode
    from src.ibkr.shutdown_evidence import REQUIRED_HOOKS
    from types import SimpleNamespace
    set_config_overrides({'RUN_MODE':'READ_ONLY','EXECUTION_ENABLED':False})
    core=CoreOrchestrator();calls=[]
    core._news_maintenance=SimpleNamespace(close=lambda:calls.append('news') or complete)
    try:
        core._request_stop(StopMode.GRACEFUL,'fixture stop','test')
        core._shutdown(StopMode.GRACEFUL)
        hooks=core.shutdown_evidence.hooks
        assert calls==['news']
        row=next(row for row in hooks if row['hook']=='news_maintenance.shutdown')
        assert row['completed'] is complete
        assert set(REQUIRED_HOOKS)<={row['hook'] for row in hooks}
        event=next(row for row in core.shutdown_evidence.events if row['event']=='SHUTDOWN_COMPLETE')
        if not complete:assert event['completed'] is False
    finally:set_config_overrides({})


def test_universe_rotation_retires_obsolete_pending_work_but_preserves_active(store):
    owner=NewsMaintenance(store=store,capacity=3,workers=1)
    owner.threads=[threading.current_thread()]
    owner.submit(tuple(NewsCandidate(symbol) for symbol in ('OLD','KEEP','RUNNING')),NewsRequest(),RetrievalPolicy())
    owner.set_active(['KEEP'],())
    running=next(item for item in owner.work.values() if item.candidate.symbol=='RUNNING');running.running=True
    owner.set_universe(['NEW'])
    assert owner.submit((NewsCandidate('NEW'),),NewsRequest(),RetrievalPolicy())==1
    assert {item.candidate.symbol for item in owner.work.values()}=={'KEEP','RUNNING','NEW'}
    assert owner.snapshot()['retired']==1


def test_real_fetcher_reuses_shared_feed_and_keeps_per_issuer_attribution(monkeypatch):
    from types import SimpleNamespace
    from src.news import news_fetcher
    from src.news.rss_lifecycle import RssFetchLifecycle
    from src.strategies.ross_momentum.policy.catalyst_policy import select_qualification_evidence
    pool=SharedFeedPool();calls=[]
    published=datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
    def fetch(url,timeout):
        calls.append(url);time.sleep(.03)
        return SimpleNamespace(entries=[{'title':f'{symbol} reports earnings beat','published':published,'published_parsed':time.gmtime(),
              'link':f'https://fixture.invalid/{symbol}'} for symbol in ('JPM','EGG')])
    monkeypatch.setattr(news_fetcher,'_fetch_feed',fetch)
    request=NewsRequest(freshness_seconds=21600,metadata={'presentation_limit':5})
    lifecycles=[RssFetchLifecycle(),RssFetchLifecycle()]
    def acquire(index):
        return news_fetcher.fetch_headlines_for_symbols([('JPM','EGG')[index]],['https://fixture.invalid/shared'],
            source_tier='operational_query',lifecycle=lifecycles[index],feed_pool=pool,
            retention_selector=select_qualification_evidence,retention_request=request,total_news_budget_seconds=2)
    try:
        with ThreadPoolExecutor(max_workers=2) as workers:results=list(workers.map(acquire,range(2)))
        assert len(calls)==1
        for symbol,(headlines,summary) in zip(('JPM','EGG'),results):
            assert len(headlines[symbol])==1 and headlines[symbol][0].title==f'{symbol} reports earnings beat'
        diag=[summary.source_diagnostics[0]['entry_diagnostics'] for _,summary in results]
        assert sorted(row['transport_cache_hit'] for row in diag)==[False,True]
        assert sorted(row['http_request_attempted'] for row in diag)==[False,True]
    finally:
        assert all(lifecycle.wait_for_cleanup(2)['cleanup_complete'] for lifecycle in lifecycles)


def test_nested_rss_workers_cancel_and_cleanup_without_late_store_write(store,monkeypatch):
    from src.news import news_fetcher
    from src.news.rss_lifecycle import current_source_timing
    from src.config.config_resolver import set_config_overrides
    entered=threading.Event()
    def slow(url,timeout):
        entered.set();timing=current_source_timing()
        while not timing['_cancel']():time.sleep(.005)
        raise TimeoutError('controlled cancellation')
    monkeypatch.setattr(news_fetcher,'_fetch_feed',slow)
    set_config_overrides({'ROSS_ISSUER_QUERY_ENABLED':True})
    owner=NewsMaintenance(store=store)
    try:
        owner.submit((NewsCandidate('JPM',company_name='JPMORGAN CHASE'),),ross._ross_news_request(),
                     ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True))
        assert entered.wait(2)
        assert owner.close(2)
        assert owner.snapshot()['alive_workers']==0 and not owner.lifecycles
        assert not store.cache_path.exists()
    finally:
        owner.close(2);set_config_overrides({})


def test_supervisor_file_cancels_independent_queue_without_scanner_progress(store,tmp_path,monkeypatch):
    stop=tmp_path/'STOP_REQUESTED';monkeypatch.setenv('PR1090_STOP_FILE',str(stop))
    release=threading.Event();calls=[]
    owner=NewsMaintenance(store=store,service_factory=factory(store,release,calls),workers=1)
    try:
        owner.submit((NewsCandidate('SLOW'),),NewsRequest(),RetrievalPolicy())
        until(lambda:bool(calls))
        stop.write_text('stop')
        until(lambda:owner.snapshot()['alive_workers']==0)
        assert not store.cache_path.exists()
    finally:assert owner.close(2)


def test_pool_checks_external_stop_before_transport():
    stopped=threading.Event();pool=SharedFeedPool(stop_requested=stopped.is_set);stopped.set()
    with pytest.raises(RuntimeError,match='stopped'):
        pool.fetch('fixture',1,lambda timeout:pytest.fail('transport started after stop'))


def test_terminal_requires_owned_news_hook_without_reclassifying_historical_receipts():
    from src.ibkr.shutdown_evidence import REQUIRED_HOOKS,validate_terminal
    hooks=[{'hook':name,'attempted':True,'completed':True} for name in REQUIRED_HOOKS]
    evidence={'events':[{'event':'SHUTDOWN_STARTED','news_maintenance_owned':True}], 'hooks':hooks}
    assert 'Incomplete hook: news_maintenance.shutdown' in validate_terminal(evidence)['blockers']
    evidence['hooks']=hooks+[{'hook':'news_maintenance.shutdown','attempted':True,'completed':True}]
    assert 'Incomplete hook: news_maintenance.shutdown' not in validate_terminal(evidence)['blockers']
    evidence['events'][0]['news_maintenance_owned']=False;evidence['hooks']=hooks
    assert 'Incomplete hook: news_maintenance.shutdown' not in validate_terminal(evidence)['blockers']


def test_failed_publication_is_not_reported_as_a_usable_result(store,monkeypatch):
    from src.news.store_owner import owner_for
    store.write({'OLD':(fact('OLD'),)});original=store.cache_path.read_bytes()
    monkeypatch.setattr(owner_for(store.cache_path),'publish',lambda text:(_ for _ in ()).throw(OSError('controlled disk failure')))
    owner=NewsMaintenance(store=store,service_factory=factory(store,threading.Event(),[]),workers=1)
    try:
        owner.submit((NewsCandidate('GOOD'),),NewsRequest(),RetrievalPolicy())
        until(lambda:owner.snapshot()['publication_failures']==1)
        assert owner.snapshot()['first_evidence_seconds'] is None
        assert owner.receipts[0]['error']=='CanonicalPublicationFailed' and not owner.receipts[0]['published']
        assert store.cache_path.read_bytes()==original
    finally:assert owner.close(2)


def test_cleanup_exception_stops_acquisition_and_cannot_certify_cleanup(store):
    release=threading.Event();calls=[]
    class Lifecycle:
        released=False
        def wait_for_cleanup(self,timeout):
            if not self.released:raise RuntimeError('fixture cleanup error')
            return {'cleanup_complete':True}
    lifecycle=Lifecycle();build=factory(store,release,calls)
    def service():
        result=build();result.retrieval_provider._lifecycle=lifecycle;return result
    owner=NewsMaintenance(store=store,service_factory=service,workers=1)
    owner.submit((NewsCandidate('GOOD'),),NewsRequest(),RetrievalPolicy())
    until(lambda:owner.stop.is_set())
    assert owner.close(.2) is False
    assert owner.snapshot()['alive_workers']==0
    lifecycle.released=True
    assert owner.close(.2) is True


def test_existing_cadence_applies_to_success_and_failure_without_exponential_retry(lifecycle):
    from test_news_catalyst_lifecycle_audit import CANDIDATE
    life=lifecycle
    owner=NewsMaintenance(store=life.store,service_factory=lambda:life.service,workers=1,
                          clock=lambda:life.clock.current.timestamp())
    policy=replace(life.policy,refresh_interval_seconds=60)
    try:
        owner.submit((CANDIDATE,),life.request,policy)
        until(lambda:owner.snapshot()['completed']==1)
        life.clock.current+=timedelta(seconds=59)
        with owner.condition:owner.condition.notify_all()
        time.sleep(.03)
        assert life.provider.calls==1
        life.provider.failure=True;life.clock.current+=timedelta(seconds=1)
        with owner.condition:owner.condition.notify_all()
        until(lambda:owner.snapshot()['completed']==2)
        assert life.provider.calls==2
        life.clock.current+=timedelta(seconds=60)
        with owner.condition:owner.condition.notify_all()
        until(lambda:owner.snapshot()['completed']==3)
        assert life.provider.calls==3
    finally:assert owner.close(2)


def test_late_publisher_merges_facts_without_rolling_back_newer_acquisition_health(store):
    newer={'completed_at':'2026-10-20T15:00:01+00:00','provider_available':False,'provider_status':'provider_request_failure'}
    older={'completed_at':'2026-10-20T15:00:00+00:00','provider_available':True,'provider_status':'available'}
    store.write({'JPM':(fact('JPM','JPM reports earnings beat'),)},retrieval_by_symbol={'JPM':newer})
    store.write({'JPM':(fact('JPM','JPM wins contract'),)},retrieval_by_symbol={'JPM':older})
    bucket=json.loads(store.cache_path.read_text())['news_intelligence']['symbols']['JPM']
    assert len(bucket['evidence'])==2 and bucket['last_retrieval']==newer


def test_runtime_pins_owner_and_news_disable_stops_without_sync_fallback(monkeypatch):
    from types import SimpleNamespace
    from src.core import orchestrator
    flags={'NEWS_ENABLED':True,'NEWS_MAINTENANCE_ENABLED':True}
    original=orchestrator.get_config
    monkeypatch.setattr(orchestrator,'get_config',lambda key:flags.get(key,original(key)))
    runtime=SimpleNamespace(stop_controller=SimpleNamespace(is_stop_requested=lambda:False))
    owner=orchestrator.CoreOrchestrator._runtime_news_maintenance(runtime)
    assert not owner.stopped() and owner.snapshot()['alive_workers']==0
    flags['NEWS_MAINTENANCE_ENABLED']=False
    assert orchestrator.CoreOrchestrator._runtime_news_maintenance(runtime) is owner
    flags['NEWS_ENABLED']=False
    assert owner.stopped()
    assert orchestrator.CoreOrchestrator._runtime_news_maintenance(runtime) is owner
    assert owner.close(.2)
