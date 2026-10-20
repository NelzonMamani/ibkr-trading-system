"""Explicit canonical event facts for routing tests, never a cached CONFIRMED flag."""
from datetime import datetime, timezone
from src.news.news_intelligence_contract import NewsCandidate, NewsEvidence
from src.strategies.ross_momentum.policy.catalyst_lifecycle import evidence_handoff


def canonical_catalyst_fixture(symbol, *, published=None):
    publication=published or datetime.now(timezone.utc)
    evidence=NewsEvidence(symbol=symbol,evidence_id=f'fixture:{symbol}:earnings',
        headline=f'{symbol} reports earnings beat',published_at=publication,
        source_tier='operational_query',provider='rss_batch',url=f'https://fixture.invalid/{symbol}')
    return evidence_handoff(symbol,(evidence,),NewsCandidate(symbol),
        acquisition_health='healthy',acquisition_reason='controlled_fixture_acquisition')
