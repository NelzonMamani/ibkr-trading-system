"""Synthetic offline routing/cache controls; no natural issuer-coverage proof."""
from dataclasses import replace
import socket
from types import SimpleNamespace

import pytest

from src.config.config_resolver import set_config_overrides
from src.news import batch_rss_adapter as adapter, news_fetcher as fetcher
from src.news import news_intelligence_service as service
from src.news.evidence_store import CanonicalNewsEvidenceStore
from src.news.issuer_rss_queries import operational_queries
from src.news.news_intelligence_contract import NewsCandidate, NewsRequest, RetrievalPolicy
from src.news.rss_lifecycle import RssFetchLifecycle
from src.news.source_groups import get_source_group_urls
from src.scanner import scanner_runner as ross

INVESTING = 'https://www.investing.com/rss/news.rss'
FORBES = 'https://www.forbes.com/business/feed2'
OLD_MARKETWATCH = 'https://www.marketwatch.com/rss/topstories'
OLD_SEEKING = 'https://seekingalpha.com/feed'
FAST = get_source_group_urls('FAST_TRADING')
EXTENDED = get_source_group_urls('PREP_EXTENDED')
OLD_FAST = tuple(OLD_MARKETWATCH if url == INVESTING else OLD_SEEKING if url == FORBES else url for url in FAST)
OLD_EXTENDED = EXTENDED[:2] + (FORBES,) + EXTENDED[2:8] + (INVESTING,) + EXTENDED[8:]
CANDIDATES = tuple(NewsCandidate(symbol, company_name=name) for symbol, name in (
    ('TESTA', 'Example Alpha Inc'), ('TESTB', 'Example Beta Ltd'),
    ('TESTC', 'Example Gamma Inc'), ('TESTD', 'Example Delta Ltd')))


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('No acquisition in offline substitution controls')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    set_config_overrides({'NEWS_ENABLED': True, 'ROSS_ISSUER_QUERY_ENABLED': True,
        'NEWS_LOOKBACK_HOURS': 6.0, 'NEWS_TOTAL_BUDGET_S': 8.0,
        'NEWS_REQUEST_TIMEOUT_S': 5, 'NEWS_EXTENDED_TIER_RESERVE_FRACTION': .35})
    yield
    set_config_overrides({})


def transport(monkeypatch, calls, available=True):
    def fake(url, timeout):
        calls.append((url, timeout))
        if not available:
            raise RuntimeError('synthetic unavailable')
        return SimpleNamespace(version='rss20', bozo=False, feed={'title': 'Synthetic empty feed'}, entries=[])
    monkeypatch.setattr(fetcher, '_fetch_feed', fake)
    monkeypatch.setattr(fetcher, 'feedparser', object())


def test_one_for_one_slots_single_group_ownership_and_unchanged_other_routes():
    assert len(FAST) == 8 and len(EXTENDED) == 11
    assert len(OLD_EXTENDED) == 13
    assert FAST[4] == INVESTING and FAST[6] == FORBES
    assert not set(FAST) & set(EXTENDED)
    assert len(set(FAST + EXTENDED)) == 19
    assert OLD_MARKETWATCH not in FAST + EXTENDED and OLD_SEEKING not in FAST + EXTENDED
    assert tuple(url for url in OLD_EXTENDED if url not in (INVESTING, FORBES)) == EXTENDED


