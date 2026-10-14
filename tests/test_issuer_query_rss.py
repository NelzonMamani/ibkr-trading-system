"""Changed research contracts: real transports are forbidden, not exercised."""
from dataclasses import replace
from datetime import datetime, timezone
from email.utils import formatdate
import hashlib
import json
import socket
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from scripts.verify_news_discovery import _inputs, _parser
from src.config.config_resolver import set_config_overrides
from src.news import news_fetcher, standalone_lookup
from src.news.batch_rss_adapter import BatchRssNewsIntelligenceProvider
from src.news.evidence_store import CanonicalNewsEvidenceStore
from src.news.issuer_rss_queries import QUERY_PROFILE, QUERY_GROUP, QUERY_GROUPS, query_plan, query_sources
from src.news.news_intelligence_contract import NewsCandidate, NewsRequest, RetrievalPolicy
from src.news.news_intelligence_service import CanonicalNewsIntelligenceService, _acquisition_profile
from src.news.rss_lifecycle import RssFetchLifecycle
from src.news.rss_raw_capture import RAW_FEED_BYTES
from src.news.source_groups import get_source_group_urls
from src.news.standalone_lookup import LookupSettings, lookup_news, research_contracts

ISSUERS = (NewsCandidate('JPM', company_name='JPMorgan Chase & Co.', aliases=('JPMorgan Chase',), exchange='NYSE', market='US', region='US'),
           NewsCandidate('IRON', company_name='Disc Medicine, Inc.', aliases=('Disc Medicine',), exchange='NASDAQ'),
           NewsCandidate('LFCR', company_name='Lifecore Biomedical, Inc.', aliases=('Lifecore Biomedical',), exchange='NASDAQ'))


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    attempts = []
    def forbid(*args, **kwargs):
        attempts.append(True)
        raise AssertionError('external socket forbidden')
    monkeypatch.setattr(socket.socket, 'connect', forbid)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbid)
    set_config_overrides({'NEWS_ENABLED': True})
    yield
    set_config_overrides({})
    assert not attempts


def settings(tmp_path, **kw):
    return LookupSettings(profile=QUERY_PROFILE, cache_file=tmp_path/'canonical.json', **kw)


def entry(title='JPMorgan Chase & Co. announces results', age=60, **kw):
    return SimpleNamespace(title=title, summary='', link='https://publisher.test/article',
                           published_parsed=time.gmtime(time.time()-age), **kw)


def feed(entries=(), title='Feed label'):
    return SimpleNamespace(entries=list(entries), feed={'title': title})


def test_explicit_contracts_encoding_and_plan_dedup():
    rows = query_sources((ISSUERS[0], ISSUERS[0]))
    assert len(rows) == 2
    google = next(r for r in rows if r['query_provider'] == 'google_news_search')
    parts = urlsplit(google['source_id']); params = parse_qs(parts.query)
    assert parts.hostname == 'news.google.com' and parts.path == '/rss/search'
    assert params['q'] == ['("JPMorgan Chase" OR "JPMorgan Chase & Co." OR "$JPM" OR "NYSE:JPM")']
    assert params['hl'] == ['en-US']
    yahoo = next(r for r in rows if r['query_provider'] == 'yahoo_ticker_rss')
    assert parse_qs(urlsplit(yahoo['source_id']).query)['s'] == ['JPM']
    assert rows[0]['query_issuers'] == ['JPM']
    assert len(query_plan(ISSUERS)) == len(set(get_source_group_urls('FAST_TRADING') + get_source_group_urls('PREP_EXTENDED'))) + 6
    assert LookupSettings().validated().source_groups == ('FAST_TRADING', 'PREP_EXTENDED')


@pytest.mark.parametrize('candidate', [replace(ISSUERS[0],company_name=None), replace(ISSUERS[0], symbol='JPM&x=y'), replace(ISSUERS[0], aliases=('bad" OR everything',))])
def test_query_identity_bounds(candidate):
    with pytest.raises(ValueError): query_sources((candidate,))


