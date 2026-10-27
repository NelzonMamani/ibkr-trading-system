"""v5 policy controls: synthetic HTTP only, strict ownership and fixed budgets."""
from dataclasses import replace
from datetime import timedelta
from email.utils import format_datetime
import json
import threading

import pytest
from src.core.acquisition import acquisition_scope, acquisition_deadline, AcquisitionCancelled, AcquisitionDeadlineExceeded
from src.news import batch_rss_adapter as adapter, news_fetcher as fetcher
from src.news.feed_pool import SharedFeedPool
from src.news.news_intelligence_contract import NewsCandidate
from src.news.source_groups import get_source_group_urls
from src.scanner import scanner_runner as ross
from test_rss_availability import Response, RSS_EMPTY, MALFORMED
from test_ross_operational_issuer_news import offline, CANDIDATE, NOW, service

EXTENDED = get_source_group_urls('PREP_EXTENDED')
FAST = get_source_group_urls('FAST_TRADING')
BAC = NewsCandidate('BAC', company_name='Bank of America Corp', exchange='NYSE')


def article(title, age=60):
    date = '' if age is None else '<pubDate>'+format_datetime(NOW-timedelta(seconds=age))+'</pubDate>'
    return ('<rss version="2.0"><channel><title>Synthetic publisher</title><item><title>'+title+
            '</title><link>https://example.invalid/article</link>'+date+'</item></channel></rss>').encode()


def transport(monkeypatch, *, failure='http403', primary_title=None, fallback_title=None,
              fallback_age=60, fallback_failure=False, all_primary_fail=False, close=None):
    calls=[];responses=[]
    def get(url, **kw):
        assert kw['allow_redirects'] is False and kw['stream'] is True
        assert 0 < kw['timeout'] <= 5
        calls.append((url, kw['timeout']))
        extended = url in EXTENDED
        body, status = RSS_EMPTY, 200
        if extended:
            if fallback_failure: status=500
            elif url==EXTENDED[0] and fallback_title: body=article(fallback_title, fallback_age)
        elif (all_primary_fail or 'reuters.com' in url) and failure:
            if failure.startswith('http'): status=int(failure[4:])
            elif failure=='redirect': status=301
            elif failure=='html': body=b'<html>not a feed</html>'
            elif failure=='empty': body=b''
            elif failure=='recovered': body=MALFORMED
            elif failure=='timeout': raise fetcher.requests.ReadTimeout('synthetic timeout')
        elif primary_title and 'news.google.com' in url and '%24JPM' in url:
            body=article(primary_title)
        response=Response(body,status)
        if close:
            response.close=lambda: (setattr(response,'closes',response.closes+1),close(url))[-1]
        responses.append(response)
        return response
    monkeypatch.setattr(fetcher.requests, 'get', get)
    return calls,responses


def execute(tmp_path, candidates=(CANDIDATE,), policy=None):
    svc=service(tmp_path)
    policy=policy or ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True)
    result=svc.get_news(candidates,ross._ross_news_request(),policy)
    return svc,result,result.diagnostics.diagnostics['refresh_diagnostics']


