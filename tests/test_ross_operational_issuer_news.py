"""Offline contract fixtures, not natural catalyst/latency acceptance evidence."""
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
import socket
import time

import pytest
from src.config.config_resolver import set_config_overrides
from src.news import news_fetcher, batch_rss_adapter, evidence_store, news_intelligence_service
from src.news.evidence_store import CanonicalNewsEvidenceStore
from src.news.news_intelligence_contract import NewsCandidate, NewsEvidence, NewsBatchResult, RetrievalDiagnostics
from src.news.news_intelligence_service import CanonicalNewsIntelligenceService
from src.news.batch_rss_adapter import BatchRssNewsIntelligenceProvider
from src.news.rss_lifecycle import RssFetchLifecycle
from src.news.issuer_rss_queries import operational_queries
from src.scanner import scanner_runner as ross
from src.strategies.ross_momentum.policy.catalyst_policy import assess_issuer_event, assess_catalyst

NOW = datetime(2026, 10, 14, 16, 39, 30, 747675, tzinfo=timezone.utc)
CANDIDATE = NewsCandidate('JPM', company_name='JPMorgan Chase & Co.', aliases=('JPMorgan Chase',), exchange='NYSE')

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(NOW.timestamp(), tz=tz)
    def forbid(*a, **k):
        raise AssertionError('No provider/broker requests in offline contracts')
    monkeypatch.setattr(socket.socket, 'connect', forbid)
    monkeypatch.setattr(socket, 'create_connection', forbid)
    monkeypatch.setattr(time, 'time', lambda: NOW.timestamp())
    for module in (news_fetcher, batch_rss_adapter, evidence_store, news_intelligence_service, ross):
        monkeypatch.setattr(module, 'datetime', Clock)
    monkeypatch.setattr(ross, '_NEWS_CACHE', {})
    set_config_overrides({'NEWS_ENABLED': True, 'ROSS_ISSUER_QUERY_ENABLED': True,
                          'NEWS_LOOKBACK_HOURS': 6.0, 'NEWS_TOTAL_BUDGET_S': 8.0,
                          'NEWS_MAX_ENTRIES_PER_SYMBOL': 5, 'NEWS_REQUEST_TIMEOUT_S': 5})
    yield
    set_config_overrides({})


def item(title, age=60, **kw):
    return NewsEvidence(symbol='JPM', evidence_id=title, headline=title,
        company_name=CANDIDATE.company_name, aliases=CANDIDATE.aliases,
        published_at=datetime.fromtimestamp(NOW.timestamp()-age, timezone.utc),
        age_seconds=age, stale=age>21600, source_tier='operational_query', **kw)

@pytest.mark.parametrize('title,reason', [
    ('Bank of America earnings surge while JPM holds steady', 'event_not_attributed_to_requested_issuer'),
    ('JPM announces Bank of America earnings', 'event_not_attributed_to_requested_issuer'),
    ('JPM tracks Bank of America earnings', 'event_not_attributed_to_requested_issuer'),
    ('JPM and Bank of America report earnings', 'event_not_attributed_to_requested_issuer'),
    ('JPM earnings preview: could beat estimates', 'event_assertion_uncertain'),
    ('JPM earnings calendar', 'event_not_attributed_to_requested_issuer'),
    ('JPM mentioned in market roundup', 'no_catalyst_classification'),
])
def test_actual_consumer_rejects_co_mentions_and_ambiguity(title, reason):
    ev=item(title)
    result=NewsBatchResult(candidates=(CANDIDATE,), request=ross._ross_news_request(),
        diagnostics=RetrievalDiagnostics(provider_available=True))
    ctx=ross._ross_news_context_from_evidence('JPM',(ev,),None,result)
    assert not ctx['ross_catalyst_valid']
    assert ctx['qualification_decisions'][0]['reason']==reason
    assert not assess_catalyst(mode='READ_ONLY',news_enabled=True,news_available=True,confirmed=ctx['ross_catalyst_valid']).satisfied


