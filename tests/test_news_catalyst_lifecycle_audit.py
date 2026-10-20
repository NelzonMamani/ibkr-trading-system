"""Offline lifecycle facts: a fixture provider, private store, controlled UTC time."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import time

import pytest

from src.config.config_resolver import set_config_overrides
from src.news import evidence_store, news_intelligence_service
from src.news.evidence_store import CanonicalNewsEvidenceStore
from src.news.news_intelligence_contract import NewsBatchResult, NewsCandidate, NewsEvidence, RetrievalDiagnostics
from src.news.news_intelligence_service import CanonicalNewsIntelligenceService
from src.scanner import scanner_runner as ross

PUB = datetime(2026, 10, 20, 11, 0, 0, 500000, tzinfo=timezone.utc)  #07:00NY PRE
CANDIDATE = NewsCandidate('JPM', company_name='JPMorgan Chase & Co.', aliases=('JPMorgan Chase',))


@pytest.fixture
def lifecycle(monkeypatch, tmp_path):
    class Clock(datetime):
        current = PUB + timedelta(minutes=5)
        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(cls.current.timestamp(), tz=tz)
    for module in (evidence_store, news_intelligence_service, ross):
        monkeypatch.setattr(module, 'datetime', Clock)
    monkeypatch.setattr(time, 'time', lambda: Clock.current.timestamp())
    monkeypatch.setattr(ross, '_NEWS_CACHE', {})
    set_config_overrides({'NEWS_ENABLED':True, 'ROSS_ISSUER_QUERY_ENABLED':True,
                          'NEWS_CACHE_FILE':str(tmp_path/'news.json'), 'NEWS_MAX_ENTRIES_PER_SYMBOL':5,
                          'NEWS_REFRESH_SECONDS_RTH':120})
    def article(title='JPM reports earnings beat', published=PUB, **kwargs):
        published=Clock.fromtimestamp(published.timestamp(),timezone.utc)
        return NewsEvidence(symbol='JPM', evidence_id=title, headline=title,
            company_name=CANDIDATE.company_name, aliases=CANDIDATE.aliases,
            published_at=published, fetched_at=Clock.now(timezone.utc), age_seconds=(Clock.current-published).total_seconds(),
            stale=False, source_tier='operational_query', provider='rss_batch',
            url='https://fixture.invalid/'+title.replace(' ','_'), **kwargs)
    class Provider:
        provider_id = 'rss_batch'
        calls = 0
        failure = False
        articles = (article(),)
        def get_news(self, candidates, request, policy):
            self.calls += 1
            return NewsBatchResult(candidates=tuple(candidates), request=request,
                evidence_by_symbol={'JPM':() if self.failure else self.articles},
                diagnostics=RetrievalDiagnostics(retrieval_status='provider_error' if self.failure else 'available',
                    provider_status='provider_request_failure' if self.failure else 'available',
                    provider_available=not self.failure), completed_at=Clock.now(timezone.utc))
    provider = Provider()
    store = CanonicalNewsEvidenceStore(tmp_path/'news.json', prep_artifact_loader=lambda:{})
    service = CanonicalNewsIntelligenceService(evidence_store=store, retrieval_provider=provider)
    request = ross._ross_news_request()
    policy = ross._ross_retrieval_policy(refresh_mode='bounded_refresh', network_allowed=True)
    yield SimpleNamespace(clock=Clock, article=article, provider=provider, store=store,
                          service=service, request=request, policy=policy)
    set_config_overrides({})


def context(result):
    return ross._ross_news_contexts_from_news_intelligence_result(result)['JPM']


def test_same_batch_reassesses_exact_expiry_within_one_second(lifecycle):
    life=lifecycle
    result=life.service.get_news((CANDIDATE,),life.request,life.policy)
    life.clock.current=PUB+timedelta(seconds=21600)
    assert context(result)['ross_catalyst_valid'] is True  # Existing inclusive boundary.
    life.clock.current+=timedelta(seconds=.1)
    expired=context(result)
    assert expired['ross_catalyst_valid'] is False
    assert expired['qualification_decisions'][0]['reason']=='missing_future_or_stale_publication_time'
    assert result.evidence_for_symbol('JPM')[0].published_at==PUB
    assert life.provider.calls==1


def test_same_batch_reassesses_future_to_current_within_one_second(lifecycle):
    life=lifecycle
    article=life.article()
    result=NewsBatchResult(candidates=(CANDIDATE,),request=life.request,
        evidence_by_symbol={'JPM':(article,)},diagnostics=RetrievalDiagnostics(provider_available=True))
    life.clock.current=PUB-timedelta(seconds=.1)
    assert context(result)['ross_catalyst_valid'] is False
    life.clock.current=PUB
    assert context(result)['ross_catalyst_valid'] is True
    assert life.provider.calls==0


def test_cache_reuses_context_without_crossing_publication_boundary(lifecycle):
    life=lifecycle
    result=life.service.get_news((CANDIDATE,),life.request,life.policy)
    initial=context(result)
    life.clock.current+=timedelta(seconds=.1)
    assert context(result) is initial


@pytest.mark.parametrize('compatible', [False,True], ids=['legacy-fact-cache','current-ross-acquisition-profile'])
def test_premarket_publication_retained_into_rth_without_new_headline(lifecycle, compatible):
    life=lifecycle
    policy=life.policy if compatible else replace(life.policy,metadata={},source_groups=('FAST_TRADING',),refresh_interval_seconds=None)
    cold=life.service.get_news((CANDIDATE,),life.request,policy)
    assert context(cold)['ross_catalyst_valid']
    life.clock.current=PUB+timedelta(hours=2,minutes=30)  #09:30NY RTH: same article still within6h.
    restarted=CanonicalNewsIntelligenceService(evidence_store=life.store,retrieval_provider=life.provider)
    warm=restarted.get_news((CANDIDATE,),life.request,replace(policy,network_allowed=False,refresh_mode='cache_only'))
    article=warm.evidence_for_symbol('JPM')[0]
    assert article.published_at==PUB and article.age_seconds==9000
    assert life.provider.calls==1
    ctx=context(warm)
    assert ctx['ross_catalyst_valid'] is True
    if compatible:
        assert warm.summary_for_symbol('JPM').provider_status=='coverage_unknown'
        assert ctx['qualification_decisions'][0]['qualified'] is True
        # A successful empty refresh restores coverage without renewing event validity.
        life.provider.articles=()
        refreshed=restarted.get_news((CANDIDATE,),life.request,policy)
        assert context(refreshed)['ross_catalyst_valid']
        assert refreshed.evidence_for_symbol('JPM')[0].published_at==PUB


def test_reported_refresh_failure_preserves_verified_event_and_degraded_health(lifecycle):
    life=lifecycle
    old=life.service.get_news((CANDIDATE,),life.request,life.policy).evidence_for_symbol('JPM')[0]
    life.clock.current+=timedelta(seconds=121)
    life.provider.failure=True
    failed=life.service.get_news((CANDIDATE,),life.request,life.policy)
    retained=failed.evidence_for_symbol('JPM')[0]
    assert retained.evidence_id==old.evidence_id and retained.published_at==old.published_at
    ctx=context(failed)
    assert ctx['qualification_decisions'][0]['qualified']
    assert ctx['ross_catalyst_valid'] and not ctx['news_available']
    assert ctx['acquisition_health']=='degraded'
    assert ctx['qualification_reason']=='verified_issuer_event_valid'


def test_new_offering_vetoes_retained_positive_and_expiry_policy_is_not_invented(lifecycle):
    life=lifecycle
    life.service.get_news((CANDIDATE,),life.request,life.policy)
    offering=life.article('JPM announces registered direct offering',PUB-timedelta(hours=5))
    life.provider.articles=(offering,)
    life.clock.current+=timedelta(seconds=121)
    both=life.service.get_news((CANDIDATE,),life.request,life.policy)
    ctx=context(both)
    assert ctx['dilution_flag'] and not ctx['ross_catalyst_valid']
    life.clock.current=PUB+timedelta(hours=2)
    # Final consumer currently vetoes any retained offering, even olderthan6h.
    ctx=context(life.service.get_news((CANDIDATE,),life.request,replace(life.policy,network_allowed=False,refresh_mode='cache_only')))
    assert ctx['dilution_flag']  # Audit fact, not approval of an expiry policy.


def test_heat_and_velocity_do_not_change_issuer_qualification_or_scanner_rank(lifecycle):
    life=lifecycle
    positive=life.article()
    generic=life.article('JPM market roundup')
    base=dict(pct_change=15.,rvol=5.,dollar_volume=1_000_000)
    score=ross._score_context(base)
    for metric in (0,100):
        for article,expected in ((positive,True),(generic,False)):
            item=replace(article,heat_score=metric,hotness_score=metric,source_reliability_score=metric,
                         source_credibility_score=metric,velocity_5m=metric,velocity_10m=metric)
            result=NewsBatchResult(candidates=(CANDIDATE,),request=life.request,evidence_by_symbol={'JPM':(item,)},
                                  diagnostics=RetrievalDiagnostics(provider_available=True))
            assert context(result)['ross_catalyst_valid'] is expected
        assert ross._score_context(dict(base,news_heat_score=metric,news_velocity_10m=metric,
                                        news_source_reliability_score=metric,novelty=metric))==score


def test_standalone_uses_same_store_without_broker_or_scanner(lifecycle):
    from src.news.standalone_lookup import LookupSettings, lookup_news
    life=lifecycle
    life.service.get_news((CANDIDATE,),life.request,life.policy)
    report=lookup_news((CANDIDATE,),LookupSettings(cache_mode='only',cache_file=life.store.cache_path),service=life.service)
    assert report['symbols']['JPM']['articles']
    assert report['research_results_are_trading_catalysts'] is False
    assert life.provider.calls==1  # No retrieval, broker or scanner needed for this consumer.


def test_cached_measurements_are_snapshot_values_but_v9_ross_recomputes_velocity(lifecycle):
    from src.news.evidence_store import enrich_evidence_metrics
    life=lifecycle
    enriched=enrich_evidence_metrics((life.article(),),now_ts=life.clock.current.timestamp())
    assert enriched[0].velocity_10m==1
    life.store.write({'JPM':enriched},life.request)
    life.clock.current+=timedelta(hours=2)
    result=life.service.get_news((CANDIDATE,),life.request,replace(life.policy,metadata={},network_allowed=False,refresh_mode='cache_only'))
    assert result.evidence_for_symbol('JPM')[0].age_seconds>7200
    assert result.summary_for_symbol('JPM').velocity_10m==1  # Preserved snapshot metric, not a live counter.
    assert context(result)['velocity_10m']==0  # Ross v9 derives accepted presentation cohort ages.


def test_conflicting_earnings_reports_have_no_automatic_revocation_policy(lifecycle):
    life=lifecycle
    life.service.get_news((CANDIDATE,),life.request,life.policy)
    life.clock.current+=timedelta(seconds=121)
    life.provider.articles=(life.article('JPM reports earnings miss',life.clock.current),)
    result=life.service.get_news((CANDIDATE,),life.request,life.policy)
    assert len(result.evidence_for_symbol('JPM'))==2
    ctx=context(result)
    assert ctx['ross_catalyst_valid'] and not ctx['dilution_flag']
    assert len(ctx['qualifying_evidence_ids'])==2  # Real-event existence, not bullish sentiment endorsement.
