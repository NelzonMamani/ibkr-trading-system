"""Controlled latency and outcome fixtures; not live trading/news acceptance."""
from dataclasses import replace
from types import SimpleNamespace
import threading
import pytest
import time

from test_ross_operational_issuer_news import offline, CANDIDATE, service, fixture_transport, entry
from src.scanner import scanner_runner as ross
from src.news import news_fetcher


@pytest.mark.parametrize('title',['JPM generic report','JPM reports earnings beat'])
def test_incomplete_primary_does_not_spend_fallback_or_clear_unavailability(monkeypatch,tmp_path,title):
    calls=[];gate=threading.Event()
    def feed(url,timeout):
        calls.append(url)
        if 'news.google.com' in url:
            return SimpleNamespace(feed={'title':'fixture query'},entries=[entry(title,60)])
        gate.wait(2)
        return SimpleNamespace(feed={},entries=[])
    monkeypatch.setattr(news_fetcher,'_fetch_feed',feed)
    monkeypatch.setattr(news_fetcher,'feedparser',object())
    svc=service(tmp_path)
    request=ross._ross_news_request()
    # Scaled timing contract, preserving allocations; not a provider latency claim.
    policy=replace(ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True),
        total_budget_seconds=0.2,tier_budgets={'fast':0.13,'extended':0.07})
    started=time.monotonic()
    try:
        result=svc.get_news((CANDIDATE,),request,policy)
        assert time.monotonic()-started < 0.5
        raw=result.diagnostics.diagnostics['refresh_diagnostics']
        assert raw['fallback_skipped_reason']=='primary_coverage_incomplete'
        assert not raw['required_primary_coverage_complete']
        assert not raw['extended_fallback_requested']
        assert result.diagnostics.budget_exhausted
        assert not any('forbes' in url or 'fortune' in url for url in calls)
        contexts=ross._ross_news_contexts_from_news_intelligence_result(result)
        assert contexts['JPM']['issuer_query_coverage_complete']
        assert not contexts['JPM']['news_available'] and not contexts['JPM']['ross_catalyst_valid']
        deferred=[r for r in result.diagnostics.source_diagnostics if r.source_group=='PREP_EXTENDED']
        assert deferred and all(not r.attempted and r.failure_reason=='primary_coverage_incomplete' for r in deferred)
        assert not svc.retrieval_provider._lifecycle.snapshot()['cleanup_complete']
    finally:
        gate.set()
        assert svc.retrieval_provider._lifecycle.wait_for_cleanup(2)['cleanup_complete']
    assert not contexts['JPM']['ross_catalyst_valid']


def test_policy_witness_in_completed_primary_avoids_unnecessary_fallback(monkeypatch,tmp_path):
    calls=[];fixture_transport(monkeypatch,calls,[entry('JPM reports earnings beat',60)])
    svc=service(tmp_path);request=ross._ross_news_request()
    result=svc.get_news((CANDIDATE,),request,ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True))
    raw=result.diagnostics.diagnostics['refresh_diagnostics']
    assert raw['required_primary_coverage_complete']
    assert raw['fallback_skipped_reason']=='ross_policy_resolved_in_primary'
    assert not raw['extended_fallback_requested'] and len(calls)==9
    assert ross._ross_news_contexts_from_news_intelligence_result(result)['JPM']['ross_catalyst_valid']
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(1)['cleanup_complete']


def test_completed_generic_primary_still_requires_unresolved_fallback(monkeypatch,tmp_path):
    calls=[];fixture_transport(monkeypatch,calls,[entry('JPM generic report',60)])
    svc=service(tmp_path)
    result=svc.get_news((CANDIDATE,),ross._ross_news_request(),ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True))
    raw=result.diagnostics.diagnostics['refresh_diagnostics']
    assert raw['extended_fallback_requested'] and len(calls)==22
    assert not ross._ross_news_contexts_from_news_intelligence_result(result)['JPM']['ross_catalyst_valid']
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(1)['cleanup_complete']


