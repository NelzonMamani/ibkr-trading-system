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
def test_incomplete_primary_defers_fallback_and_keeps_qualification_separate(monkeypatch,tmp_path,title):
    calls=[];gate=threading.Event()
    blocked_started=threading.Event();blocked_finished=threading.Event()
    def feed(url,timeout):
        calls.append(url)
        if 'news.google.com' in url:
            return SimpleNamespace(version="rss20", bozo=False, feed={'title':'fixture query'},entries=[entry(title,60)])
        blocked_started.set()
        gate.wait(2)
        blocked_finished.set()
        return SimpleNamespace(version="rss20", bozo=False, feed={},entries=[])
    monkeypatch.setattr(news_fetcher,'_fetch_feed',feed)
    monkeypatch.setattr(news_fetcher,'feedparser',object())
    svc=service(tmp_path)
    request=ross._ross_news_request()
    # Scaled timing contract, preserving allocations; not a provider latency claim.
    policy=replace(ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True),
        total_budget_seconds=0.2,tier_budgets={'fast':0.13,'extended':0.07})
    try:
        result=svc.get_news((CANDIDATE,),request,policy)
        # Whole-service wall time also includes config/cache/console work and
        # runner scheduling. Prove non-joining coordinator return directly:
        # owned gated workers must still be unfinished when the result returns.
        pending = svc.retrieval_provider._lifecycle.snapshot()
        assert pending['running_count'] > 0 and pending['unfinished_count'] > 0
        assert blocked_started.is_set() and not blocked_finished.is_set()
        assert not pending['cleanup_complete'] and not gate.is_set()
        assert result.diagnostics.total_budget_seconds == policy.total_budget_seconds == 0.2
        raw=result.diagnostics.diagnostics['refresh_diagnostics']
        assert raw['fallback_skipped_reason']=='primary_coverage_incomplete'
        assert not raw['primary_source_coverage_complete']
        assert not raw['extended_fallback_requested']
        assert result.diagnostics.budget_exhausted
        assert not any('forbes' in url or 'fortune' in url for url in calls)
        contexts=ross._ross_news_contexts_from_news_intelligence_result(result)
        assert contexts['JPM']['issuer_query_requests_completed']
        assert contexts['JPM']['acquisition_available']
        assert not contexts['JPM']['source_coverage_complete']
        assert contexts['JPM']['ross_catalyst_valid'] == ('earnings' in title)
        assert contexts['JPM']['news_available'] == ('earnings' in title)
        deferred=[r for r in result.diagnostics.source_diagnostics if r.source_group=='PREP_EXTENDED']
        assert deferred and all(not r.attempted and r.failure_reason=='primary_coverage_incomplete' for r in deferred)
        assert not svc.retrieval_provider._lifecycle.snapshot()['cleanup_complete']
    finally:
        gate.set()
        assert svc.retrieval_provider._lifecycle.wait_for_cleanup(2)['cleanup_complete']
    assert contexts['JPM']['ross_catalyst_valid'] == ('earnings' in title)


def test_policy_witness_in_completed_primary_avoids_unnecessary_fallback(monkeypatch,tmp_path):
    calls=[];fixture_transport(monkeypatch,calls,[entry('JPM reports earnings beat',60)])
    svc=service(tmp_path);request=ross._ross_news_request()
    result=svc.get_news((CANDIDATE,),request,ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True))
    raw=result.diagnostics.diagnostics['refresh_diagnostics']
    assert raw['primary_source_coverage_complete']
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
        return SimpleNamespace(version="rss20", bozo=False, feed={'title':'fixture'},entries=[entry('JPM reports earnings beat',60)] if 'news.google.com' in url else [])
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
        assert not result.summary_for_symbol('IRON').budget_exhausted
        assert contexts['IRON']['coverage_deadline_exhausted']
        timings=result.diagnostics.diagnostics['phase_timings']
        assert timings['service_total_seconds']>=timings['provider_seconds']
    finally:
        gate.set();assert svc.retrieval_provider._lifecycle.wait_for_cleanup(2)['cleanup_complete']


