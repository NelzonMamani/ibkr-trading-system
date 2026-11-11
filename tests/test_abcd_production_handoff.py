"""Synthetic source streams; actual ABCD registry, V1 and registered evaluator."""
from dataclasses import replace
from datetime import timedelta

import pytest

from src.config.runtime_config import RunMode
from src.setup_engine.setup_families.ross_families import ABCDPattern
from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.ross_momentum.tests.test_abcd_setup_family import _inputs
from test_key_level_break_production_handoff import forbid_io
from test_flat_top_production_handoff import forbid_collection_and_execution
from test_joined_core_pmh_readonly import (
    pmh_joined, cycles, no_effects, reassessment, lifecycle,
    _cadence, _snapshot as joined_snapshot, fixture_quote_batch,
)
from test_pr1082_trigger_to_intent_terminal_semantics import (
    _base_strategy, _candles, _snapshot, _watchlist_row, _reset_config, FakeRegistry,
)

ROWS = [(10.2,10.30,10.10,10.20,1000), (10.1,10.25,9.90,10.15,1100),
        (10.2,10.50,10.15,10.40,1200), (10.5,11.,10.40,10.90,1400),
        (10.8,10.8,10.5,10.6,900), (10.6,10.7,10.35,10.45,950),
        (10.5,10.95,10.45,10.90,1300), (10.9,11.05,10.9,11.02,1500)]
FACTS = ("anchor_a_price","anchor_b_price","anchor_c_price","anchor_a_index",
         "anchor_b_index","anchor_c_index","ab_length","retracement_pct",
         "d_projection","risk_reference_level")


def result(rows=None):
    return ABCDPattern().evaluate(_inputs(_candles(rows or ROWS)))


def run(monkeypatch,tmp_path,*,state="ready",supplied=None):
    from src.strategies.ross_momentum.patterns import pattern_trace
    strategy = _base_strategy(monkeypatch,tmp_path,state="ready")
    rows = [(10.2,10.3,10.1,10.2,1000)]*42 + ROWS
    execution = list(rows)
    if state == "touch": execution[-1] = (10.9,11.05,10.9,11.,1500)
    if state == "waiting": execution[-1] = (10.9,11.05,10.8,10.99,1500)
    if state == "invalidated": execution[-1] = (10.9,11.05,10.3,10.35,1500)
    data = {tf:_candles(execution if tf=="10s" else rows,step_seconds=step)
            for tf,step in (("1m",60),("5m",300),("10s",10))}
    if state == "missing": data["10s"] = []
    if state == "stale": data["10s"] = [replace(c,timestamp=c.timestamp-timedelta(minutes=10)) for c in data["10s"]]
    if state == "malformed": data["10s"][-1] = replace(data["10s"][-1],close=float("inf"))
    if state == "nonfinite_primary": data["1m"][-7] = replace(data["1m"][-7],low=float("nan"))
    if state == "missing_primary": data["1m"] = []
    if state == "stale_primary": data["1m"] = [replace(c,timestamp=c.timestamp-timedelta(minutes=10)) for c in data["1m"]]
    if state in {"future_primary","future_execution"}:
        tf = "1m" if state == "future_primary" else "10s"
        data[tf][-1] = replace(data[tf][-1],timestamp=pattern_trace.datetime.now(pattern_trace.timezone.utc)+timedelta(microseconds=1))
    monkeypatch.setattr(pattern_trace,"get_intraday_bars",lambda *,timeframe="1m",**kwargs:data[timeframe])
    captured=[]; source=[]
    if supplied is None:
        registry=RossPatternRegistry(); registry._patterns=[ABCDPattern()]
        original=registry.run
        def observe(inputs,**kwargs):
            source.append(inputs); values=original(inputs,**kwargs); captured.extend(values); return values
        monkeypatch.setattr(registry,"run",observe); strategy._pattern_registry=registry
    else:
        captured=supplied; strategy._pattern_registry=FakeRegistry(supplied)
    seen=[]; evaluator=TRIGGER_EVALUATOR_REGISTRY["ABCD"]
    def observe_trigger(payload,inputs):
        seen.append((payload,inputs)); return evaluator(payload,inputs)
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,"ABCD",observe_trigger)
    row={**_watchlist_row(),"last_price":11.02,"bid":11.01,"ask":11.03}
    snapshot=replace(_snapshot(),last=11.02,bid=11.01,ask=11.03)
    intents=strategy.process_watchlist(watchlist=[row],snapshots={"UPC":snapshot},
        session_label="RTH_OPEN",session_phase="RTH_OPEN",timestamp_utc="synthetic-abcd",mode=RunMode.READ_ONLY)
    return strategy,intents,captured,seen,source


