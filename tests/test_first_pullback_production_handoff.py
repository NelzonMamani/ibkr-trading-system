"""Actual runtime RF detector/V1; synthetic fresh market data, no acquisition."""
from dataclasses import replace
from datetime import timedelta

import pytest

from src.config.runtime_config import RunMode
from src.setup_engine.setup_families.ross_families import FirstPullbackPattern
from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1
from test_key_level_break_production_handoff import forbid_io
from test_pr1082_trigger_to_intent_terminal_semantics import (
    _base_strategy, _candles, _inputs, _snapshot, _watchlist_row, _reset_config, FakeRegistry,
)


ROWS = [(9.3,9.7,9.25,9.65,1000), (9.65,10.1,9.6,10.05,1300),
        (10.05,10.5,10.,10.4,1600), (10.4,10.42,10.2,10.3,800),
        (10.3,10.35,10.15,10.22,700), (10.22,10.6,10.2,10.55,1700)]


def result(rows=None):
    return FirstPullbackPattern().evaluate(replace(_inputs(), candles=_candles(rows or ROWS)))


def test_actual_detector_exports_own_contract_not_context():
    detected = result()
    assert detected.detected
    assert detected.trigger_level == 10.42
    assert detected.stop_level == 10.15
    assert detected.invalidation_level == 10.15
    assert detected.setup_family_id == "FIRST_PULLBACK"
    assert detected.trigger_type == "PULLBACK_HIGH_BREAK"
    assert detected.target_suggestion == "Retest impulse high then measured extension"
    assert detected.setup_metadata["pullback_high"] == 10.42
    assert detected.setup_metadata["pullback_low"] == 10.15


def run(monkeypatch, tmp_path, *, state="ready", supplied=None, session="RTH_OPEN", execution_last=None):
    strategy = _base_strategy(monkeypatch, tmp_path, state="ready")
    rows = [(9.2,9.3,9.1,9.25,900)] * 44 + ROWS
    execution = list(rows)
    if state == "waiting": execution[-1] = (10.22,10.42,10.2,10.42,1700)
    elif state == "invalidated": execution[-1] = (10.22,10.3,10.1,10.15,1700)
    if execution_last is not None: execution[-1] = execution_last
    data = {tf: _candles(execution if tf == "10s" else rows, step_seconds=step)
            for tf,step in (("1m",60),("5m",300),("10s",10))}
    if state == "missing": data["10s"] = []
    if state == "stale": data["10s"] = [replace(c,timestamp=c.timestamp-timedelta(minutes=10)) for c in data["10s"]]
    if state == "malformed": data["10s"][-1] = replace(data["10s"][-1],close=float("nan"))
    if state == "missing_primary": data["1m"] = []
    if state == "stale_primary": data["1m"] = [replace(c,timestamp=c.timestamp-timedelta(minutes=10)) for c in data["1m"]]
    monkeypatch.setattr("src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
                        lambda *,timeframe="1m",**kwargs: data[timeframe])
    captured = []
    if supplied is None:
        registry = RossPatternRegistry(); registry._patterns = [FirstPullbackPattern()]
        original = registry.run
        def observe(*args, **kwargs):
            values = original(*args,**kwargs); captured.extend(values); return values
        monkeypatch.setattr(registry,"run",observe)
        strategy._pattern_registry = registry
    else:
        captured = supplied; strategy._pattern_registry = FakeRegistry(supplied)
    seen = []
    evaluator = TRIGGER_EVALUATOR_REGISTRY["FIRST_PULLBACK"]
    def observe_trigger(payload,inputs):
        seen.append((payload,inputs)); return evaluator(payload,inputs)
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,"FIRST_PULLBACK",observe_trigger)
    row = {**_watchlist_row(),"last_price":10.55,"bid":10.54,"ask":10.56}
    snapshot = replace(_snapshot(),last=10.55,bid=10.54,ask=10.56)
    intents = strategy.process_watchlist(watchlist=[row],snapshots={"UPC":snapshot},
        session_label=session,session_phase=session,timestamp_utc="synthetic-first",
        mode=RunMode.READ_ONLY)
    return strategy,intents,captured,seen


