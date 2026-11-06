"""Existing common intent owner; no defaults, peer lookup or risk overrides."""
from copy import deepcopy
from math import isnan
from types import SimpleNamespace as NS

import pytest

from src.models.data_models import TradeIntent
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1
from src.strategies.ross_momentum.ross_momentum_risk_overlay import RossMomentumRiskOverlay, RiskContext
from test_key_level_break_production_handoff import forbid_io, _reset_config


def apply_gap(value,*,existing=None,composed=False):
    intent=TradeIntent(symbol='SYNTH',direction='LONG',strategy_name='RossMomentumStrategyV1',
        confidence=.8,rationale='synthetic common owner control',trader_type='MOMENTUM',
        stop_loss_price=10.2897,invalidation_level=10.3,gap_percent=existing,rvol=10.,float_millions=8.)
    intent.entry_price=10.3
    intent.relationship_context={'relationship_id':'synthetic-relationship'} if composed else {}
    intent.setup_metadata={'canonical_result_index':2,'marker':['selected occurrence']}
    before=deepcopy(intent.setup_metadata)
    strategy=RossMomentumStrategyV1.__new__(RossMomentumStrategyV1)
    out=strategy._apply_intent_contract_defaults(intent,
        NS(gap_pct=value,pct_change=12.,last_price=99.,float_millions=8.,rvol=10.),
        timestamp_utc='2026-10-20T13:35:41+00:00')
    assert out is intent and out.setup_metadata==before
    assert (out.entry_price,out.stop_loss_price,out.invalidation_level)==(10.3,10.2897,10.3)
    return out


@pytest.mark.parametrize('composed',[False,True])
def test_selected_summary_gap_reaches_common_owner(composed):
    intent=apply_gap(12.,composed=composed)
    assert intent.gap_percent==12.
    assert RossMomentumRiskOverlay().evaluate(intent,RiskContext(current_tick=0)) is None


@pytest.mark.parametrize('value',[None,'bad',float('nan'),float('inf'),float('-inf')])
def test_invalid_gap_never_borrows_valid_pct_change_or_prices(value):
    intent=apply_gap(value)
    decision=RossMomentumRiskOverlay().evaluate(intent,RiskContext(current_tick=0))
    assert decision is not None and not decision.allowed and decision.execution_blocked
    assert decision.max_position_size==0 and decision.reason_code=='ROSS_BLOCK_GAP_OUT_OF_RANGE'


@pytest.mark.parametrize('value,allowed',[(3.999999,False),(4.,True),(20.,True),(20.000001,False)])
def test_existing_overlay_inclusive_gap_boundaries(value,allowed):
    intent=apply_gap(value)
    assert intent.gap_percent==value
    result=RossMomentumRiskOverlay().evaluate(intent,RiskContext(current_tick=0))
    assert (result is None) is allowed
    if result:assert not result.allowed and result.reason_code=='ROSS_BLOCK_GAP_OUT_OF_RANGE'


@pytest.mark.parametrize('value',[0.,3.,25.,float('nan'),float('inf'),'bad'])
@pytest.mark.parametrize('composed',[False,True])
def test_explicit_intent_value_cannot_be_repaired_by_valid_context(value,composed):
    intent=apply_gap(12.,existing=value,composed=composed)
    if isinstance(value,float) and isnan(value):assert isnan(intent.gap_percent)
    else:assert intent.gap_percent==value


from datetime import timedelta
from test_joined_core_pmh_paper_assessment import (
    paper_pmh, reassessment, lifecycle, no_external_activity, AdmissionBoundary,
)
from src.ibkr.mutation_audit import snapshot as mutations


