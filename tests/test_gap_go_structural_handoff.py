"""Synthetic inputs; no production stop policy is supplied by these controls."""
from dataclasses import replace
from datetime import timedelta

import pytest

from src.setup_engine.registry import build_tradeable_patterns
from src.setup_engine.setup_families.ross_families import GapGoPattern
from src.strategies.ross_momentum.decision_policy import validate_entry_contract
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1 as V1
from src.core.engines.trigger_engine import TriggerEngine
from test_key_level_break_production_handoff import forbid_io
from test_gap_go_pipeline_activation import _pattern_inputs


def source(variant="PMH_BREAK"):
    data = _pattern_inputs(rvol=2.0, spread=0.01)
    keys = {"PULLBACK_HIGH": 9.9, "PULLBACK_LOW": 4.0}
    pmh, hod = 5.7, 6.0
    if variant == "HOD_BREAK": pmh = None
    if variant == "BREAK_AND_HOLD":
        pmh = hod = None
        keys["OPENING_RANGE_HIGH"] = 5.8
    if variant == "undefined": pmh = hod = None
    return replace(data, timeframe="1m", primary_timeframe="1m",
        levels=replace(data.levels, premarket_high=pmh, hod=hod, key_levels=keys),
        observed_at_utc=data.candles[-1].timestamp+timedelta(minutes=1),
        timeframe_provenance={"1m":"PRESENT"})


@pytest.mark.parametrize("variant,reference", [("PMH_BREAK",5.7),("HOD_BREAK",6.0),("BREAK_AND_HOLD",5.8)])
def test_measured_reference_not_generic_anchor(variant, reference):
    result = GapGoPattern().evaluate(source(variant))
    assert result.detected
    assert result.trigger_type == variant
    assert result.trigger_level == reference
    assert result.stop_level is None and result.invalidation_level is None
    assert result.setup_metadata["entry_contract_block_reason"] == "gap_go_structural_stop_authority_missing"
    assert validate_entry_contract(result)[0] is False


def test_prior_close_pressure_without_named_reference_is_blocked():
    result = GapGoPattern().evaluate(source("undefined"))
    assert not result.detected
    assert result.rejection_reason == "GAP_GO_TRIGGER_REFERENCE_UNDEFINED"


def synthetic_complete(result):
    """Plumbing ONLY: invented test stop is not production policy or certification."""
    metadata = dict(result.setup_metadata)
    metadata.pop("entry_contract_block_reason")
    metadata["synthetic_stop_for_plumbing_only"] = True
    return replace(result, stop_level=5.0, invalidation_level=5.1, setup_metadata=metadata)


def bridge(result):
    return V1._canonical_pattern_trigger_candidates(V1.__new__(V1), [result],
        symbol="GAPX", existing_triggers=[])


def test_unmodified_production_contract_remains_blocked():
    result = GapGoPattern().evaluate(source())
    assert validate_entry_contract(result) == (False, "gap_go_structural_stop_authority_missing")
    assert bridge(result) == []


@pytest.mark.parametrize("variant,reference", [("PMH_BREAK",5.7),("HOD_BREAK",6.0),("BREAK_AND_HOLD",5.8)])
@pytest.mark.parametrize("state", ["touch", "below", "above"])
def test_synthetic_contract_uses_special_dispatch_exact_reference(monkeypatch, variant, reference, state):
    data = source(variant)
    result = synthetic_complete(GapGoPattern().evaluate(data))
    setup = bridge(result)[0]
    clock = data.observed_at_utc
    setup["execution_stream"] = {"observed_at_utc": clock.isoformat(),
        "execution_trigger_timeframe":"10s", "stream_provenance":"PRESENT"}
    price = reference + {"touch":0.0,"below":-0.01,"above":0.01}[state]
    candles = [replace(data.candles[-1], timestamp=clock-timedelta(seconds=i),
        open=price, high=price, low=price, close=price) for i in (20,10)]
    seen = []
    original = TriggerEngine._evaluate_gap_go_trigger
    def observed(self, **kwargs):
        seen.append(kwargs)
        return original(self, **kwargs)
    monkeypatch.setattr(TriggerEngine,"_evaluate_gap_go_trigger",observed)
    out = TriggerEngine().evaluate_triggers(symbol="GAPX", candles=candles,
        setups=[setup], levels={"premarket_high":999.,"hod":999.}, structure={})[0]
    assert len(seen) == 1
    assert seen[0]["trigger_price_reference"] == reference
    assert seen[0]["levels"] == {}  # No unrelated level map can override selection.
    assert out["trigger_ready_now"] == (state != "below")
    assert out["canonical_result_index"] == 0
    assert out["stop_price_reference"] == 5.0
    assert out["invalidation_price_reference"] == 5.1


