from __future__ import annotations

from src.setup_engine.setup_families.ross_families import MomentumReclaimPattern
from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY, resolve_trigger_evaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.strategy_contracts import SessionContext


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def _base_inputs() -> PatternInputs:
    return PatternInputs(
        symbol="MR",
        timeframe="1m",
        candles=_candles(
            [
                (10.3, 10.34, 10.2, 10.22, 900),
                (10.22, 10.24, 10.08, 10.12, 880),
                (10.12, 10.18, 10.05, 10.08, 850),
                (10.08, 10.36, 10.06, 10.33, 1200),
            ]
        ),
        session_context=SessionContext.PRE,
        levels=LevelSet(premarket_high=10.5, premarket_low=9.8, hod=10.8, prior_close=9.9, key_levels={}),
        indicators=IndicatorSet(ema9=10.2, ema20=10.1, vwap=10.18),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=20.0, rvol=1.8),
    )


def test_momentum_reclaim_detected_contract_ids_and_trigger_type() -> None:
    result = MomentumReclaimPattern().evaluate(_base_inputs())
    assert result.detected is True
    assert result.setup_id == "P_MOMENTUM_RECLAIM"
    assert result.setup_family_id == "MOMENTUM_RECLAIM"
    assert result.trigger_type == "XL_MOMENTUM_RECLAIM"


def test_momentum_reclaim_trigger_requires_reclaim_cross() -> None:
    evaluator = resolve_trigger_evaluator("MOMENTUM_RECLAIM")
    assert evaluator is not None

    armed = evaluator(
        {"trigger_level": 10.2, "invalidation_level": 10.05},
        {"candles": _candles([(10.1, 10.18, 10.0, 10.15, 900), (10.15, 10.25, 10.1, 10.19, 920)])},
    )
    assert armed["trigger_type"] == "XL_MOMENTUM_RECLAIM"
    assert armed["trigger_state"] == "ARMED"
    assert armed["trigger_ready_now"] is False

    fired = evaluator(
        {"trigger_level": 10.2, "invalidation_level": 10.05},
        {"candles": _candles([(10.1, 10.20, 10.0, 10.19, 900), (10.18, 10.28, 10.15, 10.22, 920)])},
    )
    assert fired["trigger_state"] == "FIRED"
    assert fired["trigger_ready_now"] is True


def test_momentum_reclaim_trigger_contract_fields_present() -> None:
    evaluator = resolve_trigger_evaluator("MOMENTUM_RECLAIM")
    payload = evaluator(
        {"trigger_level": 10.2, "invalidation_level": 10.05},
        {"candles": _candles([(10.1, 10.20, 10.0, 10.19, 900), (10.18, 10.28, 10.15, 10.22, 920)])},
    )
    required = {
        "trigger_type",
        "trigger_state",
        "trigger_ready_now",
        "trigger_reason",
        "trigger_price_reference",
        "invalidation_price_reference",
    }
    assert required.issubset(payload.keys())


def test_trigger_registry_contains_momentum_reclaim() -> None:
    assert "MOMENTUM_RECLAIM" in TRIGGER_EVALUATOR_REGISTRY


def test_native_shakeout_owns_geometry_despite_unrelated_levels():
    from dataclasses import replace
    inputs=_base_inputs()
    for levels in (inputs.levels,replace(inputs.levels,premarket_low=1.,hod=99.,
            key_levels={'PULLBACK_HIGH':88.,'PULLBACK_LOW':.5}),
            replace(inputs.levels,premarket_low='unavailable',key_levels={'PULLBACK_HIGH':'not-ours','PULLBACK_LOW':'not-ours'})):
        result=MomentumReclaimPattern().evaluate(replace(inputs,levels=levels))
        assert result.detected
        assert result.trigger_level==10.2
        assert result.stop_level==result.invalidation_level==10.05
        assert result.setup_metadata['shakeout_low']==10.05
        assert result.target_suggestion=='Prior swing high'


def test_reclaim_alias_resolves_same_owner():
    assert resolve_trigger_evaluator('VWAP_RECLAIM_CONTINUATION') is resolve_trigger_evaluator('MOMENTUM_RECLAIM')