@pytest.mark.parametrize('failure,reason', [
    ('http401','HTTP_401'), ('http403','HTTP_403'), ('redirect','HTTP_301'),
    ('html','RSSFEEDFORMATERROR'), ('empty','RSSFEEDFORMATERROR'), ('recovered','RSSFEEDPARSEERROR'),
    (None,None),
])
def test_completed_primary_outcomes_allow_existing_bounded_fallback(monkeypatch,tmp_path,failure,reason):
    calls,responses=transport(monkeypatch,failure=failure,fallback_title='JPM reports earnings beat')
    svc,result,diag=execute(tmp_path)
    try:
        assert len(calls)==len({u for u,_ in calls})==20
        assert diag['primary_fallback_barrier_verified'] and diag['primary_cleanup_complete']
        assert diag['extended_fallback_requested'] and diag['extended_fallback_symbol_count']==1
        assert diag['primary_source_coverage_complete'] is (failure is None)
        assert diag['fast_budget_seconds']==5.2 and diag['extended_budget_reserved_seconds']==2.8
        assert 0 < diag['extended_budget_seconds'] <= 2.8
        assert not diag['stage_deadline_exhausted']
        assert all(t<=2.8 for u,t in calls if u in EXTENDED)
        if reason:
            assert any(r.failure_reason==reason for r in result.diagnostics.source_diagnostics)
            assert not diag['operational_acquisition_by_symbol']['JPM']['source_coverage_complete']
            assert result.summary_for_symbol('JPM').retrieval_status=='partial'
        ctx=ross._ross_news_contexts_from_news_intelligence_result(result)['JPM']
        assert ctx['ross_catalyst_valid'] and len(result.evidence_for_symbol('JPM'))==1
        assert ctx['qualifying_evidence_ids']
        # Publication remains the single canonical store's responsibility.
        assert svc.evidence_store.cache_path.exists()
    finally:
        assert svc.retrieval_provider._lifecycle.wait_for_cleanup(2)['cleanup_complete']
        assert all(r.closes==1 for r in responses)


def test_even_all_completed_primary_failures_can_use_existing_fallback(monkeypatch,tmp_path):
    calls,_=transport(monkeypatch,all_primary_fail=True,fallback_title='JPM reports earnings beat')
    svc,result,diag=execute(tmp_path)
    assert len(calls)==20 and diag['primary_fallback_barrier_verified']
    assert len([r for r in result.diagnostics.source_diagnostics if r.failure_reason=='HTTP_403'])==9
    assert not diag['primary_source_coverage_complete']
    assert not diag['operational_acquisition_by_symbol']['JPM']['source_coverage_complete']
    assert ross._ross_news_contexts_from_news_intelligence_result(result)['JPM']['ross_catalyst_valid']
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(2)['cleanup_complete']


@pytest.mark.parametrize('title,age,valid', [
    ('JPM reports earnings beat',60,True), ('JPM stock jumps on volatility',60,False),
    ('JPM reports earnings beat',21601,False), ('JPM reports earnings beat',-60,False),
    ('JPM reports earnings beat',None,False),
])
def test_fallback_does_not_replace_catalyst_or_publication_authority(monkeypatch,tmp_path,title,age,valid):
    calls,_=transport(monkeypatch,fallback_title=title,fallback_age=age)
    svc,result,diag=execute(tmp_path)
    assert len(calls)==20 and not diag['primary_source_coverage_complete']
    assert ross._ross_news_contexts_from_news_intelligence_result(result)['JPM']['ross_catalyst_valid'] is valid
    if valid:assert result.evidence_for_symbol('JPM')[0].published_at==(NOW-timedelta(seconds=age)).replace(microsecond=0)
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(2)['cleanup_complete']


def test_resolver_selects_only_unresolved_issuers(monkeypatch,tmp_path):
    calls,_=transport(monkeypatch,primary_title='JPM reports earnings beat',fallback_title='BAC reports earnings beat')
    svc=service(tmp_path);provider=svc.retrieval_provider;fetch=provider._extended_fetcher;stages=[]
    def observed(symbols,urls,**kw):
        stages.append(tuple(symbols))
        if len(stages)==2:assert provider._lifecycle.snapshot()['cleanup_complete'] is True
        return fetch(symbols,urls,**kw)
    monkeypatch.setattr(provider,'_extended_fetcher',observed)
    result=svc.get_news((CANDIDATE,BAC),ross._ross_news_request(),ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True))
    assert stages==[('JPM','BAC'),('BAC',)] and len(calls)==21
    assert result.diagnostics.diagnostics['refresh_diagnostics']['fallback_unresolved_symbols']==('BAC',)
    assert all(v['ross_catalyst_valid'] for v in ross._ross_news_contexts_from_news_intelligence_result(result).values())
    assert provider._lifecycle.wait_for_cleanup(2)['cleanup_complete']