@pytest.mark.parametrize('gap_fact',[None,'bad',float('nan'),float('inf'),float('-inf'),25.])
def test_native_pmh_bad_gap_cannot_borrow_valid_peer(reassessment,monkeypatch,tmp_path,capsys,
        no_external_activity,gap_fact):
    h=paper_pmh(reassessment,monkeypatch,tmp_path,'complete_empty',peer=True)
    # Explicit NEGATIVE fault at selected summary boundary. Upstream acquisition
    # adapters may legitimately normalize scanner metrics; leave them unchanged.
    # Delegate the real builder, then invalidate ONLY JPM's gap, never a success.
    from dataclasses import replace
    from src.strategies import ross_momentum_strategy_v1 as v1
    build=v1.build_input_snapshot_summary
    def invalidate_selected_gap(**kw):
        summary=build(**kw)
        row=kw['row'];symbol=row.get('symbol') if isinstance(row,dict) else row.symbol
        return replace(summary,gap_pct=gap_fact) if symbol=='JPM' else summary
    monkeypatch.setattr(v1,'build_input_snapshot_summary',invalidate_selected_gap)
    engine=h.core.execution_engine
    try:
        assert h.core.run_once();capsys.readouterr()
        h.life.clock.current+=timedelta(seconds=11)
        assert h.core.run_once();capsys.readouterr()
        raw=[i for b in h.batches for i in b]
        assert len(raw)==1 and raw[0].symbol=='JPM' and raw[0].setup_family_id=='PREMARKET_HIGH_BREAK'
        formed={i['symbol']:(c,i) for c,i in h.defaults}
        assert set(formed)=={'JPM','PEER'}
        assert formed['PEER'][0]['gap_pct']==formed['PEER'][1]['gap_percent']==12.
        assert {i.symbol for i in h.inputs}=={'JPM','PEER'}
        assert len(h.evaluated)==len(h.artifacts)==1
        intent,received,blocked=h.evaluated[0]
        assert intent is raw[0] and blocked.decision_id==h.artifacts[0][0].decision_id
        assert blocked.reason_code=='ROSS_BLOCK_GAP_OUT_OF_RANGE' and blocked.execution_blocked
        assert not blocked.allowed and blocked.max_position_size==0
        if isinstance(gap_fact,float) and isnan(gap_fact):assert isnan(received['gap_percent'])
        elif gap_fact=='bad' or gap_fact is None:assert received['gap_percent'] is None
        else:assert received['gap_percent']==gap_fact
        # One-winner selection is preserved: no fallback after JPM risk rejection.
        assert h.execution_calls==h.boundaries==h.reserves==h.execution_results==[]
        assert intent.entry_price==intent.invalidation_level==10.3
        assert intent.stop_loss_price==10.3-max(.01,10.3*.001) and intent.take_profit_price is None
        assert engine.capital_authority.capital_scope is None
    finally:cleanup_unsent(h,no_external_activity)


def cleanup_unsent(h,attempts):
    engine=h.core.execution_engine
    for authority in (engine.capital_authority,engine.strategy_allocation_authority):
        for reservation in list(authority.active_reservations.values()):
            authority.release_reservation(decision_id=reservation.decision_id,reason='OFFLINE_UNSENT_FIXTURE_CLEANUP')
        assert not authority.active_reservations
    assert engine.capital_authority.total_reserved_capital==0
    assert attempts==[] and mutations()==dict(place=0,modify=0,cancel=0)


def test_valid_peer_uses_its_own_gap_through_actual_paper(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h=paper_pmh(reassessment,monkeypatch,tmp_path,'complete_empty',peer=True,news_fault='missing')
    try:
        assert h.core.run_once();capsys.readouterr()
        h.life.clock.current+=timedelta(seconds=11)
        with pytest.raises(AdmissionBoundary):h.core.run_once()
        capsys.readouterr()
        assert len(h.evaluated)==1
        intent,received,decision=h.evaluated[0]
        assert intent.symbol=='PEER' and intent.gap_percent==received['gap_percent']==12.
        assert intent.setup_family_id=='PREMARKET_HIGH_BREAK'
        assert decision.allowed and not decision.execution_blocked and decision.max_position_size==1
        assert len(h.boundaries)==1 and h.boundaries[0].symbol=='PEER'
        assert h.reserves==['allocation','capital']
    finally:cleanup_unsent(h,no_external_activity)
