"""Synthetic fresh inputs, real standalone Micro Pullback detector/registry/dispatch/V1.

The only replacement in the acceptance path is the market-data boundary.
Observers call original owners; no PatternResult or missing contract is injected.
"""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone

import pytest

from src.config.runtime_config import RunMode
from src.setup_engine.registry import build_tradeable_patterns
from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from test_flat_top_production_handoff import forbid_collection_and_execution, forbid_io
from test_pr1082_trigger_to_intent_terminal_semantics import (
    _base_strategy, _candles, _snapshot, _watchlist_row, _reset_config,
)


CLOCK = datetime(2026, 9, 16, 14, 35, 30, tzinfo=timezone.utc)
TAIL = [
    (10.,10.2,9.99,10.18,1300), (10.18,10.45,10.16,10.42,1600),
    (10.42,10.8,10.4,10.76,2000), (10.76,10.78,10.68,10.72,900),
    (10.72,10.74,10.66,10.7,850), (10.7,10.9,10.69,10.88,2100),
]


def actual_run(monkeypatch, tmp_path, *, state="ready", duplicate=False, mode=RunMode.READ_ONLY):
    strategy = _base_strategy(monkeypatch, tmp_path, state="ready")
    rows = [(10.,10.02,9.98,10.,1000)]*44 + TAIL
    execution = [(10.7,10.75,10.65,10.72,500)]*49 + [(10.7,10.9,10.69,10.88,2100)]
    if state == "source_soft_volume": rows[-1] = (*rows[-1][:4],100)
    if state == "waiting": execution[-1] = (10.7,10.75,10.65,10.72,200)
    if state == "execution_touch": execution[-1] = (10.7,10.9,10.69,10.78,2100)
    if state == "execution_soft_volume": execution[-1] = (*execution[-1][:4],50)
    if state == "execution_zero_volume": execution[-1] = (*execution[-1][:4],0)
    if state == "source_touch": rows[-1] = (10.7,10.9,10.69,10.78,2100)
    if state == "source_weak_impulse": rows[-6:-3] = [(10.,10.02,9.99,10.01,1300)]*3
    if state == "source_deep": rows[-2] = (10.72,10.74,10.1,10.7,850)
    if state == "source_depth_inside": rows[-2] = (10.72,10.74,10.28,10.7,850)
    if state == "source_depth_outside": rows[-2] = (10.72,10.74,10.27,10.7,850)
    if state == "source_just_above": rows[-1] = (10.7,10.9,10.69,10.78+1e-9,2100)
    if state == "source_one_red": rows[-3] = (10.7,10.78,10.68,10.72,900)
    if state == "source_three_red": rows[-4] = (10.77,10.8,10.4,10.76,2000)
    if state == "source_red_confirmation": rows[-1] = (10.89,10.9,10.69,10.88,2100)
    if state == "execution_wick_touch": execution[-1] = (10.7,10.78,10.69,10.72,500)
    data = {tf: _candles(execution if tf == "10s" else rows, step_seconds=seconds,
             end=datetime(2026,9,16,14,minute,second,tzinfo=timezone.utc))
            for tf,seconds,minute,second in (("1m",60,34,0),("5m",300,30,0),("10s",10,35,20))}
    for prefix,tf in (("source","1m"),("execution","10s")):
        if state == prefix+"_missing": data[tf] = []
        if state == prefix+"_stale":
            data[tf] = [replace(c,timestamp=c.timestamp-timedelta(minutes=10)) for c in data[tf]]
        if state == prefix+"_future": data[tf][-1] = replace(data[tf][-1],timestamp=CLOCK+timedelta(microseconds=1))
        if state == prefix+"_nan_low": data[tf][-1] = replace(data[tf][-1],low=float("nan"))
        if state == prefix+"_invalid_range": data[tf][-1] = replace(data[tf][-1],low=11.)
        if state == prefix+"_inf_volume": data[tf][-1] = replace(data[tf][-1],volume=float("inf"))
        if state == prefix+"_negative_volume": data[tf][-1] = replace(data[tf][-1],volume=-1.)
        if state == prefix+"_nan_volume": data[tf][-1] = replace(data[tf][-1],volume=float("nan"))
        if state == prefix+"_naive": data[tf][-1] = replace(data[tf][-1],timestamp=CLOCK.replace(tzinfo=None))
    if state == "forming_breakout":
        data["1m"] = [replace(c,timestamp=c.timestamp+timedelta(minutes=1)) for c in data["1m"]]
    if state == "forming_execution":
        data["10s"][-1] = replace(data["10s"][-1],timestamp=CLOCK)
    if state == "incomplete_pullback":
        data["1m"][-2] = replace(data["1m"][-2],timestamp=CLOCK-timedelta(seconds=50))
        data["1m"][-1] = replace(data["1m"][-1],timestamp=CLOCK-timedelta(seconds=10))
    if state in {"pullback_at_max_age","pullback_over_max_age"}:
        end = CLOCK-timedelta(seconds=120,microseconds=1 if state == "pullback_over_max_age" else 0)
        data["1m"] = _candles(rows,end=end)
        data["1m"][-1] = replace(data["1m"][-1],timestamp=CLOCK.replace(second=0))
    if state in {"pullback_exact_completion","pullback_before_completion"}:
        end = CLOCK-timedelta(seconds=1,microseconds=-1 if state == "pullback_before_completion" else 0)
        data["1m"] = _candles(rows,end=end)
        # Penultimate bar ends at the observation clock, or one microsecond
        # after it. The breakout itself may still be forming.
        delta = timedelta(seconds=1)
        data["1m"] = [replace(c,timestamp=c.timestamp+delta) for c in data["1m"]]
    if state in {"execution_at_max_age","execution_over_max_age"}:
        data["1m"] = _candles(rows,end=CLOCK.replace(minute=33,second=30))
        end = CLOCK-timedelta(seconds=60,microseconds=1 if state == "execution_over_max_age" else 0)
        data["10s"] = _candles(execution,end=end,step_seconds=10)
    if state == "source_breakout_extremes": data["1m"][-1] = replace(data["1m"][-1],high=10.95,low=10.4)
    if state in {"impulse_nan", "pullback_nan", "pullback_negative_volume"}:
        index = -5 if state == "impulse_nan" else -3
        change = {"volume": -1.} if state == "pullback_negative_volume" else {"low": float("nan")}
        data["1m"][index] = replace(data["1m"][index], **change)
    monkeypatch.setattr("src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda *,timeframe="1m",limit=50,**kw:list(data[timeframe])[-limit:])
    registry = RossPatternRegistry()
    registry._patterns = build_tradeable_patterns(["MICRO_PULLBACK"])
    if duplicate: registry._patterns.extend(build_tradeable_patterns(["MICRO_PULLBACK"]))
    strategy._pattern_registry = registry
    results, calls, inputs = [], [], []
    original_run = registry.run
    def observed_run(source, **kwargs):
        inputs.append(source)
        output = original_run(source, **kwargs)
        results.extend(output)
        return output
    monkeypatch.setattr(registry,"run",observed_run)
    original = TRIGGER_EVALUATOR_REGISTRY["MICRO_PULLBACK"]
    def observed_trigger(payload, stream):
        output = original(payload, stream)
        calls.append((payload,stream,output))
        return output
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,"MICRO_PULLBACK",observed_trigger)
    row = {**_watchlist_row(),"last_price":10.88,"bid":10.87,"ask":10.89}
    if state == "negative_spread": row["spread"] = -.01
    if state == "nan_spread": row["spread"] = float("nan")
    if state == "inf_spread": row["spread"] = float("inf")
    if state == "nan_rvol": row["rvol"] = float("nan")
    if state == "inf_rvol": row["rvol"] = float("inf")
    if state == "negative_rvol": row["rvol"] = -1.
    intents = strategy.process_watchlist(watchlist=[row],snapshots={"UPC":replace(_snapshot(),last=10.88,bid=10.87,ask=10.89)},
        session_label="RTH_OPEN",session_phase="RTH_OPEN",timestamp_utc="synthetic-standalone-micro-pullback",mode=mode)
    return strategy,intents,results,calls,inputs