def test_resolved_primary_avoids_fallback_and_does_not_wait_for_barrier(monkeypatch,tmp_path):
    calls,_=transport(monkeypatch,primary_title='JPM reports earnings beat')
    svc=service(tmp_path);life=svc.retrieval_provider._lifecycle
    wait=life.wait_for_cleanup
    monkeypatch.setattr(life,'wait_for_cleanup',lambda *_:pytest.fail('No fallback needs a barrier'))
    result=svc.get_news((CANDIDATE,),ross._ross_news_request(),ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True))
    diag=result.diagnostics.diagnostics['refresh_diagnostics']
    assert len(calls)==9 and not diag['extended_fallback_requested']
    assert diag['fallback_skipped_reason']=='ross_policy_resolved_in_primary'
    assert life.snapshot()['unfinished_count']==0
    assert wait(2)['cleanup_complete']


def test_fallback_failure_preserves_primary_failure_and_partial_coverage(monkeypatch,tmp_path):
    calls,_=transport(monkeypatch,fallback_failure=True)
    svc,result,diag=execute(tmp_path)
    assert len(calls)==20 and diag['extended_fallback_requested']
    reasons=[r.failure_reason for r in result.diagnostics.source_diagnostics]
    assert 'HTTP_403' in reasons and reasons.count('HTTP_500')==11
    assert not diag['primary_source_coverage_complete']
    assert not ross._ross_news_contexts_from_news_intelligence_result(result)['JPM']['ross_catalyst_valid']
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(2)['cleanup_complete']


def test_shared_pool_reuse_and_cross_tier_dedup_keep_one_request_per_url(monkeypatch,tmp_path):
    calls,_=transport(monkeypatch)
    original=adapter.get_source_group_urls
    monkeypatch.setattr(adapter,'get_source_group_urls',lambda group:original(group)+(FAST[4],) if group=='PREP_EXTENDED' else original(group))
    pool=SharedFeedPool();life=adapter.RssFetchLifecycle()
    provider=adapter.BatchRssNewsIntelligenceProvider(lifecycle=life,feed_pool=pool)
    policy=ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True,refresh_symbols=('JPM',))
    first=provider.get_news((CANDIDATE,),ross._ross_news_request(),policy)
    second=provider.get_news((CANDIDATE,),ross._ross_news_request(),policy)
    assert len(calls)==len({u for u,_ in calls})==20 and pool.requests==20 and pool.hits==20
    assert first.diagnostics.diagnostics['primary_fallback_barrier_verified'] and second.diagnostics.diagnostics['primary_fallback_barrier_verified']
    assert second.diagnostics.diagnostics['cross_tier_duplicate_source_urls_avoided']==(FAST[4],)
    assert all(r['entry_diagnostics']['transport_cache_hit'] for r in second.diagnostics.diagnostics['source_diagnostics'])
    assert life.wait_for_cleanup(2)['cleanup_complete']


def test_response_cleanup_finishes_before_any_extended_fetch(monkeypatch,tmp_path):
    entered=threading.Event();release=threading.Event();results=[];errors=[]
    def close(url):
        if 'reuters.com' in url:
            entered.set()
            assert release.wait(3)
    calls,_=transport(monkeypatch,close=close)
    svc=service(tmp_path)
    def run():
        try:results.append(svc.get_news((CANDIDATE,),ross._ross_news_request(),ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True)))
        except BaseException as exc:errors.append(exc)
    thread=threading.Thread(target=run)
    thread.start()
    try:
        assert entered.wait(2)
        assert not any(url in EXTENDED for url,_ in calls)
        assert not svc.retrieval_provider._lifecycle.snapshot()['cleanup_complete']
    finally:
        release.set();thread.join(4)
    assert not thread.is_alive() and not errors and len(results)==1
    assert len(calls)==20 and results[0].diagnostics.diagnostics['refresh_diagnostics']['primary_cleanup_complete']
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(2)['cleanup_complete']


