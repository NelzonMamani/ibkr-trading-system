from __future__ import annotations

import pytest

from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.patterns.pattern_hod_break import detect_hod_break
from src.strategies.common.triggers.trigger_hod_break import evaluate_hod_break_trigger
from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY, resolve_trigger_evaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.strategy_contracts import SessionContext


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def _inputs(
    *,
    session: SessionContext = SessionContext.REGULAR,
    hod: float | None = 10.52,
    hod_source: str | None = "RTH",
    candles: list[Candle] | None = None,
) -> PatternInputs:
    return PatternInputs(
        symbol="HODT",
        timeframe="1MIN",
        candles=candles
        or _candles(
            [
                (10.20, 10.28, 10.18, 10.26, 1000),
                (10.26, 10.36, 10.24, 10.34, 1100),
                (10.34, 10.44, 10.34, 10.40, 1200),
                (10.40, 10.50, 10.39, 10.46, 1300),
                (10.46, 10.51, 10.44, 10.50, 1250),
                (10.49, 10.52, 10.47, 10.51, 1400),
            ]
        ),
        session_context=session,
        levels=LevelSet(premarket_high=10.1, premarket_low=9.7, hod=hod, hod_source=hod_source, prior_close=9.9, key_levels={}),
        indicators=IndicatorSet(ema9=10.45, ema20=10.36, vwap=10.41),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=18.0, rvol=1.9),
    )


def test_hod_break_detects_valid_compression_and_breakout_ready() -> None:
    result = detect_hod_break(_inputs())
    assert result.detected is True
    assert result.setup_id == "P_HOD_BREAK"
    assert result.setup_family_id == "HOD_BREAK"
    assert result.trigger_type == "XL_HOD_BREAK"


def test_hod_break_rejects_invalid_session() -> None:
    result = detect_hod_break(_inputs(session=SessionContext.PRE))
    assert result.detected is False
    assert result.rejection_reason == "invalid_session"


def test_hod_break_rejects_invalid_hod_source() -> None:
    result = detect_hod_break(_inputs(hod_source="PRE"))
    assert result.detected is False
    assert result.rejection_reason == "invalid_hod_source"


def test_hod_break_rejects_when_hod_missing() -> None:
    malformed = [
        {"open": 10.0, "high": None, "low": 9.9, "close": 10.0, "volume": 1000},
        {"open": 10.0, "high": None, "low": 9.9, "close": 10.0, "volume": 1000},
        {"open": 10.0, "high": None, "low": 9.9, "close": 10.0, "volume": 1000},
        {"open": 10.0, "high": None, "low": 9.9, "close": 10.0, "volume": 1000},
        {"open": 10.0, "high": None, "low": 9.9, "close": 10.0, "volume": 1000},
        {"open": 10.0, "high": None, "low": 9.9, "close": 10.0, "volume": 1000},
    ]
    result = detect_hod_break(_inputs(hod=None, candles=malformed))
    assert result.detected is False
    assert result.rejection_reason == "missing_hod"


def test_hod_break_rejects_without_compression() -> None:
    wide = _candles(
        [
            (10.2, 10.35, 10.1, 10.3, 1000),
            (10.3, 10.46, 10.2, 10.35, 1200),
            (10.35, 10.51, 10.2, 10.4, 1200),
            (10.4, 10.52, 10.21, 10.48, 1300),
            (10.48, 10.54, 10.22, 10.5, 1300),
            (10.5, 10.55, 10.24, 10.51, 1400),
        ]
    )
    result = detect_hod_break(_inputs(candles=wide, hod=10.55))
    assert result.detected is False
    assert result.rejection_reason == "no_compression"


def test_hod_break_trigger_arms_and_fires() -> None:
    armed = evaluate_hod_break_trigger(
        {"trigger_level": 10.52, "invalidation_level": 10.40, "stop_level": 10.40},
        {"candles": _candles([(10.48, 10.51, 10.46, 10.50, 1000), (10.50, 10.519, 10.49, 10.51, 1100)]), "rvol": 1.4},
    )
    assert armed["trigger_state"] == "ARMED"
    assert armed["trigger_ready_now"] is False

    fired = evaluate_hod_break_trigger(
        {"trigger_level": 10.52, "invalidation_level": 10.40, "stop_level": 10.40},
        {"candles": _candles([(10.48, 10.51, 10.46, 10.51, 1000), (10.51, 10.56, 10.50, 10.531, 1500)]), "rvol": 1.4},
    )
    assert fired["trigger_state"] == "FIRED"
    assert fired["trigger_ready_now"] is True


