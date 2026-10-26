"""Offline broad-research contracts over the existing canonical RSS pipeline."""
from dataclasses import replace
import json
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

from scripts.verify_news_discovery import _inputs, _parser
from src.config.config_resolver import set_config_overrides
from src.news import batch_rss_adapter, news_fetcher, news_intelligence_service, standalone_lookup
from src.news.evidence_store import CanonicalNewsEvidenceStore
from src.news.news_intelligence_contract import NewsCandidate, NewsRequest, RetrievalPolicy
from src.news.news_intelligence_service import CanonicalNewsIntelligenceService
from src.news.rss_lifecycle import RssFetchLifecycle
from src.news.source_groups import get_source_group_urls
from src.news.standalone_lookup import BROAD_RESEARCH_PROFILE, LookupSettings, human_report, lookup_news, research_contracts

IDENTITIES = (NewsCandidate('IRON', company_name='Disc Medicine, Inc.', aliases=('Disc Medicine',), exchange='NASDAQ', market='US', region='US', metadata={'issuer_id': 'fixture-disc'}),
              NewsCandidate('LFCR', company_name='Lifecore Biomedical, Inc.', aliases=('Lifecore Biomedical',), exchange='NASDAQ', region='US'))
URLS = ('https://fixture.test/a', 'https://fixture.test/b', 'https://fixture.test/c')


@pytest.fixture(autouse=True)
def enabled():
    set_config_overrides({'NEWS_ENABLED': True})
    yield
    set_config_overrides({})


def settings(tmp_path, **kwargs):
    return LookupSettings(profile=BROAD_RESEARCH_PROFILE, cache_file=tmp_path/'research.json', **kwargs)


def entry(title='Disc Medicine announces research results', url='https://publisher.test/A', offset=0):
    return SimpleNamespace(title=title, summary='Disc Medicine, Inc. issuer report', link=url,
                           published_parsed=time.gmtime(time.time()-60-offset))


def setup(monkeypatch, tmp_path, feeds, urls=URLS):
    for module in (batch_rss_adapter, news_intelligence_service, standalone_lookup):
        monkeypatch.setattr(module, 'get_source_group_urls', lambda group: urls if group == 'BROAD_RSS_RESEARCH' else ())
    calls=[]
    def fetch(url, timeout):
        calls.append((url, timeout))
        value=feeds[url]
        if isinstance(value, Exception): raise value
        return value
    monkeypatch.setattr(news_fetcher, '_fetch_feed', fetch)
    lifecycle=RssFetchLifecycle()
    service=CanonicalNewsIntelligenceService(evidence_store=CanonicalNewsEvidenceStore(tmp_path/'research.json', prep_artifact_loader=lambda: {}),
        retrieval_provider=batch_rss_adapter.BatchRssNewsIntelligenceProvider(lifecycle=lifecycle))
    return service,lifecycle,calls


def feed(publisher, entries):
    return SimpleNamespace(version="rss20", bozo=False, feed={'title':publisher}, entries=entries)


def test_opt_in_exclusive_catalogue_and_default_membership():
    assert len(get_source_group_urls('BROAD_RSS_RESEARCH')) == 161
    assert len(set(get_source_group_urls('BROAD_RSS_RESEARCH'))) == 161
    assert LookupSettings().validated().source_groups == ('FAST_TRADING', 'PREP_EXTENDED')
    request,policy=research_contracts(LookupSettings(profile=BROAD_RESEARCH_PROFILE))
    assert request.strategy_id == BROAD_RESEARCH_PROFILE
    assert request.metadata['research_only']
    assert policy.source_groups == ('BROAD_RSS_RESEARCH',)
    assert policy.fallback_mode == 'none'
    with pytest.raises(ValueError): LookupSettings(source_groups=('BROAD_RSS_RESEARCH',)).validated()
    with pytest.raises(ValueError): LookupSettings(profile=BROAD_RESEARCH_PROFILE, provider='massive').validated()
    with pytest.raises(ValueError): LookupSettings(profile=BROAD_RESEARCH_PROFILE, source_groups=('FAST_TRADING',)).validated()
    provider=batch_rss_adapter.BatchRssNewsIntelligenceProvider()
    with pytest.raises(ValueError):
        provider.get_news(IDENTITIES, NewsRequest(), RetrievalPolicy(source_groups=('BROAD_RSS_RESEARCH',)))
    with pytest.raises(ValueError):
        provider.get_news(IDENTITIES, NewsRequest(), policy)