def test_native_detector_registered_evaluator_selection_actual_v1(monkeypatch,tmp_path):
    strategy,intents,results,calls,inputs = actual_run(monkeypatch,tmp_path)
    assert len(results) == 1 and results[0].detected
    result = results[0]
    assert result.trigger_level == 10.78 and result.stop_level == result.invalidation_level == 10.66
    own = [c for c in calls if c[0].get("source") == "canonical_pattern_result"]
    assert len(own) == len(intents) == 1, strategy.last_symbol_terminal_outcomes
    assert own[0][0]["canonical_result_index"] == 0 and own[0][2]["trigger_ready_now"]
    intent = intents[0]
    assert intent.entry_price == result.trigger_level
    assert intent.stop_loss_price == result.stop_level and intent.invalidation_level == result.invalidation_level
    assert intent.target_model == result.target_suggestion == "Prior high / HOD"
    assert result.rationale_text in intent.rationale
    assert intent.setup_family_id == "MICRO_PULLBACK" and intent.take_profit_price is None
    assert intent.setup_metadata["canonical_result_index"] == 0
    assert intent.setup_metadata["execution_stream"]["observed_at_utc"] == inputs[0].observed_at_utc.isoformat()
    assert inputs[0].levels.hod == 10.9  # Context cannot replace selected range high.
    assert intent.timestamp_utc == "synthetic-standalone-micro-pullback" and intent.decision_id is None
    assert not intent.relationship_context and "relationship" not in result.setup_metadata


