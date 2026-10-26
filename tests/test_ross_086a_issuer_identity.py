"""Captured final-cache samples only; synthetic controls are labelled separately."""
from dataclasses import replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace as NS

import pytest

from src.news import news_fetcher as fetcher
from src.news.news_intelligence_contract import NewsEvidence, NewsCandidate
from src.news.issuer_relevance import evidence_issuer_relevance_verified
from src.news.news_intelligence_contract import NewsBatchResult
from src.strategies.ross_momentum.policy.catalyst_policy import assess_issuer_event, classify_headline

FACTS = json.loads((Path(__file__).parent / 'fixtures/ross_086a_captured_exclusions.json').read_text())
ISSUERS = FACTS['issuers']
AZTR = ISSUERS['AZTR']
ARTICLE = AZTR['exclusion_evidence']['samples']['issuer_match_unverified'][0]


def match(symbol, title, summary='', metadata=None):
    return fetcher.symbol_relevance_match(symbol, title=title, summary=summary,
        metadata=metadata if metadata is not None else {'company_name': ISSUERS[symbol]['company_name']})


def item(sample=ARTICLE, *, symbol='AZTR'):
    return NewsEvidence(symbol=symbol, evidence_id=sample['article_identity_sha256'],
        headline=sample['title'], summary=sample['summary'], url=sample['url'],
        published_at=datetime.fromisoformat(sample['timestamp_provenance']['published_utc']),
        company_name=ISSUERS[symbol]['company_name'], provider='rss_batch', source_tier='operational_query',
        raw={'timestamp_provenance':sample['timestamp_provenance']})


def test_captured_fresh_aztr_filing_matches_full_supplied_issuer():
    assert hashlib.sha256(ARTICLE['title'].encode()).hexdigest() == ARTICLE['title_sha256']
    assert not any(ARTICLE[k] for k in ('title_truncated','summary_truncated','privacy_redacted'))
    assert 'AZTR' not in ARTICLE['title'] and ARTICLE['reason'] == 'issuer_match_unverified'
    assert match('AZTR', ARTICLE['title'], ARTICLE['summary']) == ('company_name','title')


@pytest.mark.parametrize('symbol,expected', [('AZTR','AZITRA INC'),('GCTK','GLUCOTRACK INC'),
                                           ('SPRC','SCISPARC LTD'),('RENT','RENT THE RUNWAY')])
def test_supplied_legal_name_is_not_lost_when_core_is_one_word(symbol, expected):
    assert fetcher.company_aliases_for_symbol(symbol, {'company_name':ISSUERS[symbol]['company_name']}) == (expected,)


@pytest.mark.parametrize('symbol', ['AZTR','RENT','GCTK','SPRC'])
def test_final_captured_exclusion_samples_replay_without_inventing_uncaptured_entries(monkeypatch, symbol):
    facts = ISSUERS[symbol]
    now = datetime.fromisoformat(facts['evaluation_time_utc']).timestamp()
    monkeypatch.setattr(time, 'time', lambda:now)
    samples = [s for group in facts['exclusion_evidence']['samples'].values() for s in group]
    entries = [NS(title=s['title'], summary=s['summary'], link=s['url'],
                  published=s['timestamp_provenance']['published_original'],
                  published_parsed=time.gmtime(parsedate_to_datetime(s['timestamp_provenance']['published_original']).timestamp())) for s in samples]
    calls=[]
    def captured_feed(url, *args):
        calls.append(url)
        return NS(entries=entries, feed={'title':'Captured exclusion samples'})
    monkeypatch.setattr(fetcher, '_fetch_feed', captured_feed)
    url=facts['query_url']
    from src.strategies.ross_momentum.policy.catalyst_policy import select_qualification_evidence
    from src.news.news_intelligence_contract import NewsRequest
    rows, summary=fetcher.fetch_headlines_for_symbols([symbol], [url], lookback_hours=6,
        source_tier='operational_query', source_groups_by_url={url:'ROSS_ISSUER_QUERY'},
        symbol_metadata={symbol:{'company_name':facts['company_name']}},
        retention_selector=select_qualification_evidence, retention_request=NewsRequest(max_evidence_per_symbol=6,metadata={'presentation_limit':5}))
    assert calls == [url]  # Local stub only; no requests/provider acquisition.
    expected=1 if symbol == 'AZTR' else 0
    assert len(rows[symbol]) == expected
    source=summary.source_diagnostics[0]
    assert source['entries_examined_count'] == len(samples)
    assert len(samples) < facts['feed_item_count']  # Bounded samples are not full responses.
    assert source['entry_diagnostics']['stale_entries'] == len(samples)-expected
    if expected:
        assert rows[symbol][0].title == ARTICLE['title']
        assert rows[symbol][0].published_ts == item().published_at.timestamp()
    assert all(s['timestamp_provenance']['selected_time_basis']=='published' for s in samples)


