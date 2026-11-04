"""Synthetic market streams; unmodified PMH detector, registered trigger and actual V1."""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone

import pytest

from src.config.runtime_config import RunMode
from src.setup_engine.setup_families.breakouts import PremarketHighBreakPattern
from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from test_key_level_break_production_handoff import forbid_io
from test_pr1082_trigger_to_intent_terminal_semantics import (
    _base_strategy, _candles, _watchlist_row, _snapshot, _reset_config, FakeRegistry,
)


def actual_run(monkeypatch,tmp_path,*,state="ready",supplied=None):
    strategy=_base_strategy(monkeypatch,tmp_path,state="ready")
    rows=[(10.0,10.25,9.95,10.2,900)]*48+[
        (10.2,10.29,10.19,10.28,900),(10.31,10.55,10.30,10.53,1500)]
    execution=list(rows)
    if state=="waiting": execution[-1]=(10.26,10.29,10.25,10.28,1500)
    if state=="at_level": execution[-1]=(10.28,10.32,10.27,10.30,1500)
    data={tf:_candles(execution if tf=="10s" else rows,step_seconds=step)
          for tf,step in (("1m",60),("5m",300),("10s",10))}
    if state=="future_source": data["1m"][-1]=replace(data["1m"][-1],timestamp=datetime.now(timezone.utc)+timedelta(minutes=1))
    if state=="future_execution": data["10s"][-1]=replace(data["10s"][-1],timestamp=datetime.now(timezone.utc)+timedelta(minutes=1))
    if state=="bad_source": data["1m"][-1]=replace(data["1m"][-1],low=float("nan"))
    if state=="bad_execution": data["10s"][-1]=replace(data["10s"][-1],low=float("nan"))
    if state=="missing": data["10s"]=[]
    if state=="missing_source": data["1m"]=[]
    if state=="stale_source": data["1m"]=[replace(c,timestamp=c.timestamp-timedelta(minutes=10)) for c in data["1m"]]
    if state=="stale": data["10s"]=[replace(c,timestamp=c.timestamp-timedelta(minutes=10)) for c in data["10s"]]
    monkeypatch.setattr("src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda *,timeframe="1m",**kw:data[timeframe])
    registry=RossPatternRegistry(); registry._patterns=[PremarketHighBreakPattern()]
    results=[]; original_run=registry.run
    def capture(*args,**kwargs):
        values=original_run(*args,**kwargs); results.extend(values); return values
    monkeypatch.setattr(registry,"run",capture); strategy._pattern_registry=registry
    if supplied is not None:
        strategy._pattern_registry=FakeRegistry(supplied); results=supplied
    calls=[]; original=TRIGGER_EVALUATOR_REGISTRY["PREMARKET_HIGH_BREAK"]
    def observed(payload,inputs):
        output=original(payload,inputs); calls.append((payload,output)); return output
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,"PREMARKET_HIGH_BREAK",observed)
    row={**_watchlist_row(),"premarket_high":10.3,"last_price":10.53,"bid":10.52,"ask":10.54}
    snapshot=replace(_snapshot(),last=10.53,bid=10.52,ask=10.54)
    intents=strategy.process_watchlist(watchlist=[row],snapshots={"UPC":snapshot},
        session_label="RTH_OPEN",session_phase="RTH_OPEN",timestamp_utc="synthetic-pmh",mode=RunMode.READ_ONLY)
    return strategy,intents,results,calls


def test_unmodified_pmh_detector_to_actual_v1_retains_distinct_levels(monkeypatch,tmp_path):
    _,intents,results,calls=actual_run(monkeypatch,tmp_path)
    assert len(results)==1 and results[0].detected
    result=results[0]
    assert result.stop_level==10.3-max(.01,10.3*.001)
    assert result.invalidation_level==10.3
    canonical=[call for call in calls if call[0].get("source")=="canonical_pattern_result"]
    assert len(canonical)==len(intents)==1
    assert canonical[0][0]["canonical_result_index"]==0
    assert canonical[0][1]["invalidation_price_reference"]==result.invalidation_level
    assert intents[0].stop_loss_price==result.stop_level
    assert intents[0].invalidation_level==result.invalidation_level


@pytest.mark.parametrize("state",["waiting","at_level","missing","stale"])
def test_actual_pmh_nonconfirmation_and_unavailable_execution_remain_blocked(monkeypatch,tmp_path,state):
    _,intents,results,_=actual_run(monkeypatch,tmp_path,state=state)
    assert results and results[0].detected
    assert intents==[]