def test_unfinished_primary_deadline_never_starts_fallback_or_admits_late_article(monkeypatch,tmp_path):
    entered=threading.Event();release=threading.Event()
    calls,responses=transport(monkeypatch)
    get=fetcher.requests.get
    def blocked(url,**kw):
        response=get(url,**kw)
        if 'reuters.com' in url:
            def chunks(chunk_size):
                entered.set();release.wait(2)
                yield article('JPM reports earnings beat')
            response.iter_content=chunks
        return response
    monkeypatch.setattr(fetcher.requests,'get',blocked)
    policy=replace(ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True),
                   total_budget_seconds=.2,tier_budgets={'fast':.13,'extended':.07})
    svc,result,diag=execute(tmp_path,policy=policy)
    try:
        assert entered.is_set() and not any(url in EXTENDED for url,_ in calls)
        assert diag['fallback_skipped_reason']=='primary_deadline_exhausted'
        assert not diag['primary_fallback_barrier_verified'] and not result.evidence_for_symbol('JPM')
        assert not svc.retrieval_provider._lifecycle.snapshot()['cleanup_complete']
    finally:
        release.set()
        assert svc.retrieval_provider._lifecycle.wait_for_cleanup(2)['cleanup_complete']
    assert not result.evidence_for_symbol('JPM') and all(r.closes==1 for r in responses)


def test_completed_request_timeout_fails_closed(monkeypatch,tmp_path):
    calls,_=transport(monkeypatch,failure='timeout')
    svc,result,diag=execute(tmp_path)
    assert len(calls)==9 and not diag['extended_fallback_requested']
    assert diag['fallback_skipped_reason']=='primary_deadline_exhausted'
    assert any(r.timed_out for r in result.diagnostics.source_diagnostics)
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(2)['cleanup_complete']


@pytest.mark.parametrize('unknown', ['worker','cleanup','omitted_source','truncated','cancelled'])
def test_unknown_primary_completion_or_cleanup_fails_closed(monkeypatch,tmp_path,unknown):
    calls,_=transport(monkeypatch)
    svc=service(tmp_path);provider=svc.retrieval_provider;life=provider._lifecycle
    if unknown in {'worker','omitted_source','truncated'}:
        fetch=provider._extended_fetcher
        def incomplete(*args,**kwargs):
            rows,summary=fetch(*args,**kwargs)
            records=[dict(row) for row in summary.source_diagnostics]
            if unknown=='omitted_source':records.pop(0)
            elif unknown=='truncated':records[0]['processing_truncated']=True
            else:records[0]['worker_completed']=None
            return rows,replace(summary,source_diagnostics=tuple(records))
        monkeypatch.setattr(provider,'_extended_fetcher',incomplete)
    else:
        original=life.snapshot
        def altered():
            state=original()
            if unknown=='cleanup':return {**state,'cleanup_complete':None}
            return {**state,'sources':[{**r,'cancellation_requested':True} for r in state['sources']]}
        monkeypatch.setattr(life,'snapshot',altered)
    result=svc.get_news((CANDIDATE,),ross._ross_news_request(),ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True))
    diag=result.diagnostics.diagnostics['refresh_diagnostics']
    assert len(calls)==9 and not diag['primary_fallback_barrier_verified'] and not diag['extended_fallback_requested']
    assert diag['fallback_skipped_reason']==('primary_cleanup_unverified' if unknown=='cleanup' else 'primary_completion_unverified')
    # Unknown telemetry must not create an overlapping transport owner.
    if unknown in {'worker','omitted_source','truncated'}:assert life.wait_for_cleanup(2)['cleanup_complete']
    else:
        life.wait_for_cleanup(2)
        assert original()['alive_worker_count']==0 and original()['unfinished_count']==0


def test_failed_response_cleanup_cannot_enable_fallback(monkeypatch,tmp_path):
    def close(url):
        if 'reuters.com' in url:raise RuntimeError('synthetic close failure')
    calls,_=transport(monkeypatch,close=close)
    svc,result,diag=execute(tmp_path)
    snapshot=svc.retrieval_provider._lifecycle.snapshot()
    assert len(calls)==9 and not diag['extended_fallback_requested']
    assert diag['fallback_skipped_reason']=='primary_cleanup_incomplete'
    assert diag['primary_cleanup_complete'] is False
    assert snapshot['alive_worker_count']==0 and snapshot['response_cleanup_failures_count']==1
    assert any(r.failure_reason=='HTTP_403' for r in result.diagnostics.source_diagnostics)


