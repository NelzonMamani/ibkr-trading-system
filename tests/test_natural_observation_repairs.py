"""Offline retained observation replays and labelled synthetic controls."""
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace as NS
import time

import pytest

from src.news import news_fetcher as fetcher
from src.news.evidence_store import CanonicalNewsEvidenceStore, dedupe_evidence, evidence_from_mapping
from src.news.news_intelligence_contract import NewsCandidate, NewsRequest, NewsBatchResult
from src.news.issuer_relevance import evidence_issuer_relevance_verified
from src.strategies.ross_momentum.policy.catalyst_policy import assess_issuer_event

FACTS = json.loads((Path(__file__).parent/'fixtures/pr1222_observation_news.json').read_text())['symbols']
NOW = datetime(2026, 11, 12, 16, tzinfo=timezone.utc)


def parsed(symbol):
    return [evidence_from_mapping(row, now=NOW) for row in FACTS[symbol]]


@pytest.mark.parametrize('notation', ['MFI.TO', '$MFI.TO', '(MFI.TO)', 'NASDAQ:MFI.TO',
                                    'MFI/TO', 'MFI-A', 'AMFI', 'MFI1'])
def test_security_suffix_is_not_an_exact_ticker(notation):
    for symbol in ('MFI', 'XYZ'):
        title = notation.replace('MFI', symbol)
        assert fetcher.symbol_relevance_match(symbol, title=title) is None
        assert fetcher.symbol_relevance_match(symbol, title='Other issuer', summary=title) is None


@pytest.mark.parametrize('title', ['MFI reports earnings', '(MFI) reports earnings', '$MFI reports earnings',
                                  'NASDAQ: MFI reports earnings', 'MFI. Reports earnings',
                                  'MF International Ltd reports earnings; MFI.TO is unrelated'])
def test_exact_ticker_and_verified_issuer_name_remain_valid(title):
    assert fetcher.symbol_relevance_match('MFI', title=title, metadata={'company_name':'MF INTERNATIONAL LTD-A'})


@pytest.mark.parametrize('symbol', ['MFI.TO', 'BRK.B', 'BRK-B'])
def test_requested_suffix_is_preserved_as_part_of_its_own_exact_symbol(symbol):
    for title in (f'{symbol} reports earnings', f'({symbol}) reports earnings', f'${symbol} reports earnings'):
        assert fetcher.symbol_relevance_match(symbol,title=title)==('ticker_token','title')
    assert fetcher.symbol_relevance_match(symbol,title='Other issuer',summary=f'${symbol} reports earnings')==('ticker_token','summary')


def test_captured_collision_rejected_on_fresh_retrieval_and_persisted_consumption(monkeypatch, tmp_path):
    row = FACTS['MFI'][0]
    stamp = datetime.fromisoformat(row['published_at'])
    monkeypatch.setattr(time, 'time', lambda: NOW.timestamp())
    entry = NS(title=row['headline'], summary=row['summary'], link=row['url'],
               published_parsed=stamp.utctimetuple())
    calls = []
    def feed(url, *args):
        calls.append(url)
        return NS(version='rss20', bozo=False, entries=[entry], feed={'title':row['observed_source']})
    monkeypatch.setattr(fetcher, '_fetch_feed', feed)
    result, summary = fetcher.fetch_headlines_for_symbols(['MFI'], ['https://example.invalid/rss'],
        symbol_metadata={'MFI':{'company_name':row['company_name']}}, source_tier='operational_query')
    assert len(calls) == 1 and result['MFI'] == []
    candidate = NewsCandidate('MFI', company_name=row['company_name'])
    item = parsed('MFI')[0]
    assert not evidence_issuer_relevance_verified('MFI', item, NewsBatchResult(candidates=(candidate,)))
    cache = tmp_path/'cache.json'
    cache.write_text(json.dumps({'news_intelligence':{'symbols':{'MFI':{'evidence':[row],
        'ross_qualification_evidence':[row]}}}}))
    read = CanonicalNewsEvidenceStore(cache, prep_artifact_loader=lambda:{}).read((candidate,), include_prep=False)
    assert read.evidence_by_symbol['MFI'] == ()
    assert read.diagnostics['issuer_relevance_rejected_by_symbol'] == {'MFI':1}
    # Cached classification cannot make the quote page a qualifying event.
    assert not assess_issuer_event('MFI', item, (candidate,))['qualified']
    assert json.loads(cache.read_text())['news_intelligence']['symbols']['MFI']['evidence']==[row]
    synthetic=replace(item,headline='MFI.TO reports earnings beat',summary='')
    assert assess_issuer_event('MFI',synthetic,(candidate,))['reason']=='issuer_match_unverified'
    positive=replace(synthetic,headline='MFI reports earnings beat')
    assert assess_issuer_event('MFI',positive,(candidate,))['qualified']