@pytest.mark.parametrize("state",["ready","waiting","invalidated","missing","stale","malformed"])
def test_actual_runtime_detector_to_registered_trigger_and_intent(monkeypatch,tmp_path,state):
    strategy,intents,results,seen = run(monkeypatch,tmp_path,state=state)
    assert results and results[0].detected
    triggers = [t for t in strategy._failure_trace_collector._symbols[-1].input_summary["trigger_candidates"]
                if t.get("setup_family_id") == "FIRST_PULLBACK"]
    assert len(triggers) == 1
    own = triggers[0]
    assert own["canonical_result_index"] == 0
    assert own["trigger_price_reference"] == results[0].trigger_level
    assert own["stop_price_reference"] == results[0].stop_level
    assert own["invalidation_price_reference"] == results[0].invalidation_level
    if state == "ready":
        assert len(intents) == 1, strategy.last_symbol_terminal_outcomes
        assert seen and seen[0][0]["setup_metadata"] == results[0].setup_metadata
        assert seen[0][1]["candles"][-1].timestamp-seen[0][1]["candles"][-2].timestamp == timedelta(seconds=10)
        intent = intents[0]
        assert intent.setup_family_id == "FIRST_PULLBACK"
        assert intent.entry_price == 10.42 and intent.stop_loss_price == 10.15
        assert intent.invalidation_level == 10.15
        assert intent.target_model == results[0].target_suggestion
        assert results[0].rationale_text in intent.rationale
        assert intent.timestamp_utc == "synthetic-first"
        assert intent.take_profit_price is None
        assert own["execution_stream"]["execution_trigger_timeframe"] == "10s"
        assert own["execution_stream"]["timeframe_substitution"] is False
    else:
        assert intents == [] and not own["trigger_ready_now"]
        reasons = {"waiting":"awaiting_pullback_break","invalidated":"at_or_below_invalidation",
                   "missing":"execution_stream_missing","stale":"execution_stream_stale",
                   "malformed":"first_pullback_invalid_candle_data"}
        assert own["trigger_reason"] == reasons[state]


@pytest.mark.parametrize("reverse",[False,True])
def test_duplicate_occurrence_cannot_borrow_ready_contract(monkeypatch,tmp_path,reverse):
    valid = result()
    waiting = replace(valid,confidence=.99,trigger_level=11.,setup_metadata={"occurrence":"waiting"})
    supplied = [waiting,valid] if reverse else [valid,waiting]
    strategy,intents,_,_ = run(monkeypatch,tmp_path,supplied=supplied)
    assert intents == []
    triggers = [t for t in strategy._failure_trace_collector._symbols[-1].input_summary["trigger_candidates"]
                if t.get("setup_family_id") == "FIRST_PULLBACK"]
    selected = next(t for t in triggers if t["canonical_result_index"] == supplied.index(waiting))
    other = next(t for t in triggers if t["canonical_result_index"] != supplied.index(waiting))
    assert not selected["trigger_ready_now"] and other["trigger_ready_now"]


@pytest.mark.parametrize("updates",[{"target_suggestion":None},{"rationale_text":""},
                                     {"stop_level":11.},{"trigger_level":"bad"}])
def test_invalid_contract_no_intent(monkeypatch,tmp_path,updates):
    strategy,intents,_,_ = run(monkeypatch,tmp_path,supplied=[replace(result(),**updates)])
    assert intents == []
    assert not strategy.last_symbol_terminal_outcomes["UPC"]["intent_emitted"]


@pytest.mark.parametrize("fault,reason",[("short","insufficient candles"),("impulse","missing initial impulse"),
    ("green","pullback bars not controlled"),("deep","pullback too deep"),("equal_high","no reclaim trigger")])