@pytest.mark.parametrize('operational', [False, True])
@pytest.mark.parametrize('legacy_overlap', [False, True])
def test_shared_fetch_fallback_dedup_and_actual_combined_accounting(monkeypatch, operational, legacy_overlap):
    calls = []
    transport(monkeypatch, calls)
    if legacy_overlap:
        monkeypatch.setattr(adapter, 'get_source_group_urls', lambda group:
            EXTENDED + (INVESTING, FORBES) if group == 'PREP_EXTENDED' else get_source_group_urls(group))
    request = ross._ross_news_request() if operational else NewsRequest(lookback_seconds=21600)
    policy = ross._ross_retrieval_policy(refresh_mode='bounded_refresh', network_allowed=True,
        refresh_symbols=tuple(c.normalized_symbol for c in CANDIDATES)) if operational else RetrievalPolicy(
        source_groups=('FAST_TRADING', 'PREP_EXTENDED'), total_budget_seconds=8,
        request_timeout_seconds=5, extended_reserve_fraction=.35,
        metadata={'unresolved_symbols': tuple(c.normalized_symbol for c in CANDIDATES)})
    life = RssFetchLifecycle()
    try:
        result = adapter.BatchRssNewsIntelligenceProvider(lifecycle=life).get_news(CANDIDATES, request, policy)
        urls = [url for url, _ in calls]
        queries = [row['source_id'] for row in operational_queries(CANDIDATES)] if operational else []
        assert len(urls) == len(set(urls)) == 19 + len(queries)
        assert set(urls) == set(FAST + EXTENDED) | set(queries)
        assert urls.count(INVESTING) == urls.count(FORBES) == 1
        assert all(0 < timeout <= 5 for _, timeout in calls)
        diag = result.diagnostics.diagnostics
        assert diag['extended_fallback_requested'] is True
        assert diag['cross_tier_duplicate_source_urls_avoided'] == ((INVESTING, FORBES) if legacy_overlap else ())
        assert result.diagnostics.provider_available is True
        if operational:
            # Audit existing behavior honestly: 8 fixed + 4 queries + 11 fallback,
            # NOT authority to activate the documented 8-total candidate profile.
            assert len(queries) == 4 and len(FAST) + len(queries) == 12
            assert policy.total_budget_seconds == 8
            assert policy.tier_budgets == {'fast': 5.2, 'extended': 2.8}
    finally:
        assert life.wait_for_cleanup(2)['cleanup_complete']


@pytest.mark.parametrize('available', [False, True])
def test_membership_changes_invalidate_old_positive_and_negative_acquisition_without_erasing_receipt(monkeypatch, tmp_path, available):
    calls = []
    transport(monkeypatch, calls, available)
    original = get_source_group_urls
    def old_groups(group):
        return OLD_FAST if group == 'FAST_TRADING' else OLD_EXTENDED if group == 'PREP_EXTENDED' else original(group)
    monkeypatch.setattr(adapter, 'get_source_group_urls', old_groups)
    monkeypatch.setattr(service, 'get_source_group_urls', old_groups)
    life = RssFetchLifecycle()
    store = CanonicalNewsEvidenceStore(tmp_path / 'cache.json', prep_artifact_loader=lambda: {})
    canonical = service.CanonicalNewsIntelligenceService(evidence_store=store,
        retrieval_provider=adapter.BatchRssNewsIntelligenceProvider(lifecycle=life))
    request = ross._ross_news_request()
    policy = ross._ross_retrieval_policy(refresh_mode='bounded_refresh', network_allowed=True)
    try:
        first = canonical.get_news(CANDIDATES, request, policy)
        previous = first.summary_for_symbol('TESTA').diagnostics['last_retrieval']
        old_fingerprint = previous['acquisition_profile']['fingerprint']
        assert previous['provider_available'] is available
        before = store.cache_path.read_bytes()
        call_count = len(calls)
        monkeypatch.setattr(adapter, 'get_source_group_urls', original)
        monkeypatch.setattr(service, 'get_source_group_urls', original)
        cached = canonical.get_news(CANDIDATES, request, replace(policy,
            network_allowed=False, refresh_mode='cache_only', allow_cache_write=False))
        assert len(calls) == call_count and store.cache_path.read_bytes() == before
        assert cached.summary_for_symbol('TESTA').provider_status == 'coverage_unknown'
        assert cached.summary_for_symbol('TESTA').provider_available is None
        assert cached.summary_for_symbol('TESTA').diagnostics['last_retrieval'] == previous
        refreshed = canonical.get_news(CANDIDATES, request, policy)
        new = refreshed.summary_for_symbol('TESTA').diagnostics['last_retrieval']
        assert new['acquisition_profile']['fingerprint'] != old_fingerprint
        assert new['acquisition_profile']['retrieval']['source_urls_by_group']['FAST_TRADING'] == list(FAST)
        newly_called = [url for url, _ in calls[call_count:]]
        assert INVESTING in newly_called and FORBES in newly_called
        assert OLD_MARKETWATCH not in newly_called and OLD_SEEKING not in newly_called
        assert len(newly_called) == len(set(newly_called))
        count = len(calls)
        canonical.get_news(CANDIDATES, request, policy)
        assert len(calls) == count  # Current negative/empty coverage retains cadence.
    finally:
        assert life.wait_for_cleanup(2)['cleanup_complete']