def test_opt_in_and_fingerprint(tmp_path):
    request, policy = research_contracts(settings(tmp_path))
    assert policy.source_groups == QUERY_GROUPS and policy.fallback_mode == 'none'
    # Research gets one tier and no extended fallback in the adapter.
    with pytest.raises(ValueError): LookupSettings(source_groups=QUERY_GROUPS).validated()
    with pytest.raises(ValueError): settings(tmp_path, provider='massive').validated()
    with pytest.raises(ValueError): BatchRssNewsIntelligenceProvider().get_news(ISSUERS, NewsRequest(), policy)
    before = _acquisition_profile(ISSUERS[0], request, policy)
    after = _acquisition_profile(replace(ISSUERS[0],aliases=('JPMorgan Commercial Bank',)), request, policy)
    assert before['fingerprint'] != after['fingerprint']
    assert len(before['retrieval']['source_urls_by_group'][QUERY_GROUP]) == 2


def test_canonical_batch_publisher_dates_grouping_and_cache(monkeypatch,tmp_path):
    urls = query_sources(ISSUERS[:1]); google,yahoo = [r['source_id'] for r in urls]
    calls=[]
    def fetch(url, timeout):
        calls.append(url)
        if url == google:
            return feed([entry(title='JPMorgan Chase & Co. announces results - Publisher A', source={'title':'Publisher A'}),
                         entry(title='JPMorgan Chase & Co. announces results - Publisher B', source={'title':'Publisher B'}, age=120)])
        if url == yahoo:
            return feed([entry(source={'title':'Publisher A'})])
        return feed()
    monkeypatch.setattr(news_fetcher,'_fetch_feed',fetch)
    result=lookup_news((ISSUERS[0], ISSUERS[0]),settings(tmp_path,cache_mode='refresh'))
    assert len(calls)==len(set(calls))==len(query_plan(ISSUERS[:1]))
    item=result['symbols']['JPM'];facts=item['research_observations']
    assert item['query_coverage']=={'selected':2,'attempted':2,'available':2,'search_completeness_established':False}
    assert facts['issuer_match_observations']==3 and facts['distinct_retained_articles']==2
    assert facts['repeated_article_observations']==1
    group=facts['repeated_headlines_across_publishers'][0]
    assert not group['same_event_established']
    assert {r['publisher'] for r in group['observations']}=={'Publisher A','Publisher B'}
    assert all(r['timestamp_provenance']['selected_time_basis']=='published' for r in facts['observations'])
    assert any(r['raw_title'].endswith(' - Publisher B') for r in facts['observations'])
    assert not result['research_results_are_trading_catalysts']
    assert all(not a['is_qualifying_event_class'] and a['verified_source'] is None for a in item['articles'])
    cached=lookup_news(ISSUERS[:1],settings(tmp_path,cache_mode='only'))
    assert len(calls)==len(query_plan(ISSUERS[:1]))
    assert cached['symbols']['JPM']['research_observations']['issuer_match_observations']==3
    assert cached['symbols']['JPM']['research_observations']['observations']==facts['observations']


def test_date_diagnostics_rejections_and_empty(monkeypatch,tmp_path):
    old=entry(age=90000);future=entry(age=-100)
    missing=entry();missing.published_parsed=None
    invalid=entry();invalid.published_parsed=('bad',)
    fallback=entry(updated='original update');fallback.published_parsed=None;fallback.updated_parsed=time.gmtime(time.time()-60)
    rows=[entry(published='original publication'),old,future,missing,invalid,fallback,entry(title='Unrelated company'),entry(title='')]
    target=query_sources(ISSUERS[:1])[0]['source_id']
    monkeypatch.setattr(news_fetcher,'_fetch_feed',lambda url,timeout:feed(rows if url==target else []))
    result=lookup_news(ISSUERS[:1],settings(tmp_path,cache_mode='off'))
    sources=result['symbols']['JPM']['sources'];diag=next(r['entry_diagnostics'] for r in sources if r['source_id']==target)
    assert diag['usable_dates']==6 and diag['within_window']==4
    assert diag['missing_invalid_dates']==2 and diag['stale_entries']==1 and diag['future_entries']==1
    assert diag['updated_time_used']==1 and diag['relevance_rejections_by_symbol']=={'JPM':1}
    assert diag['observed_publication_min_utc'] < diag['window_start_utc']
    assert diag['observed_publication_max_utc'] > diag['evaluation_time_utc']
    assert any(r['entry_diagnostics']['empty_feed'] and r['retrieval_status']=='available' for r in sources)
    observations=result['symbols']['JPM']['research_observations']['observations']
    assert {r['timestamp_provenance']['selected_time_basis'] for r in observations}=={'published','updated'}
    assert any(r['timestamp_provenance']['updated_original']=='original update' for r in observations)