@pytest.mark.parametrize('candidates',[IDENTITIES[:1],IDENTITIES],ids=['one','list'])
def test_batch_fetch_once_and_separate_observations(monkeypatch,tmp_path,candidates):
    a=entry(); later=entry(offset=10)
    other=entry(url='https://publisher.test/Other')
    b=entry(url='https://other-publisher.test/article')
    service,lifecycle,calls=setup(monkeypatch,tmp_path,{URLS[0]:feed('Publisher A',[a,a,other]),
        URLS[1]:feed('Publisher A',[later]), URLS[2]:feed('Publisher B',[b])},urls=(*URLS,URLS[0]))
    result=lookup_news(candidates,settings(tmp_path,cache_mode='refresh'),service=service,lifecycle=lifecycle)
    assert len(calls)==3 and {url for url,_ in calls}==set(URLS)
    assert result['queried_source_groups']==['BROAD_RSS_RESEARCH']
    iron=result['symbols']['IRON']; facts=iron['research_observations']
    assert iron['coverage_status']=='complete'
    assert facts['observed_feed_entries']==5 and facts['entries_examined']==5
    assert facts['issuer_match_observations']==5
    assert facts['distinct_retained_articles']==3
    assert facts['repeated_article_observations']==2
    assert len(facts['repeated_articles'][0]['observations'])==3
    group=facts['repeated_headlines_across_publishers'][0]
    assert not group['same_event_established'] and len(group['observations'])==5
    assert {row['publisher'] for row in group['observations']}=={'Publisher A','Publisher B'}
    assert len({row['published_at'] for row in group['observations']})==2
    assert all(a['source_group']=='BROAD_RSS_RESEARCH' for a in iron['articles'])
    assert all(a['verified_source'] is None for a in iron['articles'])
    assert result['cleanup']['cleanup_complete'] is True
    assert not result['research_results_are_trading_catalysts']
    text=human_report(result)
    assert 'same event unproven' in text and 'issuer matches=5' in text
    if len(candidates)>1:
        assert result['symbols']['LFCR']['outcome']=='completed_no_match'
        stored=json.loads((tmp_path/'research.json').read_text())
        # Each acquisition keeps only its issuer's observations.
        assert 'research_by_symbol' in json.dumps(stored)
    before=len(calls)
    restarted=CanonicalNewsIntelligenceService(evidence_store=CanonicalNewsEvidenceStore(tmp_path/'research.json',prep_artifact_loader=lambda:{}))
    warm=lookup_news(candidates,settings(tmp_path,cache_mode='only'),service=restarted)
    assert len(calls)==before
    assert warm['symbols']['IRON']['research_observations']==facts
    assert warm['symbols']['IRON']['coverage_status']=='complete'


def test_retention_cap_does_not_hide_publishers_or_stop_scheduling(monkeypatch,tmp_path):
    service,lifecycle,calls=setup(monkeypatch,tmp_path,{url:feed(f'Publisher {i}',[entry(url=f'https://publisher.test/{i}')]) for i,url in enumerate(URLS)})
    result=lookup_news(IDENTITIES[:1],settings(tmp_path,max_items=1),service=service,lifecycle=lifecycle)
    facts=result['symbols']['IRON']['research_observations']
    assert len(calls)==3
    assert facts['issuer_match_observations']==3 and facts['distinct_retained_articles']==1
    assert facts['article_limit_excluded_observations']==2
    assert len(facts['repeated_headlines_across_publishers'][0]['observations'])==3
    assert result['symbols']['IRON']['coverage_status']=='partial'


