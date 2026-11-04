"""Synthetic fresh inputs, real Consolidation detector/registry/dispatch/V1.

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
    (10.0,10.4,9.98,10.3,1200), (10.3,10.42,10.28,10.36,1000),
    (10.36,10.38,10.31,10.35,850), (10.35,10.39,10.32,10.36,840),
    (10.36,10.4,10.33,10.37,830), (10.37,10.39,10.34,10.38,820),
    (10.38,10.4,10.35,10.39,810), (10.4,10.55,10.39,10.53,1400),
]


def actual_run(monkeypatch, tmp_path, *, state="ready", duplicate=False, mode=RunMode.READ_ONLY):
    strategy = _base_strategy(monkeypatch, tmp_path, state="ready")
    rows = [(10.,10.12,9.98,10.08,900)]*42 + TAIL
    execution = [(10.35,10.39,10.32,10.37,100)]*49 + [(10.37,10.56,10.32,10.53,200)]
    if state == "source_at_level": rows[-1] = (10.38,10.55,10.35,10.4,1400)
    if state == "source_just_above": rows[-1] = (10.4,10.55,10.39,10.4+1e-9,1400)
    if state == "source_wide": rows[-3] = (10.37,11.,10.34,10.38,820)
    if state == "source_flat": rows[-6:-1] = [(10.35,10.35,10.35,10.35,800)]*5
    if state == "source_soft_volume": rows[-1] = (*rows[-1][:4],100)
    if state == "waiting": execution[-1] = (10.35,10.39,10.32,10.38,200)
    if state == "execution_touch": execution[-1] = (10.35,10.4,10.32,10.4,200)
    if state == "execution_equal_volume": execution[-1] = (*execution[-1][:4],100)
    if state == "execution_weak_volume": execution[-1] = (*execution[-1][:4],50)
    if state == "execution_zero_volume": execution[-5:] = [(*row[:4],0) for row in execution[-5:]]
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
    if state == "source_forming": data["1m"][-1] = replace(data["1m"][-1],timestamp=CLOCK.replace(second=0))
    if state in {"source_exact_completion","source_before_completion"}:
        data["1m"][-1] = replace(data["1m"][-1],timestamp=CLOCK-timedelta(seconds=60)+
            timedelta(microseconds=1 if state == "source_before_completion" else 0))
    if state == "confirm_extremes": data["1m"][-1] = replace(data["1m"][-1],high=99.,low=1.)
    if state == "forming_tail":
        data["1m"].append(replace(data["1m"][-1],high=99.,low=1.,timestamp=CLOCK.replace(second=0)))
    if state in {"completed_at_max_age","completed_over_max_age","stale_prefix_forming_tail"}:
        tight = [(10.37,10.4,10.35,10.38,800)]*49 + [(10.4,10.43,10.37,10.42,1400)]
        age = 630 if state == "stale_prefix_forming_tail" else 180
        end = CLOCK-timedelta(seconds=age,microseconds=1 if state == "completed_over_max_age" else 0)
        data["1m"] = _candles(tight,end=end)
        data["1m"].append(replace(data["1m"][-1],open=10.42,high=10.6,low=10.4,close=10.53,
                                  timestamp=CLOCK.replace(second=0)))
    monkeypatch.setattr("src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda *,timeframe="1m",limit=50,**kw:list(data[timeframe])[-limit:])
    registry = RossPatternRegistry()
    registry._patterns = build_tradeable_patterns(["CONSOLIDATION_BREAKOUT"])
    if duplicate: registry._patterns.extend(build_tradeable_patterns(["CONSOLIDATION_BREAKOUT"]))
    strategy._pattern_registry = registry
    results, calls, inputs = [], [], []
    original_run = registry.run
    def observed_run(source, **kwargs):
        inputs.append(source)
        output = original_run(source, **kwargs)
        results.extend(output)
        return output
    monkeypatch.setattr(registry,"run",observed_run)
    original = TRIGGER_EVALUATOR_REGISTRY["CONSOLIDATION_BREAKOUT"]
    def observed_trigger(payload, stream):
        output = original(payload, stream)
        calls.append((payload,stream,output))
        return output
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,"CONSOLIDATION_BREAKOUT",observed_trigger)
    row = {**_watchlist_row(),"last_price":10.53,"bid":10.52,"ask":10.54}
    if state == "negative_spread": row["spread"] = -.01
    if state == "nan_spread": row["spread"] = float("nan")
    if state == "inf_spread": row["spread"] = float("inf")
    if state == "nan_rvol": row["rvol"] = float("nan")
    if state == "inf_rvol": row["rvol"] = float("inf")
    if state == "negative_rvol": row["rvol"] = -1.
    intents = strategy.process_watchlist(watchlist=[row],snapshots={"UPC":replace(_snapshot(),last=10.53,bid=10.52,ask=10.54)},
        session_label="RTH_OPEN",session_phase="RTH_OPEN",timestamp_utc="synthetic-consolidation",mode=mode)
    return strategy,intents,results,calls,inputs


def test_native_detector_registered_evaluator_selection_actual_v1(monkeypatch,tmp_path):
    strategy,intents,results,calls,inputs = actual_run(monkeypatch,tmp_path)
    assert len(results) == 1 and results[0].detected
    result = results[0]
    assert result.trigger_level == 10.4 and result.stop_level == result.invalidation_level == 10.31
    own = [c for c in calls if c[0].get("source") == "canonical_pattern_result"]
    assert len(own) == len(intents) == 1, strategy.last_symbol_terminal_outcomes
    assert own[0][0]["canonical_result_index"] == 0 and own[0][2]["trigger_ready_now"]
    intent = intents[0]
    assert intent.entry_price == result.trigger_level
    assert intent.stop_loss_price == result.stop_level and intent.invalidation_level == result.invalidation_level
    assert intent.target_model == result.target_suggestion == "Range expansion"
    assert result.rationale_text in intent.rationale
    assert intent.setup_family_id == "CONSOLIDATION_BREAKOUT" and intent.take_profit_price is None
    assert intent.setup_metadata["canonical_result_index"] == 0
    assert intent.setup_metadata["execution_stream"]["observed_at_utc"] == inputs[0].observed_at_utc.isoformat()
    assert inputs[0].levels.hod == 10.55  # Context cannot replace selected range high.
    assert intent.timestamp_utc == "synthetic-consolidation" and intent.decision_id is None


@pytest.mark.parametrize("state", ["source_at_level","source_wide","source_flat","waiting",
    "execution_weak_volume","execution_zero_volume","source_missing","source_stale","execution_missing","execution_stale",
    "source_future","execution_future","source_nan_low","execution_nan_low","source_invalid_range","execution_invalid_range",
    "source_inf_volume","execution_inf_volume","source_forming","stale_prefix_forming_tail","completed_over_max_age",
    "negative_spread","nan_spread","inf_spread","nan_rvol","inf_rvol","negative_rvol"])
def test_invalid_unavailable_or_unconfirmed_inputs_do_not_form_intents(monkeypatch,tmp_path,state):
    _,intents,results,calls,inputs = actual_run(monkeypatch,tmp_path,state=state)
    assert intents == []
    if state.startswith("execution_"):
        assert results[0].detected
    if state in {"source_stale","stale_prefix_forming_tail","completed_over_max_age"}:
        assert results[0].rejection_reason == "completed_source_stale"
        if state != "source_stale": assert inputs[0].timeframe_provenance["1m"] == "PRESENT"
    if state in {"source_future","source_nan_low","source_invalid_range","source_inf_volume"}:
        assert results[0].rejection_reason == ("FUTURE_CANDLE_DATA" if state == "source_future" else "INVALID_CANDLE_DATA")
    if state in {"execution_future","execution_nan_low","execution_invalid_range","execution_inf_volume"}:
        own = [c for c in calls if c[0].get("source") == "canonical_pattern_result"]
        assert len(own) == 1 and own[0][2]["trigger_reason"] == (
            "consolidation_future_candle_data" if state == "execution_future" else "consolidation_invalid_candle_data")


@pytest.mark.parametrize("state", ["execution_touch","execution_equal_volume","source_soft_volume","forming_tail",
                                  "completed_at_max_age","source_exact_completion","confirm_extremes","source_just_above"])
def test_existing_valid_boundaries_and_completed_structure_remain_eligible(monkeypatch,tmp_path,state):
    _,intents,results,_,_ = actual_run(monkeypatch,tmp_path,state=state)
    assert results[0].detected and len(intents) == 1
    assert intents[0].entry_price == results[0].trigger_level == 10.4
    if state == "source_soft_volume":
        assert not results[0].setup_metadata["breakout_volume_confirmed"]
        assert "volume_soft" in results[0].setup_quality_tags
        assert results[0].confidence == .55


def test_source_one_microsecond_before_completion_is_not_a_close_confirmed_breakout(monkeypatch,tmp_path):
    _,intents,results,_,_ = actual_run(monkeypatch,tmp_path,state="source_before_completion")
    assert intents == [] and not results[0].detected


def test_retained_intent_evidence_cannot_follow_later_mutation(monkeypatch,tmp_path):
    _,intents,results,calls,inputs = actual_run(monkeypatch,tmp_path)
    intent = intents[0]
    saved = asdict(intent)
    own = next(p for p,_,_ in calls if p.get("source") == "canonical_pattern_result")
    own["execution_stream"]["timeframe_provenance"].clear()
    own["trigger_level"] = 99.
    results[0].setup_metadata["breakout_volume_confirmed"] = False
    inputs[0].candles.clear()
    assert asdict(intent) == saved


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


@pytest.mark.parametrize("reverse", [False,True])
def test_distinct_native_duplicate_contracts_cannot_borrow_ready_receipts(monkeypatch,tmp_path,reverse):
    """Separate adversarial selector boundary; never injected into V1 acceptance."""
    from copy import deepcopy
    from src.core.engines.trigger_engine import TriggerEngine
    from src.setup_engine.setup_families.breakouts import ConsolidationBreakoutPattern
    strategy,_,results,calls,inputs = actual_run(monkeypatch,tmp_path)
    shifted = replace(inputs[0],candles=[replace(c,open=c.open+1,high=c.high+1,low=c.low+1,close=c.close+1)
                                       for c in inputs[0].candles])
    second = ConsolidationBreakoutPattern().evaluate(shifted)
    assert second.detected and second.trigger_level == 11.4
    native = [second,results[0]] if reverse else [results[0],second]
    setups = strategy._canonical_pattern_trigger_candidates(native,symbol="UPC",existing_triggers=[])
    stream = next(p["execution_stream"] for p,_,_ in calls if p.get("source") == "canonical_pattern_result")
    for setup in setups: setup["execution_stream"] = deepcopy(stream)
    triggers = TriggerEngine().evaluate_triggers(symbol="UPC",setups=setups,
        candles=inputs[0].timeframe_candles["10s"],levels={},structure={})
    waiting_index = 0 if reverse else 1
    waiting = strategy._select_trigger_candidate(setup_family_id="CONSOLIDATION_BREAKOUT",trigger_candidates=triggers,
                                                selected_candidate_index=waiting_index)
    ready = strategy._select_trigger_candidate(setup_family_id="CONSOLIDATION_BREAKOUT",trigger_candidates=triggers,
                                              selected_candidate_index=1-waiting_index)
    assert not waiting["trigger_ready_now"] and ready["trigger_ready_now"]
    assert waiting["trigger_price_reference"] == second.trigger_level
    assert strategy._select_trigger_candidate(setup_family_id="CONSOLIDATION_BREAKOUT",trigger_candidates=triggers) is None
    reasons = []
    assert strategy._build_trade_from_pattern(second,inputs[0],selected_contract=second,selected_trigger=ready,
                                             rejection_reasons=reasons) is None
    assert reasons == ["selected_invalidation_authority_mismatch"]


@pytest.mark.parametrize("stream", [None,{}, {"observed_at_utc":None}])
def test_active_canonical_receipt_cannot_lose_clock_authority(stream):
    from src.strategies.common.triggers.trigger_flat_top_breakout import evaluate_consolidation_breakout_trigger
    payload = {"setup_family_id":"CONSOLIDATION_BREAKOUT","source":"canonical_pattern_result",
               "trigger_level":10.4,"invalidation_level":10.31,"execution_stream":stream}
    candles = [{"open":10.37,"high":10.56,"low":10.32,"close":10.53,"volume":200}]*5
    outcome = evaluate_consolidation_breakout_trigger(payload,{"candles":candles})
    assert not outcome["trigger_ready_now"] and outcome["trigger_reason"] == "consolidation_invalid_candle_timestamps"


@pytest.mark.parametrize("mode", [RunMode.READ_ONLY,RunMode.PAPER,RunMode.LIVE])
def test_invalid_active_evidence_is_not_mode_permission(monkeypatch,tmp_path,mode):
    _,intents,_,_,_ = actual_run(monkeypatch,tmp_path,state="execution_future",mode=mode)
    assert intents == []


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


@pytest.mark.parametrize("alias", ["1min","M1"])
def test_recognized_component_timeframe_alias_cannot_expand_freshness(monkeypatch,tmp_path,alias):
    from src.setup_engine.setup_families.breakouts import ConsolidationBreakoutPattern
    _,_,_,_,inputs = actual_run(monkeypatch,tmp_path,state="completed_over_max_age")
    result = ConsolidationBreakoutPattern().evaluate(replace(inputs[0],primary_timeframe=alias))
    assert not result.detected and result.rejection_reason == "completed_source_stale"


@pytest.mark.parametrize("clock", [None,datetime(2026,9,16,14,35,30),"not-a-clock"])
def test_active_source_cannot_lose_original_clock(monkeypatch,tmp_path,clock):
    from src.setup_engine.setup_families.breakouts import ConsolidationBreakoutPattern
    _,_,_,_,inputs = actual_run(monkeypatch,tmp_path)
    result = ConsolidationBreakoutPattern().evaluate(replace(inputs[0],observed_at_utc=clock))
    assert not result.detected and result.rejection_reason == "INVALID_CANDLE_TIMESTAMPS"


def test_all_forming_source_remains_unavailable(monkeypatch,tmp_path):
    from src.setup_engine.setup_families.breakouts import ConsolidationBreakoutPattern
    _,_,_,_,inputs = actual_run(monkeypatch,tmp_path)
    forming = replace(inputs[0].candles[-1],timestamp=CLOCK.replace(second=0))
    result = ConsolidationBreakoutPattern().evaluate(replace(inputs[0],candles=[forming]))
    assert not result.detected and result.rejection_reason == "insufficient candles"


@pytest.mark.parametrize("timeframe", ["10s","1m","5m"])
@pytest.mark.parametrize("forming", [False,True])
def test_component_completion_uses_existing_request_duration(monkeypatch,tmp_path,timeframe,forming):
    from src.adapters.data.historical_bar_timeframes import resolve_intraday_timeframe_request
    from src.setup_engine.setup_families.breakouts import ConsolidationBreakoutPattern
    _,_,_,_,inputs = actual_run(monkeypatch,tmp_path)
    source = inputs[0]
    seconds = resolve_intraday_timeframe_request(timeframe=timeframe,requested_bars=50).bar_seconds
    end = CLOCK-timedelta(seconds=seconds)+timedelta(microseconds=1 if forming else 0)
    zone = timezone(timedelta(hours=-4))
    candles = [replace(c,timestamp=(end-timedelta(seconds=seconds*(len(source.candles)-i-1))).astimezone(zone))
               for i,c in enumerate(source.candles)]
    result = ConsolidationBreakoutPattern().evaluate(replace(source,candles=candles,
                                                           primary_timeframe=timeframe,timeframe=timeframe))
    assert result.detected is not forming
    if result.detected: assert result.trigger_level == 10.4 and result.stop_level == 10.31


@pytest.mark.parametrize("wide", [False,True])
def test_existing_one_percent_range_width_boundary(monkeypatch,tmp_path,wide):
    from src.setup_engine.setup_families.breakouts import ConsolidationBreakoutPattern
    _,_,_,_,inputs = actual_run(monkeypatch,tmp_path)
    source = inputs[0]
    candles = list(source.candles)
    low = 99.-(1e-8 if wide else 0)
    candles[-6:-1] = [replace(c,open=99.2,high=100.,low=low,close=99.8) for c in candles[-6:-1]]
    candles[-1] = replace(candles[-1],open=100.,high=100.5,low=99.9,close=100.4)
    result = ConsolidationBreakoutPattern().evaluate(replace(source,candles=candles))
    assert result.detected is not wide
    if wide: assert result.rejection_reason == "consolidation too wide"
    else: assert result.trigger_level == 100. and result.stop_level == result.invalidation_level == 99.


@pytest.mark.parametrize("spread,rvol", [(None,None),(.06,1.05)])
def test_component_does_not_inherit_flat_top_liquidity_cutoffs(monkeypatch,tmp_path,spread,rvol):
    from src.setup_engine.setup_families.breakouts import ConsolidationBreakoutPattern
    _,_,_,_,inputs = actual_run(monkeypatch,tmp_path)
    source = replace(inputs[0],liquidity_context=replace(inputs[0].liquidity_context,spread=spread,rvol=rvol))
    result = ConsolidationBreakoutPattern().evaluate(source)
    assert result.detected  # Component classification, not Focus or execution permission.


def test_component_declared_clock_is_validated_even_without_a_family_label():
    from src.strategies.common.triggers.trigger_flat_top_breakout import evaluate_consolidation_breakout_trigger
    payload = {"trigger_level":10.4,"invalidation_level":10.31,"execution_stream":{"observed_at_utc":None}}
    candles = [{"open":10.37,"high":10.56,"low":10.32,"close":10.53,"volume":200}]*5
    outcome = evaluate_consolidation_breakout_trigger(payload,{"candles":candles})
    assert not outcome["trigger_ready_now"] and outcome["trigger_reason"] == "consolidation_invalid_candle_timestamps"