@pytest.mark.parametrize("state", ["waiting","source_missing","source_stale",
    "execution_missing","execution_stale","source_future","execution_future","source_nan_low",
    "execution_nan_low","source_invalid_range","execution_invalid_range","source_inf_volume",
    "execution_inf_volume","incomplete_pullback","pullback_over_max_age","negative_spread","nan_spread",
    "inf_spread","nan_rvol","inf_rvol","negative_rvol","source_touch","source_weak_impulse",
    "source_deep","source_depth_outside","source_red_confirmation",
    "source_negative_volume","execution_negative_volume","source_nan_volume","execution_nan_volume",
    "pullback_before_completion","execution_over_max_age"])
def test_invalid_or_unconfirmed_native_inputs_block(monkeypatch,tmp_path,state):
    _,intents,_,_,_ = actual_run(monkeypatch,tmp_path,state=state)
    assert intents == []


@pytest.mark.parametrize("state", ["forming_breakout","pullback_at_max_age",
    "pullback_exact_completion","execution_at_max_age","source_breakout_extremes","execution_soft_volume",
    "execution_wick_touch","execution_touch","execution_zero_volume","source_depth_inside","source_just_above",
    "source_one_red","source_three_red"])
def test_micro_specific_existing_boundaries(monkeypatch,tmp_path,state):
    _,intents,results,_,_ = actual_run(monkeypatch,tmp_path,state=state)
    assert len(intents) == 1 and results[0].detected
    expected = {"source_depth_inside": (10.78,10.28), "source_one_red": (10.74,10.66),
                "source_three_red": (10.8,10.4)}.get(state,(10.78,10.66))
    assert (results[0].trigger_level,results[0].stop_level) == expected
    assert intents[0].entry_price == expected[0]
    assert intents[0].stop_loss_price == intents[0].invalidation_level == expected[1]