def test_captured_filing_stays_unqualified_after_attribution_repair(monkeypatch):
    now = datetime.fromisoformat(AZTR['evaluation_time_utc']).timestamp()
    monkeypatch.setattr(time,'time',lambda:now)
    evidence=item()
    original=evidence.published_at
    assert classify_headline(evidence.headline) is None
    candidate=NewsCandidate('AZTR',company_name=AZTR['company_name'])
    assert evidence_issuer_relevance_verified('AZTR',evidence,NewsBatchResult(candidates=(candidate,)))
    decision=assess_issuer_event('AZTR',evidence,(candidate,))
    assert not decision['qualified'] and decision['reason']=='no_catalyst_classification'
    assert decision['age_seconds'] == pytest.approx(20821.515771)
    assert evidence.published_at == original


@pytest.mark.parametrize('symbol,brand', [('AZTR','Azitra'),('GCTK','Glucotrack'),('SPRC','Scisparc')])
def test_bare_brand_or_other_supplied_issuer_does_not_gain_matching_authority(symbol, brand):
    assert match(symbol, f'{brand} reports earnings beat') is None
    assert match(symbol, f'{brand} Incubator reports earnings beat') is None
    assert match(symbol, f'{brand}x Inc reports earnings beat') is None
    assert match(symbol, ARTICLE['title'], metadata={'company_name':'Other Medical Inc'}) is None
    assert fetcher.company_aliases_for_symbol(symbol, {'aliases':[brand]}) == ()


@pytest.mark.parametrize('name', ['The Inc','Company Inc','Holdings Ltd','Group PLC','Inc LLC',
    'The Group','Company Holdings','Holdings Group','AZTR INC','Azitra Inc/USA-A',
    'Azitra Inc EXTRA','Azitra Inc/BVI-Z'])
def test_generic_symbol_core_and_unknown_decorations_are_not_full_name_fallback(name):
    assert match('AZTR', ARTICLE['title'],metadata={'company_name':name}) is None


@pytest.mark.parametrize('name', ['Azitra Inc','AZITRA INC-A','Azitra, Incorporated',
                                 'AZITRA INCORPORATED-B'])
def test_exact_legal_phrase_respects_known_display_and_punctuation(name):
    # Synthetic identity forms; not claims about which legal names the archive supplied.
    title='Azitra, Incorporated reports earnings beat' if 'INCORPORATED' in name.upper() else ARTICLE['title']
    assert match('AZTR',title,metadata={'company_name':name}) == ('company_name','title')


def test_synthetic_positive_event_and_peer_event_ownership_remain_separate(monkeypatch):
    monkeypatch.setattr(time,'time',lambda:datetime.fromisoformat(AZTR['evaluation_time_utc']).timestamp())
    synthetic=replace(item(),headline='Azitra Inc reports earnings beat')
    assert assess_issuer_event('AZTR',synthetic)['qualified']
    peer=replace(synthetic,headline='Other Medical reports earnings beat while Azitra Inc expands staffing')
    assert match('AZTR',peer.headline) == ('company_name','title')
    assert not assess_issuer_event('AZTR',peer)['qualified']
    assert not assess_issuer_event('AZTR',replace(synthetic,headline='Azitra Inc announces registered direct offering'))['qualified']
    assert not assess_issuer_event('AZTR',replace(synthetic,source_tier='research'))['qualified']
    assert not assess_issuer_event('AZTR',replace(synthetic,raw={'timestamp_provenance':{'selected_time_basis':'updated'}}))['qualified']