@pytest.mark.parametrize('positive',[False,True])
def test_primary_failure_is_partial_acquisition_without_false_deadline(monkeypatch,tmp_path,positive):
    calls=[]
    def feed(url,timeout):
        calls.append(url)
        if 'reuters.com' in url:
            raise news_fetcher.requests.HTTPError(response=SimpleNamespace(status_code=401))
        return SimpleNamespace(version="rss20", bozo=False, feed={'title':'fixture'},entries=[entry('JPM reports earnings beat' if positive else 'JPM generic report',60)] if 'news.google.com' in url else [])
    monkeypatch.setattr(news_fetcher,'_fetch_feed',feed);monkeypatch.setattr(news_fetcher,'feedparser',object())
    svc=service(tmp_path)
    result=svc.get_news((CANDIDATE,),ross._ross_news_request(),ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True))
    raw=result.diagnostics.diagnostics['refresh_diagnostics']
    assert not raw['primary_source_coverage_complete']
    assert raw['fallback_skipped_reason']=='primary_coverage_incomplete'
    assert not raw['extended_fallback_requested'] and len(calls)==9
    assert not result.diagnostics.budget_exhausted
    assert result.summary_for_symbol('JPM').retrieval_status=='partial'
    assert result.summary_for_symbol('JPM').provider_available
    contexts=ross._ross_news_contexts_from_news_intelligence_result(result)
    ctx=contexts['JPM']
    assert ctx['acquisition_available'] and not ctx['source_coverage_complete']
    assert ctx['ross_catalyst_valid'] is positive
    assert ctx['news_available'] is positive
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(1)['cleanup_complete']


@pytest.mark.parametrize('headline',[
    'JPM reports earnings of Bank of America',
    'JPM reports earnings for Bank of America',
    'JPM reports earnings at Bank of America',
    'JPM reports earnings from Bank of America',
    'JPM reports earnings of JPMorgan Chase and Bank of America',
    'JPM reports earnings for Q3 of Bank of America',
    'JPM reports earnings for its competitor Bank of America',
    'JPM reports earnings of its own competitor Bank of America',
    "JPM reports earnings of JPMorgan Chase's rival Bank of America",
    'JPM reports earnings for Q3: BAC',
])
def test_other_or_uncertain_event_owner_cannot_satisfy_actual_consumer(headline):
    from test_ross_operational_issuer_news import item
    from src.news.news_intelligence_contract import NewsBatchResult, RetrievalDiagnostics
    from src.strategies.ross_momentum.policy.catalyst_policy import assess_catalyst
    result=NewsBatchResult(candidates=(CANDIDATE,),request=ross._ross_news_request(),diagnostics=RetrievalDiagnostics(provider_available=True))
    context=ross._ross_news_context_from_evidence('JPM',(item(headline),),None,result)
    assert not context['ross_catalyst_valid']
    assert context['qualification_decisions'][0]['reason']=='event_ownership_uncertain_or_other_issuer'
    assert not assess_catalyst(mode='READ_ONLY',news_enabled=True,news_available=context['news_available'],confirmed=context['ross_catalyst_valid']).satisfied


@pytest.mark.parametrize('headline',[
    'JPM reports earnings for Q3',
    'JPM reports earnings for the third quarter',
    'JPM reports earnings for Q3 of 2026',
    'JPM reports earnings of JPMorgan Chase',
    'JPM reports earnings of JPMorgan Chase for Q3',
])
def test_verified_same_issuer_or_period_complement_keeps_fixture_positive(headline):
    from test_ross_operational_issuer_news import item
    from src.strategies.ross_momentum.policy.catalyst_policy import assess_issuer_event
    assert assess_issuer_event('JPM',item(headline))['qualified']


def test_changed_owner_qualification_contract_refreshes_old_compressed_coverage(monkeypatch,tmp_path):
    calls=[];fixture_transport(monkeypatch,calls,[])
    svc=service(tmp_path);current=ross._ross_news_request()
    assert current.metadata['qualification_profile']=='ross_issuer_event_v9'
    old=replace(current,metadata={**current.metadata,'qualification_profile':'ross_issuer_event_v1'})
    policy=ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True)
    svc.get_news((CANDIDATE,),old,policy);before=len(calls)
    current_result=svc.get_news((CANDIDATE,),current,policy)
    assert len(calls)>before
    assert current_result.diagnostics.diagnostics['acquisition_profile_mismatch_symbols']==['JPM']
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(1)['cleanup_complete']


@pytest.mark.parametrize('text',['JPM treatment update','JPM aftermath review','JPM XS1 protocol'])
def test_short_financing_terms_do_not_match_ordinary_words(text):
    from src.strategies.ross_momentum.policy.catalyst_policy import detect_dilution
    assert not detect_dilution(text)