def test_failure_coverage_and_batch_request_counts(monkeypatch,tmp_path):
    bad=query_sources(ISSUERS[1:2])[1]['source_id'];calls=[]
    def fetch(url,timeout):
        calls.append(url)
        if url==bad: raise TimeoutError('fixture timeout')
        return feed()
    monkeypatch.setattr(news_fetcher,'_fetch_feed',fetch)
    result=lookup_news(ISSUERS,settings(tmp_path,cache_mode='off'))
    assert len(calls)==len(set(calls))==27
    assert result['rss_request_counts']['attempted']==27
    assert result['symbols']['IRON']['query_coverage']['available']==1
    assert result['symbols']['IRON']['coverage_status']=='partial'
    assert result['symbols']['IRON']['outcome']!='completed_no_match'


def raw_response(body):
    return SimpleNamespace(status_code=200,iter_content=lambda chunk_size: iter([body]),
                           raise_for_status=lambda:None,close=lambda:None)


def test_raw_capture_single_http_and_offline_replay(monkeypatch,tmp_path):
    stamp=formatdate(time.time()-60,usegmt=True)
    xml=f'<rss version="2.0"><channel><title>Publisher A</title><item><title>JPMorgan Chase &amp; Co. announces results</title><link>https://publisher.test/article</link><pubDate>{stamp}</pubDate></item></channel></rss>'.encode()
    calls=[]
    def transport(url,**kw):
        calls.append(url); assert kw['stream'] is True
        return raw_response(xml)
    monkeypatch.setattr(news_fetcher.requests,'get',transport)
    result=lookup_news(ISSUERS[:1],settings(tmp_path,cache_mode='refresh',raw_feed_directory=tmp_path/'raw'))
    records=result['raw_feed_evidence']['records']
    assert len(calls)==len(records)==23
    assert result['cleanup']['cleanup_complete']
    assert all(r['body_complete'] and r['evaluation_time_utc'] for r in records)
    for record in records:
        body=(tmp_path/'raw'/record['body_file']).read_bytes()
        assert body==xml and hashlib.sha256(body).hexdigest()==record['sha256']
    # Replay the same bytes via the existing fetch hook, not another retrieval engine.
    bodies={r['url']:(tmp_path/'raw'/r['body_file']).read_bytes() for r in records}
    monkeypatch.setattr(news_fetcher,'_fetch_feed',lambda url,timeout:news_fetcher.feedparser.parse(bodies[url]))
    replay=lookup_news(ISSUERS[:1],replace(settings(tmp_path,cache_mode='off'),cache_file=tmp_path/'replay.json'))
    assert replay['symbols']['JPM']['research_observations']['issuer_match_observations']==23
    assert result['symbols']['JPM']['research_observations']['repeated_article_observations']==22
    store=json.loads((tmp_path/'canonical.json').read_text())
    assert xml.decode() not in json.dumps(store)


def test_raw_limit_no_false_completed_no_match(monkeypatch,tmp_path):
    monkeypatch.setattr(news_fetcher.requests,'get',lambda *a,**kw:raw_response(b'x'*(RAW_FEED_BYTES+1)))
    result=lookup_news(ISSUERS[:1],settings(tmp_path,cache_mode='off',raw_feed_directory=tmp_path/'raw'))
    assert result['symbols']['JPM']['coverage_status']=='unavailable'
    records=result['raw_feed_evidence']['records']
    assert records and all(not r['body_complete'] and r['bytes_captured']==RAW_FEED_BYTES for r in records)
    assert result['cleanup']['cleanup_complete']


def test_cli_capture_path_guards(tmp_path):
    args=['JPM','--company-name','JPMorgan Chase & Co.','--profile',QUERY_PROFILE]
    candidates, value=_inputs(_parser().parse_args(args))
    assert value.profile==QUERY_PROFILE and len(candidates)==1
    with pytest.raises(ValueError): _inputs(_parser().parse_args(args+['--raw-feed-directory',str(tmp_path)]))
    with pytest.raises(ValueError): _inputs(_parser().parse_args(args+['--raw-feed-directory',str(tmp_path/'raw'),'--cache-file',str(tmp_path/'raw/cache.json')]))


def test_query_deadlines_disclose_unfinished_and_unattempted(monkeypatch,tmp_path):
    def slow(url,timeout):
        time.sleep(.06)
        return feed([entry()])
    monkeypatch.setattr(news_fetcher,'_fetch_feed',slow)
    result=lookup_news(ISSUERS,settings(tmp_path,cache_mode='off',budget_seconds=.01,cleanup_seconds=1))
    facts=result['symbols']['JPM']['research_observations']
    assert facts['unattempted_sources'] and facts['unfinished_sources']
    assert result['symbols']['JPM']['coverage_status']=='partial'
    assert result['symbols']['JPM']['query_coverage']['available']==0
    assert result['cleanup']['cleanup_complete']