def test_existing_runtime_detector_structure_boundaries(fault,reason):
    rows = list(ROWS)
    if fault == "short": rows = rows[1:]
    elif fault == "impulse": rows[2] = (10.05,10.5,9.,9.2,1600)
    elif fault == "green": rows[3] = (10.2,10.42,10.2,10.3,800)
    elif fault == "deep": rows[4] = (10.3,10.35,9.8,10.22,700)
    elif fault == "equal_high": rows[-1] = (10.22,10.6,10.2,10.42,1700)
    detected = result(rows)
    assert not detected.detected and detected.rejection_reason == reason


@pytest.mark.parametrize("low,detected",[(9.9375,True),(9.937499,False)])
def test_existing_45_percent_retrace_boundary(low,detected):
    rows = list(ROWS)
    rows[4] = (10.3,10.35,low,10.22,700)
    output = result(rows)
    assert output.detected is detected
    if detected:
        assert output.stop_level == low and output.invalidation_level == low
    else:
        assert output.rejection_reason == "pullback too deep"


@pytest.mark.parametrize("reverse",[False,True])
def test_rejected_duplicate_cannot_supply_winners_levels(monkeypatch,tmp_path,reverse):
    valid = result()
    invalid = replace(valid,target_suggestion=None,trigger_level=99.,stop_level=90.,
                      invalidation_level=90.,rationale_text="Rejected duplicate")
    supplied = [invalid,valid] if reverse else [valid,invalid]
    strategy,intents,_,seen = run(monkeypatch,tmp_path,supplied=supplied)
    assert len(intents) == 1, strategy.last_symbol_terminal_outcomes
    assert intents[0].entry_price == valid.trigger_level
    assert intents[0].stop_loss_price == valid.stop_level
    assert intents[0].invalidation_level == valid.invalidation_level
    assert intents[0].target_model == valid.target_suggestion
    assert invalid.rationale_text not in intents[0].rationale
    own = next(p for p,_ in seen if p["canonical_result_index"] == supplied.index(valid))
    assert own["setup_metadata"] == valid.setup_metadata


@pytest.mark.parametrize("state",["missing_primary","stale_primary"])
def test_required_structure_timeframe_cannot_be_substituted(monkeypatch,tmp_path,state,capsys):
    strategy,intents,results,seen = run(monkeypatch,tmp_path,state=state)
    assert intents == []
    assert not any(r.detected for r in results)
    assert seen == []
    trace = strategy._failure_trace_collector._symbols[-1]
    if state == "missing_primary":
        assert trace.pre_registry_failure_reason == "failed_to_build_inputs"
        assert trace.pattern_traces == []
    else:
        assert not strategy.last_symbol_terminal_outcomes["UPC"]["intent_emitted"]
        assert "timeframe:1m" in capsys.readouterr().out


def test_steady_session_uses_real_one_minute_without_requiring_fast_stream(monkeypatch,tmp_path):
    strategy,intents,results,seen = run(monkeypatch,tmp_path,state="missing",session="RTH_MID")
    assert len(intents) == 1, strategy.last_symbol_terminal_outcomes
    assert results[0].detected and seen
    candles = seen[0][1]["candles"]
    assert candles[-1].timestamp-candles[-2].timestamp == timedelta(minutes=1)
    own = next(t for t in strategy._failure_trace_collector._symbols[-1].input_summary["trigger_candidates"]
               if t.get("setup_family_id") == "FIRST_PULLBACK")
    assert own["execution_stream"]["execution_trigger_timeframe"] == "1m"
    assert own["execution_stream"]["timeframe_substitution"] is False