def test_retained_intent_evidence_cannot_follow_later_mutation(monkeypatch,tmp_path):
    _,intents,results,calls,inputs = actual_run(monkeypatch,tmp_path)
    intent = intents[0]
    saved = asdict(intent)
    own = next(p for p,_,_ in calls if p.get("source") == "canonical_pattern_result")
    own["execution_stream"]["timeframe_provenance"].clear()
    own["trigger_level"] = 99.
    own["stop_level"] = own["invalidation_level"] = 1.
    results[0].setup_metadata["pullback_high"] = 99.
    results[0].setup_metadata["pullback_low"] = 1.
    inputs[0].candles.clear()
    assert asdict(intent) == saved


def test_existing_intrabar_execution_does_not_acquire_a_new_close_gate(monkeypatch,tmp_path):
    _,intents,results,calls,_ = actual_run(monkeypatch,tmp_path,state="forming_execution")
    assert results[0].detected and len(intents) == 1
    own = next(c for c in calls if c[0].get("source") == "canonical_pattern_result")
    assert own[1]["candles"][-1].timestamp == CLOCK and own[2]["trigger_ready_now"]


def test_native_duplicate_occurrences_keep_selection_identity(monkeypatch,tmp_path):
    _,intents,results,calls,_ = actual_run(monkeypatch,tmp_path,duplicate=True)
    assert len(results) == 2 and results[0] is not results[1] and all(r.detected for r in results)
    own = [p for p,_,_ in calls if p.get("source") == "canonical_pattern_result"]
    assert [p["canonical_result_index"] for p in own] == [0,1]
    assert len(intents) == 1 and intents[0].setup_metadata["canonical_result_index"] == 0
    assert own[0]["trigger_level"] == intents[0].entry_price
    assert own[0]["stop_level"] == intents[0].stop_loss_price
    results[1].setup_metadata["foreign"] = True
    assert "foreign" not in intents[0].setup_metadata["source_metadata"]


def test_actual_raw_formation_still_precedes_five_position_veto(monkeypatch,tmp_path,capsys):
    from test_pr1082_rth_watchlist_continuity import _install_runtime_harness, _row, _payload
    from test_ross_supported_catalyst_critical_path import _saved_shape_verdict
    from src.core import orchestrator
    _,intents,_,_,_ = actual_run(monkeypatch,tmp_path)
    assert len(intents) == 1 and intents[0].decision_id is None
    row = _row("UPC",catalyst=True)
    core,_,_ = _install_runtime_harness(monkeypatch,[_payload([row],focus=[row])])
    verdict = _saved_shape_verdict(datetime.now(timezone.utc))
    monkeypatch.setattr(core,"_resolve_position_truth_cycle",lambda **kwargs:verdict)
    core.strategy_runner.process = lambda **kwargs:intents  # Actual raw output from above, not a fabricated intent.
    def forbidden(*args,**kwargs): pytest.fail("ownership veto must admit no artifact/risk input")
    monkeypatch.setattr(core.risk_engine,"evaluate_trade_intent",forbidden)
    monkeypatch.setattr(orchestrator,"build_decision_artifact",forbidden)
    capsys.readouterr()
    assert core.run_once()
    output = capsys.readouterr().out
    assert "[PIPELINE][STRATEGY_OUTPUT] count=1" in output
    assert "dominant_blocking_reasons={'POSITION_TRUTH_BLOCK_NEW_ENTRIES': 1}" in output
    assert "[PIPELINE][RISK_INPUT] intents_count=0" in output
    assert "reason=INTENT_REJECTED_BY_EXECUTION_INTEGRITY" not in output
    assert intents[0].decision_id is None and "ORDER_SUBMITTED" not in output




@pytest.mark.parametrize("mode", [RunMode.READ_ONLY,RunMode.PAPER,RunMode.LIVE])
def test_future_execution_is_not_mode_permission(monkeypatch,tmp_path,mode):
    assert actual_run(monkeypatch,tmp_path,state="execution_future",mode=mode)[1] == []


