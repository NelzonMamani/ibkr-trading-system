from __future__ import annotations

from quote_fixtures import current_broker_quote

from src.core.engines.decision_engine import DecisionEngine
from src.core.pipeline_audit import PipelineAudit, TerminalOutcome
from src.models.data_models import TradeIntent
from src.risk.risk_engine import RiskEngine
from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.triggers.trigger_hod_break import evaluate_hod_break_trigger
from src.strategies.common.triggers.trigger_parabolic_exhaustion import evaluate_parabolic_exhaustion_trigger
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def test_hod_break_pipeline_certifies_trigger_to_intent() -> None:
    candles = _candles([(10.48, 10.51, 10.46, 10.51, 1000), (10.51, 10.56, 10.50, 10.531, 1700)])
    trigger = evaluate_hod_break_trigger(
        {"setup_family_id": "HOD_BREAK", "trigger_level": 10.52, "invalidation_level": 10.40, "stop_level": 10.40},
        {"candles": candles, "rvol": 1.3},
    )
    assert trigger["trigger_state"] == "FIRED"

    decision = DecisionEngine().compute_decision(
        symbol="HODX",
        levels={},
        structure={"trend": "UP"},
        setups=[{"setup_family": "HOD_BREAK"}],
        pattern_results=[
            {
                "setup_id": "P_HOD_BREAK",
                "setup_family_id": "HOD_BREAK",
                "pattern_name": "High of Day Break",
                "detected": True,
                "confidence": 0.8,
                "trigger_level": 10.52,
                "invalidation_level": 10.40,
                "direction": "LONG",
            }
        ],
        session_context="RTH",
    )
    assert decision["selected_pattern_id"] == "P_HOD_BREAK"
    assert trigger["trigger_ready_now"] is True


def test_parabolic_exhaustion_pipeline_stays_non_entry_and_risk_blocked() -> None:
    decision = DecisionEngine().compute_decision(
        symbol="PXS",
        levels={},
        structure={"trend": "UP"},
        setups=[{"setup_family": "PARABOLIC_EXHAUSTION"}],
        pattern_results=[
            {
                "setup_id": "P_PARABOLIC_EXHAUSTION",
                "setup_family_id": "PARABOLIC_EXHAUSTION",
                "pattern_name": "Parabolic Exhaustion",
                "detected": True,
                "confidence": 0.9,
                "direction": "LONG",
                "non_entry_signal": True,
                "signal_class": "RISK_OFF",
                "trigger_mode": "EXIT_SIGNAL",
                "risk_flags": ["EXIT_SIGNAL", "RISK_OFF"],
            }
        ],
        session_context="RTH",
    )
    assert decision["selected_pattern_id"] is None

    intent = TradeIntent(quote_evidence={'selection': current_broker_quote(), 'snapshot': None},
        symbol="PXS",
        direction="LONG",
        strategy_name="RossMomentumStrategyV1",
        confidence=0.8,
        rationale="suppressed",
        trader_type="MOMENTUM",
        decision_id="d1",
        setup_family_id="PARABOLIC_EXHAUSTION",
    )
    risk = RiskEngine().evaluate_trade_intent(intent)
    assert risk.execution_blocked is True
    assert risk.reason_code == "PARABOLIC_EXHAUSTION_SUPPRESSION"

    trigger = evaluate_parabolic_exhaustion_trigger(
        {"trigger_level": 11.5},
        {"candles": _candles([(10.9, 11.4, 10.8, 11.3, 1500), (11.3, 11.55, 11.1, 11.18, 2300)])},
    )
    assert trigger["trigger_state"] == "FIRED"


def test_interaction_hod_break_suppressed_when_parabolic_exhaustion_present() -> None:
    decision = DecisionEngine().compute_decision(
        symbol="MIXD",
        levels={},
        structure={"trend": "UP"},
        setups=[{"setup_family": "HOD_BREAK"}, {"setup_family": "PARABOLIC_EXHAUSTION"}],
        pattern_results=[
            PatternResult(
                setup_id="P_HOD_BREAK",
                pattern_name="High of Day Break",
                pattern_family=PatternFamily.BREAKOUT,
                detected=True,
                direction=Direction.LONG,
                confidence=0.8,
                setup_quality_tags=[],
                setup_family_id="HOD_BREAK",
                trigger_level=10.52,
                invalidation_level=10.4,
            ),
            PatternResult(
                setup_id="P_PARABOLIC_EXHAUSTION",
                pattern_name="Parabolic Exhaustion",
                pattern_family=PatternFamily.EXHAUSTION,
                detected=True,
                direction=Direction.LONG,
                confidence=0.9,
                setup_quality_tags=[],
                setup_family_id="PARABOLIC_EXHAUSTION",
                non_entry_signal=True,
                signal_class="RISK_OFF",
                trigger_mode="EXIT_SIGNAL",
                risk_flags=["EXIT_SIGNAL", "RISK_OFF"],
            ),
        ],
        session_context="RTH",
    )
    assert decision["selected_pattern_id"] is None

    risk = RiskEngine().evaluate_trade_intent(
        TradeIntent(quote_evidence={'selection': current_broker_quote(), 'snapshot': None},
            symbol="MIXD",
            direction="LONG",
            strategy_name="RossMomentumStrategyV1",
            confidence=0.8,
            rationale="blocked by risk-off suppression",
            trader_type="MOMENTUM",
            decision_id="d2",
            setup_family_id="PARABOLIC_EXHAUSTION",
        )
    )
    assert risk.allowed is False
    assert risk.execution_blocked is True