def test_observation_cap_is_visible_and_preserves_retained_article_contract(monkeypatch,tmp_path):
    monkeypatch.setattr(news_fetcher,'RESEARCH_OBSERVATION_LIMIT',2)
    service,lifecycle,calls=setup(monkeypatch,tmp_path,{URLS[0]:feed('Publisher A',[entry(),entry(),entry()])},urls=URLS[:1])
    result=lookup_news(IDENTITIES[:1],settings(tmp_path),service=service,lifecycle=lifecycle)
    facts=result['symbols']['IRON']['research_observations']
    assert facts['issuer_match_observations']==3
    assert facts['observation_records_truncated']==1
    assert facts['repetition_count_is_lower_bound']
    assert len(facts['observations'])==2 and facts['distinct_retained_articles']==1
    assert result['symbols']['IRON']['coverage_status']=='partial'


def test_url_case_and_urlless_publication_are_distinct(monkeypatch,tmp_path):
    service,lifecycle,_=setup(monkeypatch,tmp_path,{URLS[0]:feed('A',[entry(),entry(url='https://publisher.test/a'),entry(url='',offset=1),entry(url='',offset=2)])},urls=URLS[:1])
    result=lookup_news(IDENTITIES[:1],settings(tmp_path),service=service,lifecycle=lifecycle)
    assert len(result['symbols']['IRON']['articles'])==4


def test_similar_headlines_are_not_grouped_and_unrelated_issuers_rejected(monkeypatch,tmp_path):
    service,lifecycle,_=setup(monkeypatch,tmp_path,{URLS[0]:feed('A',[entry()]),URLS[1]:feed('B',[entry(title='Disc Medicine announces different research results')]),
        URLS[2]:feed('C',[SimpleNamespace(title='Visitors enjoy egg tarts', summary='Nothing about an issuer',link='https://example.test/egg',published_parsed=time.gmtime(time.time()-60))])})
    result=lookup_news(IDENTITIES,settings(tmp_path),service=service,lifecycle=lifecycle)
    assert result['symbols']['IRON']['research_observations']['repeated_headlines_across_publishers']==[]
    assert result['symbols']['LFCR']['research_observations']['issuer_match_observations']==0


def test_timeout_failure_and_no_false_completed_no_match(monkeypatch,tmp_path):
    service,lifecycle,_=setup(monkeypatch,tmp_path,{URLS[0]:news_fetcher.requests.exceptions.ReadTimeout('offline'),URLS[1]:feed('B',[]),URLS[2]:feed('C',[])})
    result=lookup_news(IDENTITIES,settings(tmp_path),service=service,lifecycle=lifecycle)
    item=result['symbols']['IRON']; facts=item['research_observations']
    assert item['coverage_status']=='partial' and item['outcome']!='completed_no_match'
    assert len(facts['failures'])==1 and facts['failures'][0]['timed_out']
    assert facts['feed_entry_count_unknown_sources']==[URLS[0]]


def test_deadline_unfinished_unattempted_and_cleanup(monkeypatch,tmp_path):
    monkeypatch.setattr(news_fetcher,'DEFAULT_RSS_FETCH_WORKERS',1)
    service,lifecycle,calls=setup(monkeypatch,tmp_path,{},urls=URLS)
    def slow(url,timeout):
        calls.append((url,timeout)); time.sleep(.05)
        return feed('Late Publisher',[entry()])
    monkeypatch.setattr(news_fetcher,'_fetch_feed',slow)
    result=lookup_news(IDENTITIES[:1],settings(tmp_path,budget_seconds=.01,cleanup_seconds=.5),service=service,lifecycle=lifecycle)
    item=result['symbols']['IRON']; facts=item['research_observations']
    assert item['coverage_status']!='complete' and not item['articles']
    assert len(calls)==1 and calls[0][1]<=.01
    assert len(facts['unfinished_sources'])==1 and len(facts['unattempted_sources'])==2
    assert facts['issuer_match_observations']==0
    assert result['cleanup']['cleanup_complete']