def test_serialized_pmh_evidence_is_an_isolated_snapshot(monkeypatch,tmp_path):
    _,intents,results,calls=actual_run(monkeypatch,tmp_path)
    intent=intents[0]
    canonical=next(call[0] for call in calls if call[0].get("source")=="canonical_pattern_result")
    payload=asdict(intent)
    assert payload["stop_loss_price"]==results[0].stop_level
    assert payload["invalidation_level"]==results[0].invalidation_level
    assert payload["setup_metadata"]["canonical_result_index"]==0
    assert payload["setup_metadata"]["invalidation_level"]==10.3
    canonical["setup_metadata"]["pmh_path"]="mutated"
    canonical["execution_stream"]["timeframe_provenance"].clear()
    results[0].setup_metadata.clear()
    assert asdict(intent)==payload


def contract():
    from test_premarket_high_break_pattern import _base_inputs
    data=_base_inputs()
    return PremarketHighBreakPattern().evaluate(replace(data,
        levels=replace(data.levels,premarket_high=10.3),
        candles=_candles([(10.2,10.29,10.19,10.28,900),(10.31,10.55,10.30,10.53,1500)])))


@pytest.mark.parametrize("reverse",[False,True])
def test_duplicate_id_cannot_borrow_rejected_occurrences_levels(monkeypatch,tmp_path,reverse):
    valid=contract(); assert valid.detected
    rejected=replace(valid,trigger_level=99.,stop_level=98.,invalidation_level=99.,
        target_suggestion=None,rationale_text="Rejected occurrence cannot replace winner")
    supplied=[rejected,valid] if reverse else [valid,rejected]
    _,intents,_,_=actual_run(monkeypatch,tmp_path,supplied=supplied)
    assert len(intents)==1
    assert intents[0].stop_loss_price==valid.stop_level
    assert intents[0].invalidation_level==valid.invalidation_level
    assert intents[0].setup_metadata["canonical_result_index"]==supplied.index(valid)
    assert rejected.rationale_text not in intents[0].rationale


@pytest.mark.parametrize("reverse",[False,True])
def test_selected_waiting_occurrence_cannot_borrow_a_ready_trigger(monkeypatch,tmp_path,reverse):
    valid=contract()
    waiting=replace(valid,trigger_level=10.6,stop_level=10.5894,invalidation_level=10.6,confidence=.95)
    supplied=[waiting,valid] if reverse else [valid,waiting]
    strategy,intents,_,calls=actual_run(monkeypatch,tmp_path,supplied=supplied)
    assert intents==[]
    canonical={p["canonical_result_index"]:o for p,o in calls if p.get("source")=="canonical_pattern_result"}
    assert not canonical[supplied.index(waiting)]["trigger_ready_now"]
    assert canonical[supplied.index(valid)]["trigger_ready_now"]
    assert not strategy.last_symbol_terminal_outcomes["UPC"]["intent_emitted"]


@pytest.mark.parametrize("field",["trigger_level","stop_level","invalidation_level"])
@pytest.mark.parametrize("bad",[None,float("nan"),float("inf"),"malformed",True])
def test_invalid_canonical_authority_cannot_reach_raw_intent(monkeypatch,tmp_path,field,bad):
    invalid=replace(contract(),**{field:bad})
    _,intents,_,_=actual_run(monkeypatch,tmp_path,supplied=[invalid])
    assert intents==[]


@pytest.mark.parametrize("state",["missing_source","stale_source"])
def test_unavailable_source_cannot_reach_raw_intent(monkeypatch,tmp_path,state):
    _,intents,_,_=actual_run(monkeypatch,tmp_path,state=state)
    assert intents==[]


@pytest.mark.parametrize("reference",["trigger_price_reference","stop_price_reference","invalidation_price_reference"])
@pytest.mark.parametrize("bad",[None,float("nan"),99.])
def test_selected_trigger_cannot_replace_canonical_levels(reference,bad):
    from types import SimpleNamespace
    from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1 as V1
    result=contract()
    trigger={"trigger_price_reference":result.trigger_level,"stop_price_reference":result.stop_level,
             "invalidation_price_reference":result.invalidation_level}
    trigger[reference]=bad
    reasons=[]
    assert V1._build_trade_from_pattern(SimpleNamespace(pattern_id=result.setup_id),None,
        selected_trigger=trigger,selected_contract=result,rejection_reasons=reasons) is None
    assert reasons==["selected_level_authority_mismatch"]


@pytest.mark.parametrize("state",["bad_source","bad_execution"])
def test_nonfinite_market_authority_cannot_reach_intent(monkeypatch,tmp_path,state):
    _,intents,_,_=actual_run(monkeypatch,tmp_path,state=state)
    assert intents==[]


@pytest.mark.parametrize("state",["future_source","future_execution"])
def test_future_market_authority_remains_blocked(monkeypatch,tmp_path,state):
    _,intents,_,_=actual_run(monkeypatch,tmp_path,state=state)
    assert intents==[]