@pytest.mark.parametrize("state",["ready","touch","waiting","invalidated","missing","stale",
                                   "malformed","future_primary","future_execution","nonfinite_primary"])
def test_actual_detector_v1_and_registered_evaluator(monkeypatch,tmp_path,state):
    strategy,intents,results,seen,source=run(monkeypatch,tmp_path,state=state)
    if state in {"future_primary","nonfinite_primary"}:
        assert intents==[] and not results[0].detected
        assert results[0].rejection_reason == ("FUTURE_CANDLE_DATA" if state=="future_primary" else "INVALID_CANDLE_DATA")
        return
    assert results and results[0].detected
    own=next(t for t in strategy._failure_trace_collector._symbols[-1].input_summary["trigger_candidates"]
             if t.get("setup_family_id")=="ABCD")
    if state == "ready":
        assert len(intents)==1, strategy.last_symbol_terminal_outcomes
        detected=results[0]; intent=intents[0]
        assert len(seen)==1
        for key in FACTS:
            assert seen[0][0][key]==getattr(detected,key)
            assert intent.setup_metadata[key]==getattr(detected,key)
        assert detected.anchor_a_price==9.9 and detected.anchor_b_price==11. and detected.anchor_c_price==10.35
        assert detected.d_projection==pytest.approx(11.45)
        assert detected.anchor_a_index < detected.anchor_b_index < detected.anchor_c_index < len(source[0].candles)-1
        assert intent.entry_price==11. and intent.stop_loss_price==intent.invalidation_level==10.35
        assert intent.setup_family_id=="ABCD" and detected.rationale_text in intent.rationale
        assert intent.target_model==detected.target_suggestion and intent.take_profit_price is None
        assert intent.setup_metadata["source_metadata"]==detected.setup_metadata
        from dataclasses import asdict
        assert asdict(intent)["setup_metadata"] == intent.setup_metadata
        assert detected.setup_metadata["source_candle_timestamps"] == [c.timestamp.isoformat() for c in source[0].candles]
        assert intent.setup_metadata["canonical_result_index"]==own["canonical_result_index"]==0
        assert intent.timestamp_utc=="synthetic-abcd"
        assert seen[0][1]["candles"][-1].timestamp-seen[0][1]["candles"][-2].timestamp==timedelta(seconds=10)
        assert own["execution_stream"]["timeframe_substitution"] is False
    else:
        assert intents==[] and not own["trigger_ready_now"]
        if state in {"touch","waiting"}: assert own["trigger_reason"]=="awaiting_abcd_continuation_break"
        if state == "invalidated": assert own["trigger_reason"]=="at_or_below_invalidation"


@pytest.mark.parametrize("reverse",[False,True])
def test_duplicate_contract_isolation(monkeypatch,tmp_path,reverse):
    valid=result()
    rejected=replace(valid,stop_level=12.,d_projection=99.,rationale_text="Rejected occurrence")
    supplied=[rejected,valid] if reverse else [valid,rejected]
    strategy,intents,_,seen,_=run(monkeypatch,tmp_path,supplied=supplied)
    assert len(intents)==1, strategy.last_symbol_terminal_outcomes
    assert intents[0].entry_price==valid.trigger_level
    assert intents[0].setup_metadata["d_projection"]==valid.d_projection
    assert intents[0].setup_metadata["canonical_result_index"]==supplied.index(valid)
    assert rejected.rationale_text not in intents[0].rationale


@pytest.mark.parametrize("reverse",[False,True])
def test_ready_abcd_occurrence_wins_without_borrowing_from_waiting(monkeypatch,tmp_path,reverse):
    valid=result(); waiting=replace(valid,confidence=.99,trigger_level=12.)
    supplied=[waiting,valid] if reverse else [valid,waiting]
    strategy,intents,_,_,_=run(monkeypatch,tmp_path,supplied=supplied)
    assert len(intents)==1
    intent=intents[0]
    assert intent.setup_metadata['canonical_result_index']==supplied.index(valid)
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(
        valid.trigger_level,valid.stop_level,valid.invalidation_level)
    assert intent.target_model==valid.target_suggestion and intent.take_profit_price is None
    triggers=[t for t in strategy._failure_trace_collector._symbols[-1].input_summary["trigger_candidates"] if t.get("setup_family_id")=="ABCD"]
    selected=next(t for t in triggers if t["canonical_result_index"]==supplied.index(waiting))
    other=next(t for t in triggers if t["canonical_result_index"]!=supplied.index(waiting))
    assert not selected["trigger_ready_now"] and other["trigger_ready_now"]