def test_non_feed_http_success_is_not_available(monkeypatch,tmp_path):
    monkeypatch.setattr(news_fetcher.requests,'get',lambda *a,**kw:raw_response(b'<html><title>Access page</title></html>'))
    result=lookup_news(ISSUERS[:1],settings(tmp_path,cache_mode='off',raw_feed_directory=tmp_path/'raw'))
    assert result['symbols']['JPM']['query_coverage']['available']==0
    assert result['symbols']['JPM']['coverage_status']=='unavailable'
    assert all(r['http_status']==200 and r['body_complete'] for r in result['raw_feed_evidence']['records'])


@pytest.mark.parametrize('change', ['replace_peer', 'change_peer_alias'])
def test_batch_query_plan_changes_refresh_other_issuer(monkeypatch,tmp_path,change):
    calls=[]
    peer = ISSUERS[2] if change=='replace_peer' else replace(ISSUERS[1], aliases=('Disc Medicine Research',))
    target=query_sources((peer,))[0]['source_id']
    def fetch(url,timeout):
        calls.append(url)
        return feed([entry()] if url==target else [])
    monkeypatch.setattr(news_fetcher,'_fetch_feed',fetch)
    cold=lookup_news(ISSUERS[:2],settings(tmp_path,cache_mode='refresh'))
    assert not cold['symbols']['JPM']['articles']
    calls.clear()
    warm=lookup_news((ISSUERS[0],peer),settings(tmp_path,cache_mode='use'))
    assert len(warm['symbols']['JPM']['articles'])==1
    assert warm['symbols']['JPM']['acquisition_profile']['fingerprint'] != cold['symbols']['JPM']['acquisition_profile']['fingerprint']
    assert len(calls)==len(set(calls))==25
    assert warm['symbols']['JPM']['provenance']=='provider_refresh'


def test_fixed_feed_article_group_survives_store_and_replay(monkeypatch,tmp_path):
    fast=get_source_group_urls('FAST_TRADING')[0]
    prep=get_source_group_urls('PREP_EXTENDED')[0]
    def fetch(url,timeout):
        if url in (fast,prep):
            return feed([SimpleNamespace(
                title='JPMorgan Chase announces results', summary='', link='https://publisher.test/'+('fast' if url==fast else 'prep'),
                published_parsed=time.gmtime(time.time()-60))])
        return feed()
    monkeypatch.setattr(news_fetcher,'_fetch_feed',fetch)
    cold=lookup_news(ISSUERS[:1],settings(tmp_path,cache_mode='refresh'))
    assert {a['source_group'] for a in cold['symbols']['JPM']['articles']}=={'FAST_TRADING','PREP_EXTENDED'}
    cached=lookup_news(ISSUERS[:1],settings(tmp_path,cache_mode='only'))
    assert {a['source_group'] for a in cached['symbols']['JPM']['articles']}=={'FAST_TRADING','PREP_EXTENDED'}


def test_explicit_partial_refresh_keeps_full_query_acquisition(monkeypatch,tmp_path):
    peer_url=query_sources(ISSUERS[1:2])[0]['source_id']
    warmed=False
    calls=[]
    def fetch(url,timeout):
        calls.append(url)
        return feed([entry()] if warmed and url==peer_url else [])
    monkeypatch.setattr(news_fetcher,'_fetch_feed',fetch)
    service=CanonicalNewsIntelligenceService(
        evidence_store=CanonicalNewsEvidenceStore(tmp_path/'canonical.json',prep_artifact_loader=lambda:{}),
        retrieval_provider=BatchRssNewsIntelligenceProvider())
    request,policy=research_contracts(settings(tmp_path,cache_mode='refresh'))
    service.get_news(ISSUERS[:2],request,policy)
    warmed=True
    calls.clear()
    result=service.get_news(ISSUERS[:2],request,replace(policy,refresh_mode='incremental',
        metadata={**policy.metadata,'refresh_symbols':('JPM',)}))
    assert len(result.evidence_for_symbol('JPM'))==1
    assert len(calls)==len(set(calls))==25
    assert set(result.diagnostics.diagnostics['refresh_symbols'])=={'JPM','IRON'}
