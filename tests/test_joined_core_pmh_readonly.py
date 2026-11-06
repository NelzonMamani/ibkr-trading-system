"""Offline joined PMH proof using existing fixture boundaries, real internal owners.

External facts: synthetic news batch, scanner rows, quote/history/position snapshots
and fixed clock. The inherited Core boot seams are inventoried in the checkpoint.
No prepared Focus, PatternResult, canonical contract, artifact or RiskDecision.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
import pytest

from test_joined_core_bull_micro import joined, reassessment, lifecycle, _cadence, _candles, _snapshot, _reset_config
from test_flat_top_production_handoff import forbid_collection_and_execution, forbid_io
from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY
from src.scanner import scanner_runner as ross


def pmh_joined(reassessment,monkeypatch,tmp_path,*,news_fault='none',peer=False,market_fault='none',position_case='complete_empty',runtime_options=None):
    from src.core import orchestrator as core_module
    names=('_startup_recovery_allows_strategy_execution','_autonomous_recovery_allows_new_entries',
           '_daily_risk_allows_new_entries','_resolve_fill_authority_cycle',
           '_resolve_lifecycle_authority_cycle','_run_position_management_tick','_resolve_tha_decisions',
           '_refresh_manual_focus_if_due','_resolve_manual_focus_candidates')
    real={n:getattr(core_module.CoreOrchestrator,n) for n in names}
    recovery_build,recovery_apply=core_module.build_recovery_plan,core_module.apply_recovery_actions
    h=joined(reassessment,monkeypatch,tmp_path,news_fault=news_fault,peer=peer,position_case=position_case,runtime_options=runtime_options)
    h.real_core_methods=real
    for name,method in real.items():monkeypatch.setattr(h.core,name,method.__get__(h.core))
    monkeypatch.setattr(core_module,'build_recovery_plan',recovery_build)
    monkeypatch.setattr(core_module,'apply_recovery_actions',recovery_apply)
    rows=[(10.,10.25,9.95,10.2,900)]*48+[(10.2,10.29,10.19,10.28,900),(10.31,10.55,10.30,10.53,1500)]
    rows[20]=(10.,10.3,9.95,10.2,900)  # Genuine PRE measured PMH; no override contract.
    end=h.life.clock.current.replace(second=0,microsecond=0)
    h.streams.clear()
    for tf,step in (('1m',60),('5m',300),('10s',10)):
        values=rows if tf!='5m' else [(10.,10.3,9.95,10.2,900)]*50
        h.streams[tf]=_candles(values,step_seconds=step,end=end-timedelta(seconds=step))
    if market_fault in {'waiting','touch'}:
        h.streams['10s'][-1]=replace(h.streams['10s'][-1],open=10.26,high=10.32,
            low=10.25,close=10.3 if market_fault=='touch' else 10.28)
    fault_stream='1m' if market_fault.endswith('source') else '10s'
    if market_fault.startswith('missing_'):h.streams[fault_stream]=[]
    if market_fault.startswith('stale_'):
        h.streams[fault_stream]=[replace(b,timestamp=b.timestamp-timedelta(minutes=10)) for b in h.streams[fault_stream]]
    if market_fault.startswith('future_'):
        h.streams[fault_stream][-1]=replace(h.streams[fault_stream][-1],timestamp=h.life.clock.current+timedelta(minutes=1))
    if market_fault.startswith('invalid_'):
        h.streams[fault_stream][-1]=replace(h.streams[fault_stream][-1],low=float('nan'))
    for row in h.rows.values():
        row.update(premarket_high=10.3,last_price=10.53,bid=10.52,ask=10.54,
                   spread_pct=100*.02/10.53,dollar_volume=18954000.)
    snapshot=replace(_snapshot(symbol='JPM'),last=10.53,bid=10.52,ask=10.54)
    h.core.market_data_snapshot_manager=NS(batch_snapshots=lambda symbols:({s:replace(snapshot,symbol=s,
        asof_utc=h.life.clock.current,market_timestamp_utc=h.life.clock.current) for s in symbols},[]))
    from src.storage.storage_engine import StorageEngine
    from src.storage.sqlite_store import SQLiteStore
    def forbidden_enrollment(*a,**k):pytest.fail('Atomic capital scope enrollment forbidden')
    monkeypatch.setattr(StorageEngine,'initialize_synthetic_capital_scope',forbidden_enrollment)
    monkeypatch.setattr(SQLiteStore,'initialize_synthetic_capital_scope',forbidden_enrollment)
    h.trigger_calls=[]; real=TRIGGER_EVALUATOR_REGISTRY['PREMARKET_HIGH_BREAK']
    def observed(payload,inputs):
        out=real(payload,inputs)
        h.trigger_calls.append((deepcopy(payload),deepcopy(inputs),deepcopy(out)))
        return out
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,'PREMARKET_HIGH_BREAK',observed)
    h.raw_snapshots=[]; process=h.core.strategy_runner.process
    def observed_process(**kwargs):
        out=process(**kwargs)
        h.raw_snapshots.extend(deepcopy(vars(i)) for i in out)
        return out
    h.core.strategy_runner.process=observed_process
    return h


def cycles(h,capsys):
    assert h.core.run_once()
    first=capsys.readouterr().out
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once()
    return first+capsys.readouterr().out


def no_effects(h):
    from test_joined_core_bull_micro import _assert_no_admission_effects
    _assert_no_admission_effects(h)
    capital=h.core.execution_engine.capital_authority
    assert capital.capital_scope is None and capital._capital_writer is None
    store=h.core.storage_engine._store
    assert store.connection.execute("SELECT 1 FROM sqlite_master WHERE name='capital_owner_state'").fetchone() is None


@pytest.mark.parametrize('position_case',['complete_empty','complete_matched'])
def test_native_pmh_joined_artifact_and_actual_risk_denial(reassessment,monkeypatch,tmp_path,capsys,position_case):
    h=pmh_joined(reassessment,monkeypatch,tmp_path,position_case=position_case)
    out=cycles(h,capsys)
    raw=[i for b in h.batches for i in b]
    assert len(raw)==len(h.artifacts)==len(h.evaluated)==1,out
    intent,received,decision=h.evaluated[0];artifact,built=h.artifacts[0]
    assert intent is raw[0] and artifact.intents==[intent]
    assert h.raw_snapshots==built and built[0]['decision_id'] is None
    assert received==dict(built[0],decision_id=artifact.decision_id)==vars(intent)
    assert intent.decision_id==artifact.decision_id==decision.decision_id and intent.decision_id
    assert intent.setup_family_id=='PREMARKET_HIGH_BREAK'
    source,results=h.registry_batches[-1]
    index=intent.setup_metadata['canonical_result_index'];selected=results[index]
    assert selected.setup_id=='P_PREMARKET_HIGH_BREAK' and selected.detected
    assert selected.trigger_level==selected.invalidation_level==10.3
    assert selected.stop_level==10.3-max(.01,10.3*.001)
    assert intent.entry_price==selected.trigger_level
    assert intent.stop_loss_price==selected.stop_level and intent.invalidation_level==selected.invalidation_level
    assert intent.take_profit_price is None and intent.target_model==selected.target_suggestion
    assert received['setup_metadata']['canonical_result_index']==index
    assert received['setup_metadata']['invalidation_level']==10.3
    assert received['setup_metadata']['execution_stream']['observed_at_utc']==source.observed_at_utc.isoformat()
    canonical=[(p,i,o) for p,i,o in h.trigger_calls if p.get('source')=='canonical_pattern_result' and p.get('canonical_result_index')==index]
    assert len(canonical)==1
    payload,execution,trigger=canonical[0]
    assert payload['trigger_level']==selected.trigger_level and payload['stop_level']==selected.stop_level
    assert trigger['trigger_ready_now'] and trigger['invalidation_price_reference']==10.3
    assert source.levels.premarket_high==10.3 and source.timeframe=='1m'
    assert source.timeframe_provenance=={'10s':'PRESENT','1m':'PRESENT','5m':'PRESENT'}
    assert decision.reason_code=='LIVE_READ_ONLY_BLOCK' and not decision.allowed and decision.execution_blocked
    assert decision.max_position_size==0 and decision.run_mode=='READ_ONLY'
    assert all(v.healthy and not v.block_new_entries for _,v in h.truth)
    assert _cadence(h.core).focus.symbols==['JPM']
    news=ross._ross_news_contexts_from_news_intelligence_result(h.reads[-1])
    assert news['JPM']['ross_catalyst_valid'] and news['JPM']['catalyst_type']=='EARNINGS'
    assert h.reads[-1].evidence_for_symbol('JPM')[0].evidence_id==h.article.evidence_id
    assert h.focus_calls and any([r['symbol'] for r in selected_rows]==['JPM'] for _,_,selected_rows in h.focus_calls)
    for name,method in h.real_core_methods.items():assert getattr(h.core,name).__func__ is method
    assert '[PIPELINE][RISK_OUTPUT] approved_count=0 blocked_count=1' in out
    assert 'ORDER_SUBMITTED' not in out
    no_effects(h)
    retained=deepcopy(vars(intent))
    selected.setup_metadata['pmh_path']='MUTATED_RESULT'
    source.timeframe_provenance.clear()
    assert vars(intent)==received==retained


@pytest.mark.parametrize('news_fault',['missing','stale','nonqualifying','expires_between'])
def test_pmh_news_isolation_at_real_qualification_focus(reassessment,monkeypatch,tmp_path,capsys,news_fault):
    h=pmh_joined(reassessment,monkeypatch,tmp_path,news_fault=news_fault,peer=True)
    out=cycles(h,capsys)
    news=ross._ross_news_contexts_from_news_intelligence_result(h.reads[-1])
    assert not news['JPM']['ross_catalyst_valid'] and news['PEER']['ross_catalyst_valid']
    assert news['JPM']['qualification_reason']=='no_valid_canonical_event'
    assert _cadence(h.core).watchlist.symbols==['JPM','PEER']
    assert _cadence(h.core).focus.symbols==['PEER']
    assert all([r['symbol'] for r in rows]==['PEER'] for rows,_,_ in h.focus_calls)
    assert not [s for s in h.inputs if s.symbol=='JPM']
    assert not [i for batch in h.batches for i in batch if i.symbol=='JPM']
    assert not [i for _,intents in h.artifacts for i in intents if i['symbol']=='JPM']
    assert len(h.evaluated)==1
    assert all(i.symbol=='PEER' and i.setup_family_id=='PREMARKET_HIGH_BREAK' and d.reason_code=='LIVE_READ_ONLY_BLOCK' for i,_,d in h.evaluated)
    no_effects(h)


@pytest.mark.parametrize('market_fault',['waiting','touch','missing_source','stale_source','future_source','invalid_source',
                                         'missing_execution','stale_execution','future_execution','invalid_execution'])
def test_pmh_existing_market_authority_rejects(reassessment,monkeypatch,tmp_path,capsys,market_fault):
    h=pmh_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    out=cycles(h,capsys)
    assert _cadence(h.core).focus.symbols==['JPM']
    assert not [i for batch in h.batches for i in batch if i.setup_family_id=='PREMARKET_HIGH_BREAK'],out
    pmh=[r for r in h.results if r.setup_id=='P_PREMARKET_HIGH_BREAK']
    if market_fault=='stale_source':
        assert pmh and all(not r.detected for r in pmh)
        # Full registry stays enabled: another family may use its own fresh 5m authority.
        assert any('timeframe:1m=STALE' in str(r) for r in pmh)
        assert all(i.setup_family_id!='PREMARKET_HIGH_BREAK' and d.reason_code=='LIVE_READ_ONLY_BLOCK' for i,_,d in h.evaluated)
    else:assert h.artifacts==h.evaluated==[]
    no_effects(h)


@pytest.mark.parametrize('position_case',['unknown','partial','disconnect','missing_completion','missing_interface','wrong_account',
                                         'sign_mismatch','five','quantity_warning_larger','partial_after_healthy'])
def test_pmh_raw_formation_precedes_real_portfolio_veto(reassessment,monkeypatch,tmp_path,capsys,position_case):
    h=pmh_joined(reassessment,monkeypatch,tmp_path,
        position_case='complete_matched' if position_case=='partial_after_healthy' else position_case)
    assert h.core.run_once()
    if position_case=='partial_after_healthy':
        assert h.truth[-1][1].healthy
        h.position_state['case']='partial'
    capsys.readouterr();h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once();out=capsys.readouterr().out
    raw=[i for batch in h.batches for i in batch]
    assert len(raw)==1 and raw[0].setup_family_id=='PREMARKET_HIGH_BREAK' and raw[0].decision_id is None,out
    assert h.artifacts==h.evaluated==[]
    snapshot,verdict=h.truth[-1]
    assert verdict.block_new_entries
    assert '[PIPELINE][RISK_INPUT] intents_count=0' in out and 'POSITION_TRUTH_BLOCK_NEW_ENTRIES' in out
    if position_case=='quantity_warning_larger':
        assert snapshot.broker_positions['SYNTH_MATCH'].quantity==3 and snapshot.system_positions['SYNTH_MATCH'].quantity==2
        assert [m.mismatch_type for m in snapshot.mismatches]==['QUANTITY_MISMATCH']
        assert not verdict.block_exits
    elif position_case=='five':
        assert len(snapshot.mismatches)==verdict.critical_mismatch_count==5
    elif position_case=='sign_mismatch':assert [m.mismatch_type for m in snapshot.mismatches]==['SIGN_MISMATCH']
    else:assert snapshot.snapshot_status=='UNKNOWN' and not verdict.healthy
    no_effects(h)


def test_pmh_repeat_cycles_have_no_duplicate_downstream_effects(reassessment,monkeypatch,tmp_path,capsys):
    h=pmh_joined(reassessment,monkeypatch,tmp_path)
    cycles(h,capsys)
    assert len(h.artifacts)==len(h.evaluated)==1
    h.life.clock.current+=timedelta(seconds=1)
    assert h.core.run_once();capsys.readouterr()
    assert len(h.evaluated)==2 and len(h.artifacts)==2
    assert len({a.decision_id for a,_ in h.artifacts})==2
    assert len([i for batch in h.batches for i in batch])==2
    assert all(d.reason_code=='LIVE_READ_ONLY_BLOCK' and not d.allowed for _,_,d in h.evaluated)
    assert all(i.setup_family_id=='PREMARKET_HIGH_BREAK' for batch in h.batches for i in batch)
    no_effects(h)


@pytest.mark.parametrize('stamp,premarket',[
    ('2026-10-20T13:29:59+00:00',True),('2026-10-20T13:30:00+00:00',False),
    ('2026-10-20T13:34:00+00:00',False),('2026-11-03T14:29:59+00:00',True),
    ('2026-11-03T14:30:00+00:00',False),('2026-11-03T14:34:00+00:00',False)])
def test_pmh_history_session_boundary_uses_existing_ny_open(stamp,premarket):
    from datetime import datetime
    from src.strategies.ross_momentum.patterns.pattern_trace import _is_premarket_candle
    candle=_candles([(10.,10.3,9.9,10.2,1000)],end=datetime.fromisoformat(stamp))[0]
    assert _is_premarket_candle(candle) is premarket


def test_runtime_session_reference_uses_actual_first_ny_regular_candle():
    from src.strategies.ross_momentum.patterns.pattern_trace import _infer_reference_price
    pre=_candles([(9.,10.,8.9,9.9,1000)],end=datetime(2026,10,20,13,29,tzinfo=timezone.utc))[0]
    regular=_candles([(10.1,10.4,10.,10.3,1200)],end=datetime(2026,10,20,13,30,tzinfo=timezone.utc))[0]
    assert _infer_reference_price(row={},candles=[pre,regular],session='REGULAR',prior_close=8.5)==10.1