def test_hod_break_trigger_blocks_without_liquidity_confirmation() -> None:
    blocked = evaluate_hod_break_trigger(
        {"trigger_level": 10.52, "invalidation_level": 10.40, "stop_level": 10.40},
        {"candles": _candles([(10.48, 10.51, 10.46, 10.51, 1000), (10.51, 10.56, 10.50, 10.54, 800)]), "rvol": 1.0, "avg_volume": 1200},
    )
    assert blocked["trigger_state"] == "BLOCKED"
    assert blocked["trigger_reason"] == "liquidity_confirmation_failed"


def test_hod_break_trigger_blocks_wick_only_breakout() -> None:
    blocked = evaluate_hod_break_trigger(
        {"trigger_level": 10.52, "invalidation_level": 10.40, "stop_level": 10.40},
        {"candles": _candles([(10.48, 10.51, 10.46, 10.51, 1000), (10.51, 10.60, 10.48, 10.52, 2000)]), "rvol": 1.5},
    )
    assert blocked["trigger_state"] == "BLOCKED"
    assert blocked["trigger_reason"] == "breakout_shape_invalid"


def test_trigger_registry_contains_hod_break() -> None:
    assert "HOD_BREAK" in TRIGGER_EVALUATOR_REGISTRY
    assert resolve_trigger_evaluator("HOD_BREAK") is not None


def test_ross_runtime_can_consume_hod_break_without_bypass() -> None:
    registry = RossPatternRegistry()
    registry._patterns = [pattern for pattern in registry.patterns if getattr(pattern, "pattern_id", "") == "P_HOD_BREAK"]

    result = registry.run(_inputs())[0]
    assert result.setup_id == "P_HOD_BREAK"
    assert result.setup_family_id == "HOD_BREAK"
    assert result.trigger_type == "XL_HOD_BREAK"

    evaluator = resolve_trigger_evaluator(result.setup_family_id)
    assert evaluator is not None
    trigger = evaluator(
        {"trigger_level": result.trigger_level, "invalidation_level": result.invalidation_level, "stop_level": result.stop_level},
        {"candles": _inputs().candles},
    )
    assert trigger["trigger_type"] == "XL_HOD_BREAK"


def test_native_hod_target_and_occurrence_bound_bridge_keep_own_contract():
    from dataclasses import replace
    from src.strategies.ross_momentum.decision_policy import validate_entry_contract
    from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1
    first=detect_hod_break(_inputs())
    second=detect_hod_break(_inputs(hod=10.53))
    missing=detect_hod_break(replace(_inputs(),levels=None))
    assert not missing.detected and missing.rejection_reason=='invalid_hod_source'
    assert missing.target_suggestion is None
    assert first.detected and second.detected
    for result in (first,second):
        assert result.target_suggestion=='Continuation above the established regular-session high of day.'
        assert validate_entry_contract(result)==(True,'ok')
        assert validate_entry_contract(replace(result,target_suggestion=None))==(False,'missing_target')
        assert validate_entry_contract(replace(result,stop_level=result.trigger_level))==(False,'invalid_risk_geometry')
    bridge=RossMomentumStrategyV1._canonical_pattern_trigger_candidates(
        RossMomentumStrategyV1.__new__(RossMomentumStrategyV1),[first,second],symbol='HODT',existing_triggers=[])
    assert len(bridge)==2
    for index,result in enumerate((first,second)):
        assert bridge[index]['canonical_result_index']==index
        assert bridge[index]['source']=='canonical_pattern_result'
        assert bridge[index]['setup_family_id']=='HOD_BREAK'
        assert bridge[index]['setup_metadata']==result.setup_metadata
        for name in ('trigger_level','stop_level','invalidation_level'):
            assert bridge[index][name]==getattr(result,name)
    assert bridge[0]['trigger_level']!=bridge[1]['trigger_level']
    for invalid in (float('nan'),float('inf'),True):
        values=_inputs()
        bad=detect_hod_break(replace(values,levels=replace(values.levels,established_rth_hod=invalid)))
        assert not bad.detected and bad.rejection_reason=='missing_hod'
    rejected=detect_hod_break(_inputs(session=SessionContext.PRE))
    assert not rejected.detected and rejected.target_suggestion is None