@pytest.mark.parametrize("index,field,value",[(1,"low",float("nan")),(3,"high",float("inf")),
    (5,"low",None),(5,"low",10.7),(4,"volume",float("nan"))])
def test_malformed_structure_rejects(index,field,value):
    candles=_candles(ROWS); candles[index]=replace(candles[index],**{field:value})
    output=ABCDPattern().evaluate(_inputs(candles))
    assert not output.detected
    assert output.rejection_reason=="INVALID_CANDLE_DATA"


@pytest.mark.parametrize("high",[11.05,50.])
def test_confirming_high_does_not_enter_anchor_or_trigger_window(high):
    rows=list(ROWS); o,_,l,c,v=rows[-1]; rows[-1]=(o,high,l,c,v)
    output=result(rows)
    assert output.detected
    assert (output.anchor_a_index,output.anchor_b_index,output.anchor_c_index)==(1,3,5)
    assert output.trigger_level==11. and output.invalidation_level==10.35
    assert output.d_projection==pytest.approx(11.45)


@pytest.mark.parametrize("state",["missing_primary","stale_primary"])
def test_required_primary_cannot_be_substituted(monkeypatch,tmp_path,state):
    strategy,intents,results,seen,source=run(monkeypatch,tmp_path,state=state)
    assert intents==[] and seen==[]
    assert not any(r.detected for r in results)
    if state=="missing_primary":
        assert strategy._failure_trace_collector._symbols[-1].pre_registry_failure_reason=="failed_to_build_inputs"


@pytest.mark.parametrize("mutation",["missing_time","reversed_time","missing_clock"])
def test_operational_source_time_boundary_fails_closed(mutation):
    from src.strategies.ross_momentum.patterns.pattern_inputs import build_authoritative_pattern_inputs
    candles=_candles(ROWS)
    now=candles[-1].timestamp+timedelta(seconds=30)
    inputs=build_authoritative_pattern_inputs(symbol="UPC",session_label="RTH_OPEN",
        timeframe_candles={"1m":candles},now=now)
    if mutation=="missing_time":
        inputs=replace(inputs,candles=[*candles[:-1],replace(candles[-1],timestamp=None)])
    elif mutation=="reversed_time":
        inputs=replace(inputs,candles=[*candles[:-1],replace(candles[-1],timestamp=candles[-2].timestamp)])
    else:
        inputs=replace(inputs,observed_at_utc=None)
    output=ABCDPattern().evaluate(inputs)
    assert not output.detected and output.rejection_reason=="INVALID_CANDLE_TIMESTAMPS"


def test_raw_evidence_snapshot_does_not_alias_mutable_source_metadata(monkeypatch,tmp_path):
    from copy import deepcopy
    _,intents,results,seen,_=run(monkeypatch,tmp_path)
    assert len(intents)==1
    before=deepcopy(intents[0].setup_metadata)
    results[0].setup_metadata["source_candle_timestamps"].append("later mutation")
    seen[0][0]["execution_stream"]["timeframe_provenance"]["1m"]="later mutation"
    assert intents[0].setup_metadata==before


def test_incomplete_primary_cannot_confirm_a_new_c_swing(monkeypatch,tmp_path):
    # C is now the penultimate bar. Its right-hand witness is the latest 1m
    # candle, starting 30s before the fixture clock: it has not completed.
    rows=list(ROWS)
    rows[5]=(10.6,10.7,10.5,10.55,950)
    rows[6]=(10.5,10.95,10.35,10.9,1300)
    monkeypatch.setitem(globals(),"ROWS",rows)
    _,intents,results,seen,_=run(monkeypatch,tmp_path)
    assert intents==[]
    assert results and not results[0].detected
    assert results[0].rejection_reason=="NO_COMPLETED_SWING_SEQUENCE"
    assert seen==[]