def test_terminal_outcome_exists_for_every_symbol() -> None:
    audit = PipelineAudit("cert-cycle")
    audit.mark_kept(["HODX", "PXS"])
    audit.record("HODX", TerminalOutcome.TRADE_INTENT_CREATED, "TRIGGER_FIRED_INTENT_CREATED", "intent")
    audit.record("PXS", TerminalOutcome.RISK_BLOCKED, "BLOCKED_BY_RISK", "risk")
    assert audit.contract_violations() == []


def _measured_range_case():
    from datetime import datetime, timedelta, timezone
    from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs, IndicatorSet, LevelSet, LiquidityContext
    from src.strategies.strategy_contracts import SessionContext
    start = datetime(2026, 10, 20, 13, 53, tzinfo=timezone.utc)
    rows = [(10.25,10.44,10.04,10.35,1200),(10.35,10.43,10.05,10.25,1100),
        (10.25,10.44,10.04,10.36,1000),(10.36,10.43,10.05,10.26,900),
        (10.26,10.44,10.04,10.35,1000),(10.35,10.43,10.05,10.4,1100),
        (10.4,10.5,10.39,10.48,1600)]
    source = [Candle(*row, timestamp=start+timedelta(minutes=n)) for n,row in enumerate(rows)]
    clock = source[-1].timestamp+timedelta(seconds=30)
    inputs = PatternInputs(symbol='BOX', timeframe='1m', primary_timeframe='1m',
        candles=source, observed_at_utc=clock, session_context=SessionContext.REGULAR,
        levels=LevelSet(), indicators=IndicatorSet(), liquidity_context=LiquidityContext(spread=.02,rvol=2),
        timeframe_provenance={'1m':'PRESENT','10s':'PRESENT'})
    from dataclasses import replace
    execution = [replace(c, volume=c.volume/6, timestamp=c.timestamp+timedelta(seconds=n))
        for c in source[:-1] for n in range(0,60,10)]
    execution += [Candle(*row,timestamp=source[-1].timestamp+timedelta(seconds=10*n))
        for n,row in enumerate([(10.4,10.42,10.39,10.4,200),
            (10.4,10.44,10.4,10.42,200),(10.42,10.5,10.41,10.48,1200)])]
    return inputs, execution


def test_native_range_uses_completed_measured_rectangle_not_generic_levels():
    from dataclasses import replace
    from src.setup_engine.setup_families.pullbacks import RangeBreakoutPattern
    from src.strategies.ross_momentum.decision_policy import validate_entry_contract
    inputs,_ = _measured_range_case()
    result = RangeBreakoutPattern().evaluate(inputs)
    assert result.detected and result.confidence == .58
    assert (result.trigger_level,result.stop_level,result.invalidation_level)==(10.44,10.04,10.04)
    assert result.target_suggestion=='Continuation above the measured rectangle range high.'
    assert result.setup_metadata['origin_timestamp']==inputs.candles[0].timestamp
    assert result.setup_metadata['structure_completed_timestamp']==inputs.candles[-2].timestamp
    assert validate_entry_contract(result)==(True,'ok')
    assert validate_entry_contract(replace(result,target_suggestion=None))==(False,'missing_target')
    # The developing tail supplies neither upper nor lower anchor.
    changed=list(inputs.candles)
    changed[-1]=replace(changed[-1],high=10.8,close=10.7)
    again=RangeBreakoutPattern().evaluate(replace(inputs,candles=changed))
    assert (again.trigger_level,again.stop_level)==(10.44,10.04)


def test_measured_range_registered_strict_confirmation_and_same_stream_volume():
    from dataclasses import replace
    from src.setup_engine.setup_families.pullbacks import RangeBreakoutPattern
    from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY
    from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1
    inputs,execution = _measured_range_case()
    native=RangeBreakoutPattern().evaluate(inputs)
    setup=RossMomentumStrategyV1()._canonical_pattern_trigger_candidates([native],symbol='BOX',existing_triggers=[])[0]
    setup['execution_stream']={'execution_trigger_timeframe':'10s','stream_provenance':'PRESENT',
        'policy_action':'ALLOW','observed_at_utc':inputs.observed_at_utc.isoformat()}
    evaluate=TRIGGER_EVALUATOR_REGISTRY['RANGE_BREAK']
    ready=evaluate(setup,{'candles':execution})
    assert ready['trigger_ready_now'] and ready['trigger_type']=='BREAKOUT_HIGH'
    assert (ready['trigger_price_reference'],ready['invalidation_price_reference'])==(10.44,10.04)
    assert ready['execution_stream']['volume_baseline_candle_count']==36
    from math import nextafter, inf
    volume=ready['execution_stream']['volume_baseline']
    assert not evaluate(setup,{'candles':execution[:-1]+[replace(execution[-1],volume=volume)]})['trigger_ready_now']
    assert evaluate(setup,{'candles':execution[:-1]+[replace(execution[-1],volume=nextafter(volume,inf),
        close=nextafter(10.44,inf))]})['trigger_ready_now']
    for last in [replace(execution[-1],close=10.44),replace(execution[-1],volume=1),
            replace(execution[-1],low=10.04)]:
        assert not evaluate(setup,{'candles':execution[:-1]+[last]})['trigger_ready_now']
    # Source metadata cannot substitute for a missing real execution stream.
    assert not evaluate({k:v for k,v in setup.items() if k!='execution_stream'},
        {'candles':execution})['trigger_ready_now']
    assert not evaluate({**setup,'trigger_level':10.45},{'candles':execution})['trigger_ready_now']
    assert not evaluate({**setup,'setup_family_id':'FIRST_PULLBACK'},{'candles':execution})['trigger_ready_now']