def test_hod_source_and_registered_execution_reject_future_or_nonfinite_data():
    from dataclasses import replace
    from datetime import datetime,timedelta,timezone
    now=datetime(2026,10,20,14,10,tzinfo=timezone.utc)
    valid=[replace(c,timestamp=now-timedelta(minutes=6-i)) for i,c in enumerate(_inputs().candles)]
    source=replace(_inputs(),candles=valid,observed_at_utc=now)
    assert detect_hod_break(source).detected
    for fault,expected in (('future','FUTURE_CANDLE_DATA'),('nan','INVALID_CANDLE_DATA'),
                           ('malformed','INVALID_CANDLE_DATA'),('stale','STALE_SOURCE')):
        bars=list(valid)
        if fault=='future':bars[-1]=replace(bars[-1],timestamp=now+timedelta(seconds=1))
        if fault=='nan':bars[-1]=replace(bars[-1],volume=float('nan'))
        if fault=='malformed':bars[-1]=replace(bars[-1],low=11.)
        if fault=='stale':bars=[replace(c,timestamp=c.timestamp-timedelta(hours=1)) for c in bars]
        result=detect_hod_break(replace(source,candles=bars))
        assert not result.detected and result.rejection_reason==expected and result.target_suggestion is None
    bars=[replace(valid[-2],close=10.51),replace(valid[-1],open=10.51,high=10.56,low=10.50,close=10.54)]
    payload={'trigger_level':10.52,'stop_level':10.4,'invalidation_level':10.4,
             'execution_stream':{'observed_at_utc':now.isoformat()}}
    assert evaluate_hod_break_trigger(payload,{'candles':bars,'rvol':1.4})['trigger_ready_now']
    for fault,expected in (('future','hod_future_candle_data'),('nan','hod_invalid_candle_data')):
        bad=list(bars)
        bad[-1]=replace(bad[-1],**({'timestamp':now+timedelta(seconds=1)} if fault=='future' else {'high':float('nan')}))
        out=evaluate_hod_break_trigger(payload,{'candles':bad,'rvol':1.4})
        assert not out['trigger_ready_now'] and out['trigger_reason']==expected


def test_hod_registered_threshold_cross_volume_and_invalidation_owners():
    from dataclasses import replace
    from src.core.engines.trigger_engine import TriggerEngine
    threshold=10.52*1.001
    bars=_candles([(10.48,10.52,10.46,10.52,1000),
                  (10.51,threshold+.001,10.5,threshold,1000)])
    payload={'setup_family_id':'HOD_BREAK','setup_detected':True,'required_trigger_types':['XL_HOD_BREAK'],
             'trigger_level':10.52,'stop_level':10.4,'invalidation_level':10.4}
    def trigger(values,**kw):return evaluate_hod_break_trigger(payload,{'candles':values,'rvol':1.,**kw})
    assert not trigger(bars)['trigger_ready_now']  # equality is not strict confirmation
    bars[-1]=replace(bars[-1],close=threshold+1e-9)
    assert trigger(bars)['trigger_ready_now']  # equality to prior mean volume remains valid
    bars[-1]=replace(bars[-1],volume=999)
    assert trigger(bars)['trigger_reason']=='liquidity_confirmation_failed'
    assert trigger(bars,rvol=1.2)['trigger_ready_now']  # native RVOL OR volume law
    bars[-2]=replace(bars[-2],close=10.53,high=10.53)
    assert not trigger(bars,rvol=1.2)['trigger_ready_now']
    bars[-1]=replace(bars[-1],close=10.4,low=10.39)
    out=TriggerEngine().evaluate_triggers(symbol='HODT',candles=bars,setups=[payload],levels={'rvol':1.2},structure={})[0]
    assert not out['trigger_ready_now'] and out['trigger_reason']=='at_or_below_invalidation'