@pytest.mark.parametrize('when', ['before_barrier','during_cleanup'])
def test_cooperative_stop_cannot_start_fallback_or_publish(monkeypatch,tmp_path,when):
    stop=threading.Event();calls,_=transport(monkeypatch)
    svc=service(tmp_path);provider=svc.retrieval_provider;life=provider._lifecycle
    original_wait=life.wait_for_cleanup
    if when=='before_barrier':
        fetch=provider._extended_fetcher
        def stopped(*args,**kwargs):
            result=fetch(*args,**kwargs);stop.set();return result
        monkeypatch.setattr(provider,'_extended_fetcher',stopped)
    else:
        def stopped(timeout):
            result=original_wait(timeout);stop.set();return result
        monkeypatch.setattr(life,'wait_for_cleanup',stopped)
    try:
        with pytest.raises(AcquisitionCancelled),acquisition_scope(stop.is_set):
            svc.get_news((CANDIDATE,),ross._ross_news_request(),ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True))
        assert len(calls)==9 and not svc.evidence_store.cache_path.exists()
    finally:assert original_wait(2)['cleanup_complete']


@pytest.mark.parametrize('elapsed,expected', [(0,True),(5.199,True),(5.2,False),(8,False)])
def test_primary_barrier_and_original_stage_deadline_boundaries(monkeypatch,tmp_path,elapsed,expected):
    clock=[100.0];monkeypatch.setattr(adapter.time,'monotonic',lambda:clock[0])
    calls,_=transport(monkeypatch)
    svc=service(tmp_path);provider=svc.retrieval_provider;fetch=provider._extended_fetcher;stages=[]
    def observed(*args,**kw):
        stages.append(kw)
        result=fetch(*args,**kw)
        if len(stages)==1:clock[0]+=elapsed
        return result
    monkeypatch.setattr(provider,'_extended_fetcher',observed)
    result=svc.get_news((CANDIDATE,),ross._ross_news_request(),ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True))
    diag=result.diagnostics.diagnostics['refresh_diagnostics']
    assert diag['extended_fallback_requested'] is expected
    assert len(calls)==(20 if expected else 9)
    assert all(kw['stage_started_at_s']==100 and kw['stage_deadline_s']==108 for kw in stages)
    if expected:
        assert stages[1]['tier_budget_seconds']<=2.8
        assert stages[1]['tier_deadline_s']<=108
    else:assert diag['fallback_skipped_reason']=='primary_deadline_exhausted'
    assert provider._lifecycle.wait_for_cleanup(2)['cleanup_complete']


def test_zero_extended_allocation_does_not_invoke_extended_fetcher(monkeypatch,tmp_path):
    calls,_=transport(monkeypatch)
    policy=replace(ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True),
                   tier_budgets={'fast':5.2,'extended':0})
    svc,result,diag=execute(tmp_path,policy=policy)
    assert len(calls)==9 and not diag['extended_fallback_requested'] and diag['extended_budget_exhausted']
    assert not any(row.attempted for row in result.diagnostics.source_diagnostics if row.source_group=='PREP_EXTENDED')
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(2)['cleanup_complete']