@pytest.mark.parametrize('text',['JPM announces ATM program','JPM files S-1/A','JPM files S1','JPM announces offerings'])
def test_actual_short_financing_terms_keep_veto(text):
    from src.strategies.ross_momentum.policy.catalyst_policy import detect_dilution
    assert detect_dilution(text)


def test_treatment_cannot_displace_valid_policy_witness(monkeypatch,tmp_path):
    calls=[]
    entries=[entry('JPM generic report '+str(n),n+1) for n in range(5)]
    entries.extend([entry('JPM treatment overview',600),entry('JPM reports earnings beat',700)])
    fixture_transport(monkeypatch,calls,entries)
    svc=service(tmp_path)
    result=svc.get_news((CANDIDATE,),ross._ross_news_request(),ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True))
    context=ross._ross_news_contexts_from_news_intelligence_result(result)['JPM']
    assert context['ross_catalyst_valid'] and not context['dilution_flag']
    assert context['news_count']==5 and context['qualification_evidence_count']==6
    assert not any('treatment' in x.headline for x in result.evidence_for_symbol('JPM'))
    assert svc.retrieval_provider._lifecycle.wait_for_cleanup(1)['cleanup_complete']


def test_degradation_uses_acquisition_policy_even_after_dynamic_flag_changes():
    from src.config.config_resolver import set_config_overrides
    from src.news.news_intelligence_contract import NewsBatchResult,RetrievalDiagnostics
    policy=ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True)
    result=NewsBatchResult(retrieval_policy=policy,diagnostics=RetrievalDiagnostics(
        retrieval_status='unavailable',provider_status='partial_request_failure',provider_available=False))
    set_config_overrides({'ROSS_ISSUER_QUERY_ENABLED':False})
    assert ross._news_diagnostics_from_news_intelligence_result(result,{}).news_degraded


@pytest.mark.parametrize('headline',[
    'ACME announces FDA approval for Rival Therapeutics',
    'ACME announces FDA approval at Rival Therapeutics',
    'ACME announces FDA approval from Rival Therapeutics',
    'ACME announces upgrade for Rival Therapeutics',
    'ACME announces contract for Rival Therapeutics',
])
def test_non_earnings_foreign_ownership_cannot_qualify_actual_consumer(headline):
    from test_ross_operational_issuer_news import item
    from src.news.news_intelligence_contract import NewsBatchResult,NewsCandidate,RetrievalDiagnostics
    from src.strategies.ross_momentum.policy.catalyst_policy import assess_catalyst
    candidate=NewsCandidate('ACME',company_name='Acme Therapeutics, Inc.',aliases=('Acme Therapeutics',))
    evidence=replace(item(headline),symbol='ACME',company_name=candidate.company_name,aliases=candidate.aliases)
    result=NewsBatchResult(candidates=(candidate,),request=ross._ross_news_request(),diagnostics=RetrievalDiagnostics(provider_available=True))
    context=ross._ross_news_context_from_evidence('ACME',(evidence,),None,result)
    assert not context['ross_catalyst_valid']
    assert context['qualification_decisions'][0]['reason']=='event_ownership_uncertain_or_other_issuer'
    assert not assess_catalyst(mode='READ_ONLY',news_enabled=True,news_available=context['news_available'],confirmed=context['ross_catalyst_valid']).satisfied


@pytest.mark.parametrize('headline',[
    'JPM reports earnings for the quarter ended September 30, 2026',
    'JPM reports earnings for the third quarter ended September 30, 2026',
    'JPM receives FDA approval for its lead drug AX-101',
    'JPM receives FDA approval for lead therapy',
    'JPM wins contract for cloud services',
    'JPM launches AI platform for hospitals',
])
def test_direct_event_ordinary_complements_are_not_issuer_owners(headline):
    from test_ross_operational_issuer_news import item
    from src.strategies.ross_momentum.policy.catalyst_policy import assess_issuer_event
    assert assess_issuer_event('JPM',item(headline))['qualified']


@pytest.mark.parametrize('tail',[
    'the quarter ended September 31, 2026',
    'the quarter ended September 30, 2026 of Bank of America',
    'its lead drug AX-101 of Bank of America',
    'cloud services from Bank of America',
    'hospitals of Bank of America',
])
def test_ordinary_complement_cannot_hide_invalid_date_or_foreign_owner(tail):
    from test_ross_operational_issuer_news import item
    from src.strategies.ross_momentum.policy.catalyst_policy import assess_issuer_event
    assert not assess_issuer_event('JPM',item('JPM reports earnings for '+tail))['qualified']