def test_established_rth_reference_requires_full_current_day_completed_coverage():
    from dataclasses import replace
    from datetime import datetime,timedelta,timezone
    from src.strategies.ross_momentum.patterns.pattern_trace import _established_rth_hod
    start=datetime(2026,10,20,13,30,tzinfo=timezone.utc)
    bars=[replace(_inputs().candles[-1],timestamp=start+timedelta(minutes=i)) for i in range(40)]
    now=start+timedelta(minutes=40,seconds=41)
    assert _established_rth_hod(bars,now)==10.52
    pre=replace(bars[0],timestamp=start-timedelta(minutes=1),high=99.)
    forming=replace(bars[-1],timestamp=start+timedelta(minutes=40),high=100.)
    assert _established_rth_hod([pre]+bars+[forming],now)==10.52
    assert _established_rth_hod(bars[1:],now) is None
    assert _established_rth_hod(bars[:10]+bars[11:],now) is None
    assert _established_rth_hod([replace(c,timestamp=c.timestamp-timedelta(days=1)) for c in bars],now) is None
    assert _established_rth_hod(bars,now-timedelta(hours=1)) is None
    # A duplicated or shifted timestamp cannot fill a missing minute.
    wrong=list(bars);wrong[5]=replace(wrong[5],timestamp=wrong[4].timestamp)
    assert _established_rth_hod(wrong,now) is None


def test_hod_preserves_native_liquidity_trend_volume_and_shape_laws():
    from dataclasses import replace
    base=_inputs()
    for spread,reason in ((None,'low_liquidity'),(.080000001,'wide_spread')):
        result=detect_hod_break(replace(base,liquidity_context=replace(base.liquidity_context,spread=spread)))
        assert not result.detected and result.rejection_reason==reason and result.target_suggestion is None
    assert detect_hod_break(replace(base,liquidity_context=replace(base.liquidity_context,spread=.08))).detected
    assert detect_hod_break(replace(base,indicators=replace(base.indicators,ema9=10.6))).rejection_reason=='broken_trend_context'
    assert detect_hod_break(_inputs(hod=10.6)).rejection_reason=='no_hod_proximity'
    values=list(base.candles);values[-1]=replace(values[-1],volume=0.)
    low=replace(base,candles=values,liquidity_context=replace(base.liquidity_context,rvol=1.24))
    assert detect_hod_break(low).rejection_reason=='insufficient_volume_confirmation'
    assert detect_hod_break(replace(low,liquidity_context=replace(low.liquidity_context,rvol=1.25))).detected
    mean=sum(c.volume for c in values[-6:-1])/5
    values[-1]=replace(values[-1],volume=mean)
    assert detect_hod_break(replace(low,candles=values)).detected
    wick=_candles([(10.48,10.51,10.46,10.50,1000)]*5+[(10.5,10.54,10.49,10.51,1400)])
    assert detect_hod_break(_inputs(candles=wick)).rejection_reason=='wick_through_only'


