"""CONDITIONAL SYNTHETIC proof only: no production original-publisher verifier
exists. Feed facts, verification witness, market quotes and shortlist are synthetic.
"""
from datetime import timedelta
from email.utils import format_datetime
import pytest
from src.strategies.ross_momentum.policy import catalyst_policy as cp
from src.strategies.ross_momentum.policy.catalyst_lifecycle import revalidate_handoff
from test_news_catalyst_lifecycle_audit import lifecycle
from test_watchlist_between_scan_reassessment import reassessment, publish


def listing(c):
    publication=c.life.clock.current-timedelta(minutes=1)
    return c.life.article('JPM regains compliance with Nasdaq listing requirements',publication,
        raw={'timestamp_provenance':{'selected_time_basis':'published',
             'published_original':publication.isoformat(),
             'published_utc':publication.isoformat()}})


def test_actual_cached_reconsideration_requires_provenance_then_all_market_gates(reassessment,monkeypatch):
    c=reassessment;item=listing(c);publish(c,(item,))
    original=c.life.store.cache_path.read_bytes()
    assert c.run()==[] and c.calls==[]  # Production fail-closed provenance.
    # Explicit hypothetical verification witness, NOT publisher/Google/source-name
    # inference. It exists only in this offline control, never configuration/cache.
    monkeypatch.setattr(cp,'_verified_original_publisher',lambda ev:ev.evidence_id==item.evidence_id)
    c.life.clock.current+=timedelta(seconds=1)
    selected=c.run()
    assert [r.symbol for r in selected]==['JPM'] and c.calls==['JPM']
    handoff=selected[0].catalyst_evidence
    assert revalidate_handoff('JPM',handoff,store=c.life.store)['qualified']
    assert c.life.provider.calls==1 and c.life.store.cache_path.read_bytes()==original
    c.life.clock.current=item.published_at+timedelta(seconds=21600,microseconds=1)
    assert not revalidate_handoff('JPM',handoff,store=c.life.store)['qualified']
    assert c.run()==[] and c.calls==['JPM'] and c.life.provider.calls==1


@pytest.mark.parametrize('fault',['stale_quote','missing_time','wrong_symbol','spread','halt','float','rvol'])
def test_conditional_listing_eligibility_cannot_bypass_market_gates(reassessment,monkeypatch,fault):
    c=reassessment;item=listing(c);publish(c,(item,))
    monkeypatch.setattr(cp,'_verified_original_publisher',lambda ev:ev.evidence_id==item.evidence_id)
    original=c.provider.refresh_quote
    def refresh(symbol):
        quote=original(symbol)
        if fault=='stale_quote':quote.timestamp_utc=c.row['quote_timestamp_utc']
        elif fault=='missing_time':quote.timestamp_source='RECEIVED'
        elif fault=='wrong_symbol':quote.symbol='OTHER'
        return quote
    c.provider.refresh_quote=refresh
    if fault=='spread':c.row.update(bid=4.,ask=8.,spread_pct=100.)
    elif fault=='halt':c.row['halted']=True
    elif fault=='float':c.row['float_shares']=500000000
    elif fault=='rvol':c.row.update(rvol=0.,rvol_phase=0.,rvol_discovery=0.)
    assert c.run()==[] and c.calls==['JPM'] and c.life.provider.calls==1


def test_later_financing_veto_cancels_conditional_listing_qualification(reassessment,monkeypatch):
    c=reassessment;item=listing(c);publish(c,(item,))
    monkeypatch.setattr(cp,'_verified_original_publisher',lambda ev:ev.evidence_id==item.evidence_id)
    selected=c.run();assert selected
    c.life.clock.current+=timedelta(seconds=121)
    publish(c,(c.life.article('JPM announces registered direct offering'),))
    assert c.run()==[] and c.calls==['JPM']
    assert not revalidate_handoff('JPM',selected[0].catalyst_evidence,store=c.life.store)['qualified']