@pytest.mark.parametrize('headline',[
    'JPM Wins Contract for Cloud Services',
    'JPM Receives FDA Approval for Its Lead Drug AX-101',
    'JPM Launches AI Platform for Hospitals',
])
def test_title_case_direct_product_complements(headline):
    from test_ross_operational_issuer_news import item
    from src.strategies.ross_momentum.policy.catalyst_policy import assess_issuer_event
    assert assess_issuer_event('JPM',item(headline))['qualified']


@pytest.mark.parametrize('headline,qualified',[
    ('AS reports earnings beat',True),
    ('$AS reports earnings beat',True),
    ('Amer Sports reports earnings beat',True),
    ('AS tracks rival earnings',False),
    ('Bank of America reports earnings beat as AS watches',False),
    ('AS comments as Bank of America reports earnings beat',False),
])
def test_clause_boundaries_preserve_leading_verified_identity(headline,qualified):
    from test_ross_operational_issuer_news import item
    from src.strategies.ross_momentum.policy.catalyst_policy import assess_issuer_event
    evidence=replace(item(headline),symbol='AS',company_name='Amer Sports, Inc.',aliases=('Amer Sports',))
    assert assess_issuer_event('AS',evidence)['qualified'] is qualified


@pytest.mark.parametrize('headline,qualified',[
    ('JPM announces FDA approval granted to Rival Therapeutics',False),
    ('JPM announces contract awarded to Bank of America',False),
    ('JPM announces FDA approval granted exclusively to Rival Therapeutics',False),
    ('JPM announces FDA approval issued to Rival Therapeutics',False),
    ('JPM announces contract assigned to Bank of America',False),
    ('JPM announces FDA approval granted to JPMorgan Chase',True),
    ('JPM wins contract to improve hospitals',True),
])
def test_passive_event_recipients_must_belong_to_requested_issuer(headline,qualified):
    from test_ross_operational_issuer_news import item
    from src.news.news_intelligence_contract import NewsBatchResult,RetrievalDiagnostics
    result=NewsBatchResult(candidates=(CANDIDATE,),request=ross._ross_news_request(),diagnostics=RetrievalDiagnostics(provider_available=True))
    context=ross._ross_news_context_from_evidence('JPM',(item(headline),),None,result)
    assert context['ross_catalyst_valid'] is qualified
    if not qualified:
        assert context['qualification_decisions'][0]['reason']=='event_ownership_uncertain_or_other_issuer'


@pytest.mark.parametrize('headline,qualified',[
    ('JPM announces FDA approval granted to JPMorgan Chase for its lead drug AX-101',True),
    ('JPM Announces FDA Approval Granted to JPMorgan Chase for Its Lead Drug AX-101',True),
    ('JPM announces contract awarded to JPMorgan Chase for cloud services',True),
    ('JPM announces FDA approval granted to JPMorgan Chase for its lead drug AX-101 of Rival Therapeutics',False),
    ('JPM announces contract awarded to JPMorgan Chase for Bank of America',False),
    ('JPM announces contract awarded to Bank of America for cloud services',False),
])
def test_verified_recipient_reuses_anchored_ordinary_complement(headline,qualified):
    from test_ross_operational_issuer_news import item
    from src.news.news_intelligence_contract import NewsBatchResult,RetrievalDiagnostics
    result=NewsBatchResult(candidates=(CANDIDATE,),request=ross._ross_news_request(),diagnostics=RetrievalDiagnostics(provider_available=True))
    context=ross._ross_news_context_from_evidence('JPM',(item(headline),),None,result)
    assert context['ross_catalyst_valid'] is qualified


@pytest.mark.parametrize('suffix,qualified',[
    (', for its lead drug AX-101',True),
    (', For Its Lead Drug AX-101',True),
    (',for its lead drug AX-101',True),
    (', for Rival Therapeutics',False),
    (', for its lead drug AX-101 of Rival Therapeutics',False),
])
def test_verified_recipient_complement_separator_punctuation(suffix,qualified):
    from test_ross_operational_issuer_news import item
    from src.news.news_intelligence_contract import NewsBatchResult,RetrievalDiagnostics
    result=NewsBatchResult(candidates=(CANDIDATE,),request=ross._ross_news_request(),diagnostics=RetrievalDiagnostics(provider_available=True))
    context=ross._ross_news_context_from_evidence('JPM',(item('JPM announces FDA approval granted to JPMorgan Chase'+suffix),),None,result)
    assert context['ross_catalyst_valid'] is qualified