def test_publication_not_stored_flags_controls_attribution():
    good=item('JPM reports earnings beat')
    assert assess_issuer_event('JPM',good)['qualified']
    for bad in (replace(good,published_at=None), replace(good,published_at=datetime.fromtimestamp(NOW.timestamp()-21601,timezone.utc),stale=False),
                replace(good,published_at=datetime.fromtimestamp(NOW.timestamp()+1,timezone.utc)),replace(good,source_tier='research')):
        assert not assess_issuer_event('JPM',bad)['qualified']
    result=NewsBatchResult(candidates=(CANDIDATE,),diagnostics=RetrievalDiagnostics(provider_available=False,provider_status='provider_unavailable'))
    ctx=ross._ross_news_context_from_evidence('JPM',(good,),None,result)
    assert ctx['ross_catalyst_valid'] and ctx['acquisition_health']=='degraded'
    assert not ctx['news_available']


def test_setting_disabled_preserves_acquisition_contract():
    set_config_overrides({'ROSS_ISSUER_QUERY_ENABLED':False})
    request=ross._ross_news_request()
    policy=ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True)
    assert request.max_evidence_per_symbol==5 and 'retention_selector' not in request.metadata
    assert policy.source_groups==('FAST_TRADING','PREP_EXTENDED')
    assert not policy.metadata.get('ross_issuer_query')


def fixture_transport(monkeypatch, calls, entries):
    def fetch(url, timeout):
        calls.append((url,timeout))
        return SimpleNamespace(version="rss20", bozo=False, feed={'title':'Fixture publisher'},entries=entries if 'news.google.com/rss/search?' in url else [])
    monkeypatch.setattr(news_fetcher, '_fetch_feed', fetch)
    monkeypatch.setattr(news_fetcher, 'feedparser', object())


def entry(title, age):
    return SimpleNamespace(title=title,link='https://fixture.invalid/'+str(age),
                           published_parsed=time.gmtime(NOW.timestamp()-age))


def service(tmp_path):
    return CanonicalNewsIntelligenceService(evidence_store=CanonicalNewsEvidenceStore(tmp_path/'cache.json',prep_artifact_loader=lambda:{}),
        retrieval_provider=BatchRssNewsIntelligenceProvider(lifecycle=RssFetchLifecycle()))


def test_actual_enrichment_witness_batch_cache_and_canonical_queries(monkeypatch,tmp_path):
    calls=[]
    fixture_transport(monkeypatch,calls,[entry('JPM market roundup '+str(n),n+1) for n in range(7)] + [entry('JPM reports earnings beat',600)])
    svc=service(tmp_path)
    monkeypatch.setattr(ross,'_news_intelligence_service_for_scanner',lambda:svc)
    metadata={'JPM':{'company_name':CANDIDATE.company_name,'aliases':CANDIDATE.aliases,'exchange':'NYSE'}}
    contexts,diag=ross._enrich_news_context(['JPM','JPM'],'RSS',metadata)
    ctx=contexts['JPM']
    assert ctx['ross_catalyst_valid'] and ctx['news_count']==5 and ctx['qualification_evidence_count']==6
    assert not set(ctx['qualifying_evidence_ids']) & set(ctx['presentation_evidence_ids'])
    assert diag.news_intelligence_diagnostics['rss_cleanup']['cleanup_elapsed_seconds'] == 0
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(1)['cleanup_complete'] is True
    urls=[url for url,_ in calls]
    assert len(urls)==len(set(urls)) and urls[0].startswith('https://news.google.com/rss/search?')
    assert not any('yahoo' in url for url in urls)
    policy=ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True)
    assert policy.total_budget_seconds==8 and policy.tier_budgets=={'fast':5.2,'extended':2.8}
    before=len(calls)
    again,_=ross._enrich_news_context(['JPM'],'RSS',metadata)
    assert again['JPM']['ross_catalyst_valid'] and len(calls)==before
    # New process/store still retains policy witness and avoids HTTP requests.
    fresh=service(tmp_path)
    result=fresh.get_news(ross._news_candidates_for_symbols(['JPM'],metadata),ross._ross_news_request(),policy)
    assert len(calls)==before and len(result.evidence_for_symbol('JPM'))==6