@pytest.mark.parametrize("confirmation", [
    (10.22,10.6,10.2,10.55,1700),
    (10.22,50.,10.2,10.55,1700),
    (10.22,10.6,10.16,10.55,1700),
])
def test_confirming_candle_cannot_move_prior_pullback_anchors(confirmation):
    from copy import deepcopy
    rows = list(ROWS); rows[-1] = confirmation
    inputs = replace(_inputs(), candles=_candles(rows))
    before = deepcopy(inputs)
    output = FirstPullbackPattern().evaluate(inputs)
    assert output.detected
    assert (output.trigger_level, output.stop_level, output.invalidation_level) == (10.42,10.15,10.15)
    assert output.setup_metadata["pullback_high"] == 10.42
    assert output.setup_metadata["pullback_low"] == 10.15
    assert inputs == before  # Includes original candle timestamps and source metadata.


def test_window_excludes_prefix_and_impulse_extremes():
    prefix = [(9.2,100.,.01,9.25,1000)]
    output = result(prefix + ROWS)
    assert output.detected
    assert output.trigger_level == 10.42  # Neither prefix100 nor impulse10.5.
    assert output.stop_level == 10.15  # Neither prefix.01 nor impulse9.25.


@pytest.mark.parametrize("index,high,low",[(3,10.45,10.2),(4,10.35,10.12)])
def test_each_pullback_bar_supplies_its_actual_extreme(index,high,low):
    rows = list(ROWS)
    o,_,_,c,v = rows[index]; rows[index] = (o,high,low,c,v)
    output = result(rows)
    assert output.detected
    assert output.trigger_level == max(row[1] for row in rows[-3:-1])
    assert output.stop_level == min(row[2] for row in rows[-3:-1])
    assert output.invalidation_level == output.stop_level


@pytest.mark.parametrize("close,ready,reason", [
    (10.42,False,"awaiting_pullback_break"),
    (10.419,False,"awaiting_pullback_break"),
    (10.421,True,"pullback_high_broken"),
    (10.15,False,"at_or_below_invalidation"),
])
def test_execution_wick_touch_is_not_close_break(monkeypatch,tmp_path,close,ready,reason):
    # High always exceeds the trigger: only the existing close rule can confirm.
    low = min(10.2,close)
    strategy,intents,results,seen = run(monkeypatch,tmp_path,
        execution_last=(10.22,10.6,low,close,1700))
    assert results[0].detected and seen
    own = next(t for t in strategy._failure_trace_collector._symbols[-1].input_summary["trigger_candidates"]
               if t.get("setup_family_id") == "FIRST_PULLBACK")
    assert own["trigger_ready_now"] is ready and own["trigger_reason"] == reason
    assert len(intents) == (1 if ready else 0)
    assert own["trigger_price_reference"] == 10.42
    assert own["stop_price_reference"] == own["invalidation_price_reference"] == 10.15


@pytest.mark.parametrize("index,field,value", [
    (-3,"low",float("nan")), (-2,"high",float("inf")),
    (-6,"open",float("nan")), (-1,"close",float("nan")),
    (-3,"low",10.41), (-2,"high",10.20),
    (-3,"low","bad"), (-3,"low",None),
])
def test_malformed_primary_window_cannot_mint_numeric_authority(monkeypatch,tmp_path,index,field,value):
    original = _candles
    if value is None or isinstance(value,str):
        # Nonnumeric source values can fail in the shared input builder before
        # RF runs; test this owner's boundary directly without changing it.
        candles = original(ROWS)
        candles[index] = replace(candles[index],**{field:value})
        output = FirstPullbackPattern().evaluate(replace(_inputs(),candles=candles))
        assert not output.detected and output.rejection_reason == "malformed_candles"
        return
    def malformed(rows, **kwargs):
        candles = original(rows,**kwargs)
        if kwargs.get("step_seconds") == 60:
            candles[index] = replace(candles[index],**{field:value})
        return candles
    monkeypatch.setitem(globals(),"_candles",malformed)
    strategy,intents,results,seen = run(monkeypatch,tmp_path)
    assert intents == []
    assert results and not results[0].detected
    assert results[0].rejection_reason == "malformed_candles"
    assert seen == []