@pytest.mark.parametrize("field", ["open","high","low","close","volume"])
@pytest.mark.parametrize("bad", [float("nan"),float("inf")])
def test_source_nonfinite_rejects(field,bad):
    data=source(); bars=list(data.candles); bars[0]=replace(bars[0], **{field:bad})
    result=GapGoPattern().evaluate(replace(data,candles=bars))
    assert not result.detected
    assert "INVALID_CANDLE_DATA" in result.rejection_reason


def test_completed_source_boundary_excludes_newer_pressure():
    data=source()
    # Earlier four bars are below PMH; last bar cannot create context until closed.
    earlier=[replace(c,open=5.2,high=5.3,low=5.1,close=5.2) for c in data.candles[:-1]]
    bars=earlier+[data.candles[-1]]
    before=replace(data,candles=bars,observed_at_utc=data.observed_at_utc-timedelta(microseconds=1))
    assert not GapGoPattern().evaluate(before).detected
    result=GapGoPattern().evaluate(replace(data,candles=bars))
    assert result.detected and result.trigger_level == 5.7
    assert result.setup_metadata["completed_bar_count"] == 5


def actual_v1(monkeypatch,tmp_path,*,synthetic=False,state="ready"):
    from src.config.runtime_config import RunMode
    from test_pr1082_trigger_to_intent_terminal_semantics import (
        _base_strategy,_candles,_watchlist_row,_snapshot)
    strategy=_base_strategy(monkeypatch,tmp_path,state="ready")
    rows=[(9.5+i*.011,9.53+i*.011,9.48+i*.011,9.52+i*.011,900+i*20) for i in range(50)]
    data={tf:_candles(rows,step_seconds=step) for tf,step in (("1m",60),("5m",300),("10s",10))}
    if state=="missing": data["10s"]=[]
    if state=="stale": data["10s"]=[replace(c,timestamp=c.timestamp-timedelta(minutes=10)) for c in data["10s"]]
    if state=="stale_source": data["1m"]=[replace(c,timestamp=c.timestamp-timedelta(minutes=10)) for c in data["1m"]]
    if state=="malformed": data["1m"][0]=replace(data["1m"][0],low=float("nan"))
    monkeypatch.setattr("src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda *,timeframe="1m",**kw:data[timeframe])
    registry=RossPatternRegistry()
    registry._patterns=build_tradeable_patterns(["GAP_GO","GAP_CONTINUATION"])
    if synthetic:
        original=registry._patterns[0].evaluate
        def completed(inputs):
            result=original(inputs)
            if not result.detected: return result
            metadata=dict(result.setup_metadata)
            metadata.pop("entry_contract_block_reason")
            metadata["synthetic_stop_for_plumbing_only"]=True
            return replace(result,stop_level=9.7,invalidation_level=9.75,setup_metadata=metadata)
        monkeypatch.setattr(registry._patterns[0],"evaluate",completed)
    captured=[]; original_run=registry.run
    def observed(*args,**kwargs):
        values=original_run(*args,**kwargs); captured.extend(values); return values
    monkeypatch.setattr(registry,"run",observed)
    strategy._pattern_registry=registry
    seen=[]; original_trigger=TriggerEngine._evaluate_gap_go_trigger
    def record(self,**kwargs):
        seen.append(kwargs); return original_trigger(self,**kwargs)
    monkeypatch.setattr(TriggerEngine,"_evaluate_gap_go_trigger",record)
    row={**_watchlist_row(),"premarket_high":10.,"last_price":10.03,"bid":10.02,"ask":10.04}
    snap=replace(_snapshot(),last=10.03,bid=10.02,ask=10.04)
    intents=strategy.process_watchlist(watchlist=[row],snapshots={"UPC":snap},
        session_label="RTH_OPEN",session_phase="RTH_OPEN",timestamp_utc="synthetic-gap-go",mode=RunMode.READ_ONLY)
    return strategy,intents,captured,seen


def test_actual_v1_unmodified_detector_retains_explicit_policy_block(monkeypatch,tmp_path):
    _,intents,results,seen=actual_v1(monkeypatch,tmp_path)
    assert len(results)==1 and results[0].detected
    assert results[0].setup_metadata["requested_setup_ids"]==["GAP_CONTINUATION","GAP_GO"]
    assert validate_entry_contract(results[0])==(False,"gap_go_structural_stop_authority_missing")
    assert intents==[] and seen==[]


@pytest.mark.parametrize("state",["ready","missing","stale","malformed","stale_source"])
def test_actual_v1_synthetic_stop_plumbing_only(monkeypatch,tmp_path,state):
    _,intents,results,seen=actual_v1(monkeypatch,tmp_path,synthetic=True,state=state)
    if state=="ready":
        assert len(intents)==len(seen)==1
        intent=intents[0]
        assert intent.stop_loss_price==9.7 and intent.invalidation_level==9.75
        assert intent.take_profit_price is None
        assert intent.setup_metadata["canonical_result_index"]==0
        metadata=intent.setup_metadata["source_metadata"]
        assert metadata["synthetic_stop_for_plumbing_only"] is True
        assert metadata["requested_setup_ids"]==["GAP_CONTINUATION","GAP_GO"]
        results[0].setup_metadata["requested_setup_ids"].clear()
        assert metadata["requested_setup_ids"]==["GAP_CONTINUATION","GAP_GO"]
    else:
        assert intents==[]


@pytest.mark.parametrize("state",["future","missing_clock","bad_interval"])
def test_source_clock_and_interval_reject(state):
    data=source()
    if state=="future":
        bars=list(data.candles); bars[-1]=replace(bars[-1],timestamp=data.observed_at_utc+timedelta(microseconds=1))
        data=replace(data,candles=bars)
    if state=="missing_clock": data=replace(data,observed_at_utc=None)
    if state=="bad_interval": data=replace(data,timeframe="unknown")
    assert not GapGoPattern().evaluate(data).detected


def test_duplicate_occurrences_cannot_borrow_trigger_or_contract():
    results=[synthetic_complete(GapGoPattern().evaluate(source(v))) for v in ("PMH_BREAK","HOD_BREAK")]
    setups=V1._canonical_pattern_trigger_candidates(V1.__new__(V1),results,symbol="GAPX",existing_triggers=[])
    assert len(setups)==2
    assert V1._select_trigger_candidate(setup_family_id="GAP_GO",trigger_candidates=setups) is None
    for i in (0,1):
        chosen=V1._select_trigger_candidate(setup_family_id="GAP_GO",trigger_candidates=setups,selected_candidate_index=i)
        assert chosen is setups[i]
        assert chosen["trigger_level"]==results[i].trigger_level
        assert V1._resolve_selected_contract(decision={"selected_pattern_id":"P_GAP_GO","selected_candidate_index":i},pattern_results=results) is results[i]
    assert V1._select_trigger_candidate(setup_family_id="GAP_GO",trigger_candidates=setups,selected_candidate_index=2) is None


@pytest.mark.parametrize("change",["nan","future","reference_mismatch","close_at_invalidation"])
def test_canonical_special_dispatch_fail_closed(change):
    data=source(); setup=bridge(synthetic_complete(GapGoPattern().evaluate(data)))[0]
    clock=data.observed_at_utc
    setup["execution_stream"]={"observed_at_utc":clock.isoformat(),"execution_trigger_timeframe":"10s","stream_provenance":"PRESENT"}
    candle=replace(data.candles[-1],timestamp=clock-timedelta(seconds=10))
    if change=="nan": candle=replace(candle,high=float("nan"))
    if change=="future": candle=replace(candle,timestamp=clock+timedelta(microseconds=1))
    if change=="reference_mismatch": setup["trigger_level"]=5.6
    if change=="close_at_invalidation": candle=replace(candle,open=5.1,low=5.0,close=5.1)
    out=TriggerEngine().evaluate_triggers(symbol="GAPX",candles=[candle],setups=[setup],levels={},structure={})[0]
    assert not out["trigger_ready_now"]


@pytest.mark.parametrize("field",["rvol","spread","float_millions"])
def test_nonfinite_liquidity_rejects(field):
    data=source()
    data=replace(data,liquidity_context=replace(data.liquidity_context,**{field:float("nan")}))
    assert not GapGoPattern().evaluate(data).detected


def test_contract_block_cannot_be_bypassed_by_filling_generic_levels():
    result=GapGoPattern().evaluate(source())
    result=replace(result,stop_level=5.,invalidation_level=5.1)
    assert validate_entry_contract(result)==(False,"gap_go_structural_stop_authority_missing")
    assert bridge(result)==[]


def test_canonical_hold_requires_previous_completed_close():
    data=source("BREAK_AND_HOLD")
    setup=bridge(synthetic_complete(GapGoPattern().evaluate(data)))[0]
    clock=data.observed_at_utc
    setup["execution_stream"]={"observed_at_utc":clock.isoformat(),"execution_trigger_timeframe":"10s","stream_provenance":"PRESENT"}
    bars=[replace(data.candles[-1],timestamp=clock-timedelta(seconds=20),open=5.7,low=5.7,close=5.7),
          replace(data.candles[-1],timestamp=clock-timedelta(seconds=10))]
    out=TriggerEngine().evaluate_triggers(symbol="GAPX",candles=bars,setups=[setup],levels={},structure={})[0]
    assert not out["trigger_ready_now"]
    assert out["trigger_reason"]=="gap_go_break_and_hold_not_confirmed"


def test_malformed_metadata_fails_contract_without_exception():
    result=synthetic_complete(GapGoPattern().evaluate(source()))
    assert validate_entry_contract(replace(result,setup_metadata="invalid"))==(False,"gap_go_invalid_contract_metadata")


def test_reference_kind_cannot_be_relabelled_as_another_trigger():
    result=synthetic_complete(GapGoPattern().evaluate(source("PMH_BREAK")))
    changed=replace(result,trigger_type="HOD_BREAK")
    assert validate_entry_contract(changed)==(False,"gap_go_trigger_reference_mismatch")
    assert bridge(changed)==[]


def test_old_source_clock_cannot_admit_a_new_execution_context():
    data=source()
    setup=bridge(synthetic_complete(GapGoPattern().evaluate(data)))[0]
    later=data.observed_at_utc+timedelta(minutes=1)
    setup["execution_stream"]={"observed_at_utc":later.isoformat(),"execution_trigger_timeframe":"10s","stream_provenance":"PRESENT"}
    bars=[replace(data.candles[-1],timestamp=later-timedelta(seconds=10))]
    out=TriggerEngine().evaluate_triggers(symbol="GAPX",candles=bars,setups=[setup],levels={},structure={})[0]
    assert not out["trigger_ready_now"]
    assert out["trigger_reason"]=="gap_go_observation_context_mismatch"


def test_existing_intrabar_execution_policy_remains_available():
    """Synthetic stop only; a valid in-progress10s bar need not close to trigger."""
    data=source()
    setup=bridge(synthetic_complete(GapGoPattern().evaluate(data)))[0]
    clock=data.observed_at_utc
    setup["execution_stream"]={"observed_at_utc":clock.isoformat(),"execution_trigger_timeframe":"10s","stream_provenance":"PRESENT"}
    candle=replace(data.candles[-1],timestamp=clock-timedelta(seconds=1))
    out=TriggerEngine().evaluate_triggers(symbol="GAPX",candles=[candle],setups=[setup],levels={},structure={})[0]
    assert out["trigger_ready_now"]
    assert out["trigger_reason"]=="gap_go_pmh_break"


@pytest.mark.parametrize("malformed",["malformed",["malformed"],1,[],0,None])
def test_malformed_execution_stream_is_an_explicit_block(malformed):
    data=source()
    setup=bridge(synthetic_complete(GapGoPattern().evaluate(data)))[0]
    setup["execution_stream"]=malformed
    out=TriggerEngine().evaluate_triggers(symbol="GAPX",candles=data.candles,
        setups=[setup],levels={},structure={})[0]
    assert not out["trigger_ready_now"]
    assert out["trigger_state"]=="BLOCKED"
    assert out["trigger_reason"]=="gap_go_invalid_execution_stream"