def test_native_range_rejects_unmeasured_incomplete_and_stale_geometry():
    from dataclasses import replace
    from datetime import timedelta
    from src.setup_engine.setup_families.pullbacks import RangeBreakoutPattern
    inputs,_ = _measured_range_case()
    cases = [replace(inputs,observed_at_utc=None),
        replace(inputs,candles=inputs.candles[1:]),
        replace(inputs,observed_at_utc=inputs.observed_at_utc+timedelta(minutes=10))]
    for field,value in [('low',float('nan')),('high',10.2),('timestamp',inputs.observed_at_utc+timedelta(seconds=1))]:
        bars=list(inputs.candles);bars[2]=replace(bars[2],**{field:value})
        cases.append(replace(inputs,candles=bars))
    bars=list(inputs.candles);bars[2]=replace(bars[2],timestamp=bars[2].timestamp+timedelta(seconds=10))
    cases.append(replace(inputs,candles=bars))
    # Rising lows are triangle-like, not this policy's two flat boundaries.
    bars=list(inputs.candles)
    bars[3]=replace(bars[3],low=10.2)
    cases.append(replace(inputs,candles=bars))
    for bad in cases:
        result=RangeBreakoutPattern().evaluate(bad)
        assert not result.detected and result.target_suggestion is None


def test_measured_range_boundary_tolerances_are_inclusive_and_bounded():
    from dataclasses import replace
    from src.setup_engine.setup_families.pullbacks import RangeBreakoutPattern
    inputs,_=_measured_range_case()
    for field,at,outside in [('high',10.40,10.3999),('low',10.08,10.0801)]:
        bars=list(inputs.candles);bars[3]=replace(bars[3],**{field:at})
        assert RangeBreakoutPattern().evaluate(replace(inputs,candles=bars)).detected
        bars[3]=replace(bars[3],**{field:outside})
        assert not RangeBreakoutPattern().evaluate(replace(inputs,candles=bars)).detected


def test_measured_range_occurrence_cannot_replay_or_outlive_confirmation_window():
    from dataclasses import replace
    from datetime import timedelta
    from src.setup_engine.setup_families.pullbacks import RangeBreakoutPattern
    from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY
    from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1
    inputs,execution=_measured_range_case()
    own=RangeBreakoutPattern().evaluate(inputs)
    setup=RossMomentumStrategyV1()._canonical_pattern_trigger_candidates([own],symbol='BOX',existing_triggers=[])[0]
    setup['execution_stream']={'execution_trigger_timeframe':'10s','stream_provenance':'PRESENT',
        'policy_action':'ALLOW','observed_at_utc':inputs.observed_at_utc}
    evaluate=TRIGGER_EVALUATOR_REGISTRY['RANGE_BREAK']
    metadata=dict(setup['setup_metadata'])
    extended=execution+[
        replace(execution[-1],open=10.4,high=10.43,low=10.38,close=10.4,volume=200,
            timestamp=execution[-1].timestamp+timedelta(seconds=10)),
        replace(execution[-1],open=10.4,high=10.5,low=10.4,close=10.49,volume=1500,
            timestamp=execution[-1].timestamp+timedelta(seconds=20))]
    setup['execution_stream']['observed_at_utc']=inputs.observed_at_utc+timedelta(seconds=20)
    replay=evaluate(setup,{'candles':extended})
    assert not replay['trigger_ready_now'] and replay['trigger_reason']=='range_breakout_already_consumed'
    assert setup['setup_metadata']==metadata  # Shared-baseline adaptation is detached.
    setup['execution_stream']['observed_at_utc']=metadata['confirmation_expiry_timestamp']
    expired=evaluate(setup,{'candles':execution})
    assert not expired['trigger_ready_now'] and expired['trigger_reason']=='range_confirmation_expired_or_missing'
    setup['execution_stream']['observed_at_utc']=inputs.observed_at_utc-timedelta(seconds=5)
    forming=evaluate(setup,{'candles':execution})
    assert not forming['trigger_ready_now'] and forming['trigger_reason']=='range_incomplete_execution_confirmation'