def test_cli_requires_identities_and_roundtrips_batch_fields(tmp_path):
    parser=_parser()
    with pytest.raises(ValueError): _inputs(parser.parse_args(['IRON','--profile',BROAD_RESEARCH_PROFILE]))
    candidate_file=tmp_path/'identities.json'
    candidate_file.write_text(json.dumps([{'symbol':'IRON','company_name':'Disc Medicine, Inc.','aliases':['Disc Medicine'], 'exchange':'NASDAQ','region':'US','metadata':{'issuer_id':'fixture'}}]))
    candidates,config=_inputs(parser.parse_args(['--candidates-file',str(candidate_file),'--profile',BROAD_RESEARCH_PROFILE,'--cache-file',str(tmp_path/'cache.json')]))
    assert candidates[0].metadata['issuer_id']=='fixture' and candidates[0].exchange=='NASDAQ'
    assert config.source_groups==('BROAD_RSS_RESEARCH',)


def test_processing_deadline_visible_and_no_late_matches(monkeypatch,tmp_path):
    service,lifecycle,_=setup(monkeypatch,tmp_path,{URLS[0]:feed('A',[entry(),entry()])},urls=URLS[:1])
    original=news_fetcher._entry_summary
    def slow_summary(value):
        time.sleep(.02)
        return original(value)
    monkeypatch.setattr(news_fetcher,'_entry_summary',slow_summary)
    result=lookup_news(IDENTITIES[:1],settings(tmp_path,budget_seconds=.01),service=service,lifecycle=lifecycle)
    item=result['symbols']['IRON']; facts=item['research_observations']
    assert facts['processing_truncated_sources']==[URLS[0]]
    assert facts['issuer_match_observations']==0 and item['articles']==[]
    assert item['sources'][0]['failure_reason']=='processing_deadline_exhausted'
    assert item['sources'][0]['budget_exhausted']
    assert item['coverage_status']!='complete'


def test_scoped_persistence_and_changed_identity_coverage_unknown(monkeypatch,tmp_path):
    service,lifecycle,_=setup(monkeypatch,tmp_path,{url:feed('A',[entry()]) for url in URLS})
    lookup_news(IDENTITIES,settings(tmp_path),service=service,lifecycle=lifecycle)
    stored=json.loads((tmp_path/'research.json').read_text())
    namespace=stored['news_intelligence']['symbols']
    for symbol,bucket in namespace.items():
        facts=bucket['last_retrieval']['coverage']['diagnostics']['research_by_symbol']
        assert set(facts)=={symbol}
    changed=(replace(IDENTITIES[0],company_name='Different Issuer Corp.'),)
    result=lookup_news(changed,settings(tmp_path,cache_mode='only'),service=service)
    assert result['symbols']['IRON']['coverage_status']=='unknown'


def test_operational_diagnostics_and_evidence_signature_preserve_old_keys():
    from dataclasses import asdict
    from src.news.news_intelligence_contract import SourceDiagnostic
    original_fields={'source_id','provider','source_group','source_tier','retrieval_status','attempted','matched_count',
        'failure_reason','elapsed_seconds','timeout_seconds','timed_out','budget_exhausted',
        'request_elapsed_seconds','parse_elapsed_seconds','http_status','response_closed','feed_item_count','elapsed_kind','worker_completed'}
    def operational_fetch(symbols,sources,**kwargs):
        return {symbol:[] for symbol in symbols},news_fetcher.RssFailureSummary(len(sources),0,{},None,
            source_diagnostics=({'source_id':sources[0],'provider':'rss_batch','source_group':'FAST_TRADING',
                                 'source_tier':'fast','retrieval_status':'available','attempted':True},))
    provider=batch_rss_adapter.BatchRssNewsIntelligenceProvider(fast_fetcher=operational_fetch)
    result=provider.get_news(IDENTITIES[:1],NewsRequest(),RetrievalPolicy(source_groups=('FAST_TRADING',)))
    # This is the whole dataclass representation used by operational evidence signatures,
    # not just the nested adapter diagnostics payload.
    row=asdict(result.diagnostics)['source_diagnostics'][0]
    assert set(row)==original_fields
    assert type(result.diagnostics.source_diagnostics[0]) is SourceDiagnostic
    assert 'entries_examined_count' not in json.dumps(asdict(result.diagnostics))
    assert 'processing_truncated' not in json.dumps(asdict(result.diagnostics))