@pytest.mark.parametrize("microseconds,eligible",[(-1,False),(0,True)])
def test_swing_witness_completion_boundary(microseconds,eligible):
    from src.strategies.ross_momentum.patterns.pattern_inputs import build_authoritative_pattern_inputs
    rows=list(ROWS); rows[5]=(10.6,10.7,10.5,10.55,950); rows[6]=(10.5,10.95,10.35,10.9,1300)
    candles=_candles(rows)
    observed=candles[-1].timestamp+timedelta(minutes=1,microseconds=microseconds)
    inputs=build_authoritative_pattern_inputs(symbol="UPC",session_label="RTH_OPEN",
        timeframe_candles={"1m":candles},now=observed)
    output=ABCDPattern().evaluate(inputs)
    assert output.detected is eligible
    if eligible:
        assert (output.anchor_a_index,output.anchor_b_index,output.anchor_c_index)==(1,3,6)
        assert output.trigger_level==11. and output.stop_level==output.invalidation_level==10.35
        assert output.d_projection==pytest.approx(11.45)
    else:
        assert output.rejection_reason=="NO_COMPLETED_SWING_SEQUENCE"


def test_input_mutation_cannot_rewrite_serialized_raw_intent(monkeypatch,tmp_path):
    from copy import deepcopy
    from dataclasses import asdict
    _,intents,results,_,source=run(monkeypatch,tmp_path)
    assert len(intents)==1
    before=deepcopy(asdict(intents[0]))
    source[0].candles[-1]=replace(source[0].candles[-1],high=99.)
    source[0].timeframe_provenance["1m"]="changed after formation"
    results[0].setup_metadata["structure_completed_candle_count"]=-1
    assert asdict(intents[0])==before


def test_bounded_lookback_indices_and_original_times_stay_aligned():
    from src.strategies.ross_momentum.patterns.pattern_inputs import build_authoritative_pattern_inputs
    candles=_candles([(10.2,10.3,10.1,10.2,1000)]*70+ROWS)
    inputs=build_authoritative_pattern_inputs(symbol="UPC",session_label="RTH_OPEN",
        timeframe_candles={"1m":candles},now=candles[-1].timestamp+timedelta(seconds=30))
    output=ABCDPattern().evaluate(inputs)
    assert output.detected
    assert (output.anchor_a_index,output.anchor_b_index,output.anchor_c_index)==(53,55,57)
    assert output.setup_metadata["lookback_start_index"]==18
    assert output.setup_metadata["structure_completed_candle_count"]==59
    times=output.setup_metadata["source_candle_timestamps"]
    assert len(times)==60 and times[output.anchor_c_index]==candles[75].timestamp.isoformat()
    assert output.trigger_level==11. and output.stop_level==10.35
    assert output.d_projection==pytest.approx(11.45)