def test_reclaim_rejects_nonfinite_reference_and_malformed_structure():
    from dataclasses import replace
    inputs=_base_inputs()
    for value in (float('nan'),float('inf'),0.,True):
        result=MomentumReclaimPattern().evaluate(replace(inputs,indicators=replace(inputs.indicators,ema9=value)))
        assert not result.detected and result.rejection_reason=='invalid reclaim reference'
    bad=[*inputs.candles[:-1],replace(inputs.candles[-1],high=10.1)]
    assert not MomentumReclaimPattern().evaluate(replace(inputs,candles=bad)).detected


def test_registered_reclaim_strict_cross_and_own_invalidation_controls():
    from dataclasses import replace
    evaluator=resolve_trigger_evaluator('MOMENTUM_RECLAIM')
    bars=_candles([(10.1,10.2,10.06,10.19,900),(10.18,10.28,10.15,10.22,920)])
    payload={'trigger_level':10.2,'invalidation_level':10.05}
    assert evaluator(payload,{'candles':bars})['trigger_ready_now']
    for changed,expected in (
        ([bars[0],replace(bars[1],close=10.2)],'ARMED'),
        ([replace(bars[0],high=10.23,close=10.21),bars[1]],'ARMED'),
        ([bars[0],replace(bars[1],low=10.05)],'INVALIDATED'),
        ([bars[0],replace(bars[1],close=float('nan'))],'BLOCKED')):
        out=evaluator(payload,{'candles':changed})
        assert out['trigger_state']==expected and not out['trigger_ready_now']
    from datetime import datetime,timezone,timedelta
    now=datetime(2026,10,20,14,10,tzinfo=timezone.utc)
    stamped=[replace(bars[0],timestamp=now-timedelta(seconds=10)),replace(bars[1],timestamp=now+timedelta(seconds=1))]
    out=evaluator(dict(payload,execution_stream={'observed_at_utc':now.isoformat()}),{'candles':stamped})
    assert not out['trigger_ready_now'] and out['trigger_reason']=='momentum_reclaim_future_candle_data'


def test_readiness_filter_preserves_occurrence_risk_off_and_opposing_direction():
    from src.core.engines.decision_engine import DecisionEngine
    def candidate(identity,family,confidence,direction='LONG'):
        return dict(pattern_id=identity,setup_family_id=family,confidence=confidence,
            detected=True,direction=direction,trigger_level=10.2,invalidation_level=10.05)
    high=candidate('P_HOD_BREAK','HOD_BREAK',.99)
    low=candidate('P_FIRST_PULLBACK','FIRST_PULLBACK',.7)
    calls=[]
    def readiness(index,source):
        calls.append((index,source))
        return (index==1,'own_trigger_unready')
    engine=DecisionEngine()
    kwargs=dict(symbol='TEST',levels={},structure={},setups=[],pattern_results=[high,low],
        session_context='REGULAR',entry_contract_validator=lambda source:(True,'valid'),
        trigger_readiness_validator=readiness)
    out=engine.compute_decision(**kwargs)
    assert out['selected_pattern_id']=='P_FIRST_PULLBACK' and out['selected_candidate_index']==1
    assert calls==[(0,high),(1,low)]
    assert any(r['pattern_id']=='P_HOD_BREAK' and r['reason']=='own_trigger_unready' for r in out['rejected_candidates'])
    # Repeated IDs remain distinct occurrences and retain the ready one's index.
    same=candidate('P_HOD_BREAK','HOD_BREAK',.7)
    out=engine.compute_decision(**dict(kwargs,pattern_results=[high,same]))
    assert out['selected_pattern_id']=='P_HOD_BREAK' and out['selected_candidate_index']==1
    calls.clear()
    warning=candidate('P_PARABOLIC_EXHAUSTION','PARABOLIC_EXHAUSTION',.9)
    out=engine.compute_decision(**dict(kwargs,pattern_results=[high,low,warning]))
    assert out['selected_pattern_id'] is None and not calls
    opposing=candidate('P_FAILED_ORB_FAKEOUT','FAILED_ORB_FAKEOUT',.5,'SHORT')
    out=engine.compute_decision(**dict(kwargs,pattern_results=[high,low,opposing]))
    assert out['decision_reason']=='rejected_true_conflict_opposing_direction' and not calls