@pytest.mark.parametrize("stream", [None,{}, {"observed_at_utc":None}])
def test_bound_execution_cannot_lose_its_original_clock(monkeypatch,tmp_path,stream):
    from src.strategies.common.triggers.trigger_micro_pullback import evaluate_micro_pullback_trigger
    _,_,_,calls,_ = actual_run(monkeypatch,tmp_path)
    payload,values,_ = next(c for c in calls if c[0].get("source") == "canonical_pattern_result")
    out = evaluate_micro_pullback_trigger({**payload,"execution_stream":stream},values)
    assert not out["trigger_ready_now"] and out["trigger_reason"] == "micro_pullback_invalid_candle_timestamps"


@pytest.mark.parametrize("clock", [None,datetime(2026,9,16,14,35,30),"invalid"])
def test_active_source_cannot_lose_its_original_clock(monkeypatch,tmp_path,clock):
    from src.setup_engine.setup_families.micro_pullback import MicroPullbackPattern
    *_,inputs = actual_run(monkeypatch,tmp_path)
    out = MicroPullbackPattern().evaluate(replace(inputs[0],observed_at_utc=clock))
    assert not out.detected and out.rejection_reason == "INVALID_CANDLE_TIMESTAMPS"


@pytest.mark.parametrize("field", ["ema9"])
@pytest.mark.parametrize("value", [float("nan"),float("inf")])
def test_nonfinite_required_indicator_evidence_cannot_admit_entry(monkeypatch,tmp_path,field,value):
    from src.setup_engine.setup_families.micro_pullback import MicroPullbackPattern
    *_,inputs = actual_run(monkeypatch,tmp_path)
    source = inputs[0]
    out = MicroPullbackPattern().evaluate(replace(source,indicators=replace(source.indicators,**{field:value})))
    assert not out.detected and out.rejection_reason == "invalid EMA9"


@pytest.mark.parametrize("reverse", [False,True])
def test_distinct_native_duplicate_contracts_cannot_borrow_ready_receipts(monkeypatch,tmp_path,reverse):
    """Separate adversarial boundary; these results are never injected into V1."""
    from copy import deepcopy
    from src.core.engines.trigger_engine import TriggerEngine
    from src.setup_engine.setup_families.micro_pullback import MicroPullbackPattern
    strategy,_,results,calls,inputs = actual_run(monkeypatch,tmp_path)
    source = inputs[0]
    shifted = replace(source,candles=[replace(c,open=c.open+1,high=c.high+1,low=c.low+1,close=c.close+1)
                                     for c in source.candles])
    second = MicroPullbackPattern().evaluate(shifted)
    assert second.detected and second.trigger_level == 11.78
    native = [second,results[0]] if reverse else [results[0],second]
    setups = strategy._canonical_pattern_trigger_candidates(native,symbol="UPC",existing_triggers=[])
    stream = next(p["execution_stream"] for p,_,_ in calls if p.get("source") == "canonical_pattern_result")
    for setup in setups: setup["execution_stream"] = deepcopy(stream)
    triggers = TriggerEngine().evaluate_triggers(symbol="UPC",setups=setups,
        candles=source.timeframe_candles["10s"],levels={},structure={})
    waiting_index = 0 if reverse else 1
    waiting = strategy._select_trigger_candidate(setup_family_id="MICRO_PULLBACK",trigger_candidates=triggers,
                                                selected_candidate_index=waiting_index)
    ready = strategy._select_trigger_candidate(setup_family_id="MICRO_PULLBACK",trigger_candidates=triggers,
                                              selected_candidate_index=1-waiting_index)
    assert not waiting["trigger_ready_now"] and ready["trigger_ready_now"]
    assert waiting["trigger_price_reference"] == second.trigger_level
    assert strategy._select_trigger_candidate(setup_family_id="MICRO_PULLBACK",trigger_candidates=triggers) is None
    reasons = []
    assert strategy._build_trade_from_pattern(second,source,selected_contract=second,selected_trigger=ready,
                                             rejection_reasons=reasons) is None
    assert reasons == ["selected_invalidation_authority_mismatch"]