def test_captured_clinical_headline_remains_stale_and_missing_dates_fail_closed(monkeypatch):
    monkeypatch.setattr(time,'time',lambda:datetime.fromisoformat(AZTR['evaluation_time_utc']).timestamp())
    stale=AZTR['exclusion_evidence']['samples']['outside_lookback_window'][0]
    decision=assess_issuer_event('AZTR',item(stale))
    assert decision['reason']=='missing_future_or_stale_publication_time' and not decision['qualified']
    decision=assess_issuer_event('AZTR',replace(item(),published_at=None))
    assert decision['reason']=='missing_future_or_stale_publication_time' and not decision['qualified']


def test_captured_article_replay_uses_single_canonical_writer_and_readonly_consumers(monkeypatch, tmp_path):
    from src.news import evidence_store as store_module, news_intelligence_service as service_module, batch_rss_adapter
    from src.scanner import scanner_runner as ross
    from src.config.config_resolver import set_config_overrides
    now=datetime.fromisoformat(AZTR['evaluation_time_utc'])
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):
            return cls.fromisoformat(now.isoformat())
    for module in (store_module, service_module, batch_rss_adapter):
        monkeypatch.setattr(module,'datetime',Clock)
    monkeypatch.setattr(time,'time',lambda:now.timestamp())
    entry=NS(title=ARTICLE['title'],summary=ARTICLE['summary'],link=ARTICLE['url'],
             published=ARTICLE['timestamp_provenance']['published_original'],
             published_parsed=time.gmtime(item().published_at.timestamp()))
    def captured_feed(url,*args):
        # Duplicate the same captured item deliberately to exercise deduplication.
        # Empty primary stubs are synthetic, not a replay of inaccessible bodies.
        return NS(entries=[entry,entry] if 'news.google.com' in url else [],feed={'title':'Offline sample'})
    monkeypatch.setattr(fetcher,'_fetch_feed',captured_feed)
    writes=[]
    class Store(store_module.CanonicalNewsEvidenceStore):
        def write_with_retrieval_metadata(self,*args,**kwargs):
            writes.append(kwargs['retrieval_by_symbol'])
            return super().write_with_retrieval_metadata(*args,**kwargs)
    store=Store(tmp_path/'news.json',prep_artifact_loader=lambda:{})
    from src.news.rss_lifecycle import RssFetchLifecycle
    lifecycle=RssFetchLifecycle()
    service=service_module.CanonicalNewsIntelligenceService(evidence_store=store,
        retrieval_provider=batch_rss_adapter.BatchRssNewsIntelligenceProvider(lifecycle=lifecycle))
    candidates=(NewsCandidate('AZTR',company_name=AZTR['company_name']),)
    set_config_overrides({'ROSS_ISSUER_QUERY_ENABLED':True,'NEWS_ENABLED':True})
    try:
        result=service.get_news(candidates,ross._ross_news_request(),
            ross._ross_retrieval_policy(refresh_mode='force_refresh',network_allowed=True))
        assert len(writes)==1 and len(result.evidence_for_symbol('AZTR'))==1
        evidence=result.evidence_for_symbol('AZTR')[0]
        assert evidence.headline==ARTICLE['title'] and evidence.published_at==item().published_at
        assert evidence.match_type=='company_name'
        context=ross._ross_news_contexts_from_news_intelligence_result(result)['AZTR']
        assert not context['ross_catalyst_valid']
        assert {d['reason'] for d in context['qualification_decisions']}=={'no_catalyst_classification'}
        before=store.cache_path.read_bytes()
        class ForbiddenProvider:
            provider_id='rss_batch'
            def get_news(self,*args,**kwargs):
                pytest.fail('Read-only consumer invoked acquisition')
        reader=service_module.CanonicalNewsIntelligenceService(evidence_store=store,retrieval_provider=ForbiddenProvider())
        cached=reader.get_news(candidates,ross._ross_news_request(),replace(
            ross._ross_retrieval_policy(refresh_mode='cache_only',network_allowed=False),allow_cache_write=False))
        assert len(cached.evidence_for_symbol('AZTR'))==1 and len(writes)==1
        assert store.cache_path.read_bytes()==before
        assert not ross._ross_news_contexts_from_news_intelligence_result(cached)['AZTR']['ross_catalyst_valid']
    finally:
        assert lifecycle.wait_for_cleanup(2.)['cleanup_complete']
        set_config_overrides(None)