def test_empty_failure_cadence_query_cap_and_batch_identity(monkeypatch,tmp_path):
    calls=[]
    fixture_transport(monkeypatch,calls,[])
    candidates=tuple(NewsCandidate('T'+str(n),company_name='Fixture Issuer '+str(n)) for n in range(6))+(NewsCandidate('NONAME'),)
    svc=service(tmp_path)
    request=ross._ross_news_request();policy=ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True)
    result=svc.get_news(candidates,request,policy)
    facts=result.diagnostics.diagnostics['refresh_diagnostics']['issuer_query']
    assert facts['attempted_queries']==4 and facts['planned_queries']==6
    assert facts['per_issuer']['T5'][0]['reason']=='query_request_limit'
    assert facts['per_issuer']['NONAME'][0]['reason']=='query_identity_unavailable'
    assert len([url for url,_ in calls if 'news.google.com' in url])==4
    before=len(calls)
    again=svc.get_news(candidates,request,policy)
    assert len(calls)==before and again.diagnostics.diagnostics['acquisition_cache_hit_symbols']
    svc.get_news(candidates[:-1],request,policy)
    # Removing a peer with no query URL still changes batch identity? Its issuer has no acquisition URL;
    # valid peers have identical acquisition sources, so reuse is safe.
    changed=(*candidates[:5],replace(candidates[5],company_name='Changed Identity'))
    svc.get_news(changed,request,policy)
    assert len(calls)>before
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(1)['cleanup_complete']

@pytest.mark.parametrize('headline', ['JPM reports earnings beat', '$JPM reports earnings beat',
    'JPMorgan Chase announces record quarterly earnings', 'JPM wins new contract', 'JPM announces new supply contract'])
def test_fixture_direct_issuer_events_can_qualify(headline):
    assert assess_issuer_event('JPM',item(headline))['qualified']


def test_update_only_is_not_fresh_publication():
    assert assess_issuer_event('JPM',replace(item('JPM reports earnings'),raw={'timestamp_provenance':{'selected_time_basis':'updated'}}))['reason']=='publication_time_unverified_update_only'


def test_quote_changes_do_not_trigger_retry_storm(monkeypatch,tmp_path):
    calls=[];fixture_transport(monkeypatch,calls,[])
    svc=service(tmp_path);request=ross._ross_news_request();policy=ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True)
    first=replace(CANDIDATE,metadata={'last_price':1,'rvol':2})
    svc.get_news((first,),request,policy);before=len(calls)
    svc.get_news((replace(first,metadata={'last_price':2,'rvol':3}),),request,policy)
    assert len(calls)==before
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(1)['cleanup_complete']


def test_failure_empty_results_have_cadence_and_visible_429(monkeypatch,tmp_path):
    calls=[]
    def unavailable(url,timeout):
        calls.append(url)
        response=SimpleNamespace(status_code=429)
        raise news_fetcher.requests.HTTPError(response=response)
    monkeypatch.setattr(news_fetcher,'_fetch_feed',unavailable)
    monkeypatch.setattr(news_fetcher,'feedparser',object())
    svc=service(tmp_path);request=ross._ross_news_request();policy=ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True)
    result=svc.get_news((CANDIDATE,),request,policy)
    rows=result.diagnostics.source_diagnostics
    assert rows and any('429' in str(row.failure_reason) for row in rows)
    assert not result.evidence_for_symbol('JPM')
    before=len(calls);svc.get_news((CANDIDATE,),request,policy)
    assert len(calls)==before
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(1)['cleanup_complete']