def test_parent_remaining_deadline_clips_extended_budget_without_renewal(monkeypatch,tmp_path):
    clock=[100.0];monkeypatch.setattr(adapter.time,'monotonic',lambda:clock[0])
    calls,_=transport(monkeypatch)
    svc=service(tmp_path);provider=svc.retrieval_provider;fetch=provider._extended_fetcher;stages=[]
    def observed(*args,**kw):
        stages.append(kw);result=fetch(*args,**kw)
        if len(stages)==1:clock[0]=104.0
        return result
    monkeypatch.setattr(provider,'_extended_fetcher',observed)
    with acquisition_deadline(104.15):
        result=svc.get_news((CANDIDATE,),ross._ross_news_request(),ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True))
    assert len(stages)==2 and stages[1]['stage_deadline_s']==108
    assert stages[1]['tier_budget_seconds']==pytest.approx(.15)
    assert stages[1]['tier_deadline_s']<=104.15
    assert all(t<=.15+1e-9 for u,t in calls if u in EXTENDED)
    assert result.diagnostics.diagnostics['refresh_diagnostics']['extended_fallback_requested']
    assert provider._lifecycle.wait_for_cleanup(2)['cleanup_complete']


def test_v4_cache_coverage_is_invalidated_without_erasing_original_failures(monkeypatch,tmp_path):
    import hashlib
    calls,_=transport(monkeypatch)
    svc=service(tmp_path);request=ross._ross_news_request()
    policy=ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True)
    svc.get_news((CANDIDATE,),request,policy)
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(2)['cleanup_complete']
    path=svc.evidence_store.cache_path;data=json.loads(path.read_text())
    old=data['news_intelligence']['symbols']['JPM']['last_retrieval']
    profile=old['acquisition_profile'];profile['retrieval']['operational_scheduling_contract']='ross_issuer_acquisition_v4'
    profile.pop('fingerprint');profile['fingerprint']=hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    path.write_text(json.dumps(data));before=path.read_bytes();count=len(calls)
    # Caller metadata cannot pretend the running v5 scheduler is still v4.
    old_policy=replace(policy,metadata={**policy.metadata,'operational_scheduling_contract':'ross_issuer_acquisition_v4'})
    cached=svc.get_news((CANDIDATE,),request,replace(old_policy,network_allowed=False,refresh_mode='cache_only',allow_cache_write=False))
    assert len(calls)==count and path.read_bytes()==before
    assert cached.summary_for_symbol('JPM').provider_status=='coverage_unknown'
    assert cached.summary_for_symbol('JPM').diagnostics['last_retrieval']==old
    fresh=svc.get_news((CANDIDATE,),request,old_policy)
    assert len(calls)==count+20
    new=fresh.summary_for_symbol('JPM').diagnostics['last_retrieval']
    assert new['acquisition_profile']['retrieval']['operational_scheduling_contract']==adapter.OPERATIONAL_SCHEDULING_CONTRACT
    assert new['acquisition_profile']['fingerprint']!=profile['fingerprint']
    assert any(row['failure_reason']=='HTTP_403' for row in new['coverage']['diagnostics']['source_diagnostics'])
    count=len(calls);svc.get_news((CANDIDATE,),request,old_policy);assert len(calls)==count
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(2)['cleanup_complete']


@pytest.mark.parametrize('parent', [False,True])
def test_deadline_rechecked_after_cleanup_before_extended_requests(monkeypatch,tmp_path,parent):
    clock=[100.0];monkeypatch.setattr(adapter.time,'monotonic',lambda:clock[0])
    calls,_=transport(monkeypatch)
    svc=service(tmp_path);life=svc.retrieval_provider._lifecycle;wait=life.wait_for_cleanup
    def delayed_return(timeout):
        if parent:assert timeout<=.2+1e-9
        result=wait(timeout);clock[0]=100.2 if parent else 105.2;return result
    monkeypatch.setattr(life,'wait_for_cleanup',delayed_return)
    policy=ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True)
    if parent:
        with pytest.raises(AcquisitionDeadlineExceeded),acquisition_deadline(100.2):
            svc.get_news((CANDIDATE,),ross._ross_news_request(),policy)
        assert not svc.evidence_store.cache_path.exists()
    else:
        result=svc.get_news((CANDIDATE,),ross._ross_news_request(),policy)
        diag=result.diagnostics.diagnostics['refresh_diagnostics']
        assert diag['fallback_skipped_reason']=='primary_deadline_exhausted'
        assert not diag['extended_fallback_requested']
    assert len(calls)==9
    assert wait(2)['cleanup_complete']
