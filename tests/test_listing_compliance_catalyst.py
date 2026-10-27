"""New policy controls. All HTTP, market inputs and positive events are synthetic
except the explicitly identified, unmodified four-article IPST receipt fixture.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from types import SimpleNamespace
import json
import pytest

from src.news import batch_rss_adapter, evidence_store, news_fetcher, news_intelligence_service
from src.news.evidence_store import CanonicalNewsEvidenceStore, evidence_from_mapping
from src.news.news_intelligence_contract import NewsCandidate, NewsBatchResult, NewsEvidence, RetrievalDiagnostics
from src.scanner import scanner_runner as ross
from src.strategies.ross_momentum.policy import catalyst_policy as cp
from src.strategies.ross_momentum.policy.catalyst_lifecycle import revalidate_handoff, filter_catalyst_rows
from src.domain import quote_freshness
from test_ross_operational_issuer_news import offline, service

NOW=datetime(2026,10,27,15,20,tzinfo=timezone.utc)
PUB=NOW-timedelta(minutes=1)
CANDIDATE=NewsCandidate('IPST',company_name='IP STRATEGY HOLDINGS INC')
TITLE='IP Strategy Holdings, Inc. Regains Compliance with Nasdaq Listing Rule'
FIXTURE=json.loads((Path(__file__).parent/'fixtures/ipst_listing_compliance_receipt.json').read_text())

@pytest.fixture(autouse=True)
def clock(offline,monkeypatch):
    class Clock(datetime):
        current=NOW
        @classmethod
        def now(cls,tz=None):
            return cls.fromtimestamp(cls.current.timestamp(),tz=tz)
    for module in (news_fetcher,batch_rss_adapter,evidence_store,news_intelligence_service,ross,quote_freshness):
        monkeypatch.setattr(module,'datetime',Clock)
    monkeypatch.setattr(cp.time,'time',lambda:Clock.current.timestamp())
    return Clock


@pytest.fixture
def synthetic_publisher_verification(monkeypatch):
    """Hypothetical verified original publisher, not an existing trust authority.

    Only these synthetic article URLs receive the test witness. This is a
    conditional positive policy proof, never verification of a captured source.
    """
    monkeypatch.setattr(cp,'_verified_original_publisher',lambda item:
        str(getattr(item,'url','')).startswith('https://www.globenewswire.com/news-release/synthetic'))


def article(title=TITLE,published=PUB,**changes):
    published=evidence_store.datetime.fromtimestamp(published.timestamp(),timezone.utc)
    return replace(NewsEvidence(symbol='IPST',evidence_id=title,headline=title,
        company_name=CANDIDATE.company_name,published_at=published,first_seen_at=published,
        provider='rss_batch',source_tier='operational_query',source_group='FAST_TRADING',
        url='https://www.globenewswire.com/news-release/synthetic',
        raw={'source_provenance':{'feed_url':'https://www.globenewswire.com/RssFeed?Category=Finance',
             'source_group':'FAST_TRADING','publisher_url':'https://www.globenewswire.com'},
             'timestamp_provenance':{'selected_time_basis':'published',
             'published_original':format_datetime(published,usegmt=True),'published_utc':published.isoformat()}}),**changes)

@pytest.mark.parametrize('title',[
 TITLE,'IPST has regained compliance with Nasdaq listing requirements',
 'IPST has restored compliance with NYSE continued listing standards',
 'IPST confirms that it has regained compliance with the Nasdaq minimum bid price requirement',
 'IPST announces it has regained compliance with Nasdaq Listing Rule 5550(a)(2)',
 'IPST restores full compliance with New York Stock Exchange listing requirements',
])
def test_direct_completed_verified_event(title,synthetic_publisher_verification):
    d=cp.assess_issuer_event('IPST',article(title),(CANDIDATE,))
    assert d['qualified'] and d['catalyst_type']==cp.LISTING_COMPLIANCE_EVENT
    assert d['confirmation_basis']=='single_verified_source_assertion_not_independent_confirmation'

@pytest.mark.parametrize('title',[
 'IPST receives Nasdaq deficiency notice','IPST receives delisting notice',
 'IPST appeals Nasdaq decision','IPST gets extension to regain Nasdaq compliance',
 'IPST plans to regain compliance with Nasdaq Listing Rule',
 'IPST expects it has regained compliance with Nasdaq Listing Rule',
 'IPST may have regained compliance with Nasdaq Listing Rule',
 'IPST seeks restored compliance with Nasdaq Listing Rule',
 'IPST has not regained compliance with Nasdaq Listing Rule',
 "IPST hasn't regained compliance with Nasdaq Listing Rule",
 'IPST never regained compliance with Nasdaq Listing Rule',
 'IPST regains compliance with Nasdaq Listing Rule if financing closes',
 'IPST regains compliance with Nasdaq Listing Rule pending review',
 'IPST regains compliance with Nasdaq Listing Rule?',
 'IPST regains compliance with Nasdaq Listing Rule following an appeal',
 'IPST regains compliance with Nasdaq Listing Rule in 2020',
 'IPST previously regained compliance with Nasdaq Listing Rule',
 'IPST reports on ABC regaining compliance with Nasdaq Listing Rule',
 'ABC regains compliance with Nasdaq Listing Rule while IPST holds steady',
 'IPST announces ABC has regained compliance with Nasdaq Listing Rule',
 'IPST and ABC regain compliance with Nasdaq Listing Rule',
 'IPST announces registered direct offering and regains compliance with Nasdaq Listing Rule',
 'IPST regains compliance with Nasdaq Listing Rule after financing',
 'IPST regains compliance with FDA requirements',
 'IPST regains compliance with Nasdaq reporting guidelines',
 'IPST maintains compliance with Nasdaq Listing Rule',
 'Form 8K IP Strategy Holdings Inc For: 27 October By Investing.com',
 'An October 23 quarterly report leads to a Nasdaq decision for IP Strategy Holdings (Nasdaq: IPST).',
])
def test_non_completed_uncertain_peer_and_nonlisting_events_reject(title,synthetic_publisher_verification):
    assert not cp.assess_issuer_event('IPST',article(title),(CANDIDATE,))['qualified']

@pytest.mark.parametrize('change',[
 'missing_route','query_copy','fake_domain','publisher_mismatch','credentials','flag_only',
 'update_only','original_mismatch','old_first_seen','missing_original','missing_timestamp','research','offering_flag',
])
def test_untrusted_or_renewed_provenance_rejects(change):
    ev=article();raw=json.loads(json.dumps(ev.raw));source=raw['source_provenance'];dates=raw['timestamp_provenance']
    if change=='missing_route':source.pop('feed_url')
    elif change=='query_copy':source.update(feed_url='https://news.google.com/rss/search?q=IPST',source_group='ROSS_ISSUER_QUERY')
    elif change=='fake_domain':ev=replace(ev,url='https://www.globenewswire.com.evil.invalid/news')
    elif change=='publisher_mismatch':source['publisher_url']='https://unknown.invalid'
    elif change=='credentials':ev=replace(ev,url='https://www.globenewswire.com@evil.invalid/news')
    elif change=='flag_only':raw={};ev=replace(ev,verified_source=True,independent_source_count=999,catalyst_classification=cp.LISTING_COMPLIANCE_EVENT)
    elif change=='update_only':dates['selected_time_basis']='updated'
    elif change=='original_mismatch':dates['published_original']=format_datetime(PUB-timedelta(days=1),usegmt=True)
    elif change=='old_first_seen':ev=replace(ev,first_seen_at=PUB-timedelta(days=1))
    elif change=='missing_original':dates.pop('published_original')
    elif change=='missing_timestamp':ev=replace(ev,published_at=None)
    elif change=='research':ev=replace(ev,source_tier='research')
    elif change=='offering_flag':ev=replace(ev,dilution_or_offering=True)
    assert not cp.assess_issuer_event('IPST',replace(ev,raw=raw),(CANDIDATE,))['qualified']

@pytest.mark.parametrize('age,eligible',[(-.000001,False),(0,True),(21600,True),(21600.000001,False)])
def test_publication_boundaries(clock,age,eligible,synthetic_publisher_verification):
    ev=article(published=PUB)
    clock.current=PUB+timedelta(seconds=age)
    assert cp.assess_issuer_event('IPST',ev,(CANDIDATE,))['qualified'] is eligible

@pytest.mark.parametrize('index',range(4))
def test_captured_ipst_original_clocks_are_not_retroactive_success(clock,index):
    row=FIXTURE['articles'][index]
    for stamp in FIXTURE['evaluation_clocks']:
        clock.current=datetime.fromisoformat(stamp)
        ev=evidence_from_mapping(row,now=clock.current)
        assert ev.published_at.isoformat()==row['published_at']
        assert cp.issuer_event_time_state(ev,now_ts=clock.current.timestamp())=='current'
        assert news_fetcher.symbol_relevance_match('IPST',title=ev.headline,summary=ev.summary,metadata={'company_name':CANDIDATE.company_name})
        d=cp.assess_issuer_event('IPST',ev,(CANDIDATE,))
        assert not d['qualified']
        assert d['reason']==('no_catalyst_classification' if index<2 else 'listing_compliance_provenance_unverified')
    print('CAPTURED_IPST',index,row['published_at'],d['reason'])


def test_two_captured_syndicated_copies_never_establish_confirmation(clock):
    for row in FIXTURE['articles'][2:]:
        ev=evidence_from_mapping(row,now=clock.current)
        ev=replace(ev,independent_source_count=2,publication_count=2,verified_source=True)
        assert not cp.assess_issuer_event('IPST',ev,(CANDIDATE,))['qualified']


def _contexts(result):
    return ross._ross_news_contexts_from_news_intelligence_result(result)['IPST']


def test_synthetic_canonical_publication_cached_reconsideration_and_expiry(clock,monkeypatch,tmp_path,synthetic_publisher_verification):
    """SYNTHETIC feed and valid market inputs, never natural IPST success."""
    calls=[]
    entry=SimpleNamespace(title=TITLE,summary=TITLE,link=article().url,
        published=format_datetime(PUB,usegmt=True),published_parsed=cp.time.gmtime(PUB.timestamp()))
    def feed(url,*a):
        calls.append(url)
        return SimpleNamespace(version='rss20',bozo=False,feed={'title':'Synthetic fixed feed'},
            entries=[entry,entry] if url=='https://www.globenewswire.com/RssFeed?Category=Finance' else [])
    monkeypatch.setattr(news_fetcher,'_fetch_feed',feed);monkeypatch.setattr(news_fetcher,'feedparser',object())
    svc=service(tmp_path);store=svc.evidence_store if hasattr(svc,'evidence_store') else svc._evidence_store
    writes=[];write=store.write_with_retrieval_metadata
    def record(*a,**kw):writes.append(1);return write(*a,**kw)
    monkeypatch.setattr(store,'write_with_retrieval_metadata',record)
    request=ross._ross_news_request();policy=ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True)
    try:
        result=svc.get_news((CANDIDATE,),request,policy)
        assert len(writes)==1 and len(result.evidence_for_symbol('IPST'))==1
        assert _contexts(result)['ross_catalyst_valid']
        assert not result.diagnostics.diagnostics['refresh_diagnostics']['extended_fallback_requested']
        count=len(calls);before=store.cache_path.read_bytes()
        clock.current+=timedelta(seconds=1)
        cached=svc.get_news((CANDIDATE,),request,replace(policy,network_allowed=False,refresh_mode='cache_only',allow_cache_write=False))
        ctx=_contexts(cached)
        assert ctx['ross_catalyst_valid'] and len(calls)==count and len(writes)==1
        assert store.cache_path.read_bytes()==before
        assert revalidate_handoff('IPST',ctx['catalyst_evidence'],store=store)['qualified']
        # Same normal gate/ranking function used for cached reconsideration. Market
        # fields are explicit synthetic values; no broker/provider or forced branch.
        policy_obj=ross.RossPolicy().stock_selection
        thresholds=ross._gate_thresholds(policy_obj,ross._resolve_runtime_thresholds(policy_obj,'RTH_MID'))
        row={'symbol':'IPST','session':'RTH_MID','last_price':5.,'bid':5.,'ask':5.01,
             'pct_change':25.,'rvol_phase':10.,'rvol_discovery':10.,'relative_volume':10.,
             'volume':2000000,'premarket_volume':200000,'dollar_volume':10000000.,
             'float_shares':8000000,'spread_pct':.2,'halted':False,'ssr':False,
             'quote_evidence':quote_freshness.quote_evidence(clock.current.isoformat(),'LAST_TRADE')}
        focus=ross._select_ross_focus_contexts([row],{'IPST':ctx},thresholds,
            run_mode='READ_ONLY',news_enabled=True,validation_override_active=False,
            catalyst_decision=None,session_label='RTH_MID',symbol_contexts={},focus_limit=1)
        assert len(focus)==1
        handoff=json.loads(json.dumps(ctx['catalyst_evidence']))
        restarted=CanonicalNewsEvidenceStore(store.cache_path,prep_artifact_loader=lambda:{})
        assert revalidate_handoff('IPST',handoff,store=restarted)['qualified']
        clock.current=PUB+timedelta(seconds=21600,microseconds=1)
        assert not revalidate_handoff('IPST',handoff,store=restarted)['qualified']
        assert store.cache_path.read_bytes()==before and len(calls)==count
    finally:
        assert svc.retrieval_provider._lifecycle.wait_for_cleanup(2)['cleanup_complete']

@pytest.mark.parametrize('change',['wrong_issuer','untrusted','update_only','missing_timestamp','research','old_wrapper','offering'])
def test_listing_cached_handoff_rechecks_original_facts(clock,tmp_path,change,synthetic_publisher_verification):
    ev=article();raw=json.loads(json.dumps(ev.raw))
    if change=='wrong_issuer':ev=replace(ev,headline='Other Issuer regains compliance with Nasdaq Listing Rule')
    elif change=='untrusted':ev=replace(ev,url='https://unknown.invalid/article')
    elif change=='update_only':raw['timestamp_provenance']['selected_time_basis']='updated'
    elif change=='missing_timestamp':ev=replace(ev,published_at=None)
    elif change=='research':ev=replace(ev,source_tier='research')
    elif change=='old_wrapper':raw['timestamp_provenance']['published_original']=format_datetime(PUB-timedelta(days=1),usegmt=True)
    elif change=='offering':ev=replace(ev,dilution_or_offering=True)
    ev=replace(ev,raw=raw,verified_source=True,catalyst_classification=cp.LISTING_COMPLIANCE_EVENT)
    from src.strategies.ross_momentum.policy.catalyst_lifecycle import evidence_handoff
    handoff=evidence_handoff('IPST',(ev,),CANDIDATE,acquisition_health='healthy',acquisition_reason='synthetic')
    store=CanonicalNewsEvidenceStore(tmp_path/'private.json',prep_artifact_loader=lambda:{})
    assert not revalidate_handoff('IPST',handoff,store=store)['qualified']


def test_new_retained_financing_veto_blocks_listing_handoff(clock,tmp_path,synthetic_publisher_verification):
    from src.strategies.ross_momentum.policy.catalyst_lifecycle import evidence_handoff
    ev=article();handoff=evidence_handoff('IPST',(ev,),CANDIDATE,acquisition_health='healthy',acquisition_reason='synthetic')
    store=CanonicalNewsEvidenceStore(tmp_path/'private.json',prep_artifact_loader=lambda:{})
    initial=revalidate_handoff('IPST',handoff,store=store)
    assert initial['qualified'],initial
    store.write({'IPST':(replace(ev,headline='IPST announces registered direct offering',evidence_id='veto'),)},ross._ross_news_request())
    d=revalidate_handoff('IPST',handoff,store=store)
    assert not d['qualified'] and d['dilution_veto'] and d['qualification_reason']=='retained_dilution_veto'


def test_copies_and_cached_scores_cannot_supply_independent_confirmation(synthetic_publisher_verification):
    first=article();second=replace(first,evidence_id='syndicated',url=first.url+'-copy',observed_source='Syndicated label',independent_source_count=999)
    for ev in (first,second):
        d=cp.assess_issuer_event('IPST',ev,(CANDIDATE,))
        assert d['qualified'] and d['independent_confirmation_verified'] is False
    # Labels and replication counts cannot establish a verified route.
    second=replace(second,raw={},url="https://unverified.invalid/copy")
    assert not cp.assess_issuer_event('IPST',second,(CANDIDATE,))['qualified']


def test_microsecond_original_publication_is_preserved(clock,synthetic_publisher_verification):
    publication=PUB+timedelta(microseconds=1)
    ev=article(published=publication)
    raw=json.loads(json.dumps(ev.raw));raw['timestamp_provenance']['published_original']=publication.isoformat()
    ev=replace(ev,raw=raw)
    assert cp.assess_issuer_event('IPST',ev,(CANDIDATE,))['qualified']
    assert ev.published_at==publication


def test_existing_event_qualifications_are_not_shadowed_by_listing_mentions():
    # A separate eligible FDA assertion retains existing authority. This does
    # not qualify a speculative listing event or change the FDA policy.
    ev=article('IPST receives FDA approval and regains compliance with Nasdaq Listing Rule')
    ev=replace(ev,raw={})
    d=cp.assess_issuer_event('IPST',ev,(CANDIDATE,))
    assert d['qualified'] and d['catalyst_type']=='FDA'


def test_issuer_theme_word_cannot_shadow_completed_listing_event(synthetic_publisher_verification):
    ev=replace(article('AI Group Inc regains compliance with Nasdaq listing requirements'),
               symbol='AIGR',company_name='AI GROUP INC')
    d=cp.assess_issuer_event('AIGR',ev,(NewsCandidate('AIGR',company_name='AI GROUP INC'),))
    assert d['qualified'] and d['catalyst_type']==cp.LISTING_COMPLIANCE_EVENT


def test_explicit_untrusted_flag_is_never_overruled(synthetic_publisher_verification):
    assert not cp.assess_issuer_event('IPST',replace(article(),verified_source=False),(CANDIDATE,))['qualified']


def test_v9_acquisition_receipt_cannot_certify_new_policy_but_other_event_facts_survive(clock,monkeypatch,tmp_path):
    calls=[]
    entry=SimpleNamespace(title='IPST reports earnings beat',summary='',link='https://fixture.invalid/earnings',
        published=format_datetime(PUB,usegmt=True),published_parsed=cp.time.gmtime(PUB.timestamp()))
    def feed(url,*args):
        calls.append(url)
        return SimpleNamespace(version='rss20',bozo=False,feed={'title':'Synthetic'},
            entries=[entry] if 'news.google.com/rss/search?' in url else [])
    monkeypatch.setattr(news_fetcher,'_fetch_feed',feed);monkeypatch.setattr(news_fetcher,'feedparser',object())
    svc=service(tmp_path);request=ross._ross_news_request();policy=ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True)
    old_request=replace(request,metadata={**request.metadata,'qualification_profile':'ross_issuer_event_v9'})
    old_policy=replace(policy,metadata={**policy.metadata,'qualification_profile':'ross_issuer_event_v9'})
    try:
        old=svc.get_news((CANDIDATE,),old_request,old_policy)
        store=svc.evidence_store;before=store.cache_path.read_bytes();count=len(calls)
        cached=svc.get_news((CANDIDATE,),request,replace(policy,network_allowed=False,refresh_mode='cache_only',allow_cache_write=False))
        assert cached.summary_for_symbol('IPST').provider_status=='coverage_unknown'
        assert _contexts(cached)['ross_catalyst_valid']  # Existing earnings policy unchanged.
        assert cached.evidence_for_symbol('IPST')[0].published_at==PUB
        assert len(calls)==count and store.cache_path.read_bytes()==before
        fresh=svc.get_news((CANDIDATE,),request,policy)
        assert _contexts(fresh)['ross_catalyst_valid'] and len(calls)>count
        current_count=len(calls);svc.get_news((CANDIDATE,),request,policy)
        assert len(calls)==current_count
        assert policy.total_budget_seconds==old_policy.total_budget_seconds==8
        assert policy.tier_budgets==old_policy.tier_budgets=={'fast':5.2,'extended':2.8}
    finally:
        assert svc.retrieval_provider._lifecycle.wait_for_cleanup(2)['cleanup_complete']


def test_malformed_new_class_timestamp_facts_fail_closed():
    assert cp.assess_issuer_event('IPST',replace(article(),raw={'timestamp_provenance':['untrusted']}),(CANDIDATE,))['reason']=='listing_compliance_provenance_unverified'


@pytest.mark.parametrize('url,source',[
    ('https://www.globenewswire.com/news-release/synthetic','GlobeNewswire'),
    ('https://www.reuters.com/article/synthetic','Reuters'),
    ('https://news.google.com/rss/articles/synthetic','The Globe and Mail'),
    ('https://www.corsicanadailysun.com/synthetic','Corsicana Daily Sun'),
])
def test_production_has_no_implicit_publisher_verification_authority(url,source):
    ev=replace(article(),url=url,observed_source=source,original_source=source,
        verified_source=True,publication_count=2,independent_source_count=2,
        source_credibility_score=1.,source_reliability_score=1.)
    d=cp.assess_issuer_event('IPST',ev,(CANDIDATE,))
    assert d['catalyst_type']==cp.LISTING_COMPLIANCE_EVENT
    assert not d['qualified'] and d['reason']=='listing_compliance_provenance_unverified'