@pytest.mark.parametrize("timeframe", ["10s","1min","M1","5m"])
@pytest.mark.parametrize("incomplete", [False,True])
def test_structure_completion_uses_existing_duration_and_timezone(monkeypatch,tmp_path,timeframe,incomplete):
    from src.adapters.data.historical_bar_timeframes import resolve_intraday_timeframe_request
    from src.setup_engine.setup_families.micro_pullback import MicroPullbackPattern
    *_,inputs = actual_run(monkeypatch,tmp_path)
    source = inputs[0]
    seconds = resolve_intraday_timeframe_request(timeframe=timeframe,requested_bars=50).bar_seconds
    # For 5m, last pullback start is exactly the existing 900s maximum age.
    pullback_start = CLOCK-timedelta(seconds=seconds if seconds <= 180 else 900)
    if incomplete: pullback_start = CLOCK-timedelta(seconds=seconds,microseconds=-1)
    end = pullback_start+timedelta(seconds=seconds)
    bars = [replace(c,timestamp=(end-timedelta(seconds=seconds*(len(source.candles)-i-1))).astimezone(
        timezone(timedelta(hours=-4)))) for i,c in enumerate(source.candles)]
    # A forming breakout starts at/before the original clock.
    bars[-1] = replace(bars[-1],timestamp=CLOCK)
    out = MicroPullbackPattern().evaluate(replace(source,candles=bars,primary_timeframe=timeframe,timeframe=timeframe))
    assert out.detected is not incomplete
    if incomplete: assert out.rejection_reason == "incomplete_pullback_structure"


@pytest.mark.parametrize("state", ["impulse_nan", "pullback_nan", "pullback_negative_volume"])
def test_invalid_underlying_structure_cannot_hide_behind_valid_breakout(monkeypatch,tmp_path,state):
    _,intents,results,_,_ = actual_run(monkeypatch,tmp_path,state=state)
    assert not results[0].detected and results[0].rejection_reason == "INVALID_CANDLE_DATA"
    assert intents == []



@pytest.mark.parametrize("value", [None,float("nan"),float("inf")])
def test_only_the_required_ema9_is_a_micro_indicator_gate(monkeypatch,tmp_path,value):
    from src.setup_engine.setup_families.micro_pullback import MicroPullbackPattern
    *_,inputs = actual_run(monkeypatch,tmp_path)
    source=inputs[0]
    out=MicroPullbackPattern().evaluate(replace(source,indicators=replace(source.indicators,ema20=value,vwap=value)))
    assert out.detected and out.trigger_level == 10.78


def test_missing_required_ema9_is_unavailable(monkeypatch,tmp_path):
    from src.setup_engine.setup_families.micro_pullback import MicroPullbackPattern
    *_,inputs = actual_run(monkeypatch,tmp_path)
    source=inputs[0]
    out=MicroPullbackPattern().evaluate(replace(source,indicators=replace(source.indicators,ema9=None)))
    assert not out.detected and out.rejection_reason == "missing EMA9"


def test_source_soft_volume_keeps_native_confidence_without_a_new_volume_veto(monkeypatch,tmp_path):
    _,intents,results,_,_=actual_run(monkeypatch,tmp_path,state="source_soft_volume")
    assert results[0].detected and results[0].confidence == .55
    assert "volume_soft" in results[0].setup_quality_tags
    assert len(intents) == 1 and intents[0].target_model == "Prior high / HOD"