def test_actual_consumer_reuses_negative_canonical_acquisition_without_second_read(monkeypatch,tmp_path):
    calls=[];fixture_transport(monkeypatch,calls,[])
    svc=service(tmp_path);monkeypatch.setattr(ross,'_news_intelligence_service_for_scanner',lambda:svc)
    metadata={'JPM':{'company_name':CANDIDATE.company_name,'aliases':CANDIDATE.aliases}}
    contexts,_=ross._enrich_news_context(['JPM'],'RSS',metadata)
    before=len(calls);reads=[];get=svc.get_news
    def counted(*a,**kw):
        reads.append(a[2].refresh_mode);return get(*a,**kw)
    monkeypatch.setattr(svc,'get_news',counted)
    again,diag=ross._enrich_news_context(['JPM'],'RSS',metadata)
    assert reads==['cache_only'] and len(calls)==before
    assert again['JPM']['ross_catalyst_valid']==contexts['JPM']['ross_catalyst_valid']
    assert diag.news_intelligence_diagnostics['ross_consumer_elapsed_seconds']>=0
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(1)['cleanup_complete']


def test_successful_primary_peer_does_not_inherit_unresolved_peer_fallback_deadline(monkeypatch,tmp_path):
    from src.news.news_intelligence_contract import NewsCandidate
    from src.news.source_groups import get_source_group_urls
    secondary=set(get_source_group_urls('PREP_EXTENDED'));gate=threading.Event();calls=[]
    def feed(url,timeout):
        calls.append(url)
        if url in secondary:gate.wait(2)
        return SimpleNamespace(feed={'title':'fixture'},entries=[entry('JPM reports earnings beat',60)] if 'news.google.com' in url else [])
    monkeypatch.setattr(news_fetcher,'_fetch_feed',feed);monkeypatch.setattr(news_fetcher,'feedparser',object())
    svc=service(tmp_path);request=ross._ross_news_request()
    policy=replace(ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True),
        total_budget_seconds=0.2,tier_budgets={'fast':0.13,'extended':0.07})
    try:
        result=svc.get_news((CANDIDATE,NewsCandidate('IRON',company_name='Disc Medicine, Inc.')),request,policy)
        contexts=ross._ross_news_contexts_from_news_intelligence_result(result)
        assert contexts['JPM']['ross_catalyst_valid']
        assert not contexts['IRON']['news_available']
        assert not result.summary_for_symbol('JPM').budget_exhausted
        assert result.summary_for_symbol('IRON').budget_exhausted
        timings=result.diagnostics.diagnostics['phase_timings']
        assert timings['service_total_seconds']>=timings['provider_seconds']
    finally:
        gate.set();assert svc.retrieval_provider._lifecycle.wait_for_cleanup(2)['cleanup_complete']


@pytest.mark.parametrize('positive',[False,True])
def test_one_required_primary_failure_remains_unavailable_without_false_deadline(monkeypatch,tmp_path,positive):
    calls=[]
    def feed(url,timeout):
        calls.append(url)
        if 'reuters.com' in url:
            raise news_fetcher.requests.HTTPError(response=SimpleNamespace(status_code=401))
        return SimpleNamespace(feed={'title':'fixture'},entries=[entry('JPM reports earnings beat' if positive else 'JPM generic report',60)] if 'news.google.com' in url else [])
    monkeypatch.setattr(news_fetcher,'_fetch_feed',feed);monkeypatch.setattr(news_fetcher,'feedparser',object())
    svc=service(tmp_path)
    result=svc.get_news((CANDIDATE,),ross._ross_news_request(),ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True))
    raw=result.diagnostics.diagnostics['refresh_diagnostics']
    assert not raw['required_primary_coverage_complete']
    assert raw['fallback_skipped_reason']=='primary_coverage_incomplete'
    assert not raw['extended_fallback_requested'] and len(calls)==9
    assert not result.diagnostics.budget_exhausted
    assert result.summary_for_symbol('JPM').retrieval_status=='unavailable'
    assert not result.summary_for_symbol('JPM').provider_available
    contexts=ross._ross_news_contexts_from_news_intelligence_result(result)
    ctx=contexts['JPM']
    assert not ctx['news_available'] and not ctx['ross_catalyst_valid']
    assert ross._news_diagnostics_from_news_intelligence_result(result,contexts).news_degraded
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(1)['cleanup_complete']