def abcd_joined(reassessment,monkeypatch,tmp_path,*,news_fault='none',peer=False,
                market_fault='none',position_case='complete_empty',runtime_options=None):
    from copy import deepcopy
    from types import SimpleNamespace as NS
    h=pmh_joined(reassessment,monkeypatch,tmp_path,news_fault=news_fault,peer=peer,
        position_case=position_case,runtime_options=runtime_options)
    rows=[(10.2,10.3,10.1,10.2,1000)]*42+ROWS
    rows[20]=(10.2,12.,10.1,10.2,1000)  # Actual prior PRE high; no competing PMH break.
    # The continuation bar opens above 11, preserving all A/B/C geometry and
    # strict close confirmation without also forming a new whole-dollar break.
    rows[-1]=(11.01,11.05,10.9,11.02,1500)
    end=h.life.clock.current.replace(second=0,microsecond=0)
    h.streams.clear()
    for tf,step in (('1m',60),('5m',300),('10s',10)):
        h.streams[tf]=_candles(rows,step_seconds=step,end=end-timedelta(seconds=step))
    stream='1m' if market_fault.endswith('source') else '10s'
    if market_fault.startswith('missing_'):h.streams[stream]=[]
    elif market_fault.startswith('stale_'):
        h.streams[stream]=[replace(b,timestamp=b.timestamp-timedelta(minutes=10)) for b in h.streams[stream]]
    elif market_fault.startswith('future_'):
        h.streams[stream][-1]=replace(h.streams[stream][-1],timestamp=h.life.clock.current+timedelta(seconds=12))
    elif market_fault.startswith('nan_'):
        h.streams[stream][-3]=replace(h.streams[stream][-3],low=float('nan'))
    elif market_fault.startswith('malformed_'):
        h.streams[stream][-3]=replace(h.streams[stream][-3],low=12.)
    elif market_fault in {'touch_execution','below_execution','invalidated_execution'}:
        close={'touch_execution':11.,'below_execution':10.99,'invalidated_execution':10.35}[market_fault]
        h.streams['10s'][-1]=replace(h.streams['10s'][-1],low=min(10.9,close),close=close)
    elif market_fault in {'forming_witness_source','delayed_witness_source','witness_boundary_source'}:
        seconds=49 if market_fault=='witness_boundary_source' else 9
        h.streams['1m'][-2]=replace(h.streams['1m'][-2],timestamp=h.life.clock.current-timedelta(seconds=seconds))
        h.streams['1m'][-1]=replace(h.streams['1m'][-1],timestamp=h.life.clock.current+timedelta(seconds=1))
    for row in h.rows.values():
        gap=(11.02/9.8-1)*100
        row.update(premarket_high=12.,last_price=11.02,bid=11.01,ask=11.03,
            prev_close=9.8,ref_close_rth=9.8,reference_price=9.8,gap_pct=gap,pct_change=gap,
            spread_pct=100*.02/11.02,dollar_volume=19836000.)
    snapshot=replace(joined_snapshot(symbol='JPM'),last=11.02,bid=11.01,ask=11.03)
    h.core.market_data_snapshot_manager=NS(batch_snapshots=lambda symbols:fixture_quote_batch(h,snapshot,symbols))
    h.abcd_triggers=[];evaluator=TRIGGER_EVALUATOR_REGISTRY['ABCD']
    def observed(payload,inputs):
        out=evaluator(payload,inputs)
        h.abcd_triggers.append((deepcopy(payload),deepcopy(inputs),deepcopy(out)))
        return out
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,'ABCD',observed)
    if market_fault=='delayed_witness_source':
        original=h.strategy._pattern_registry.run
        def delayed(source,**kwargs):
            h.life.clock.current+=timedelta(minutes=2)
            return original(source,**kwargs)
        monkeypatch.setattr(h.strategy._pattern_registry,'run',delayed)
    return h


@pytest.mark.parametrize('position_case',['complete_empty','complete_matched'])
def test_joined_abcd_real_news_focus_artifact_and_risk(reassessment,monkeypatch,tmp_path,capsys,position_case):
    from copy import deepcopy
    from src.scanner import scanner_runner as ross
    h=abcd_joined(reassessment,monkeypatch,tmp_path,position_case=position_case)
    out=cycles(h,capsys)
    raw=[i for batch in h.batches for i in batch]
    assert len(raw)==len(h.artifacts)==len(h.evaluated)==1,out
    intent,received,decision=h.evaluated[0];artifact,built=h.artifacts[0]
    assert intent is raw[0] and artifact.intents==[intent]
    assert built==h.raw_snapshots and built[0]['decision_id'] is None
    assert received==dict(built[0],decision_id=artifact.decision_id)==vars(intent)
    assert intent.decision_id==artifact.decision_id==decision.decision_id
    assert intent.setup_family_id=='ABCD' and not intent.relationship_context
    source,results=h.registry_batches[-1]
    index=intent.setup_metadata['canonical_result_index'];selected=results[index]
    assert selected.setup_id=='P_ABCD' and selected.detected and index>0
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(11.,10.35,10.35)
    assert (selected.anchor_a_price,selected.anchor_b_price,selected.anchor_c_price)==(9.9,11.,10.35)
    assert (selected.anchor_a_index,selected.anchor_b_index,selected.anchor_c_index)==(43,45,47)
    for key in FACTS:assert intent.setup_metadata[key]==getattr(selected,key)
    assert intent.setup_metadata['d_projection']==pytest.approx(11.45)
    assert intent.take_profit_price is None and intent.target_model==selected.target_suggestion
    assert selected.setup_metadata['source_candle_timestamps']==[b.timestamp.isoformat() for b in source.candles]
    assert selected.setup_metadata['observed_at_utc']==source.observed_at_utc.isoformat()
    assert source.observed_at_utc==h.life.clock.current
    assert all(b.timestamp+timedelta(minutes=1)<=source.observed_at_utc for b in source.candles)
    payload,execution,trigger=h.abcd_triggers[-1]
    assert payload['canonical_result_index']==index and trigger['trigger_ready_now']
    for key in FACTS:assert payload[key]==intent.setup_metadata[key]
    assert execution['candles'][-1].close>selected.trigger_level
    assert decision.reason_code=='LIVE_READ_ONLY_BLOCK' and not decision.allowed
    assert decision.execution_blocked and decision.max_position_size==0 and decision.run_mode=='READ_ONLY'
    assert h.focus_calls and _cadence(h.core).focus.symbols==['JPM']
    news=ross._ross_news_contexts_from_news_intelligence_result(h.reads[-1])
    assert news['JPM']['ross_catalyst_valid'] and news['JPM']['catalyst_type']=='EARNINGS'
    assert h.reads[-1].evidence_for_symbol('JPM')[0].evidence_id==h.article.evidence_id
    assert all(v.healthy and not v.block_new_entries for _,v in h.truth)
    for name,method in h.real_core_methods.items():assert getattr(h.core,name).__func__ is method
    assert 'ORDER_SUBMITTED' not in out
    no_effects(h)
    retained=deepcopy(vars(intent));selected.setup_metadata.clear();source.timeframe_provenance.clear()
    assert vars(intent)==received==retained