@pytest.mark.parametrize("field", ["spread","rvol"])
@pytest.mark.parametrize("value", [float("nan"),float("inf"),-1.])
def test_invalid_bound_liquidity_cannot_hide_behind_price_confirmation(monkeypatch,tmp_path,field,value):
    from src.strategies.common.triggers.trigger_micro_pullback import evaluate_micro_pullback_trigger
    _,_,_,calls,_=actual_run(monkeypatch,tmp_path)
    payload,values,_=next(c for c in calls if c[0].get("source")=="canonical_pattern_result")
    out=evaluate_micro_pullback_trigger(payload,{**values,field:value})
    assert not out["trigger_ready_now"] and out["trigger_reason"] == "invalid_liquidity_"+field


def test_native_armed_readiness_is_not_confirmed_standalone_entry(monkeypatch,tmp_path):
    from src.setup_engine.setup_families.micro_pullback import MicroPullbackPattern
    from src.core.engines.decision_engine import DecisionEngine
    from src.strategies.ross_momentum.decision_policy import validate_entry_contract, build_trade_intents
    from src.strategies.ross_momentum.patterns.pattern_evaluator import PatternEvaluationSummary
    *_,inputs=actual_run(monkeypatch,tmp_path)
    source=replace(inputs[0],candles=inputs[0].candles[:-1])
    native=MicroPullbackPattern()
    armed=native.evaluate_readiness(source)
    assert armed.detected and armed.trigger_type == "XL_MICRO_PULLBACK"
    assert not native.evaluate(source).detected  # Last red has not confirmed continuation.
    assert not validate_entry_contract(armed)[0]  # Do not manufacture a target/entry contract.
    decision=DecisionEngine().compute_decision(symbol=source.symbol,levels={},structure={"trend":"UP"},
        setups=[{"setup_family":"MICRO_PULLBACK"}],pattern_results=[armed],session_context="RTH",
        entry_contract_validator=validate_entry_contract)
    assert decision["selected_pattern_id"] is None
    summary=PatternEvaluationSummary([armed],armed,None,False,armed.rationale_text,[])
    assert build_trade_intents("RossMomentumStrategyV1",source.symbol,summary,
                              trigger_ready_now=True,session="RTH_OPEN") == []


@pytest.mark.parametrize("bound", [False,True])
def test_composed_owner_propagates_its_child_clock_without_parent_duration_substitution(monkeypatch,bound):
    from src.execution.trade_management_engine import TradeManagementEngine
    from src.setup_engine.setup_families.bull_flag import BullFlagPattern
    from src.setup_engine.setup_families.micro_pullback import MicroPullbackPattern
    from test_ross_bullflag_micro_management import composed_inputs
    source,now=composed_inputs()
    clock=now-timedelta(seconds=5) if bound else now
    if bound: source=replace(source,observed_at_utc=clock)
    seen=[]
    original=MicroPullbackPattern.evaluate
    def observe(self,inputs):
        out=original(self,inputs)
        seen.append((inputs,out))
        return out
    monkeypatch.setattr(MicroPullbackPattern,"evaluate",observe)
    result=TradeManagementEngine().compose_bull_flag(BullFlagPattern(),source,security_id="conId:123",now=now)
    assert result.detected and result.setup_metadata["relationship"]
    assert len(seen)==1 and seen[0][1].detected
    child=seen[0][0]
    assert child.observed_at_utc == clock
    assert child.timeframe == "10s" and child.primary_timeframe == "1m"
    assert all(c.timestamp+timedelta(seconds=10)<=clock for c in child.candles[:-1])


@pytest.mark.parametrize("clock", [False,"invalid"])
def test_composed_child_cannot_substitute_now_for_an_explicit_invalid_clock(clock):
    from src.execution.trade_management_engine import TradeManagementEngine
    from src.setup_engine.setup_families.bull_flag import BullFlagPattern
    from test_ross_bullflag_micro_management import composed_inputs
    source,now=composed_inputs()
    out=TradeManagementEngine().compose_bull_flag(BullFlagPattern(),replace(source,observed_at_utc=clock),
                                                security_id="conId:123",now=now)
    assert not out.detected and out.rejection_reason == "parent_armed_no_eligible_child"
