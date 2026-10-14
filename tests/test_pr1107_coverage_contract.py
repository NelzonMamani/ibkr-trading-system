"""Labelled offline acquisition contracts, not observed trading evidence."""
from dataclasses import replace
from types import SimpleNamespace
import threading
import pytest

from test_ross_operational_issuer_news import offline, CANDIDATE, entry, service
from src.news import news_fetcher
from src.news.news_intelligence_contract import NewsCandidate
from src.scanner import scanner_runner as ross
from src.strategies.ross_momentum.policy.catalyst_policy import assess_catalyst


def context(result,symbol='JPM'):
    return ross._ross_news_contexts_from_news_intelligence_result(result)[symbol]


@pytest.mark.parametrize('title,age,qualified,veto',[
    ('JPM reports earnings beat',60,True,False),
    ('JPM generic report',60,False,False),
    ('JPM tracks Bank of America earnings',60,False,False),
    ('JPM reports earnings beat',21601,False,False),
    ('JPM announces ATM offering',60,False,True),
])
def test_query_acquisition_partial_coverage_and_qualification_are_separate(monkeypatch,tmp_path,title,age,qualified,veto):
    calls=[]
    def feed(url,timeout):
        calls.append(url)
        if 'news.google.com' not in url:
            raise news_fetcher.requests.HTTPError(response=SimpleNamespace(status_code=403))
        return SimpleNamespace(feed={},entries=[entry(title,age)])
    monkeypatch.setattr(news_fetcher,'_fetch_feed',feed);monkeypatch.setattr(news_fetcher,'feedparser',object())
    svc=service(tmp_path);request=ross._ross_news_request();policy=ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True)
    result=svc.get_news((CANDIDATE,),request,policy);ctx=context(result)
    assert result.summary_for_symbol('JPM').retrieval_status=='partial'
    assert result.summary_for_symbol('JPM').provider_available
    assert ctx['acquisition_available'] and not ctx['source_coverage_complete']
    assert ctx['issuer_query_requests_completed']
    assert ctx['ross_catalyst_valid'] is qualified and bool(ctx['dilution_flag']) is veto
    decision=assess_catalyst(mode='READ_ONLY',news_enabled=True,news_available=ctx['news_available'],confirmed=True if ctx['ross_catalyst_valid'] else False if ctx['news_available'] else None)
    assert decision.satisfied is qualified
    if not qualified and not veto:assert decision.status.value=='DATA_UNAVAILABLE'
    raw=result.diagnostics.diagnostics['refresh_diagnostics']
    assert not raw['extended_fallback_requested'] and raw['issuer_query']['search_completeness_established'] is False
    assert len(calls)==len(set(calls))
    before=len(calls)
    # Same canonical acquisition persists partial coverage and negative facts.
    again=svc.get_news((CANDIDATE,),request,ross._ross_retrieval_policy(refresh_mode='cache_only',network_allowed=False))
    cached=context(again)
    assert len(calls)==before and cached['ross_catalyst_valid'] is qualified
    assert cached['acquisition_available'] and not cached['source_coverage_complete']
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(1)['cleanup_complete']


def test_successful_peer_query_does_not_certify_failed_issuer_route(monkeypatch,tmp_path):
    def feed(url,timeout):
        if 'news.google.com' not in url or 'Disc+' in url:
            raise news_fetcher.requests.HTTPError(response=SimpleNamespace(status_code=401))
        return SimpleNamespace(feed={},entries=[entry('JPM reports earnings beat',60)])
    monkeypatch.setattr(news_fetcher,'_fetch_feed',feed);monkeypatch.setattr(news_fetcher,'feedparser',object())
    svc=service(tmp_path)
    result=svc.get_news((CANDIDATE,NewsCandidate('IRON',company_name='Disc Medicine, Inc.')),ross._ross_news_request(),ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True))
    assert context(result)['ross_catalyst_valid']
    failed=context(result,'IRON')
    assert not failed['acquisition_available'] and not failed['ross_catalyst_valid'] and not failed['news_available']
    assert result.summary_for_symbol('IRON').retrieval_status=='unavailable'
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(1)['cleanup_complete']


@pytest.mark.parametrize('late_query',[False,True])
def test_deadline_keeps_completed_evidence_and_excludes_late_evidence(monkeypatch,tmp_path,late_query):
    gate=threading.Event();calls=[]
    def feed(url,timeout):
        calls.append(url)
        query='news.google.com' in url
        if not query or late_query:gate.wait(2)
        return SimpleNamespace(feed={},entries=[entry('JPM reports earnings beat',60)] if query else [])
    monkeypatch.setattr(news_fetcher,'_fetch_feed',feed);monkeypatch.setattr(news_fetcher,'feedparser',object())
    svc=service(tmp_path);policy=replace(ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True),total_budget_seconds=.2,tier_budgets={'fast':.13,'extended':.07})
    try:
        result=svc.get_news((CANDIDATE,),ross._ross_news_request(),policy);ctx=context(result)
        assert ctx['ross_catalyst_valid'] is (not late_query)
        assert ctx['acquisition_available'] is (not late_query)
        assert ctx['coverage_deadline_exhausted'] and result.diagnostics.budget_exhausted
        assert not ctx['source_coverage_complete']
        assert not svc.retrieval_provider._lifecycle.snapshot()['cleanup_complete']
    finally:
        gate.set();assert svc.retrieval_provider._lifecycle.wait_for_cleanup(2)['cleanup_complete']
    assert context(result)['ross_catalyst_valid'] is (not late_query)


@pytest.mark.parametrize('scenario',['fixed_article','all_failed','veto','update_only','generic_empty'])
def test_partial_routes_do_not_require_sample_tickers_or_certify_missing_events(monkeypatch,tmp_path,scenario):
    candidate=NewsCandidate('ZZZZ',company_name='Example Robotics, Inc.',aliases=('Example Robotics',))
    def feed(url,timeout):
        query='news.google.com' in url
        fixed='benzinga.com' in url
        if scenario=='all_failed' or (scenario=='fixed_article' and query) or (not query and not (scenario=='fixed_article' and fixed)):
            raise news_fetcher.requests.HTTPError(response=SimpleNamespace(status_code=401))
        entries=[]
        if scenario=='fixed_article' and fixed:entries=[entry('ZZZZ announces new supply contract',60)]
        if scenario=='veto':entries=[entry('ZZZZ reports earnings beat',60),entry('ZZZZ announces ATM offering',61)]
        if scenario=='update_only':entries=[SimpleNamespace(title='ZZZZ reports earnings beat',link='https://fixture.invalid/update-only',updated_parsed=entry('',60).published_parsed)]
        return SimpleNamespace(feed={},entries=entries)
    monkeypatch.setattr(news_fetcher,'_fetch_feed',feed);monkeypatch.setattr(news_fetcher,'feedparser',object())
    svc=service(tmp_path)
    result=svc.get_news((candidate,),ross._ross_news_request(),ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True));ctx=context(result,'ZZZZ')
    assert ctx['ross_catalyst_valid'] is (scenario=='fixed_article')
    assert not ctx['source_coverage_complete']
    if scenario=='all_failed':
        assert not ctx['acquisition_available']
        assert not result.summary_for_symbol('ZZZZ').budget_exhausted
        assert result.summary_for_symbol('ZZZZ').retrieval_status=='unavailable'
    elif scenario=='veto':assert ctx['dilution_flag']
    else:assert ctx['acquisition_available']
    if scenario in {'update_only','generic_empty'}:
        assert not ctx['news_available']
        assert ctx['news_diagnostic_status']=='partial_coverage_no_qualifying_catalyst'
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(1)['cleanup_complete']