def test_capped_queries_respect_candidate_priority():
    low=replace(CANDIDATE,priority_rank=9)
    high=NewsCandidate('ZZZ',company_name='Fixture Zed Corp.',priority_rank=1)
    assert operational_queries((low,high))[0]['query_issuers']==['ZZZ']


def test_operational_deadline_late_worker_never_adds_evidence(monkeypatch,tmp_path):
    import threading
    gate=threading.Event()
    def late(url,timeout):
        gate.wait(1)
        return SimpleNamespace(version="rss20", bozo=False, feed={'title':'late fixture'},entries=[entry('JPM reports earnings beat',60)])
    monkeypatch.setattr(news_fetcher,'_fetch_feed',late)
    monkeypatch.setattr(news_fetcher,'feedparser',object())
    svc=service(tmp_path)
    policy=replace(ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True),
                   total_budget_seconds=0.03,tier_budgets={'fast':0.02,'extended':0.01})
    try:
        result=svc.get_news((CANDIDATE,),ross._ross_news_request(),policy)
        assert result.diagnostics.budget_exhausted
        assert not result.evidence_for_symbol('JPM')
        assert not svc.retrieval_provider._lifecycle.wait_for_cleanup(0)['cleanup_complete']
    finally:
        gate.set()
        assert svc.retrieval_provider._lifecycle.wait_for_cleanup(2)['cleanup_complete']
    assert not result.evidence_for_symbol('JPM')


def test_older_fresh_dilution_witness_vetoes_positive(monkeypatch,tmp_path):
    calls=[]
    entries=[entry('JPM market roundup '+str(n),n+1) for n in range(7)]
    entries.extend([entry('JPM reports earnings beat',600),entry('JPM announces registered direct offering',900)])
    fixture_transport(monkeypatch,calls,entries)
    svc=service(tmp_path);monkeypatch.setattr(ross,'_news_intelligence_service_for_scanner',lambda:svc)
    ctx,_=ross._enrich_news_context(['JPM'],'RSS',{'JPM':{'company_name':CANDIDATE.company_name}})
    assert ctx['JPM']['qualification_evidence_count']==6
    assert ctx['JPM']['dilution_flag'] and not ctx['JPM']['ross_catalyst_valid']


def test_witness_is_excluded_from_all_presentation_metrics():
    from src.news.news_intelligence_contract import NewsEvidenceSummary
    display=tuple(replace(item('JPM market roundup '+str(n),n+1),original_source='Fixture Low Wire',
        url='https://low.invalid/'+str(n),source_domain='low.invalid',velocity_5m=6,heat_score=99,
        source_reliability_score=1) for n in range(5))
    witness=replace(item('JPM announces new supply contract',100),original_source='Reuters',
        url='https://reuters.invalid/event',source_domain='reuters.invalid',velocity_5m=6,heat_score=99,source_reliability_score=1)
    result=NewsBatchResult(candidates=(CANDIDATE,),request=ross._ross_news_request(),diagnostics=RetrievalDiagnostics(provider_available=True))
    ctx=ross._ross_news_context_from_evidence('JPM',(*display,witness),NewsEvidenceSummary('JPM',velocity_5m=6,independent_source_count=2),result)
    assert ctx['ross_catalyst_valid'] and ctx['catalyst_type']=='CONTRACT'
    assert ctx['news_count']==ctx['fresh_news_count']==ctx['velocity_5m']==5
    assert ctx['news_independent_source_count']==1 and ctx['news_heat_score']<99
    assert ctx['news_source_reliability_score']==0
    assert ctx['top_news_catalyst_tag']=='generic'
    assert all('reuters' not in link for link in ctx['top_links'])
    assert ctx['top_domains']==['low.invalid']
    assert len(ctx['news_intelligence_source_provenance'])==5