def test_diagnostic_exclusions_never_turn_into_canonical_evidence(monkeypatch, tmp_path):
    from src.news.evidence_store import CanonicalNewsEvidenceStore
    path=tmp_path/'news.json'
    # Exact historical empty evidence semantics, with the captured exclusions
    # nested in retrieval diagnostics only. This is not a new publication.
    buckets={symbol:{'evidence':[],'last_retrieval':{'coverage':{'diagnostics':{
        'exclusion_evidence':facts['exclusion_evidence']}}},'updated_at':facts['evaluation_time_utc']}
        for symbol,facts in ISSUERS.items()}
    path.write_text(json.dumps({'news_intelligence':{'schema_version':'PR1069.news_intelligence_evidence_store.v1','symbols':buckets}}))
    before=path.read_bytes()
    store=CanonicalNewsEvidenceStore(path,prep_artifact_loader=lambda:{})
    from src.news.news_intelligence_contract import NewsRequest
    result=store.read(tuple(NewsCandidate(symbol,company_name=facts['company_name']) for symbol,facts in ISSUERS.items()),NewsRequest())
    assert all(not evidence for evidence in result.evidence_by_symbol.values())
    assert path.read_bytes()==before


def test_effective_matching_profile_changes_but_operational_query_is_unchanged(monkeypatch):
    from src.news.news_intelligence_service import _acquisition_profile
    from src.scanner import scanner_runner as ross
    from src.config.config_resolver import set_config_overrides
    candidate=NewsCandidate('AZTR',company_name=AZTR['company_name'],exchange='SMART')
    set_config_overrides({'ROSS_ISSUER_QUERY_ENABLED':True,'NEWS_ENABLED':True})
    try:
        request=ross._ross_news_request()
        policy=ross._ross_retrieval_policy(refresh_mode='bounded_refresh',network_allowed=True)
        current=_acquisition_profile(candidate,request,policy)
        with monkeypatch.context() as old:
            # The exact old effective identity is archived, not guessed.
            old.setattr(fetcher,'company_aliases_for_symbol',lambda *args:tuple(AZTR['matching_aliases']))
            previous=_acquisition_profile(candidate,request,policy)
        assert current['issuer']['metadata']['matching_aliases']==['AZITRA INC']
        assert previous['issuer']['metadata']['matching_aliases']==[]
        assert current['fingerprint'] != previous['fingerprint']
        assert current['retrieval']==previous['retrieval'] and current['request']==previous['request']
        assert current['retrieval']['operational_selected_query_urls']==[AZTR['query_url']]
    finally:
        set_config_overrides(None)


@pytest.mark.parametrize('company,title,kind', [('AI Inc','AI Inc launches a routine website',None),
    ('Contract Inc','Contract Inc reports record annual sales',None),
    ('AI Inc','AI Inc reports earnings beat','EARNINGS'),
    ('Contract Inc','Contract Inc wins major contract','CONTRACT')])
def test_synthetic_full_legal_identity_does_not_supply_its_own_event_keyword(monkeypatch, company, title, kind):
    monkeypatch.setattr(time,'time',lambda:datetime.fromisoformat(AZTR['evaluation_time_utc']).timestamp())
    evidence=replace(item(),company_name=company,headline=title)
    decision=assess_issuer_event('AZTR',evidence)
    assert decision['qualified'] is (kind is not None)
    if kind:
        assert decision['catalyst_type']==kind
