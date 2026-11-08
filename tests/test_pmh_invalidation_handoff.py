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


def actual_run(monkeypatch,tmp_path,*,state="ready",supplied=None,all_patterns=False,mode=RunMode.READ_ONLY):
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
    if state=="trace_native":
        from src.strategies.ross_momentum.patterns import pattern_trace
        from test_joined_core_pmh_readonly import _closed_minutes_and_execution
        trace_asof=pattern_trace.datetime.now(timezone.utc)
        rows[-1]=(10.31,10.35,10.30,10.34,1500)
        source=_candles(rows,end=trace_asof.replace(second=0)-timedelta(minutes=1))
        assert source[0].timestamp.minute%5==0 and source[0].timestamp.second==0
        grouped=[]
        for start in range(0,len(rows),5):
            chunk=rows[start:start+5]
            grouped.append((chunk[0][0],max(b[1] for b in chunk),min(b[2] for b in chunk),
                chunk[-1][3],sum(b[4] for b in chunk)))
        earlier=[(10.,10.25,9.95,10.2,4500)]*40
        earlier[10]=(10.,10.3,9.95,10.2,4500)  # Independent completed PRE high.
        data={"1m":source,
            "5m":_candles(earlier+grouped,step_seconds=300,
                end=source[-5].timestamp),
            "10s":_closed_minutes_and_execution(source,
                [(10.29,10.30,10.29,10.29,200),(10.29,10.31,10.29,10.30,200),
                 (10.30,10.35,10.30,10.34,1200)],
                end=trace_asof.replace(second=0)-timedelta(seconds=10))}
    monkeypatch.setattr("src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda *,timeframe="1m",**kw:data[timeframe])
    registry=RossPatternRegistry()
    if not all_patterns: registry._patterns=[PremarketHighBreakPattern()]
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
    if state=="trace_native":
        row.update(last_price=10.34,bid=10.33,ask=10.35)
        snapshot=replace(snapshot,last=10.34,bid=10.33,ask=10.35,
            asof_utc=trace_asof,market_timestamp_utc=trace_asof)
    intents=strategy.process_watchlist(watchlist=[row],snapshots={"UPC":snapshot},
        session_label="RTH_OPEN",session_phase="RTH_OPEN",timestamp_utc="synthetic-pmh",mode=mode)
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
def test_ready_pmh_occurrence_wins_with_own_distinct_stop_and_invalidation(monkeypatch,tmp_path,reverse):
    valid=contract()
    waiting=replace(valid,trigger_level=10.6,stop_level=10.5894,invalidation_level=10.6,confidence=.95)
    supplied=[waiting,valid] if reverse else [valid,waiting]
    strategy,intents,_,calls=actual_run(monkeypatch,tmp_path,supplied=supplied)
    assert len(intents)==1
    intent=intents[0]
    assert intent.setup_metadata['canonical_result_index']==supplied.index(valid)
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(
        valid.trigger_level,valid.stop_level,valid.invalidation_level)
    assert intent.target_model==valid.target_suggestion and intent.take_profit_price is None
    canonical={p["canonical_result_index"]:o for p,o in calls if p.get("source")=="canonical_pattern_result"}
    assert not canonical[supplied.index(waiting)]["trigger_ready_now"]
    assert canonical[supplied.index(valid)]["trigger_ready_now"]
    assert strategy.last_symbol_terminal_outcomes["UPC"]["intent_emitted"]


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


@pytest.mark.parametrize("bad",[None,float("nan"),float("inf"),"malformed"])
def test_common_builder_never_substitutes_explicit_invalid_authority(bad):
    from types import SimpleNamespace
    from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1 as V1
    strategy=V1.__new__(V1); strategy.name="RossMomentumStrategyV1"; strategy.trader_type="SCALPER"
    assert strategy._build_trade_intent(symbol="PMH",best_pattern=SimpleNamespace(pattern_id="P_PREMARKET_HIGH_BREAK",confidence=.8),
        setup_family="PREMARKET_HIGH_BREAK",trigger_ready=True,entry=10.3,stop=10.2897,
        invalidation_level=bad,target_model="HOD / next resistance",setup_rationale="Synthetic authority rejection") is None


@pytest.mark.parametrize("bad",[None,float("nan"),99.])
def test_common_handoff_rejects_missing_or_replaced_key_level_invalidation(bad):
    from types import SimpleNamespace
    from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1 as V1
    from test_key_level_break_production_handoff import _result
    result=_result()
    trigger={"canonical_result_index":0,"trigger_price_reference":result.trigger_level,
        "stop_price_reference":result.stop_level,"invalidation_price_reference":bad}
    assert V1._build_trade_from_pattern(SimpleNamespace(pattern_id=result.setup_id),None,
        selected_trigger=trigger,selected_contract=result,rejection_reasons=[]) is None


@pytest.mark.parametrize("explicit",[False,True])
def test_common_builder_retains_equal_stop_invalidation_and_legacy_omission(explicit):
    from types import SimpleNamespace
    from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1 as V1
    strategy=V1.__new__(V1); strategy.name="RossMomentumStrategyV1"; strategy.trader_type="SCALPER"
    kwargs={"invalidation_level":10.05} if explicit else {}
    intent=strategy._build_trade_intent(symbol="MICRO",best_pattern=SimpleNamespace(pattern_id="P_MICRO_PULLBACK",confidence=.8),
        setup_family="MICRO_PULLBACK",trigger_ready=True,entry=10.2,stop=10.05,
        target_model="Prior high / HOD",setup_rationale="Synthetic equal-anchor compatibility",**kwargs)
    assert intent.stop_loss_price==intent.invalidation_level==10.05