@pytest.mark.parametrize('news_fault',['missing','stale','nonqualifying','expires_between'])
def test_joined_abcd_news_isolation(reassessment,monkeypatch,tmp_path,capsys,news_fault):
    from src.scanner import scanner_runner as ross
    h=abcd_joined(reassessment,monkeypatch,tmp_path,news_fault=news_fault,peer=True)
    out=cycles(h,capsys)
    news=ross._ross_news_contexts_from_news_intelligence_result(h.reads[-1])
    assert not news['JPM']['ross_catalyst_valid'] and news['PEER']['ross_catalyst_valid']
    assert news['JPM']['qualification_reason']=='no_valid_canonical_event'
    assert _cadence(h.core).watchlist.symbols==['JPM','PEER']
    assert _cadence(h.core).focus.symbols==['PEER']
    assert all([r['symbol'] for r in selected]==['PEER'] for _,_,selected in h.focus_calls)
    assert not [source for source in h.inputs if source.symbol=='JPM']
    assert not [i for batch in h.batches for i in batch if i.symbol=='JPM']
    assert len(h.evaluated)==1 and all(i.symbol=='PEER' and i.setup_family_id=='ABCD'
        and d.reason_code=='LIVE_READ_ONLY_BLOCK' for i,_,d in h.evaluated),out
    no_effects(h)


@pytest.mark.parametrize('market_fault',['touch_execution','below_execution','invalidated_execution',
    'missing_source','stale_source','future_source','nan_source','malformed_source','forming_witness_source',
    'missing_execution','stale_execution','future_execution','nan_execution','malformed_execution'])
def test_joined_abcd_market_authority_rejects(reassessment,monkeypatch,tmp_path,capsys,market_fault):
    h=abcd_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    out=cycles(h,capsys)
    assert _cadence(h.core).focus.symbols==['JPM']
    assert not [i for batch in h.batches for i in batch if i.setup_family_id=='ABCD'],out
    assert all(i.setup_family_id!='ABCD' and d.reason_code=='LIVE_READ_ONLY_BLOCK' for i,_,d in h.evaluated)
    if market_fault in {'touch_execution','below_execution','invalidated_execution'}:
        assert h.abcd_triggers and not h.abcd_triggers[-1][2]['trigger_ready_now']
        own=next(t for t in h.strategy._failure_trace_collector._symbols[-1].input_summary['trigger_candidates']
            if t.get('setup_family_id')=='ABCD')
        assert own['trigger_reason']==('at_or_below_invalidation' if market_fault=='invalidated_execution'
            else 'awaiting_abcd_continuation_break')
    if market_fault in {'missing_execution','stale_execution','future_execution','nan_execution','malformed_execution'}:
        own=next(t for t in h.strategy._failure_trace_collector._symbols[-1].input_summary['trigger_candidates']
            if t.get('setup_family_id')=='ABCD')
        reasons={'missing_execution':'execution_stream_missing','stale_execution':'execution_stream_stale',
            'future_execution':'abcd_future_candle_data','nan_execution':'abcd_invalid_candle_data',
            'malformed_execution':'abcd_invalid_candle_data'}
        assert not own['trigger_ready_now'] and own['trigger_reason']==reasons[market_fault]
    if market_fault in {'future_source','nan_source','malformed_source'}:
        result=next(r for r in h.registry_batches[-1][1] if r.setup_id=='P_ABCD')
        assert not result.detected
        assert result.rejection_reason==('FUTURE_CANDLE_DATA' if market_fault=='future_source' else 'INVALID_CANDLE_DATA')
    if market_fault=='forming_witness_source':
        result=next(r for r in h.registry_batches[-1][1] if r.setup_id=='P_ABCD')
        assert not result.detected and result.rejection_reason=='NO_COMPLETED_SWING_SEQUENCE'
    no_effects(h)