def test_captured_same_url_and_headline_deduplicate_across_publisher_labels(tmp_path):
    rows = parsed('MYPS')
    assert rows[0].url == rows[1].url and rows[0].headline == rows[1].headline
    assert rows[0].observed_source != rows[1].observed_source
    unique = dedupe_evidence(rows, max_items=10)
    assert len(unique) == 2
    assert all(item in rows for item in unique)
    retained=next(item for item in unique if item.url==rows[0].url)
    assert retained.published_at==rows[0].published_at
    assert retained.raw in (rows[0].raw, rows[1].raw)
    store = CanonicalNewsEvidenceStore(tmp_path/'cache.json', prep_artifact_loader=lambda:{})
    request = NewsRequest(max_evidence_per_symbol=10)
    store.write({'MYPS':rows[:1]}, request)
    store.write({'MYPS':rows[1:]}, request)
    persisted = json.loads(store.cache_path.read_text())['news_intelligence']['symbols']['MYPS']['evidence']
    assert len(persisted) == 2
    assert len({x['url'] for x in persisted}) == 2
    assert {x['published_at'] for x in persisted} == {x.published_at.isoformat() for x in rows}
    # Different URLs (including case), no-URL publisher/time facts stay distinct.
    base = rows[0]
    controls = [replace(base,evidence_id=str(i),url=url,observed_source=source)
                for i,(url,source) in enumerate([('https://example.test/A','News'),
                    ('https://example.test/a','News'),('', 'News'),('', 'Other')])]
    assert len(dedupe_evidence(controls,max_items=10)) == 4


@pytest.mark.parametrize('symbol', ['ADXN','CRE'])
def test_captured_generic_headlines_with_partial_coverage_do_not_force_focus(monkeypatch, symbol):
    from src.news.news_intelligence_contract import NewsEvidenceSummary
    from src.scanner.scanner_runner import _ross_news_contexts_from_news_intelligence_result
    monkeypatch.setattr(time,'time',lambda:NOW.timestamp())
    rows=tuple(parsed(symbol))
    candidate=NewsCandidate(symbol,company_name=rows[0].company_name)
    summary=NewsEvidenceSummary(symbol,evidence_count=len(rows),provider_available=True,
        provider_status='partial_request_failure',retrieval_status='partial',fresh_evidence_count=len(rows))
    result=NewsBatchResult(candidates=(candidate,),evidence_by_symbol={symbol:rows},summaries_by_symbol={symbol:summary})
    context=_ross_news_contexts_from_news_intelligence_result(result)[symbol]
    assert context['news_present'] and context['news_available']
    assert not context['ross_catalyst_valid']
    assert context['qualification_reason']=='no_valid_canonical_event'
    assert context['qualifying_evidence_ids']==[]
    assert result.summary_for_symbol(symbol).provider_status=='partial_request_failure'


def test_duplicate_aliases_do_not_inflate_fresh_or_persisted_metrics(monkeypatch, tmp_path):
    from src.news.evidence_store import enrich_evidence_metrics, serialize_evidence, retained_evidence
    import src.news.evidence_store as owner
    clock=NOW.replace(hour=15,minute=47)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None): return clock
    monkeypatch.setattr(owner,'datetime',Clock)
    rows=tuple(parsed('MYPS')[:2])
    # Simulate the exact former enrichment shape in the persisted cache.
    polluted=tuple(replace(item,publication_count=2,independent_source_count=2,
        velocity_5m=2,velocity_10m=2,velocity_30m=2,velocity_60m=2) for item in rows)
    fresh=enrich_evidence_metrics(rows,now_ts=clock.timestamp())
    assert len(fresh)==1
    assert fresh[0].publication_count==fresh[0].independent_source_count==fresh[0].velocity_5m==1
    cache=tmp_path/'cache.json'
    cache.write_text(json.dumps({'news_intelligence':{'symbols':{'MYPS':{'evidence':[serialize_evidence(item) for item in polluted]}}}}))
    candidate=NewsCandidate('MYPS',company_name=rows[0].company_name)
    store=CanonicalNewsEvidenceStore(cache,prep_artifact_loader=lambda:{})
    for metadata in ({},{'read_retained_cohort':True}):
        read=store.read((candidate,),NewsRequest(max_evidence_per_symbol=10,metadata=metadata),include_prep=False)
        item,=read.evidence_by_symbol['MYPS']
        assert item.publication_count==item.independent_source_count==item.velocity_5m==1
        assert read.summaries_by_symbol['MYPS'].velocity_5m==1
        assert item.published_at==rows[0].published_at
        assert item.raw in (rows[0].raw,rows[1].raw)
    # Merge must repair old duplicate metrics before collapsing old rows.
    store.write({'MYPS':()},NewsRequest(max_evidence_per_symbol=10))
    item,=store.read((candidate,),include_prep=False).evidence_by_symbol['MYPS']
    assert item.publication_count==item.independent_source_count==item.velocity_5m==1