def test_actual_consumer_never_waits_for_cleanup(monkeypatch,tmp_path):
    calls=[];fixture_transport(monkeypatch,calls,[])
    svc=service(tmp_path);life=svc.retrieval_provider._lifecycle
    def forbidden(*a,**k):
        raise AssertionError('Scanner must not synchronously wait after news budget')
    original=life.wait_for_cleanup
    monkeypatch.setattr(life,'wait_for_cleanup',forbidden)
    monkeypatch.setattr(ross,'_news_intelligence_service_for_scanner',lambda:svc)
    try:
        _,diag=ross._enrich_news_context(['JPM'],'RSS',{'JPM':{'company_name':CANDIDATE.company_name}})
        assert diag.news_intelligence_diagnostics['rss_cleanup']['cleanup_elapsed_seconds']==0
    finally:
        assert original(2)['cleanup_complete']


def test_captured_bac_event_does_not_qualify_comentioned_jpm():
    # Actual captured headline/publication instant; offline regression at the captured clock.
    title = "Bank of America Falls 5% as $1.2B Money Laundering Penalty Drives Earnings Miss; JPMorgan Chase and Wells Fargo Hold Steady"
    age = NOW.timestamp() - datetime(2026,10,14,12,32,tzinfo=timezone.utc).timestamp()
    decision = assess_issuer_event('JPM', item(title,age))
    assert not decision['qualified']
    assert decision['reason'] == 'event_not_attributed_to_requested_issuer'


def test_scanner_context_order_reaches_actual_capped_acquisition(monkeypatch,tmp_path):
    calls=[];fixture_transport(monkeypatch,calls,[])
    contexts=[{'symbol':s,'company_name':'Fixture '+s+' Corporation'} for s in ('ZZZ','YYY','XXX','WWW','AAA','BBB')]
    metadata=ross._news_symbol_metadata_for_contexts(iter(contexts))
    assert metadata['ZZZ']['priority_rank']==1 and metadata['AAA']['priority_rank']==5
    svc=service(tmp_path);monkeypatch.setattr(ross,'_news_intelligence_service_for_scanner',lambda:svc)
    result,_=ross._enrich_news_context([row['symbol'] for row in contexts],'RSS',metadata)
    assert all(result[s]['issuer_query_outcomes'][0]['attempted'] for s in ('ZZZ','YYY','XXX','WWW'))
    assert result['AAA']['issuer_query_outcomes'][0]['reason']=='query_request_limit'
    assert result['BBB']['issuer_query_outcomes'][0]['reason']=='query_request_limit'
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(1)['cleanup_complete']
    explicit=ross._news_symbol_metadata_for_contexts([{'symbol':'ZZZ','priority_rank':8},{'symbol':'AAA','priority_rank':1}])
    assert explicit['ZZZ']['priority_rank']==8 and explicit['AAA']['priority_rank']==1


def test_disabled_setting_does_not_add_priority_to_legacy_handoff():
    set_config_overrides({'ROSS_ISSUER_QUERY_ENABLED':False})
    assert 'priority_rank' not in ross._news_symbol_metadata_for_contexts([{'symbol':'JPM','company_name':CANDIDATE.company_name}])['JPM']


def test_rank_permutation_reuses_wave_but_changed_selected_issuer_refreshes(monkeypatch,tmp_path):
    calls=[];fixture_transport(monkeypatch,calls,[])
    svc=service(tmp_path);request=ross._ross_news_request();policy=ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True)
    candidates=tuple(NewsCandidate('T'+str(n),company_name='Fixture Corporation '+str(n),priority_rank=n+1) for n in range(5))
    svc.get_news(candidates,request,policy);before=len(calls)
    same_wave=(replace(candidates[0],priority_rank=2),replace(candidates[1],priority_rank=1),*candidates[2:])
    svc.get_news(same_wave,request,policy)
    assert len(calls)==before
    new_wave=(*same_wave[:-1],replace(same_wave[-1],priority_rank=1))
    svc.get_news(new_wave,request,policy)
    assert len(calls)>before
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(1)['cleanup_complete']