@pytest.mark.parametrize('fault',['none','gap','duplicate','short','old','delayed','invalid_early_ohlc'])
def test_runtime_acquisition_keeps_full_rth_reference_separate_from_rolling_inputs(monkeypatch,fault):
    from dataclasses import replace
    from datetime import datetime,timedelta,timezone
    from src.strategies.ross_momentum.patterns import pattern_trace as trace
    start=datetime(2026,10,20,13,30,tzinfo=timezone.utc)
    now=start+timedelta(minutes=185,seconds=30)
    fetch_clock=[now]
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return fetch_clock[0]
    monkeypatch.setattr(trace,'datetime',Clock)
    base=_inputs().candles[-1]
    bars=[replace(base,timestamp=start+timedelta(minutes=i)) for i in range(186)]
    bars[3]=replace(bars[3],high=12.)
    bars[-1]=replace(bars[-1],high=99.) # Forming source cannot establish HOD.
    calls=[]
    def external(*,symbol,timeframe,limit):
        calls.append((timeframe,limit))
        if timeframe!='1m':return []
        selected=list(bars[-limit:])
        if fault=='delayed':
            fetch_clock[0]=now+timedelta(minutes=2)
            selected.append(replace(bars[-1],timestamp=bars[-1].timestamp+timedelta(minutes=1),high=100.))
        if fault=='invalid_early_ohlc':selected[3]=replace(selected[3],high=9.)
        if fault=='gap':selected.pop(40)
        if fault=='duplicate':selected[40]=selected[39]
        if fault=='short':selected=selected[-50:]
        if fault=='old':selected=[replace(c,timestamp=c.timestamp-timedelta(days=1)) for c in selected]
        return selected
    monkeypatch.setattr(trace,'get_intraday_bars',external)
    row=dict(last_price=10.52,volume=1000000,prior_close=9.8,float_millions=8.,rvol=3.,
        bid=10.51,ask=10.53,spread=.02)
    inputs,_=trace.build_runtime_pattern_inputs(symbol='HODH',row=row,snapshot=None,
        session_label='RTH_MID',session_phase='RTH_MID')
    assert inputs is not None and inputs.observed_at_utc==now
    assert inputs.levels.established_rth_hod==(12. if fault in {'none','delayed'} else None)
    assert len(inputs.candles)==50
    assert inputs.candles[0].timestamp==bars[-49 if fault=='delayed' else -50].timestamp-(timedelta(days=1) if fault=='old' else timedelta())
    assert inputs.levels.hod==(100. if fault=='delayed' else 99.) # Legacy rolling/forming semantics remain separate.
    if fault=='delayed':
        assert inputs.observed_at_utc<inputs.candles[-1].timestamp<=fetch_clock[0]
        rejected=detect_hod_break(inputs)
        assert not rejected.detected and rejected.rejection_reason=='FUTURE_CANDLE_DATA'
    assert [tf for tf,_ in calls]==['10s','1m','5m']
    assert calls[0][1]==120 and calls[2][1]==50
    assert calls[1][1]>=186 and calls[1][1]<=392
    if fault=='none':
        # Identical external rolling tail, real builder: only the separately
        # authorized complete-RTH reference may change, never legacy geometry.
        fault='short'
        rolling,_=trace.build_runtime_pattern_inputs(symbol='HODH',row=row,snapshot=None,
            session_label='RTH_MID',session_phase='RTH_MID')
        assert inputs.levels.rth_open_price==bars[0].open
        assert inputs.levels.rth_open_timestamp==start
        assert rolling.levels.rth_open_price is rolling.levels.rth_open_timestamp is None
        assert replace(inputs,levels=replace(inputs.levels,established_rth_hod=None,
            rth_open_price=None,rth_open_timestamp=None),level_provenance=rolling.level_provenance)==rolling


@pytest.mark.parametrize('stamp,session,expected',[
    ('2026-10-20T13:29:59+00:00','PRE',50),
    ('2026-10-20T13:30:00+00:00','RTH_OPEN',50),
    ('2026-10-20T14:30:01+00:00','RTH_MID',62),
    ('2026-11-06T15:30:01+00:00','RTH_MID',62), # NY winter offset.
    ('2026-11-06T20:59:59+00:00','RTH_LATE',391),
    ('2026-11-06T21:00:00+00:00','AH',50),
])
def test_rth_reference_request_is_bounded_session_specific_single_fetch(monkeypatch,stamp,session,expected):
    from datetime import datetime
    from src.strategies.ross_momentum.patterns import pattern_trace as trace
    calls=[]
    def external(**kwargs):calls.append(kwargs);return []
    monkeypatch.setattr(trace.historical_data_provider,'get_intraday_bars',external)
    assert trace._fetch_runtime_timeframe_bars('HODH',observed_at_utc=datetime.fromisoformat(stamp),
        session_label=session)=={}
    assert [(c['timeframe'],c['limit']) for c in calls]==[('10s',120),('1m',expected),('5m',50)]
