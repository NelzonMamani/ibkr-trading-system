"""Synthetic external facts; real news/Focus/native FIRST_PULLBACK/Core/risk owners."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace as NS

import pytest

from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY
from src.scanner import scanner_runner as ross
from test_joined_core_pmh_readonly import (
    pmh_joined, cycles, no_effects, reassessment, lifecycle, _reset_config,
    forbid_collection_and_execution, forbid_io, _cadence, _candles, _snapshot,
)
from test_first_pullback_production_handoff import ROWS


def first_joined(reassessment,monkeypatch,tmp_path,*,news_fault='none',peer=False,
                 market_fault='none',position_case='complete_empty'):
    h=pmh_joined(reassessment,monkeypatch,tmp_path,news_fault=news_fault,peer=peer,position_case=position_case)
    end=h.life.clock.current.replace(second=0,microsecond=0)
    rows=[(9.2,9.3,9.1,9.25,900)]*44+ROWS
    rows[20]=(9.2,11.,9.1,9.25,900)  # Genuine pre-session high; no competing PMH breakout.
    h.streams.clear()
    for tf,step in (('1m',60),('5m',300),('10s',10)):
        h.streams[tf]=_candles(rows,step_seconds=step,end=end-timedelta(seconds=step))
    stream='1m' if market_fault.endswith('source') else '10s'
    if market_fault.startswith('missing_'):h.streams[stream]=[]
    elif market_fault.startswith('stale_'):
        h.streams[stream]=[replace(b,timestamp=b.timestamp-timedelta(minutes=10)) for b in h.streams[stream]]
    elif market_fault.startswith('future_'):
        h.streams[stream][-1]=replace(h.streams[stream][-1],timestamp=h.life.clock.current+timedelta(seconds=12))
    elif market_fault in {'forming_structure_source','delayed_forming_structure_source'}:
        h.streams['1m'][-2]=replace(h.streams['1m'][-2],timestamp=h.life.clock.current-timedelta(seconds=9))
        h.streams['1m'][-1]=replace(h.streams['1m'][-1],timestamp=h.life.clock.current+timedelta(seconds=1))
    elif market_fault=='forming_confirmation_source':
        h.streams['1m'][-1]=replace(h.streams['1m'][-1],timestamp=h.life.clock.current-timedelta(seconds=9))
    elif market_fault=='structural_boundary_source':
        h.streams['1m'][-2]=replace(h.streams['1m'][-2],timestamp=h.life.clock.current-timedelta(seconds=49))
        h.streams['1m'][-1]=replace(h.streams['1m'][-1],timestamp=h.life.clock.current+timedelta(seconds=11))
    elif market_fault=='source_boundary':
        h.streams['1m'][-1]=replace(h.streams['1m'][-1],timestamp=h.life.clock.current-timedelta(seconds=49))
    elif market_fault.startswith('nan_'):
        h.streams[stream][-2]=replace(h.streams[stream][-2],low=float('nan'))
    elif market_fault.startswith('malformed_'):
        h.streams[stream][-2]=replace(h.streams[stream][-2],low=12.)
    elif market_fault in {'touch_execution','touch_source','below_execution'}:
        h.streams[stream][-1]=replace(h.streams[stream][-1],close=10.41 if market_fault=='below_execution' else 10.42)
    for row in h.rows.values():
        row.update(premarket_high=11.,last_price=10.55,bid=10.54,ask=10.56,
                   spread_pct=100*.02/10.55,dollar_volume=18990000.)
    snapshot=replace(_snapshot(symbol='JPM'),last=10.55,bid=10.54,ask=10.56)
    h.core.market_data_snapshot_manager=NS(batch_snapshots=lambda symbols:({s:replace(snapshot,symbol=s,
        asof_utc=h.life.clock.current,market_timestamp_utc=h.life.clock.current) for s in symbols},[]))
    h.first_triggers=[];evaluator=TRIGGER_EVALUATOR_REGISTRY['FIRST_PULLBACK']
    def observed(payload,inputs):
        result=evaluator(payload,inputs)
        h.first_triggers.append((deepcopy(payload),deepcopy(inputs),deepcopy(result)))
        return result
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,'FIRST_PULLBACK',observed)
    if market_fault=='delayed_forming_structure_source':
        run=h.strategy._pattern_registry.run
        def delayed(source,**kwargs):
            h.life.clock.current+=timedelta(minutes=2)
            return run(source,**kwargs)
        monkeypatch.setattr(h.strategy._pattern_registry,'run',delayed)
    return h


@pytest.mark.parametrize('position_case',['complete_empty','complete_matched'])
def test_joined_first_pullback_real_owners(reassessment,monkeypatch,tmp_path,capsys,position_case):
    h=first_joined(reassessment,monkeypatch,tmp_path,position_case=position_case)
    out=cycles(h,capsys)
    raw=[i for b in h.batches for i in b]
    assert len(raw)==len(h.artifacts)==len(h.evaluated)==1,out
    intent,received,decision=h.evaluated[0]
    assert intent.setup_family_id=='FIRST_PULLBACK',out
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(10.42,10.15,10.15)
    assert decision.reason_code=='LIVE_READ_ONLY_BLOCK' and not decision.allowed
    assert h.first_triggers and _cadence(h.core).focus.symbols==['JPM']
    artifact,built=h.artifacts[0]
    assert artifact.intents==[intent] and intent is raw[0]
    assert h.raw_snapshots==built and built[0]['decision_id'] is None
    assert received==dict(built[0],decision_id=artifact.decision_id)==vars(intent)
    assert intent.decision_id==artifact.decision_id==decision.decision_id
    source,results=h.registry_batches[-1]
    index=intent.setup_metadata['canonical_result_index'];selected=results[index]
    assert selected.setup_id=='P_FIRST_PULLBACK' and selected.detected and index>0
    assert (selected.trigger_level,selected.stop_level,selected.invalidation_level)==(10.42,10.15,10.15)
    assert intent.take_profit_price is None and intent.target_model==selected.target_suggestion
    payload,execution,trigger=h.first_triggers[-1]
    assert payload['canonical_result_index']==index
    assert payload['trigger_level']==intent.entry_price and payload['stop_level']==intent.stop_loss_price
    assert payload['invalidation_level']==intent.invalidation_level
    assert trigger['trigger_ready_now'] and execution['candles'][-1].close>10.42
    assert source.observed_at_utc==h.life.clock.current
    assert all(b.timestamp+timedelta(minutes=1)<=source.observed_at_utc for b in source.candles)
    assert source.timeframe=='1m' and source.timeframe_provenance=={'1m':'PRESENT','10s':'PRESENT','5m':'PRESENT'}
    news=ross._ross_news_contexts_from_news_intelligence_result(h.reads[-1])
    assert news['JPM']['ross_catalyst_valid'] and news['JPM']['catalyst_type']=='EARNINGS'
    assert h.reads[-1].evidence_for_symbol('JPM')[0].evidence_id==h.article.evidence_id
    assert h.focus_calls and all(v.healthy for _,v in h.truth)
    assert decision.execution_blocked and decision.max_position_size==0 and decision.run_mode=='READ_ONLY'
    assert 'ORDER_SUBMITTED' not in out and '[PIPELINE][RISK_OUTPUT] approved_count=0 blocked_count=1' in out
    assert not intent.relationship_context
    # Hierarchy suppression stays real and cannot turn a lower-family trace into entry.
    traces=h.strategy._failure_trace_collector._symbols[-1].pattern_traces
    micro=[t for t in traces if t.pattern_id=='P_MICRO_PULLBACK']
    assert micro and not micro[0].detected and micro[0].rejection_reason=='suppressed_by_setup_exclusivity'
    for name,method in h.real_core_methods.items():assert getattr(h.core,name).__func__ is method
    no_effects(h)
    retained=deepcopy(vars(intent));selected.setup_metadata.clear();source.timeframe_provenance.clear()
    assert vars(intent)==received==retained


@pytest.mark.parametrize('news_fault',['missing','stale','nonqualifying','expires_between'])
def test_first_news_cannot_borrow_peer_catalyst(reassessment,monkeypatch,tmp_path,capsys,news_fault):
    h=first_joined(reassessment,monkeypatch,tmp_path,news_fault=news_fault,peer=True)
    out=cycles(h,capsys)
    news=ross._ross_news_contexts_from_news_intelligence_result(h.reads[-1])
    assert not news['JPM']['ross_catalyst_valid'] and news['PEER']['ross_catalyst_valid']
    assert news['JPM']['qualification_reason']=='no_valid_canonical_event'
    assert _cadence(h.core).watchlist.symbols==['JPM','PEER']
    assert _cadence(h.core).focus.symbols==['PEER']
    assert all([row['symbol'] for row in selected]==['PEER'] for _,_,selected in h.focus_calls)
    assert not [source for source in h.inputs if source.symbol=='JPM']
    assert not [i for batch in h.batches for i in batch if i.symbol=='JPM']
    assert len(h.evaluated)==1 and all(i.symbol=='PEER' and i.setup_family_id=='FIRST_PULLBACK'
        and d.reason_code=='LIVE_READ_ONLY_BLOCK' for i,_,d in h.evaluated),out
    no_effects(h)


@pytest.mark.parametrize('market_fault',['touch_execution','below_execution','touch_source',
    'missing_source','stale_source','future_source','forming_structure_source','nan_source','malformed_source',
    'missing_execution','stale_execution','future_execution','nan_execution','malformed_execution'])
def test_first_market_authority_cannot_form_an_entry(reassessment,monkeypatch,tmp_path,capsys,market_fault):
    h=first_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    out=cycles(h,capsys)
    assert _cadence(h.core).focus.symbols==['JPM']
    assert not [i for batch in h.batches for i in batch if i.setup_family_id=='FIRST_PULLBACK'],out
    assert all(i.setup_family_id!='FIRST_PULLBACK' and d.reason_code=='LIVE_READ_ONLY_BLOCK' for i,_,d in h.evaluated)
    if market_fault=='touch_execution':
        assert h.first_triggers and not h.first_triggers[-1][2]['trigger_ready_now']
        assert h.first_triggers[-1][1]['candles'][-1].close==10.42
    no_effects(h)


@pytest.mark.parametrize('position_case',['unknown','partial','disconnect','missing_completion','missing_interface',
    'wrong_account','sign_mismatch','quantity_warning_larger','five','partial_after_healthy'])
def test_first_raw_formation_precedes_position_truth_veto(reassessment,monkeypatch,tmp_path,capsys,position_case):
    h=first_joined(reassessment,monkeypatch,tmp_path,
        position_case='complete_matched' if position_case=='partial_after_healthy' else position_case)
    assert h.core.run_once();capsys.readouterr()
    if position_case=='partial_after_healthy':
        assert h.truth[-1][1].healthy;h.position_state['case']='partial'
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once();out=capsys.readouterr().out
    raw=[i for batch in h.batches for i in batch]
    assert len(raw)==1 and raw[0].setup_family_id=='FIRST_PULLBACK' and raw[0].decision_id is None,out
    assert h.artifacts==h.evaluated==[] and h.truth[-1][1].block_new_entries
    snapshot,verdict=h.truth[-1]
    if position_case=='quantity_warning_larger':
        assert snapshot.broker_positions['SYNTH_MATCH'].quantity==3 and snapshot.system_positions['SYNTH_MATCH'].quantity==2
        assert [m.mismatch_type for m in snapshot.mismatches]==['QUANTITY_MISMATCH'] and not verdict.block_exits
    elif position_case=='five':assert verdict.critical_mismatch_count==5
    elif position_case=='sign_mismatch':assert verdict.critical_mismatch_count==1
    else:assert snapshot.snapshot_status=='UNKNOWN'
    assert '[PIPELINE][RISK_INPUT] intents_count=0' in out
    no_effects(h)


def test_first_exact_completed_source_boundary(reassessment,monkeypatch,tmp_path,capsys):
    h=first_joined(reassessment,monkeypatch,tmp_path,market_fault='source_boundary')
    cycles(h,capsys)
    assert len(h.evaluated)==1 and h.evaluated[0][0].setup_family_id=='FIRST_PULLBACK'
    source=h.registry_batches[-1][0]
    assert source.candles[-1].timestamp+timedelta(minutes=1)==source.observed_at_utc
    no_effects(h)


def test_first_repeats_have_no_downstream_effects(reassessment,monkeypatch,tmp_path,capsys):
    h=first_joined(reassessment,monkeypatch,tmp_path)
    out=cycles(h,capsys)
    for _ in range(2):
        batches_before=len(h.batches);risk_before=len(h.evaluated)
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();out+=capsys.readouterr().out
        assert len(h.batches)==batches_before+1 and len(h.batches[-1])==1
        assert len(h.evaluated)==risk_before+1
        assert h.evaluated[-1][0] is h.batches[-1][0]
        no_effects(h)
    assert all(d.reason_code=='LIVE_READ_ONLY_BLOCK' for _,_,d in h.evaluated)
    assert all(i.setup_family_id=='FIRST_PULLBACK' for batch in h.batches for i in batch)
    assert 'ORDER_SUBMITTED' not in out
    no_effects(h)


def test_first_forming_reclaim_does_not_supply_structural_anchors(reassessment,monkeypatch,tmp_path,capsys):
    h=first_joined(reassessment,monkeypatch,tmp_path,market_fault='forming_confirmation_source')
    cycles(h,capsys)
    assert len(h.evaluated)==1 and h.evaluated[0][0].setup_family_id=='FIRST_PULLBACK'
    source=h.registry_batches[-1][0];intent=h.evaluated[0][0]
    assert source.candles[-1].timestamp<=source.observed_at_utc<source.candles[-1].timestamp+timedelta(minutes=1)
    assert all(b.timestamp+timedelta(minutes=1)<=source.observed_at_utc for b in source.candles[-6:-1])
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(10.42,10.15,10.15)
    no_effects(h)


def test_first_structural_completion_equality_is_accepted(reassessment,monkeypatch,tmp_path,capsys):
    h=first_joined(reassessment,monkeypatch,tmp_path,market_fault='structural_boundary_source')
    cycles(h,capsys)
    assert len(h.evaluated)==1 and h.evaluated[0][0].setup_family_id=='FIRST_PULLBACK'
    source=h.registry_batches[-1][0]
    assert source.candles[-2].timestamp+timedelta(minutes=1)==source.observed_at_utc
    assert source.candles[-1].timestamp==source.observed_at_utc
    no_effects(h)


def test_first_later_processing_time_cannot_complete_old_structure(reassessment,monkeypatch,tmp_path,capsys):
    h=first_joined(reassessment,monkeypatch,tmp_path,market_fault='delayed_forming_structure_source')
    cycles(h,capsys)
    source,results=h.registry_batches[-1]
    result=next(r for r in results if r.setup_id=='P_FIRST_PULLBACK')
    assert source.observed_at_utc<h.life.clock.current
    assert source.candles[-2].timestamp+timedelta(minutes=1)>source.observed_at_utc
    assert source.candles[-2].timestamp+timedelta(minutes=1)<h.life.clock.current
    assert not result.detected and result.rejection_reason=='FIRST_PULLBACK_INCOMPLETE_STRUCTURE'
    assert not [i for batch in h.batches for i in batch if i.setup_family_id=='FIRST_PULLBACK']
    no_effects(h)