@pytest.mark.parametrize('position_case',['unknown','partial','quantity_warning_larger','five','partial_after_healthy'])
def test_joined_abcd_raw_before_position_veto(reassessment,monkeypatch,tmp_path,capsys,position_case):
    h=abcd_joined(reassessment,monkeypatch,tmp_path,
        position_case='complete_matched' if position_case=='partial_after_healthy' else position_case)
    assert h.core.run_once();capsys.readouterr()
    if position_case=='partial_after_healthy':
        assert h.truth[-1][1].healthy;h.position_state['case']='partial'
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once();out=capsys.readouterr().out
    raw=[i for batch in h.batches for i in batch]
    assert len(raw)==1 and raw[0].setup_family_id=='ABCD' and raw[0].decision_id is None,out
    assert h.artifacts==h.evaluated==[] and h.truth[-1][1].block_new_entries
    snapshot,verdict=h.truth[-1]
    if position_case=='quantity_warning_larger':
        assert snapshot.broker_positions['SYNTH_MATCH'].quantity==3 and snapshot.system_positions['SYNTH_MATCH'].quantity==2
        assert [m.mismatch_type for m in snapshot.mismatches]==['QUANTITY_MISMATCH'] and not verdict.block_exits
    elif position_case=='five':assert verdict.critical_mismatch_count==5
    else:assert snapshot.snapshot_status=='UNKNOWN'
    assert '[PIPELINE][RISK_INPUT] intents_count=0' in out
    no_effects(h)


def test_joined_abcd_repeat_cycles_have_new_raw_denials_and_zero_effects(reassessment,monkeypatch,tmp_path,capsys):
    h=abcd_joined(reassessment,monkeypatch,tmp_path)
    cycles(h,capsys)
    for _ in range(2):
        raw_count=len(h.batches);risk_count=len(h.evaluated)
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
        assert len(h.batches)==raw_count+1 and len(h.batches[-1])==1
        assert len(h.evaluated)==risk_count+1 and h.evaluated[-1][0] is h.batches[-1][0]
        assert h.evaluated[-1][0].setup_family_id=='ABCD'
        assert h.evaluated[-1][2].reason_code=='LIVE_READ_ONLY_BLOCK'
        no_effects(h)
    assert len({a.decision_id for a,_ in h.artifacts})==3


def test_joined_abcd_witness_completion_equality(reassessment,monkeypatch,tmp_path,capsys):
    h=abcd_joined(reassessment,monkeypatch,tmp_path,market_fault='witness_boundary_source')
    cycles(h,capsys)
    assert len(h.evaluated)==1 and h.evaluated[0][0].setup_family_id=='ABCD'
    source,results=h.registry_batches[-1]
    selected=next(r for r in results if r.setup_id=='P_ABCD')
    assert source.candles[-2].timestamp+timedelta(minutes=1)==source.observed_at_utc
    assert source.candles[-1].timestamp<=source.observed_at_utc<source.candles[-1].timestamp+timedelta(minutes=1)
    assert selected.setup_metadata['structure_completed_candle_count']==49
    assert selected.stop_level==10.35 and selected.trigger_level==11.
    no_effects(h)


def test_joined_abcd_processing_latency_cannot_complete_original_witness(reassessment,monkeypatch,tmp_path,capsys):
    h=abcd_joined(reassessment,monkeypatch,tmp_path,market_fault='delayed_witness_source')
    cycles(h,capsys)
    source,results=h.registry_batches[-1]
    selected=next(r for r in results if r.setup_id=='P_ABCD')
    assert source.observed_at_utc<h.life.clock.current
    assert source.candles[-2].timestamp+timedelta(minutes=1)>source.observed_at_utc
    assert not selected.detected and selected.rejection_reason=='NO_COMPLETED_SWING_SEQUENCE'
    assert not [i for batch in h.batches for i in batch if i.setup_family_id=='ABCD']
    no_effects(h)
