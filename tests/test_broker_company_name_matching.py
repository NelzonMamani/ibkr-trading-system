"""Captured current article and explicitly counterfactual event replays; offline."""
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from src.news.news_fetcher import company_aliases_for_symbol, symbol_relevance_match
from src.news.news_intelligence_contract import NewsEvidence
from src.strategies.ross_momentum.policy.catalyst_policy import assess_issuer_event, classify_headline

FACTS=json.loads((Path(__file__).parent/'fixtures/clik_current_retrieval_article.json').read_text())
ARTICLE=FACTS['article']


def match(title, metadata=None, summary=''):
    return symbol_relevance_match('CLIK',title=title,summary=summary,
        metadata=metadata if metadata is not None else {'company_name':FACTS['company_name']})


@pytest.mark.parametrize('name',('CLICK HOLDINGS LTD/BVI-A','CLICK HOLDINGS LIMITED/BVI-B',
    'Click Holdings Ltd','Click Holdings Limited-A','Click Holdings'))
def test_recognized_display_suffix_and_two_word_public_identity(name):
    assert company_aliases_for_symbol('CLIK',{'company_name':name})==('CLICK HOLDINGS',)
    assert match(ARTICLE['title'],{'company_name':name})==('company_name','title')


def test_supplied_alias_remains_separate_and_must_be_specific():
    assert match(ARTICLE['title'],{'aliases':['Click Holdings']})==('company_name','title')
    assert match(ARTICLE['title'],{'aliases':['Click']}) is None
    assert match(ARTICLE['title'],{'company_name':'Other Medical Inc'}) is None
    assert match(ARTICLE['title'],{'company_name':'Other Medical Inc','aliases':['Other Holdings']}) is None


@pytest.mark.parametrize('title',('Click reports record revenue','Click Holdingsworth reports earnings',
    'ClickHouse Holdings reports earnings','Click Logistics Holdings reports earnings',
    'An unrelated company wins a contract'))
def test_unrelated_names_and_partial_brand_are_not_matches(title):
    assert match(title) is None


@pytest.mark.parametrize('name',('Click Inc-A','The Group','Company Holdings','Holdings Group',
    'CLICK HOLDINGS LTD/BVI-Z','CLICK HOLDINGS LTD/USA-A','CLICK HOLDINGS LTD/BVI-A EXTRA'))
def test_no_single_word_generic_or_unknown_decoration_alias(name):
    assert match(ARTICLE['title'],{'company_name':name}) is None


def test_ticker_collision_and_summary_bare_word_rules_unchanged():
    assert symbol_relevance_match('CAT',title='A cat reports earnings',metadata={}) is None
    assert symbol_relevance_match('CLIK',title='Other issuer',summary='clik earnings',metadata={}) is None
    assert symbol_relevance_match('CLIK',title='Other issuer',summary='$CLIK earnings',metadata={})==('ticker_token','summary')
    assert symbol_relevance_match('CLIK',title='CLIK reports earnings',metadata={})==('ticker_token','title')


def evidence(title=None):
    return NewsEvidence(symbol='CLIK',evidence_id=ARTICLE['article_identity'],headline=title or ARTICLE['title'],
        summary=ARTICLE['summary'],company_name=FACTS['company_name'],
        published_at=datetime.fromisoformat(ARTICLE['timestamp_provenance']['published_utc']),
        source_tier='operational_query',raw={'timestamp_provenance':ARTICLE['timestamp_provenance']})


def test_captured_article_remains_stale_at_actual_experiment_clock(monkeypatch):
    import time
    monkeypatch.setattr(time,'time',lambda:datetime.fromisoformat(FACTS['reference_utc']).timestamp())
    item=evidence()
    before=item.published_at
    assert match(ARTICLE['title'])==('company_name','title')
    decision=assess_issuer_event('CLIK',item)
    assert not decision['qualified']
    assert decision['reason']=='missing_future_or_stale_publication_time'
    assert decision['age_seconds']==pytest.approx(22671.890520)
    assert item.published_at==before and classify_headline(item.headline) is None


def test_labelled_counterfactual_current_time_does_not_broaden_classification(monkeypatch):
    import time
    # Counterfactual only: does not establish receipt9 availability or acceptance.
    monkeypatch.setattr(time,'time',lambda:datetime(2026,10,22,17,20,tzinfo=timezone.utc).timestamp())
    decision=assess_issuer_event('CLIK',evidence())
    assert not decision['qualified'] and decision['reason']=='no_catalyst_classification'
    assert decision['catalyst_type'] is None
    # Synthetic positive control exercises existing earnings ownership vocabulary.
    assert assess_issuer_event('CLIK',evidence('Click Holdings reports earnings beat'))['qualified']


@pytest.mark.parametrize('title',('OtherCo reports earnings; Click Holdings expands nursing',
    'Click Holdings tracks OtherCo earnings', 'Click Holdings and OtherCo report earnings',
    'Click Holdings Europe reports earnings'))
def test_other_company_event_ownership_is_not_inherited(monkeypatch,title):
    import time
    monkeypatch.setattr(time,'time',lambda:datetime(2026,10,22,17,20,tzinfo=timezone.utc).timestamp())
    assert not assess_issuer_event('CLIK',evidence(title))['qualified']


@pytest.mark.parametrize('company,title,expected',(
    ('AI Group Ltd', 'AI Group launches a routine website redesign', None),
    ('EV Holdings Ltd', 'EV Holdings expands nursing services', None),
    ('Contract Group Ltd', 'Contract Group reports record annual sales', None),
    ('AI Holdings Ltd/BVI-A', 'AI Holdings launches services', None),
    ('Contract Holdings Ltd/BVI-A', 'Contract Holdings reports record', None),
    ('AI Group Ltd', 'AI Group reports earnings beat', 'EARNINGS'),
    ('AI Holdings Ltd/BVI-A', 'AI Holdings launches AI platform', 'TECH_CATALYST'),
    ('Contract Group Ltd', 'Contract Group wins major contract', 'CONTRACT'),
))
def test_issuer_brand_cannot_supply_event_keyword(monkeypatch, company, title, expected):
    import time
    monkeypatch.setattr(time, 'time', lambda: datetime(2026,10,22,17,20,tzinfo=timezone.utc).timestamp())
    item = replace(evidence(title), company_name=company)
    decision = assess_issuer_event('CLIK', item)
    assert decision['qualified'] is (expected is not None)
    if expected is not None:
        assert decision['catalyst_type'] == expected
