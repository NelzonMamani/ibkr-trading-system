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


def raw_fixture_quote(h, snapshot, symbol):
    """External quote facts; prior close comes only from the existing row."""
    from src.ibkr.market_data_client import MarketDataSnapshot
    row=h.rows.get(symbol,{})
    close=snapshot.close
    if close is None:
        close=row.get('ref_close_rth')
        if close is None:close=row.get('prev_close')
    stamp=h.life.clock.current
    fields={name:getattr(snapshot,name) for name in
        ('bid','ask','last','bid_size','ask_size','last_size','volume','open','high','low')}
    return MarketDataSnapshot(symbol=symbol,**fields,close=close,vwap=None,change_percent=None,
        spread=(snapshot.ask-snapshot.bid if snapshot.bid is not None and snapshot.ask is not None else None),
        timestamp_utc=stamp.isoformat(),data_quality_flags=list(snapshot.data_quality_flags),
        requested_market_data_type=snapshot.requested_market_data_type,
        returned_market_data_type=snapshot.returned_market_data_type,
        market_data_type_confirmed=snapshot.market_data_type_confirmed,
        timestamp_source=snapshot.timestamp_source,received_at_utc=stamp.isoformat(),
        snapshot_complete=snapshot.snapshot_complete,request_id=snapshot.request_id,
        market_data_type_confirmation_source=snapshot.market_data_type_confirmation_source,
        field_availability={name:value is not None for name,value in fields.items()}|{'close':close is not None})


def fixture_quote_batch(h, snapshot, symbols):
    """Match the real batch API, retaining actual per-symbol quality objects."""
    from src.market_data.market_data_snapshot_manager import MarketDataSnapshotManager
    values={};qualities={}
    for symbol in symbols:
        value,qualities[symbol]=MarketDataSnapshotManager._translate_snapshot(raw_fixture_quote(h,snapshot,symbol))
        values[symbol]=replace(value,asof_utc=h.life.clock.current)
    return values,qualities


def pmh_joined(reassessment,monkeypatch,tmp_path,*,news_fault='none',peer=False,market_fault='none',position_case='complete_empty',runtime_options=None,clock_time=None,context_session=None):
    from src.core import orchestrator as core_module
    names=('_startup_recovery_allows_strategy_execution','_autonomous_recovery_allows_new_entries',
           '_daily_risk_allows_new_entries','_resolve_fill_authority_cycle',
           '_resolve_lifecycle_authority_cycle','_run_position_management_tick','_resolve_tha_decisions',
           '_refresh_manual_focus_if_due','_resolve_manual_focus_candidates')
    real={n:getattr(core_module.CoreOrchestrator,n) for n in names}
    recovery_build,recovery_apply=core_module.build_recovery_plan,core_module.apply_recovery_actions
    h=joined(reassessment,monkeypatch,tmp_path,news_fault=news_fault,peer=peer,position_case=position_case,runtime_options=runtime_options,clock_time=clock_time,context_session=context_session)
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
    h.core.market_data_snapshot_manager=NS(batch_snapshots=lambda symbols:fixture_quote_batch(h,snapshot,symbols))
    from src.storage.storage_engine import StorageEngine
    from src.storage.sqlite_store import SQLiteStore
    def forbidden_enrollment(*a,**k):pytest.fail('Atomic capital scope enrollment forbidden')
    monkeypatch.setattr(StorageEngine,'initialize_synthetic_capital_scope',forbidden_enrollment)
    monkeypatch.setattr(SQLiteStore,'initialize_synthetic_capital_scope',forbidden_enrollment)
    from src.strategies.ross_momentum.patterns import pattern_trace
    from src.ibkr.market_data_client import HistoricalDataResult
    from src.market_data.candidate_identity import CandidateIdentity
    from src.strategies.common.candles.candle_types import Candle
    h.pre_history_queries=[]
    def external_history(*,symbol,timeframe="1m",limit=50):
        h.pre_history_queries.append((symbol,timeframe,limit))
        bars=list(h.streams[timeframe])
        from src.utils.time_utils import to_ny_time
        local_clock=to_ny_time(h.life.clock.current)
        needed=max(2,min(722,int((local_clock-local_clock.replace(hour=4,minute=0,second=0,microsecond=0)).total_seconds()//60)+2))
        if timeframe=="1m" and limit==needed and bars and getattr(h,"pre_reference_fault","none")!="missing":
            from src.utils.time_utils import to_ny_time
            start=to_ny_time(h.life.clock.current).replace(hour=4,minute=0,second=0,microsecond=0).astimezone(timezone.utc)
            cursor=start
            earlier=[]
            cutoff=min(bars[0].timestamp,start+timedelta(minutes=330))
            while cursor<cutoff:
                earlier.append(Candle(10.,10.25,9.95,10.2,900,timestamp=cursor))
                context=next((b for b in h.streams.get("5m",[]) if b.timestamp<=cursor<b.timestamp+timedelta(minutes=5)),None)
                if context is not None:
                    # Expand existing external PRE context, preserving its
                    # measured high/low instead of inventing a lower PMH rival.
                    terminal=cursor==context.timestamp+timedelta(minutes=4)
                    earlier[-1]=Candle(context.open,context.high if terminal else context.open,
                        context.low if terminal else context.open,context.close if terminal else context.open,
                        context.volume/5,timestamp=cursor)
                if getattr(h,"orb_pre_history",False) and to_ny_time(cursor).hour==9 and to_ny_time(cursor).minute==29:
                    earlier[-1]=Candle(10.2,12.,9.8,10.28,100,timestamp=cursor)
                if getattr(h,"trusted_pre_scenario",False) and to_ny_time(cursor).time().hour==9 and to_ny_time(cursor).minute==29:
                    earlier[-1]=Candle(10.2,10.3,10.19,10.28,1000,timestamp=cursor)
                cursor+=timedelta(minutes=1)
            bars=earlier+bars
        return HistoricalDataResult("COMPLETE_BARS",tuple(bars[-limit:]),True,
            contract_identity=CandidateIdentity(symbol=symbol,con_id=123 if symbol=="JPM" else 456,currency="USD"))
    monkeypatch.setattr(pattern_trace,"get_intraday_bars",external_history)
    from src.market_data.reference_resolver import PersistentReferenceCache
    monkeypatch.setattr(pattern_trace,"PersistentReferenceCache",lambda:PersistentReferenceCache(tmp_path/"pre-reference.json"))
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


def key_joined(reassessment,monkeypatch,tmp_path,*,news_fault='none',peer=False,
               market_fault='none',position_case='complete_empty',runtime_options=None):
    from copy import deepcopy
    from types import SimpleNamespace as NS
    h=pmh_joined(reassessment,monkeypatch,tmp_path,news_fault=news_fault,peer=peer,
        position_case=position_case,runtime_options=runtime_options)
    rows=[(10.2,10.3,10.1,10.2,1000)]*48+[
        (10.8,10.95,10.75,10.9,1300),(10.9,11.05,10.88,11.02,1500)]
    rows[20]=(10.2,12.,10.1,10.2,1000)  # Prior PRE high prevents a competing PMH break.
    end=h.life.clock.current.replace(second=0,microsecond=0)
    h.streams.clear()
    for tf,step in (('1m',60),('5m',300),('10s',10)):
        bar_end=end if market_fault=='forming_source' and tf=='1m' else end-timedelta(seconds=step)
        if market_fault=='forming_execution' and tf=='10s':bar_end=end+timedelta(seconds=40)
        h.streams[tf]=_candles(rows,step_seconds=step,end=bar_end)
    if market_fault!='competing_opening_drive':
        from src.utils.time_utils import to_ny_time
        opening=to_ny_time(h.life.clock.current).replace(hour=9,minute=30,second=0,microsecond=0).astimezone(timezone.utc)
        # A weak opening followed by recovery is a genuine Key context, rather
        # than the original strong opening-drive competitor retained below.
        h.streams['1m']=[replace(bar,open=10.90,high=10.95) if bar.timestamp==opening else bar
            for bar in h.streams['1m']]
    flat=(10.9,10.9,10.9,10.9,0)
    _coherent_profile_streams(h,[flat]*(1 if market_fault=='forming_source' else 4)+[
        (10.9,10.95,10.88,10.9,1300),(10.9,11.05,10.88,11.02,1500)])
    if market_fault=='forming_execution':
        last=h.streams['10s'][-1]
        h.streams['10s'].extend([replace(last,timestamp=end+timedelta(seconds=30),
            open=11.02,high=11.02,low=10.9,close=10.9,volume=1300),
            replace(last,timestamp=end+timedelta(seconds=40))])
    fault=market_fault.removeprefix('delayed_')
    stream='1m' if fault.endswith('source') else '10s'
    if fault.startswith('missing_'):
        for tf in (('1m','5m') if stream=='1m' else ('10s',)):h.streams[tf]=[]
    elif fault.startswith('stale_'):
        for tf in (('1m','5m') if stream=='1m' else ('10s',)):
            h.streams[tf]=[replace(b,timestamp=b.timestamp-timedelta(minutes=10)) for b in h.streams[tf]]
    elif fault.startswith('future_'):
        h.streams[stream][-1]=replace(h.streams[stream][-1],timestamp=h.life.clock.current+timedelta(seconds=12))
    elif fault.startswith('nan_'):
        h.streams[stream][-2]=replace(h.streams[stream][-2],low=float('nan'))
    elif fault.startswith('malformed_'):
        h.streams[stream][-2]=replace(h.streams[stream][-2],low=99.)
    elif fault in {'touch_source','touch_execution','below_execution','invalidated_execution'}:
        close={'touch_source':11.,'touch_execution':11.,'below_execution':10.99,'invalidated_execution':10.88}[fault]
        h.streams[stream][-1]=replace(h.streams[stream][-1],close=close,low=min(10.88,close))
    elif fault=='no_cross_source':h.streams['1m'][-1]=replace(h.streams['1m'][-1],open=11.01)
    elif fault in {'previous_at_level_execution','previous_above_execution'}:
        close=11. if fault=='previous_at_level_execution' else 11.01
        h.streams['10s'][-2]=replace(h.streams['10s'][-2],close=close,high=close)
    elif fault in {'low_volume_execution','equal_volume_execution'}:
        h.streams['10s'][-1]=replace(h.streams['10s'][-1],volume=1000 if fault=='low_volume_execution' else 1300)
    for row in h.rows.values():
        gap=(11.02/9.8-1)*100
        row.update(premarket_high=12.,last_price=11.02,bid=11.01,ask=11.03,
            prev_close=9.8,ref_close_rth=9.8,reference_price=9.8,gap_pct=gap,pct_change=gap,
            spread_pct=100*.02/11.02,dollar_volume=19836000.)
    snapshot=replace(_snapshot(symbol='JPM'),last=11.02,bid=11.01,ask=11.03)
    h.core.market_data_snapshot_manager=NS(batch_snapshots=lambda symbols:fixture_quote_batch(h,snapshot,symbols))
    h.key_triggers=[];evaluator=TRIGGER_EVALUATOR_REGISTRY['KEY_LEVEL_BREAK']
    def observed(payload,inputs):
        out=evaluator(payload,inputs)
        h.key_triggers.append((deepcopy(payload),deepcopy(inputs),deepcopy(out)))
        return out
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,'KEY_LEVEL_BREAK',observed)
    if market_fault.startswith('delayed_'):
        original=h.strategy._pattern_registry.run
        def delayed(source,**kwargs):
            h.life.clock.current+=timedelta(minutes=2)
            return original(source,**kwargs)
        monkeypatch.setattr(h.strategy._pattern_registry,'run',delayed)
    return h


@pytest.mark.parametrize('position_case',['complete_empty','complete_matched'])
def test_joined_key_real_news_focus_artifact_and_risk(reassessment,monkeypatch,tmp_path,capsys,position_case):
    from copy import deepcopy
    from src.scanner import scanner_runner as ross
    h=key_joined(reassessment,monkeypatch,tmp_path,position_case=position_case)
    out=cycles(h,capsys)
    raw=[i for batch in h.batches for i in batch]
    assert len(raw)==len(h.artifacts)==len(h.evaluated)==1,out
    intent,received,decision=h.evaluated[0];artifact,built=h.artifacts[0]
    assert intent is raw[0] and artifact.intents==[intent]
    assert built==h.raw_snapshots and built[0]['decision_id'] is None
    assert received==dict(built[0],decision_id=artifact.decision_id)==vars(intent)
    assert intent.decision_id==artifact.decision_id==decision.decision_id
    assert intent.setup_family_id=='KEY_LEVEL_BREAK' and not intent.relationship_context
    source,results=h.registry_batches[-1]
    index=intent.setup_metadata['canonical_result_index'];selected=results[index]
    assert selected.setup_id=='P_KEY_LEVEL_BREAK' and selected.detected and index>0
    assert (selected.trigger_level,selected.stop_level,selected.invalidation_level)==(11.,10.88,11.)
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(11.,10.88,11.)
    assert intent.setup_metadata['source_metadata']==selected.setup_metadata
    assert selected.setup_metadata['level_type']=='WHOLE_DOLLAR'
    assert selected.setup_metadata['selected_level_source']=='round_number'
    assert intent.target_model==selected.target_suggestion=='Expansion to next overhead key level'
    assert intent.take_profit_price is None
    for key in ('trigger_level','stop_level','invalidation_level'):
        assert intent.setup_metadata[key]==getattr(selected,key)
    payload,execution,trigger=h.key_triggers[-1]
    assert payload['canonical_result_index']==index and trigger['trigger_ready_now']
    assert payload['stop_level']==trigger['stop_level']==10.88
    assert payload['invalidation_level']==trigger['invalidation_price_reference']==11.
    assert execution['candles'][-2].close<=11.<execution['candles'][-1].close
    assert source.observed_at_utc==h.life.clock.current
    assert received['setup_metadata']['execution_stream']['observed_at_utc']==source.observed_at_utc.isoformat()
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


@pytest.mark.parametrize('market_fault',['future_source','nan_source','malformed_source',
    'future_execution','nan_execution','malformed_execution','delayed_future_source','delayed_future_execution'])
def test_joined_key_invalid_market_cannot_form_intent(reassessment,monkeypatch,tmp_path,capsys,market_fault):
    h=key_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    out=cycles(h,capsys)
    assert _cadence(h.core).focus.symbols==['JPM']
    assert not [i for batch in h.batches for i in batch if i.setup_family_id=='KEY_LEVEL_BREAK'],out
    assert all(i.setup_family_id!='KEY_LEVEL_BREAK' and d.reason_code=='LIVE_READ_ONLY_BLOCK' for i,_,d in h.evaluated)
    if market_fault.endswith('source'):
        source,results=h.registry_batches[-1]
        selected=next(r for r in results if r.setup_id=='P_KEY_LEVEL_BREAK')
        reason='FUTURE_CANDLE_DATA' if 'future' in market_fault else 'INVALID_CANDLE_DATA'
        assert not selected.detected and selected.rejection_reason=='KEY_LEVEL_BREAK_'+reason
        if market_fault.startswith('delayed_'):assert source.observed_at_utc<h.life.clock.current
    else:
        assert h.key_triggers and not h.key_triggers[-1][2]['trigger_ready_now']
        reason='future_candle_data' if 'future' in market_fault else 'invalid_candle_data'
        assert h.key_triggers[-1][2]['trigger_reason']=='key_level_break_'+reason
        if market_fault.startswith('delayed_'):
            stream=h.key_triggers[-1][0]['execution_stream']
            assert stream['observed_at_utc']==h.registry_batches[-1][0].observed_at_utc.isoformat()
            assert h.registry_batches[-1][0].observed_at_utc<h.life.clock.current
    no_effects(h)


@pytest.mark.parametrize('market_fault',['forming_source','forming_execution','previous_at_level_execution','equal_volume_execution'])
def test_joined_key_preserves_live_break_and_confirmation_boundaries(reassessment,monkeypatch,tmp_path,capsys,market_fault):
    h=key_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    cycles(h,capsys)
    assert len(h.evaluated)==1 and h.evaluated[0][0].setup_family_id=='KEY_LEVEL_BREAK'
    intent,_,decision=h.evaluated[0]
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(11.,10.88,11.)
    assert decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    if market_fault=='forming_source':
        source=h.registry_batches[-1][0]
        assert source.candles[-1].timestamp<=source.observed_at_utc<source.candles[-1].timestamp+timedelta(minutes=1)
    if market_fault=='forming_execution':
        _,execution,_=h.key_triggers[-1]
        now=h.life.clock.current
        assert execution['candles'][-1].timestamp<=now<execution['candles'][-1].timestamp+timedelta(seconds=10)
    if market_fault=='previous_at_level_execution':assert h.key_triggers[-1][1]['candles'][-2].close==11.
    if market_fault=='equal_volume_execution':
        candles=h.key_triggers[-1][1]['candles']
        assert candles[-1].volume==candles[-2].volume==1300
    no_effects(h)


@pytest.mark.parametrize('market_fault',['missing_source','stale_source','missing_execution','stale_execution',
    'touch_source','no_cross_source','touch_execution','below_execution','invalidated_execution',
    'previous_above_execution','low_volume_execution'])
def test_joined_key_missing_or_unconfirmed_data_blocks(reassessment,monkeypatch,tmp_path,capsys,market_fault):
    h=key_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    out=cycles(h,capsys)
    assert _cadence(h.core).focus.symbols==['JPM']
    assert not [i for batch in h.batches for i in batch if i.setup_family_id=='KEY_LEVEL_BREAK'],out
    assert all(i.setup_family_id!='KEY_LEVEL_BREAK' and d.reason_code=='LIVE_READ_ONLY_BLOCK' for i,_,d in h.evaluated)
    if market_fault in {'missing_execution','stale_execution','touch_execution','below_execution',
                        'invalidated_execution','previous_above_execution','low_volume_execution'}:
        own=next(t for t in h.strategy._failure_trace_collector._symbols[-1].input_summary['trigger_candidates']
            if t.get('setup_family_id')=='KEY_LEVEL_BREAK')
        reasons={'missing_execution':'execution_stream_missing','stale_execution':'execution_stream_stale',
            'touch_execution':'at_or_below_invalidation','below_execution':'at_or_below_invalidation',
            'invalidated_execution':'at_or_below_invalidation','previous_above_execution':'awaiting_decisive_break_and_acceptance',
            'low_volume_execution':'awaiting_decisive_break_and_acceptance'}
        assert not own['trigger_ready_now'] and own['trigger_reason']==reasons[market_fault]
    if market_fault in {'touch_source','no_cross_source'}:
        selected=next(r for r in h.registry_batches[-1][1] if r.setup_id=='P_KEY_LEVEL_BREAK')
        assert not selected.detected and selected.rejection_reason==('wick_through_only' if market_fault=='touch_source' else 'no_relevant_key_level')
    no_effects(h)


@pytest.mark.parametrize('news_fault',['missing','stale','nonqualifying','expires_between'])
def test_joined_key_issuer_isolation(reassessment,monkeypatch,tmp_path,capsys,news_fault):
    h=key_joined(reassessment,monkeypatch,tmp_path,news_fault=news_fault,peer=True)
    out=cycles(h,capsys)
    news=ross._ross_news_contexts_from_news_intelligence_result(h.reads[-1])
    assert not news['JPM']['ross_catalyst_valid'] and news['PEER']['ross_catalyst_valid']
    assert news['JPM']['qualification_reason']=='no_valid_canonical_event'
    assert _cadence(h.core).watchlist.symbols==['JPM','PEER'] and _cadence(h.core).focus.symbols==['PEER']
    assert all([r['symbol'] for r in selected]==['PEER'] for _,_,selected in h.focus_calls)
    assert not [source for source in h.inputs if source.symbol=='JPM']
    assert not [i for batch in h.batches for i in batch if i.symbol=='JPM']
    assert len(h.evaluated)==1 and all(i.symbol=='PEER' and i.setup_family_id=='KEY_LEVEL_BREAK'
        and d.reason_code=='LIVE_READ_ONLY_BLOCK' for i,_,d in h.evaluated),out
    no_effects(h)


@pytest.mark.parametrize('position_case',['unknown','partial','quantity_warning_larger','five','partial_after_healthy'])
def test_joined_key_raw_before_actual_position_veto(reassessment,monkeypatch,tmp_path,capsys,position_case):
    h=key_joined(reassessment,monkeypatch,tmp_path,
        position_case='complete_matched' if position_case=='partial_after_healthy' else position_case)
    assert h.core.run_once();capsys.readouterr()
    if position_case=='partial_after_healthy':
        assert h.truth[-1][1].healthy;h.position_state['case']='partial'
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once();out=capsys.readouterr().out
    raw=[i for batch in h.batches for i in batch]
    assert len(raw)==1 and raw[0].setup_family_id=='KEY_LEVEL_BREAK' and raw[0].decision_id is None,out
    assert h.artifacts==h.evaluated==[] and h.truth[-1][1].block_new_entries
    snapshot,verdict=h.truth[-1]
    if position_case=='quantity_warning_larger':
        assert snapshot.broker_positions['SYNTH_MATCH'].quantity==3 and snapshot.system_positions['SYNTH_MATCH'].quantity==2
        assert [m.mismatch_type for m in snapshot.mismatches]==['QUANTITY_MISMATCH'] and not verdict.block_exits
    elif position_case=='five':assert verdict.critical_mismatch_count==5
    else:assert snapshot.snapshot_status=='UNKNOWN'
    assert '[PIPELINE][RISK_INPUT] intents_count=0' in out
    no_effects(h)


def test_joined_key_repeats_observe_new_raw_and_actual_denials(reassessment,monkeypatch,tmp_path,capsys):
    h=key_joined(reassessment,monkeypatch,tmp_path)
    cycles(h,capsys)
    for _ in range(2):
        raw_count=len(h.batches);risk_count=len(h.evaluated)
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
        assert len(h.batches)==raw_count+1 and len(h.batches[-1])==1
        assert len(h.evaluated)==risk_count+1 and h.evaluated[-1][0] is h.batches[-1][0]
        assert h.evaluated[-1][0].setup_family_id=='KEY_LEVEL_BREAK'
        assert h.evaluated[-1][2].reason_code=='LIVE_READ_ONLY_BLOCK'
        no_effects(h)
    assert len({a.decision_id for a,_ in h.artifacts})==3


def consolidation_joined(reassessment,monkeypatch,tmp_path,*,news_fault='none',peer=False,
                         market_fault='none',position_case='complete_empty',runtime_options=None):
    from test_consolidation_production_authority import TAIL
    h=pmh_joined(reassessment,monkeypatch,tmp_path,news_fault=news_fault,peer=peer,
                 position_case=position_case,runtime_options=runtime_options)
    # Keep the existing range geometry below the next half-dollar level.
    # Equal last-five mean volume is accepted by Consolidation's own >= law;
    # it is not Flat Top's strict volume expansion. No registry/rank override.
    rows=[(10.,10.1,9.95,10.,900)]*42+[
        tuple(round(v-.1,2) if i<4 else v for i,v in enumerate(row)) for row in TAIL]
    rows[-1]=(*rows[-1][:4],825)
    rows[20]=(10.,12.,9.95,10.,900)  # Actual prior PRE high, no competing PMH break.
    end=h.life.clock.current.replace(second=0,microsecond=0)
    h.streams.clear()
    for tf,step in (('1m',60),('5m',300)):
        h.streams[tf]=_candles(rows,step_seconds=step,end=end-timedelta(seconds=step))
    h.streams['10s']=_candles([(10.25,10.29,10.22,10.27,100)]*29+
        [(10.27,10.46,10.22,10.43,200)],step_seconds=10,end=end-timedelta(seconds=10))
    fault=market_fault.removeprefix('delayed_')
    stream='1m' if fault.endswith('source') else '10s'
    if fault.startswith(('missing_','stale_','short_')):
        for tf in (('1m','5m') if stream=='1m' else ('10s',)):
            if fault.startswith('missing_'):h.streams[tf]=[]
            elif fault.startswith('short_'):h.streams[tf]=h.streams[tf][-7:]
            else:h.streams[tf]=[replace(b,timestamp=b.timestamp-timedelta(hours=1)) for b in h.streams[tf]]
    elif fault.startswith('future_'):
        h.streams[stream][-1]=replace(h.streams[stream][-1],timestamp=h.life.clock.current+timedelta(seconds=12))
    elif fault.startswith('nan_'):h.streams[stream][-2]=replace(h.streams[stream][-2],low=float('nan'))
    elif fault.startswith('infinite_'):h.streams[stream][-2]=replace(h.streams[stream][-2],volume=float('inf'))
    elif fault.startswith('malformed_'):h.streams[stream][-2]=replace(h.streams[stream][-2],low=99.)
    elif fault.startswith('unordered_'):
        h.streams[stream][-1]=replace(h.streams[stream][-1],timestamp=h.streams[stream][-2].timestamp)
    elif fault=='forming_source':
        h.streams['1m'][-1]=replace(h.streams['1m'][-1],timestamp=end)
    elif fault=='appended_forming_source':
        h.streams['1m'].append(replace(h.streams['1m'][-1],timestamp=end,
            open=10.43,high=10.47,low=10.25,close=10.44,volume=9000))
    elif fault=='forming_execution':
        h.streams['10s'][-1]=replace(h.streams['10s'][-1],timestamp=end+timedelta(seconds=40))
    elif fault in {'touch_source','wide_source'}:
        if fault=='touch_source':h.streams['1m'][-1]=replace(h.streams['1m'][-1],close=10.3)
        else:h.streams['1m'][-3]=replace(h.streams['1m'][-3],low=10.1)
    elif fault in {'touch_execution','below_execution','invalidated_execution'}:
        close={'touch_execution':10.3,'below_execution':10.29,'invalidated_execution':10.21}[fault]
        h.streams['10s'][-1]=replace(h.streams['10s'][-1],close=close,low=min(10.22,close))
    elif fault in {'equal_volume_execution','low_volume_execution'}:
        h.streams['10s'][-1]=replace(h.streams['10s'][-1],volume=100 if fault.startswith('equal_') else 99)
    elif fault=='previous_above_execution':
        h.streams['10s'][-2]=replace(h.streams['10s'][-2],high=10.35,close=10.32)
    for row in h.rows.values():
        row.update(premarket_high=12.,last_price=10.43,bid=10.42,ask=10.44,
            prev_close=9.3,ref_close_rth=9.3,reference_price=9.3,
            gap_pct=(10.43/9.3-1)*100,pct_change=(10.43/9.3-1)*100,
            spread_pct=100*.02/10.43,dollar_volume=18774000.)
    snapshot=replace(_snapshot(symbol='JPM'),last=10.43,bid=10.42,ask=10.44)
    h.core.market_data_snapshot_manager=NS(batch_snapshots=lambda symbols:fixture_quote_batch(h,snapshot,symbols))
    h.consolidation_triggers=[]
    evaluator=TRIGGER_EVALUATOR_REGISTRY['CONSOLIDATION_BREAKOUT']
    def observed(payload,inputs):
        out=evaluator(payload,inputs)
        h.consolidation_triggers.append((deepcopy(payload),deepcopy(inputs),deepcopy(out)))
        return out
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,'CONSOLIDATION_BREAKOUT',observed)
    if market_fault.startswith('delayed_'):
        original=h.strategy._pattern_registry.run
        def delayed(source,**kwargs):
            h.life.clock.current+=timedelta(seconds=6)
            return original(source,**kwargs)
        monkeypatch.setattr(h.strategy._pattern_registry,'run',delayed)
    return h


@pytest.mark.parametrize('position_case',['complete_empty','complete_matched'])
def test_joined_consolidation_real_news_focus_artifact_and_risk(reassessment,monkeypatch,tmp_path,capsys,position_case):
    h=consolidation_joined(reassessment,monkeypatch,tmp_path,position_case=position_case)
    out=cycles(h,capsys)
    raw=[i for batch in h.batches for i in batch]
    assert len(raw)==len(h.artifacts)==len(h.evaluated)==1,out
    intent,received,decision=h.evaluated[0]
    artifact,built=h.artifacts[0]
    assert intent is raw[0] and artifact.intents==[intent]
    assert built==h.raw_snapshots and built[0]['decision_id'] is None
    assert received==dict(built[0],decision_id=artifact.decision_id)==vars(intent)
    assert intent.decision_id==artifact.decision_id==decision.decision_id and intent.decision_id
    assert intent.setup_family_id=='CONSOLIDATION_BREAKOUT' and not intent.relationship_context,out
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(10.3,10.21,10.21)
    source,results=h.registry_batches[-1]
    index=intent.setup_metadata['canonical_result_index'];selected=results[index]
    from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
    assert [p.pattern_id for p in h.strategy._pattern_registry._patterns]==[
        p.pattern_id for p in RossPatternRegistry()._patterns]
    assert selected.setup_id=='P_CONSOLIDATION_BREAK' and selected.detected and index>0
    completed=[b for b in source.candles if b.timestamp+timedelta(minutes=1)<=source.observed_at_utc]
    assert len(completed)==50 and source.timeframe=='1m'
    assert max(b.high for b in completed[-6:-1])==selected.trigger_level==10.3
    assert min(b.low for b in completed[-6:-1])==selected.stop_level==selected.invalidation_level==10.21
    assert completed[-1].close>selected.trigger_level
    assert completed[-1].volume==sum(b.volume for b in completed[-5:-1])/4==825
    assert selected.setup_metadata['breakout_volume_confirmed'] is True
    assert intent.setup_metadata['source_metadata']==selected.setup_metadata
    assert intent.target_model==selected.target_suggestion=='Range expansion' and intent.take_profit_price is None
    for key in ('trigger_level','stop_level','invalidation_level'):
        assert intent.setup_metadata[key]==getattr(selected,key)
    canonical=[t for t in h.consolidation_triggers if t[0].get('source')=='canonical_pattern_result'
               and t[0].get('canonical_result_index')==index]
    assert len(canonical)==1
    payload,execution,trigger=canonical[0]
    assert (payload['trigger_level'],payload['stop_level'],payload['invalidation_level'])==(10.3,10.21,10.21)
    assert trigger['trigger_ready_now'] and trigger['trigger_reason']=='consolidation_breakout_confirmed'
    assert trigger['trigger_price_reference']==10.3 and trigger['invalidation_price_reference']==10.21
    assert source.observed_at_utc==h.life.clock.current
    assert received['setup_metadata']['execution_stream']==payload['execution_stream']
    assert payload['execution_stream']['observed_at_utc']==source.observed_at_utc.isoformat()
    assert payload['execution_stream']['execution_trigger_timeframe']=='10s'
    assert payload['execution_stream']['timeframe_substitution'] is False
    assert decision.reason_code=='LIVE_READ_ONLY_BLOCK' and not decision.allowed
    assert decision.execution_blocked and decision.max_position_size==0 and decision.run_mode=='READ_ONLY'
    assert all(v.healthy and not v.block_new_entries for _,v in h.truth)
    assert _cadence(h.core).focus.symbols==['JPM'] and h.focus_calls
    news=ross._ross_news_contexts_from_news_intelligence_result(h.reads[-1])
    assert news['JPM']['ross_catalyst_valid'] and news['JPM']['catalyst_type']=='EARNINGS'
    assert h.reads[-1].evidence_for_symbol('JPM')[0].evidence_id==h.article.evidence_id
    for name,method in h.real_core_methods.items():assert getattr(h.core,name).__func__ is method
    assert '[PIPELINE][RISK_OUTPUT] approved_count=0 blocked_count=1' in out and 'ORDER_SUBMITTED' not in out
    no_effects(h)
    retained=deepcopy(vars(intent))
    selected.setup_metadata.clear();source.timeframe_provenance.clear();source.candles.clear()
    payload['setup_metadata'].clear();payload['execution_stream'].clear()
    assert vars(intent)==received==retained


@pytest.mark.parametrize('market_fault',['missing_source','stale_source','short_source','future_source',
    'nan_source','infinite_source','malformed_source','unordered_source','forming_source','touch_source','wide_source',
    'missing_execution','stale_execution','future_execution','nan_execution','infinite_execution',
    'malformed_execution','unordered_execution','below_execution','invalidated_execution','low_volume_execution',
    'delayed_future_source','delayed_future_execution'])
def test_joined_consolidation_existing_authority_rejects(reassessment,monkeypatch,tmp_path,capsys,market_fault):
    h=consolidation_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    out=cycles(h,capsys)
    assert _cadence(h.core).focus.symbols==['JPM']
    assert not [i for batch in h.batches for i in batch if i.setup_family_id=='CONSOLIDATION_BREAKOUT'],out
    assert all(i.setup_family_id!='CONSOLIDATION_BREAKOUT' and d.reason_code=='LIVE_READ_ONLY_BLOCK' for i,_,d in h.evaluated)
    if market_fault.endswith('source'):
        own=[r for r in h.results if r.setup_id=='P_CONSOLIDATION_BREAK']
        if market_fault=='missing_source':
            assert own==[] and h.inputs==[] and h.artifacts==h.evaluated==[]
        else:assert own and all(not r.detected for r in own)
        expected={'short_source':'insufficient candles','forming_source':'consolidation too wide',
                  'touch_source':'no breakout from consolidation','wide_source':'consolidation too wide',
                  'future_source':'FUTURE_CANDLE_DATA','delayed_future_source':'FUTURE_CANDLE_DATA',
                  'nan_source':'INVALID_CANDLE_DATA','infinite_source':'INVALID_CANDLE_DATA',
                  'malformed_source':'INVALID_CANDLE_DATA','unordered_source':'INVALID_CANDLE_TIMESTAMPS'}
        if market_fault in expected:assert own[-1].rejection_reason==expected[market_fault]
    else:
        own=next(t for t in h.strategy._failure_trace_collector._symbols[-1].input_summary['trigger_candidates']
                 if t.get('setup_family_id')=='CONSOLIDATION_BREAKOUT')
        expected={'missing_execution':'execution_stream_missing','stale_execution':'execution_stream_stale',
            'future_execution':'consolidation_future_candle_data','delayed_future_execution':'consolidation_future_candle_data',
            'nan_execution':'consolidation_invalid_candle_data','infinite_execution':'consolidation_invalid_candle_data',
            'malformed_execution':'consolidation_invalid_candle_data','unordered_execution':'execution_stream_stale',
            'below_execution':'breakout_not_cleared','invalidated_execution':'at_or_below_invalidation',
            'low_volume_execution':'breakout_volume_unconfirmed'}
        assert not own['trigger_ready_now'] and own['trigger_reason']==expected[market_fault]
        if market_fault=='invalidated_execution':
            assert own['invalidation_price_reference']==10.21 and 'NEAR_INVALIDATION' in own['trigger_quality_flags']
    if market_fault.startswith('delayed_'):
        source=h.registry_batches[-1][0]
        assert source.observed_at_utc<h.life.clock.current
        tf='1m' if market_fault.endswith('source') else '10s'
        assert source.observed_at_utc<h.streams[tf][-1].timestamp<=h.life.clock.current
        if market_fault.endswith('execution'):
            assert h.consolidation_triggers[-1][0]['execution_stream']['observed_at_utc']==source.observed_at_utc.isoformat()
    no_effects(h)


@pytest.mark.parametrize('market_fault',['appended_forming_source','forming_execution','touch_execution',
                                       'equal_volume_execution','previous_above_execution'])
def test_joined_consolidation_preserves_own_completion_and_confirmation(reassessment,monkeypatch,tmp_path,capsys,market_fault):
    h=consolidation_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    out=cycles(h,capsys)
    if market_fault=='appended_forming_source':
        source,results=h.registry_batches[-1]
        own=next(r for r in results if r.setup_id=='P_CONSOLIDATION_BREAK')
        assert own.detected and (own.trigger_level,own.stop_level,own.invalidation_level)==(10.3,10.21,10.21)
        assert source.candles[-1].high==10.47 and source.candles[-1].timestamp+timedelta(minutes=1)>source.observed_at_utc
        momentum=next(r for r in results if r.setup_id=='P_MOMENTUM_RECLAIM')
        assert momentum.detected  # Detection alone cannot starve a ready continuation.
    assert len(h.evaluated)==1 and h.evaluated[0][0].setup_family_id=='CONSOLIDATION_BREAKOUT',out
    intent,_,decision=h.evaluated[0]
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(10.3,10.21,10.21)
    assert decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    source=h.registry_batches[-1][0];payload,execution,trigger=h.consolidation_triggers[-1]
    if market_fault=='forming_execution':
        assert execution['candles'][-1].timestamp<=source.observed_at_utc<execution['candles'][-1].timestamp+timedelta(seconds=10)
    if market_fault=='touch_execution':assert execution['candles'][-1].close==10.3
    if market_fault=='equal_volume_execution':assert execution['candles'][-1].volume==sum(b.volume for b in execution['candles'][-5:-1])/4==100
    if market_fault=='previous_above_execution':assert execution['candles'][-2].close>10.3
    assert trigger['trigger_ready_now'] and trigger['trigger_reason']=='consolidation_breakout_confirmed'
    no_effects(h)


@pytest.mark.parametrize('news_fault',['missing','stale','nonqualifying','expires_between'])
@pytest.mark.parametrize('family',['CONSOLIDATION_BREAKOUT','FLAT_TOP_BREAKOUT','OPENING_RANGE_BREAKOUT','HOD_BREAK','MICRO_PULLBACK'])
def test_joined_range_breakout_issuer_isolation(reassessment,monkeypatch,tmp_path,capsys,news_fault,family):
    factory={'CONSOLIDATION_BREAKOUT':consolidation_joined,'FLAT_TOP_BREAKOUT':flat_top_joined,'OPENING_RANGE_BREAKOUT':orb_joined,'HOD_BREAK':hod_joined,'MICRO_PULLBACK':micro_joined}[family]
    h=factory(reassessment,monkeypatch,tmp_path,news_fault=news_fault,peer=True)
    out=cycles(h,capsys)
    news=ross._ross_news_contexts_from_news_intelligence_result(h.reads[-1])
    assert not news['JPM']['ross_catalyst_valid'] and news['PEER']['ross_catalyst_valid']
    assert news['JPM']['qualification_reason']=='no_valid_canonical_event'
    assert _cadence(h.core).watchlist.symbols==['JPM','PEER'] and _cadence(h.core).focus.symbols==['PEER']
    assert all([r['symbol'] for r in selected]==['PEER'] for _,_,selected in h.focus_calls)
    assert not [source for source in h.inputs if source.symbol=='JPM']
    assert not [i for batch in h.batches for i in batch if i.symbol=='JPM']
    assert len(h.evaluated)==1 and all(i.symbol=='PEER' and i.setup_family_id==family
        and d.reason_code=='LIVE_READ_ONLY_BLOCK' for i,_,d in h.evaluated),out
    no_effects(h)


@pytest.mark.parametrize('position_case',['unknown','partial','quantity_warning_larger','five','partial_after_healthy'])
@pytest.mark.parametrize('family',['CONSOLIDATION_BREAKOUT','FLAT_TOP_BREAKOUT','OPENING_RANGE_BREAKOUT','HOD_BREAK','MICRO_PULLBACK'])
def test_joined_range_breakout_raw_before_actual_position_veto(reassessment,monkeypatch,tmp_path,capsys,position_case,family):
    factory={'CONSOLIDATION_BREAKOUT':consolidation_joined,'FLAT_TOP_BREAKOUT':flat_top_joined,'OPENING_RANGE_BREAKOUT':orb_joined,'HOD_BREAK':hod_joined,'MICRO_PULLBACK':micro_joined}[family]
    h=factory(reassessment,monkeypatch,tmp_path,
        position_case='complete_matched' if position_case=='partial_after_healthy' else position_case)
    assert h.core.run_once();capsys.readouterr()
    if position_case=='partial_after_healthy':
        assert h.truth[-1][1].healthy;h.position_state['case']='partial'
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once();out=capsys.readouterr().out
    raw=[i for batch in h.batches for i in batch]
    assert len(raw)==1 and raw[0].setup_family_id==family and raw[0].decision_id is None,out
    assert h.artifacts==h.evaluated==[] and h.truth[-1][1].block_new_entries
    snapshot,verdict=h.truth[-1]
    if position_case=='quantity_warning_larger':
        assert snapshot.broker_positions['SYNTH_MATCH'].quantity==3 and snapshot.system_positions['SYNTH_MATCH'].quantity==2
        assert [m.mismatch_type for m in snapshot.mismatches]==['QUANTITY_MISMATCH'] and not verdict.block_exits
    elif position_case=='five':assert verdict.critical_mismatch_count==5
    else:assert snapshot.snapshot_status=='UNKNOWN'
    assert '[PIPELINE][RISK_INPUT] intents_count=0' in out
    no_effects(h)


@pytest.mark.parametrize('family',['CONSOLIDATION_BREAKOUT','FLAT_TOP_BREAKOUT','OPENING_RANGE_BREAKOUT','HOD_BREAK','MICRO_PULLBACK'])
def test_joined_range_breakout_repeats_observe_new_raw_and_actual_denials(reassessment,monkeypatch,tmp_path,capsys,family):
    factory={'CONSOLIDATION_BREAKOUT':consolidation_joined,'FLAT_TOP_BREAKOUT':flat_top_joined,'OPENING_RANGE_BREAKOUT':orb_joined,'HOD_BREAK':hod_joined,'MICRO_PULLBACK':micro_joined}[family]
    h=factory(reassessment,monkeypatch,tmp_path)
    cycles(h,capsys)
    for _ in range(2):
        raw_count=len(h.batches);risk_count=len(h.evaluated)
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
        assert len(h.batches)==raw_count+1 and len(h.batches[-1])==1
        assert len(h.evaluated)==risk_count+1 and h.evaluated[-1][0] is h.batches[-1][0]
        assert h.evaluated[-1][0].setup_family_id==family
        assert h.evaluated[-1][2].reason_code=='LIVE_READ_ONLY_BLOCK'
        no_effects(h)
    assert len({a.decision_id for a,_ in h.artifacts})==3


def flat_top_joined(reassessment,monkeypatch,tmp_path,*,news_fault='none',peer=False,
                    market_fault='none',position_case='complete_empty',runtime_options=None):
    from test_flat_top_production_handoff import TAIL
    h=pmh_joined(reassessment,monkeypatch,tmp_path,news_fault=news_fault,peer=peer,
                 position_case=position_case,runtime_options=runtime_options)
    rows=[(10.,10.12,9.98,10.08,900)]*45+list(TAIL)
    rows[20]=(10.,12.,9.98,10.08,900)  # Real prior PRE high, no competing PMH break.
    end=h.life.clock.current.replace(second=0,microsecond=0)
    h.streams.clear()
    for tf,step in (('1m',60),('5m',300)):
        h.streams[tf]=_candles(rows,step_seconds=step,end=end-timedelta(seconds=step))
    h.streams['10s']=_candles([(10.15,10.19,10.14,10.18,100)]*29+
        [(10.18,10.3,10.14,10.27,200)],step_seconds=10,end=end-timedelta(seconds=10))
    fault=market_fault.removeprefix('delayed_')
    stream='1m' if fault.endswith('source') else '10s'
    if fault.startswith(('missing_','stale_','short_')):
        for tf in (('1m','5m') if stream=='1m' else ('10s',)):
            if fault.startswith('missing_'):h.streams[tf]=[]
            elif fault.startswith('short_'):h.streams[tf]=h.streams[tf][-4:]
            else:h.streams[tf]=[replace(b,timestamp=b.timestamp-timedelta(hours=1)) for b in h.streams[tf]]
    elif fault.startswith('future_'):
        h.streams[stream][-1]=replace(h.streams[stream][-1],timestamp=h.life.clock.current+timedelta(seconds=12))
    elif fault.startswith('nan_'):h.streams[stream][-2]=replace(h.streams[stream][-2],low=float('nan'))
    elif fault.startswith('infinite_'):h.streams[stream][-2]=replace(h.streams[stream][-2],volume=float('inf'))
    elif fault.startswith('malformed_'):h.streams[stream][-2]=replace(h.streams[stream][-2],low=99.)
    elif fault.startswith('unordered_'):
        h.streams[stream][-1]=replace(h.streams[stream][-1],timestamp=h.streams[stream][-2].timestamp)
    elif fault=='forming_source':h.streams['1m'][-1]=replace(h.streams['1m'][-1],timestamp=end)
    elif fault in {'exact_completion_source','before_completion_source'}:
        h.streams['1m'][-1]=replace(h.streams['1m'][-1],timestamp=h.life.clock.current+
            timedelta(seconds=11-60,microseconds=1 if fault.startswith('before_') else 0))
    elif fault=='appended_forming_source':
        h.streams['1m'].append(replace(h.streams['1m'][-1],timestamp=end,open=10.27,high=99.,low=1.))
    elif fault in {'at_threshold_source','below_threshold_source'}:
        close=10.2+max(.02,10.2*.003)*.25
        h.streams['1m'][-1]=replace(h.streams['1m'][-1],close=close-(1e-9 if fault.startswith('below_') else 0))
    elif fault in {'equal_volume_source','low_volume_source'}:
        mean=sum(b.volume for b in h.streams['1m'][-5:-1])/4
        h.streams['1m'][-1]=replace(h.streams['1m'][-1],volume=mean-(1 if fault.startswith('low_') else 0))
    elif fault=='nonflat_source':h.streams['1m'][-3]=replace(h.streams['1m'][-3],high=10.4)
    elif fault in {'touch_execution','below_execution','invalidated_execution'}:
        close={'touch_execution':10.2,'below_execution':10.19,'invalidated_execution':9.99}[fault]
        h.streams['10s'][-1]=replace(h.streams['10s'][-1],close=close,low=min(10.14,close))
    elif fault=='zero_volume_execution':h.streams['10s'][-1]=replace(h.streams['10s'][-1],volume=0.)
    elif fault=='forming_execution':
        h.streams['10s'][-1]=replace(h.streams['10s'][-1],timestamp=end+timedelta(seconds=40))
    last,previous,premarket=10.27,9.2,12.
    if fault=='competing_key':
        h.streams.update({tf:[replace(b,**{key:round(getattr(b,key)+.3,2)
            for key in ('open','high','low','close')}) for b in bars] for tf,bars in h.streams.items()})
        last,previous,premarket=10.57,9.5,12.3
    for row in h.rows.values():
        row.update(premarket_high=premarket,last_price=last,bid=round(last-.01,2),ask=round(last+.01,2),
            prev_close=previous,ref_close_rth=previous,reference_price=previous,
            gap_pct=(last/previous-1)*100,pct_change=(last/previous-1)*100,
            spread_pct=100*.02/last,dollar_volume=last*1_800_000)
    snapshot=replace(_snapshot(symbol='JPM'),last=last,bid=round(last-.01,2),ask=round(last+.01,2))
    h.core.market_data_snapshot_manager=NS(batch_snapshots=lambda symbols:fixture_quote_batch(h,snapshot,symbols))
    h.flat_top_triggers=[];evaluator=TRIGGER_EVALUATOR_REGISTRY['FLAT_TOP_BREAKOUT']
    def observed(payload,inputs):
        out=evaluator(payload,inputs)
        h.flat_top_triggers.append((deepcopy(payload),deepcopy(inputs),deepcopy(out)))
        return out
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,'FLAT_TOP_BREAKOUT',observed)
    if market_fault.startswith('delayed_'):
        original=h.strategy._pattern_registry.run
        def delayed(source,**kwargs):
            h.life.clock.current+=timedelta(seconds=6)
            return original(source,**kwargs)
        monkeypatch.setattr(h.strategy._pattern_registry,'run',delayed)
    return h


@pytest.mark.parametrize('position_case',['complete_empty','complete_matched'])
def test_joined_flat_top_real_news_focus_artifact_and_risk(reassessment,monkeypatch,tmp_path,capsys,position_case):
    h=flat_top_joined(reassessment,monkeypatch,tmp_path,position_case=position_case)
    out=cycles(h,capsys)
    raw=[i for batch in h.batches for i in batch]
    assert len(raw)==len(h.artifacts)==len(h.evaluated)==1,out
    intent,received,decision=h.evaluated[0];artifact,built=h.artifacts[0]
    assert intent is raw[0] and artifact.intents==[intent]
    assert built==h.raw_snapshots and built[0]['decision_id'] is None
    assert received==dict(built[0],decision_id=artifact.decision_id)==vars(intent)
    assert intent.decision_id==artifact.decision_id==decision.decision_id and intent.decision_id
    assert intent.setup_family_id=='FLAT_TOP_BREAKOUT' and not intent.relationship_context,out
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(10.2,9.99,9.99)
    source,results=h.registry_batches[-1]
    index=intent.setup_metadata['canonical_result_index'];selected=results[index]
    from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
    assert [p.pattern_id for p in h.strategy._pattern_registry._patterns]==[
        p.pattern_id for p in RossPatternRegistry()._patterns]
    assert selected.setup_id=='P_FLAT_TOP_BREAKOUT' and selected.detected and index>0
    completed=[b for b in source.candles if b.timestamp+timedelta(minutes=1)<=source.observed_at_utc]
    pre=completed[-5:-1]
    assert len(completed)==50 and source.primary_timeframe=='1m' and len(pre)==4
    resistance=max(b.high for b in pre);tolerance=max(.02,resistance*.003)
    assert resistance==selected.trigger_level==10.2
    assert min(b.low for b in pre)==selected.stop_level==selected.invalidation_level==9.99
    assert sum(abs(b.high-resistance)<=tolerance for b in pre)>=3
    assert completed[-1].close>=resistance+tolerance*.25
    assert completed[-1].volume>sum(b.volume for b in pre)/4
    assert selected.trigger_level!=completed[-1].high
    assert intent.target_model==selected.target_suggestion=='Measured range expansion above flat-top resistance'
    assert intent.take_profit_price is None and intent.setup_metadata['source_metadata']==selected.setup_metadata
    for key in ('trigger_level','stop_level','invalidation_level'):
        assert intent.setup_metadata[key]==getattr(selected,key)
    canonical=[t for t in h.flat_top_triggers if t[0].get('source')=='canonical_pattern_result'
               and t[0].get('canonical_result_index')==index]
    assert len(canonical)==1
    payload,execution,trigger=canonical[0]
    assert (payload['trigger_level'],payload['stop_level'],payload['invalidation_level'])==(10.2,9.99,9.99)
    assert trigger['trigger_ready_now'] and trigger['trigger_reason']=='breakout_already_through_level'
    assert trigger['trigger_price_reference']==10.2 and trigger['invalidation_price_reference']==9.99
    assert received['setup_metadata']['execution_stream']==payload['execution_stream']
    assert source.observed_at_utc==h.life.clock.current
    assert payload['execution_stream']['observed_at_utc']==source.observed_at_utc.isoformat()
    assert payload['execution_stream']['execution_trigger_timeframe']=='10s'
    assert payload['execution_stream']['timeframe_substitution'] is False
    assert decision.reason_code=='LIVE_READ_ONLY_BLOCK' and not decision.allowed
    assert decision.execution_blocked and decision.max_position_size==0 and decision.run_mode=='READ_ONLY'
    assert all(v.healthy and not v.block_new_entries for _,v in h.truth)
    assert _cadence(h.core).focus.symbols==['JPM'] and h.focus_calls
    news=ross._ross_news_contexts_from_news_intelligence_result(h.reads[-1])
    assert news['JPM']['ross_catalyst_valid'] and news['JPM']['catalyst_type']=='EARNINGS'
    assert h.reads[-1].evidence_for_symbol('JPM')[0].evidence_id==h.article.evidence_id
    for name,method in h.real_core_methods.items():assert getattr(h.core,name).__func__ is method
    assert '[PIPELINE][RISK_OUTPUT] approved_count=0 blocked_count=1' in out and 'ORDER_SUBMITTED' not in out
    no_effects(h)
    retained=deepcopy(vars(intent))
    selected.setup_metadata.clear();source.timeframe_provenance.clear();source.candles.clear()
    payload['setup_metadata'].clear();payload['execution_stream'].clear()
    assert vars(intent)==received==retained


@pytest.mark.parametrize('market_fault',['missing_source','stale_source','short_source','future_source',
    'nan_source','infinite_source','malformed_source','unordered_source','forming_source','before_completion_source',
    'below_threshold_source','equal_volume_source','low_volume_source','nonflat_source',
    'missing_execution','stale_execution','future_execution','nan_execution','infinite_execution',
    'malformed_execution','unordered_execution','below_execution','invalidated_execution',
    'delayed_future_source','delayed_future_execution'])
def test_joined_flat_top_existing_authority_rejects(reassessment,monkeypatch,tmp_path,capsys,market_fault):
    h=flat_top_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    out=cycles(h,capsys)
    assert _cadence(h.core).focus.symbols==['JPM']
    assert not [i for batch in h.batches for i in batch if i.setup_family_id=='FLAT_TOP_BREAKOUT'],out
    assert all(i.setup_family_id!='FLAT_TOP_BREAKOUT' and d.reason_code=='LIVE_READ_ONLY_BLOCK' for i,_,d in h.evaluated)
    if market_fault.endswith('source'):
        own=[r for r in h.results if r.setup_id=='P_FLAT_TOP_BREAKOUT']
        if market_fault=='missing_source':assert own==[] and h.inputs==[] and h.artifacts==h.evaluated==[]
        else:assert own and all(not r.detected for r in own)
        expected={'short_source':'insufficient_candles','future_source':'FUTURE_CANDLE_DATA',
            'delayed_future_source':'FUTURE_CANDLE_DATA','nan_source':'INVALID_CANDLE_DATA',
            'infinite_source':'INVALID_CANDLE_DATA','malformed_source':'INVALID_CANDLE_DATA',
            'unordered_source':'INVALID_CANDLE_TIMESTAMPS','below_threshold_source':'breakout_not_confirmed',
            'equal_volume_source':'breakout_volume_below_average','low_volume_source':'breakout_volume_below_average',
            'nonflat_source':'resistance_not_flat'}
        if market_fault in expected:assert own[-1].rejection_reason==expected[market_fault]
        if market_fault in {'forming_source','before_completion_source'}:
            source=h.registry_batches[-1][0]
            assert source.candles[-1].timestamp+timedelta(minutes=1)>source.observed_at_utc
    else:
        own=next(t for t in h.strategy._failure_trace_collector._symbols[-1].input_summary['trigger_candidates']
                 if t.get('setup_family_id')=='FLAT_TOP_BREAKOUT')
        expected={'missing_execution':'execution_stream_missing','stale_execution':'execution_stream_stale',
            'future_execution':'flat_top_future_candle_data','delayed_future_execution':'flat_top_future_candle_data',
            'nan_execution':'flat_top_invalid_candle_data','infinite_execution':'flat_top_invalid_candle_data',
            'malformed_execution':'flat_top_invalid_candle_data','unordered_execution':'execution_stream_stale',
            'below_execution':'breakout_not_cleared','invalidated_execution':'at_or_below_invalidation'}
        assert not own['trigger_ready_now'] and own['trigger_reason']==expected[market_fault]
        if market_fault=='invalidated_execution':
            assert own['invalidation_price_reference']==9.99 and 'NEAR_INVALIDATION' in own['trigger_quality_flags']
    if market_fault.startswith('delayed_'):
        source=h.registry_batches[-1][0];tf='1m' if market_fault.endswith('source') else '10s'
        assert source.observed_at_utc<h.streams[tf][-1].timestamp<=h.life.clock.current
        if market_fault.endswith('execution'):
            assert h.flat_top_triggers[-1][0]['execution_stream']['observed_at_utc']==source.observed_at_utc.isoformat()
    no_effects(h)


@pytest.mark.parametrize('market_fault',['exact_completion_source','at_threshold_source','appended_forming_source',
                                       'forming_execution','touch_execution','zero_volume_execution'])
def test_joined_flat_top_preserves_own_completion_and_confirmation(reassessment,monkeypatch,tmp_path,capsys,market_fault):
    h=flat_top_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    out=cycles(h,capsys)
    assert len(h.evaluated)==1 and h.evaluated[0][0].setup_family_id=='FLAT_TOP_BREAKOUT',out
    intent,_,decision=h.evaluated[0]
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(10.2,9.99,9.99)
    assert decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    source=h.registry_batches[-1][0];_,execution,trigger=h.flat_top_triggers[-1]
    if market_fault=='exact_completion_source':assert source.candles[-1].timestamp+timedelta(minutes=1)==source.observed_at_utc
    if market_fault=='at_threshold_source':assert source.candles[-1].close==10.2+max(.02,10.2*.003)*.25
    if market_fault=='appended_forming_source':
        assert source.candles[-1].high==99. and source.candles[-1].timestamp+timedelta(minutes=1)>source.observed_at_utc
    if market_fault=='forming_execution':
        assert execution['candles'][-1].timestamp<=source.observed_at_utc<execution['candles'][-1].timestamp+timedelta(seconds=10)
    if market_fault=='touch_execution':assert execution['candles'][-1].close==10.2
    if market_fault=='zero_volume_execution':assert execution['candles'][-1].volume==0.
    assert trigger['trigger_ready_now'] and trigger['trigger_reason']=='breakout_already_through_level'
    no_effects(h)


def test_joined_flat_top_keeps_genuine_key_competition(reassessment,monkeypatch,tmp_path,capsys):
    h=flat_top_joined(reassessment,monkeypatch,tmp_path,market_fault='competing_key')
    out=cycles(h,capsys)
    source,results=h.registry_batches[-1]
    flat=next(r for r in results if r.setup_id=='P_FLAT_TOP_BREAKOUT')
    assert flat.detected and (flat.trigger_level,flat.stop_level,flat.invalidation_level)==(10.5,10.29,10.29)
    assert len(h.evaluated)==1,out
    intent,received,decision=h.evaluated[0]
    selected=results[intent.setup_metadata['canonical_result_index']]
    assert selected.setup_id=='P_KEY_LEVEL_BREAK' and intent.setup_family_id=='KEY_LEVEL_BREAK'
    assert selected.confidence>flat.confidence
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(10.5,10.44,10.5)
    assert intent.stop_loss_price!=flat.stop_level and intent.target_model!=flat.target_suggestion
    assert received==vars(intent) and decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    no_effects(h)


def orb_joined(reassessment,monkeypatch,tmp_path,*,position_case='complete_empty',news_fault='none',peer=False,market_fault='none',runtime_options=None):
    from test_orb_pattern import _base_inputs
    # Use the native fixed UTC opening window; external clock precedes news/cache
    # acquisition too. No prepared range, MACD, PatternResult or selected family.
    h=pmh_joined(reassessment,monkeypatch,tmp_path,position_case=position_case,
        news_fault=news_fault,peer=peer,clock_time=(14,36,30),runtime_options=runtime_options)
    h.orb_pre_history=True
    monkeypatch.setattr('src.strategies.common.patterns.pattern_orb._ORB_RANGE_LOCK',{})
    rows=[(10.,10.05,9.98,10.,900)]*44+[
        (b.open,b.high,b.low,b.close,b.volume) for b in _base_inputs().candles]
    end=h.life.clock.current.replace(second=0,microsecond=0)
    h.streams.clear()
    for tf,step in (('1m',60),('5m',300)):
        h.streams[tf]=_candles(rows,step_seconds=step,end=end-timedelta(seconds=step))
    from src.utils.time_utils import to_ny_time
    pre_peak=to_ny_time(h.life.clock.current).replace(hour=9,minute=29,second=0,microsecond=0).astimezone(timezone.utc)
    # The existing external PRE12 declaration now has a completed minute
    # witness; its overlapping context bar must describe the same tape.
    h.streams['5m']=[replace(b,high=max(b.high,12.),low=min(b.low,9.8))
        if b.timestamp<=pre_peak<b.timestamp+timedelta(minutes=5) else b for b in h.streams['5m']]
    h.streams['10s']=_candles([(10.23,10.29,10.22,10.26,100)]*29+
        [(10.26,10.45,10.22,10.42,200)],step_seconds=10,end=end-timedelta(seconds=10))
    if market_fault in {'missing_source','stale_source'}:
        for tf in ('1m','5m'):
            h.streams[tf]=[] if market_fault=='missing_source' else [
                replace(b,timestamp=b.timestamp-timedelta(hours=1)) for b in h.streams[tf]]
    elif market_fault in {'touch_source','equal_volume_source'}:
        bar=h.streams['1m'][-1]
        h.streams['1m'][-1]=replace(bar,**({'close':10.3} if market_fault=='touch_source' else {'volume':900}))
    elif market_fault in {'missing_execution','stale_execution'}:
        h.streams['10s']=[] if market_fault=='missing_execution' else [
            replace(b,timestamp=b.timestamp-timedelta(hours=1)) for b in h.streams['10s']]
    elif market_fault in {'touch_execution','invalidated_execution'}:
        close=10.3 if market_fault=='touch_execution' else 9.95
        h.streams['10s'][-1]=replace(h.streams['10s'][-1],close=close,low=min(10.22,close))
    elif market_fault=='forming_execution':
        h.streams['10s'][-1]=replace(h.streams['10s'][-1],timestamp=end+timedelta(seconds=40))
    elif market_fault=='zero_volume_execution':
        h.streams['10s'][-1]=replace(h.streams['10s'][-1],volume=0.)
    for row in h.rows.values():
        row.update(premarket_high=12.,premarket_low=9.8,last_price=10.42,bid=10.4175,ask=10.4225,
            prev_close=9.3,ref_close_rth=9.3,reference_price=9.3,
            gap_pct=(10.42/9.3-1)*100,pct_change=(10.42/9.3-1)*100,
            spread_pct=100*.005/10.42,dollar_volume=10.42*1_800_000)
    snapshot=replace(_snapshot(symbol='JPM'),last=10.42,bid=10.4175,ask=10.4225)
    h.core.market_data_snapshot_manager=NS(batch_snapshots=lambda symbols:fixture_quote_batch(h,snapshot,symbols))
    h.orb_triggers=[];evaluator=TRIGGER_EVALUATOR_REGISTRY['OPENING_RANGE_BREAKOUT']
    def observed(payload,inputs):
        out=evaluator(payload,inputs)
        h.orb_triggers.append((deepcopy(payload),deepcopy(inputs),deepcopy(out)))
        return out
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,'OPENING_RANGE_BREAKOUT',observed)
    from src.core.engines.trigger_engine import TriggerEngine
    h.orb_engine_outputs=[];evaluate=TriggerEngine.evaluate_triggers
    def observed_engine(self,**kwargs):
        out=evaluate(self,**kwargs)
        h.orb_engine_outputs.extend(deepcopy(t) for t in out if t.get('setup_family_id')=='OPENING_RANGE_BREAKOUT')
        return out
    monkeypatch.setattr(TriggerEngine,'evaluate_triggers',observed_engine)
    return h


@pytest.mark.parametrize('position_case',['complete_empty','complete_matched'])
@pytest.mark.parametrize('market_fault',['none','forming_execution','zero_volume_execution'])
def test_joined_orb_native_selected_handoff(reassessment,monkeypatch,tmp_path,capsys,position_case,market_fault):
    h=orb_joined(reassessment,monkeypatch,tmp_path,position_case=position_case,market_fault=market_fault)
    out=cycles(h,capsys)
    source,results=h.registry_batches[-1]
    orb=next(r for r in results if r.setup_id=='P_ORB')
    assert orb.detected, (orb.rejection_reason,source.indicators.macd_line,source.news_context)
    assert len(h.evaluated)==1,out
    intent,received,decision=h.evaluated[0]
    assert intent.setup_family_id=='OPENING_RANGE_BREAKOUT', (intent,out)
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(10.3,9.95,9.95)
    assert intent.target_model=='Continuation above the completed opening-range high.'
    assert intent.take_profit_price is None and decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    no_effects(h)
    raw=[i for batch in h.batches for i in batch]
    assert len(raw)==len(h.artifacts)==len(h.evaluated)==1,out
    artifact,built=h.artifacts[0]
    assert intent is raw[0] and artifact.intents==[intent]
    assert built==h.raw_snapshots and built[0]['decision_id'] is None
    assert received==dict(built[0],decision_id=artifact.decision_id)==vars(intent)
    assert intent.decision_id==artifact.decision_id==decision.decision_id and intent.decision_id
    index=intent.setup_metadata['canonical_result_index']
    assert results[index] is orb and index>0
    from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
    assert len(h.strategy._pattern_registry.patterns)==33
    assert [p.pattern_id for p in h.strategy._pattern_registry.patterns]==[
        p.pattern_id for p in RossPatternRegistry().patterns]
    opening=[b for b in source.candles if b.timestamp.hour==14 and 30<=b.timestamp.minute<=34]
    assert len(opening)==5 and all(b.timestamp+timedelta(minutes=1)<=source.observed_at_utc for b in opening)
    assert (max(b.high for b in opening),min(b.low for b in opening))==(10.3,9.95)
    assert source.candles[-1].close>orb.trigger_level and source.candles[-1].volume>sum(b.volume for b in source.candles[:5])/5
    assert source.indicators.macd_line>0 and 'macd' not in source.news_context and 'macd_hist' not in source.news_context
    assert orb.target_suggestion==intent.target_model
    assert not intent.relationship_context
    assert intent.setup_metadata['source_metadata']==orb.setup_metadata
    for name in ('trigger_level','stop_level','invalidation_level'):
        assert intent.setup_metadata[name]==getattr(orb,name)
    canonical=[t for t in h.orb_triggers if t[0].get('source')=='canonical_pattern_result'
        and t[0].get('canonical_result_index')==index]
    assert len(canonical)==1
    payload,execution,trigger=canonical[0]
    assert (payload['trigger_level'],payload['stop_level'],payload['invalidation_level'])==(10.3,9.95,9.95)
    assert trigger['trigger_ready_now'] and trigger['trigger_reason']=='break_and_hold_above_orh'
    confirmed=[t for t in h.orb_engine_outputs if t.get('canonical_result_index')==index]
    assert len(confirmed)==1 and confirmed[0]['trigger_ready_now']
    assert (confirmed[0]['trigger_price_reference'],confirmed[0]['stop_price_reference'],
        confirmed[0]['invalidation_price_reference'])==(10.3,9.95,9.95)
    assert received['setup_metadata']['execution_stream']==payload['execution_stream']
    assert payload['execution_stream']['observed_at_utc']==source.observed_at_utc.isoformat()
    assert payload['execution_stream']['execution_trigger_timeframe']=='10s'
    assert payload['execution_stream']['timeframe_substitution'] is False
    assert not decision.allowed and decision.execution_blocked and decision.max_position_size==0
    assert decision.run_mode=='READ_ONLY' and all(v.healthy and not v.block_new_entries for _,v in h.truth)
    assert _cadence(h.core).focus.symbols==['JPM'] and h.focus_calls
    news=ross._ross_news_contexts_from_news_intelligence_result(h.reads[-1])
    assert news['JPM']['ross_catalyst_valid'] and news['JPM']['catalyst_type']=='EARNINGS'
    assert h.reads[-1].evidence_for_symbol('JPM')[0].evidence_id==h.article.evidence_id
    for name,method in h.real_core_methods.items():assert getattr(h.core,name).__func__ is method
    assert '[PIPELINE][RISK_OUTPUT] approved_count=0 blocked_count=1' in out and 'ORDER_SUBMITTED' not in out
    retained=deepcopy(vars(intent))
    orb.setup_metadata.clear();source.timeframe_provenance.clear();source.candles.clear()
    payload['setup_metadata'].clear();payload['execution_stream'].clear()
    assert vars(intent)==received==retained


@pytest.mark.parametrize('market_fault',['missing_source','stale_source','touch_source','equal_volume_source',
    'missing_execution','stale_execution','touch_execution','invalidated_execution'])
def test_joined_orb_existing_gates_still_block(reassessment,monkeypatch,tmp_path,capsys,market_fault):
    h=orb_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    out=cycles(h,capsys)
    assert not [i for batch in h.batches for i in batch if i.setup_family_id=='OPENING_RANGE_BREAKOUT'],out
    assert not [i for i,_,_ in h.evaluated if i.setup_family_id=='OPENING_RANGE_BREAKOUT'],out
    if market_fault in {'touch_source','equal_volume_source'}:
        orb=next(r for r in h.registry_batches[-1][1] if r.setup_id=='P_ORB')
        assert not orb.detected and orb.target_suggestion is None
        assert orb.rejection_reason==('no_hold_above_orh' if market_fault=='touch_source' else 'breakout_volume_below_opening_average')
    elif market_fault.endswith('execution'):
        orb=next(r for r in h.registry_batches[-1][1] if r.setup_id=='P_ORB')
        assert orb.detected and h.orb_engine_outputs
        blocked=h.orb_engine_outputs[-1]
        assert not blocked['trigger_ready_now']
        expected={'missing_execution':'execution_stream_missing','stale_execution':'execution_stream_stale',
            'touch_execution':'orb_trigger_armed','invalidated_execution':'at_or_below_invalidation'}
        assert blocked['trigger_reason']==expected[market_fault]
        if market_fault in {'missing_execution','stale_execution'}:
            assert h.orb_triggers==[]
    no_effects(h)


def hod_joined(reassessment,monkeypatch,tmp_path,*,news_fault='none',peer=False,
               market_fault='none',position_case='complete_empty',runtime_options=None):
    h=pmh_joined(reassessment,monkeypatch,tmp_path,news_fault=news_fault,peer=peer,
        position_case=position_case,clock_time=(14,10,30),runtime_options=runtime_options)
    rows=[(10.2,10.25,10.18,10.22,900)]*44+[
        (10.23,10.29,10.21,10.27,900),(10.27,10.30,10.20,10.28,900),
        (10.28,10.30,10.22,10.29,900),(10.29,10.30,10.23,10.28,900),
        (10.28,10.30,10.24,10.29,900),(10.26,10.30,10.25,10.29,900)]
    rows[5]=(10.2,12.,10.18,10.22,900)  # Retained PRE high, outside RTH; survives an appended tail.
    rows[40]=(10.22,10.3,10.2,10.27,900)
    end=h.life.clock.current.replace(second=0,microsecond=0)
    h.streams.clear()
    for tf,step in (('1m',60),('5m',300)):
        h.streams[tf]=_candles(rows,step_seconds=step,end=end-timedelta(seconds=step))
    def execution_bars(source,current):
        return _closed_minutes_and_execution(source,current,end=end)
    h.streams['10s']=execution_bars(h.streams['1m'],[
        (10.31,10.31,10.25,10.29,100),(10.29,10.30,10.27,10.29,100),
        (10.29,10.30,10.27,10.29,100),(10.29,10.36,10.27,10.34,200)])
    fault=market_fault.removeprefix('delayed_')
    stream='1m' if fault.endswith('source') else '10s'
    if fault in {'missing_source','stale_source'}:
        for tf in ('1m','5m'):
            h.streams[tf]=[] if fault=='missing_source' else [replace(c,timestamp=c.timestamp-timedelta(hours=1)) for c in h.streams[tf]]
    elif fault in {'missing_execution','stale_execution'}:
        h.streams['10s']=[] if fault=='missing_execution' else [replace(c,timestamp=c.timestamp-timedelta(hours=1)) for c in h.streams['10s']]
    elif fault in {'late_window_source','opening_gap_source'}:
        if fault=='late_window_source':h.streams['1m']=h.streams['1m'][-30:]
        else:del h.streams['1m'][25]
    elif fault=='previous_day_source':
        h.streams['1m']=[replace(c,timestamp=c.timestamp-timedelta(days=1)) for c in h.streams['1m']]
    elif fault in {'forming_source','future_source'}:
        stamp=end if fault=='forming_source' else h.life.clock.current+timedelta(seconds=12)
        h.streams['1m'].append(replace(h.streams['1m'][-1],timestamp=stamp,open=10.31,high=10.36,low=10.25,close=10.34,volume=500))
    elif fault=='future_execution':
        h.streams['10s'][-1]=replace(h.streams['10s'][-1],timestamp=h.life.clock.current+timedelta(seconds=12))
    elif fault in {'nan_source','nan_execution','malformed_source','malformed_execution'}:
        h.streams[stream][-2]=replace(h.streams[stream][-2],low=float('nan') if fault.startswith('nan_') else 99.)
    elif fault in {'at_threshold_execution','above_threshold_execution'}:
        close=10.3*1.001+(1e-9 if fault.startswith('above_') else 0.)
        h.streams['10s'][-1]=replace(h.streams['10s'][-1],close=close,high=close+.001)
    elif fault in {'previous_at_level_execution','previous_above_execution'}:
        close=10.3+(0.01 if fault=='previous_above_execution' else 0.)
        h.streams['10s'][-2]=replace(h.streams['10s'][-2],close=close,high=max(close,10.3))
    elif fault=='invalidated_execution':
        h.streams['10s'][-1]=replace(h.streams['10s'][-1],close=10.2,low=10.19)
    elif fault=='forming_execution':
        h.streams['10s'][-1]=replace(h.streams['10s'][-1],timestamp=end+timedelta(seconds=40))
    elif fault=='zero_volume_execution':
        h.streams['10s'][-1]=replace(h.streams['10s'][-1],volume=0.)
    last,previous,premarket=10.34,9.2,12.
    if fault=='competing_key':
        h.streams.update({tf:[replace(c,**{key:round(getattr(c,key)+.2,2) for key in ('open','high','low','close')}) for c in bars] for tf,bars in h.streams.items()})
        h.streams['1m'][40]=replace(h.streams['1m'][40],high=10.55)
        h.streams['1m'][-1]=replace(h.streams['1m'][-1],open=10.49,high=10.55,low=10.45,close=10.54,volume=1800)
        h.streams['10s']=execution_bars(h.streams['1m'],[
            (10.51,10.55,10.45,10.49,100),(10.49,10.50,10.47,10.49,100),
            (10.49,10.50,10.47,10.49,100),(10.49,10.59,10.47,10.57,200)])
        last,previous,premarket=10.57,9.4,12.2
    for row in h.rows.values():
        row.update(premarket_high=premarket,premarket_low=9.8,last_price=last,bid=round(last-.01,2),ask=round(last+.01,2),
            prev_close=previous,ref_close_rth=previous,reference_price=previous,
            gap_pct=(last/previous-1)*100,pct_change=(last/previous-1)*100,
            spread_pct=100*.02/last,dollar_volume=last*1_800_000)
    snapshot=replace(_snapshot(symbol='JPM'),last=last,bid=round(last-.01,2),ask=round(last+.01,2))
    h.core.market_data_snapshot_manager=NS(batch_snapshots=lambda symbols:fixture_quote_batch(h,snapshot,symbols))
    h.hod_triggers=[];evaluator=TRIGGER_EVALUATOR_REGISTRY['HOD_BREAK']
    def observed(payload,inputs):
        out=evaluator(payload,inputs)
        h.hod_triggers.append((deepcopy(payload),deepcopy(inputs),deepcopy(out)))
        return out
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,'HOD_BREAK',observed)
    if market_fault.startswith('delayed_'):
        original=h.strategy._pattern_registry.run
        def delayed(source,**kwargs):
            h.life.clock.current+=timedelta(seconds=6)
            return original(source,**kwargs)
        monkeypatch.setattr(h.strategy._pattern_registry,'run',delayed)
    from src.core.engines.trigger_engine import TriggerEngine
    evaluate=TriggerEngine.evaluate_triggers;h.hod_engine_outputs=[]
    def observed_engine(self,**kwargs):
        out=evaluate(self,**kwargs)
        h.hod_engine_outputs.extend(deepcopy(t) for t in out if t.get('setup_family_id')=='HOD_BREAK')
        return out
    monkeypatch.setattr(TriggerEngine,'evaluate_triggers',observed_engine)
    compute=h.strategy._decision_engine.compute_decision;h.hod_decisions=[]
    def observed_decision(**kwargs):
        out=compute(**kwargs)
        h.hod_decisions.append(deepcopy(out))
        return out
    monkeypatch.setattr(h.strategy._decision_engine,'compute_decision',observed_decision)
    return h


@pytest.mark.parametrize('position_case',['complete_empty','complete_matched'])
@pytest.mark.parametrize('market_fault',['none','forming_execution','zero_volume_execution',
    'above_threshold_execution','previous_at_level_execution'])
def test_joined_hod_native_selected_handoff(reassessment,monkeypatch,tmp_path,capsys,position_case,market_fault):
    h=hod_joined(reassessment,monkeypatch,tmp_path,position_case=position_case,market_fault=market_fault)
    out=cycles(h,capsys)
    source,results=h.registry_batches[-1]
    hod=next(r for r in results if r.setup_id=='P_HOD_BREAK')
    assert hod.detected,(hod.rejection_reason,source.levels)
    assert len(h.evaluated)==1,out
    intent,received,decision=h.evaluated[0]
    assert intent.setup_family_id=='HOD_BREAK',(intent,out)
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(10.3,10.2,10.2)
    assert intent.target_model=='Continuation above the established regular-session high of day.'
    assert intent.take_profit_price is None and decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    no_effects(h)
    raw=[i for batch in h.batches for i in batch]
    artifact,built=h.artifacts[0]
    assert len(raw)==len(h.artifacts)==len(h.evaluated)==1 and intent is raw[0]
    assert artifact.intents==[intent] and built==h.raw_snapshots and built[0]['decision_id'] is None
    assert received==dict(built[0],decision_id=artifact.decision_id)==vars(intent)
    assert intent.decision_id==artifact.decision_id==decision.decision_id and intent.decision_id
    from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
    assert len(h.strategy._pattern_registry.patterns)==33
    assert [p.pattern_id for p in h.strategy._pattern_registry.patterns]==[p.pattern_id for p in RossPatternRegistry().patterns]
    index=intent.setup_metadata['canonical_result_index']
    assert results[index] is hod and index>0
    assert h.hod_decisions[-1]['selected_pattern_id']=='P_HOD_BREAK'
    assert h.hod_decisions[-1]['selected_candidate_index']==index
    assert source.levels.established_rth_hod==hod.trigger_level==10.3
    assert hod.setup_metadata['level_source']=='RTH'
    assert max(b.high for b in source.candles)==12. and source.levels.premarket_high==12.
    assert source.levels.hod==12. and source.levels.key_levels['HOD']==12.
    assert intent.target_model==hod.target_suggestion and not intent.relationship_context
    assert intent.setup_metadata['source_metadata']==hod.setup_metadata
    canonical=[t for t in h.hod_triggers if t[0].get('source')=='canonical_pattern_result' and t[0].get('canonical_result_index')==index]
    assert len(canonical)==1
    payload,execution,trigger=canonical[0]
    for key in ('trigger_level','stop_level','invalidation_level'):
        assert intent.setup_metadata[key]==received['setup_metadata'][key]==payload[key]==getattr(hod,key)
    assert trigger['trigger_ready_now'] and trigger['trigger_reason']=='hod_break_confirmed'
    assert trigger['trigger_price_reference']==10.3 and trigger['invalidation_price_reference']==hod.invalidation_level
    assert execution['candles'][-2].close<=10.3 and execution['candles'][-1].close>10.3*1.001
    assert execution['candles'][-1].high!=hod.trigger_level
    assert execution['candles'][-1].timestamp>=source.candles[-1].timestamp+timedelta(minutes=1)
    # Closed ten-second intervals aggregate exactly to the source minutes.
    for bar in source.candles[-5:]:
        parts=[c for c in execution['candles'] if bar.timestamp<=c.timestamp<bar.timestamp+timedelta(minutes=1)]
        assert len(parts)==6
        assert (parts[0].open,max(c.high for c in parts),min(c.low for c in parts),parts[-1].close,sum(c.volume for c in parts))==(bar.open,bar.high,bar.low,bar.close,bar.volume)
    assert received['setup_metadata']['execution_stream']==payload['execution_stream']
    assert payload['execution_stream']['observed_at_utc']==source.observed_at_utc.isoformat()
    assert payload['execution_stream']['execution_trigger_timeframe']=='10s'
    assert payload['execution_stream']['timeframe_substitution'] is False
    assert source.observed_at_utc==h.life.clock.current
    assert not decision.allowed and decision.execution_blocked and decision.max_position_size==0 and decision.run_mode=='READ_ONLY'
    assert all(v.healthy and not v.block_new_entries for _,v in h.truth)
    assert _cadence(h.core).focus.symbols==['JPM'] and h.focus_calls
    news=ross._ross_news_contexts_from_news_intelligence_result(h.reads[-1])
    assert news['JPM']['ross_catalyst_valid'] and news['JPM']['catalyst_type']=='EARNINGS'
    assert h.reads[-1].evidence_for_symbol('JPM')[0].evidence_id==h.article.evidence_id
    for name,method in h.real_core_methods.items():assert getattr(h.core,name).__func__ is method
    if market_fault=='forming_execution':
        assert execution['candles'][-1].timestamp<=source.observed_at_utc<execution['candles'][-1].timestamp+timedelta(seconds=10)
    if market_fault=='zero_volume_execution':assert execution['candles'][-1].volume==0 and execution['rvol']>=1.2
    assert '[PIPELINE][RISK_OUTPUT] approved_count=0 blocked_count=1' in out and 'ORDER_SUBMITTED' not in out
    retained=deepcopy(vars(intent))
    hod.setup_metadata.clear();source.timeframe_provenance.clear();source.candles.clear()
    payload['setup_metadata'].clear();payload['execution_stream'].clear()
    assert vars(intent)==received==retained


@pytest.mark.parametrize('market_fault',['missing_source','stale_source','late_window_source','opening_gap_source',
    'previous_day_source','future_source','nan_source','malformed_source','missing_execution','stale_execution',
    'future_execution','nan_execution','malformed_execution','at_threshold_execution','previous_above_execution',
    'invalidated_execution','delayed_future_source','delayed_future_execution'])
def test_joined_hod_existing_guards_and_reference_limits(reassessment,monkeypatch,tmp_path,capsys,market_fault):
    h=hod_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    out=cycles(h,capsys)
    assert not [i for batch in h.batches for i in batch if i.setup_family_id=='HOD_BREAK'],out
    assert not [i for i,_,_ in h.evaluated if i.setup_family_id=='HOD_BREAK'],out
    fault=market_fault.removeprefix('delayed_')
    if fault in {'late_window_source','opening_gap_source','previous_day_source'}:
        source,results=h.registry_batches[-1]
        hod=next(r for r in results if r.setup_id=='P_HOD_BREAK')
        assert not hod.detected and source.levels.established_rth_hod is None
        assert hod.rejection_reason==('pr4_input_block:HOD_BREAK:timeframe:1m=STALE' if fault=='previous_day_source' else 'invalid_hod_source')
    elif fault=='future_source':
        hod=next(r for r in h.registry_batches[-1][1] if r.setup_id=='P_HOD_BREAK')
        assert not hod.detected and hod.rejection_reason=='FUTURE_CANDLE_DATA'
    elif fault in {'nan_source','malformed_source'}:
        from src.strategies.common.triggers.trigger_abcd_continuation import abcd_candle_rejection
        source,results=h.registry_batches[-1]
        hod=next(r for r in results if r.setup_id=='P_HOD_BREAK')
        assert not hod.detected and hod.rejection_reason=='invalid_hod_source'
        assert source.levels.established_rth_hod is None
        assert abcd_candle_rejection(source.candles,observed_at_utc=source.observed_at_utc,
            require_clock=True)=='INVALID_CANDLE_DATA'
    elif fault.endswith('execution'):
        index=next(i for i,r in enumerate(h.registry_batches[-1][1]) if r.setup_id=='P_HOD_BREAK')
        outputs=[t for t in h.hod_engine_outputs if t.get('canonical_result_index')==index]
        assert len(outputs)==1 and not outputs[0]['trigger_ready_now']
        reason={'missing_execution':'execution_stream_missing','stale_execution':'execution_stream_stale',
            'future_execution':'hod_future_candle_data','nan_execution':'hod_invalid_candle_data',
            'malformed_execution':'hod_invalid_candle_data','at_threshold_execution':'breakout_shape_invalid',
            'previous_above_execution':'awaiting_hod_break','invalidated_execution':'at_or_below_invalidation'}[fault]
        assert outputs[0]['trigger_reason']==reason
    if market_fault.startswith('delayed_'):
        source=h.registry_batches[-1][0]
        bad=(source.candles if fault.endswith('source') else h.streams['10s'])[-1]
        assert source.observed_at_utc<bad.timestamp<=h.life.clock.current
    no_effects(h)


def test_joined_hod_preserves_genuine_key_winner(reassessment,monkeypatch,tmp_path,capsys):
    h=hod_joined(reassessment,monkeypatch,tmp_path,market_fault='competing_key')
    out=cycles(h,capsys)
    source,results=h.registry_batches[-1]
    hod=next(r for r in results if r.setup_id=='P_HOD_BREAK')
    assert hod.detected and (hod.trigger_level,hod.stop_level,hod.invalidation_level)==(10.55,10.4,10.4)
    assert len(h.evaluated)==1,out
    intent,received,decision=h.evaluated[0]
    selected=results[intent.setup_metadata['canonical_result_index']]
    assert selected.setup_id=='P_KEY_LEVEL_BREAK' and selected.confidence>hod.confidence
    assert intent.setup_family_id=='KEY_LEVEL_BREAK' and (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(10.5,10.45,10.5)
    assert intent.target_model!=hod.target_suggestion and received==vars(intent)
    assert decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    canonical=[t for t in h.hod_triggers if t[0].get('source')=='canonical_pattern_result']
    assert len(canonical)==1 and canonical[0][2]['trigger_ready_now']
    no_effects(h)


def test_joined_hod_forming_source_ready_hod_not_starved_by_unready_momentum(reassessment,monkeypatch,tmp_path,capsys):
    h=hod_joined(reassessment,monkeypatch,tmp_path,market_fault='forming_source')
    out=cycles(h,capsys)
    source,results=h.registry_batches[-1]
    hod=next(r for r in results if r.setup_id=='P_HOD_BREAK')
    assert hod.detected and (hod.trigger_level,hod.stop_level,hod.invalidation_level)==(10.3,10.22,10.22)
    assert source.levels.established_rth_hod==10.3
    forming=source.candles[-1]
    assert forming.timestamp<=source.observed_at_utc<forming.timestamp+timedelta(minutes=1)
    assert forming.high==10.36 and hod.trigger_level!=forming.high
    selected=h.hod_decisions[-1]
    momentum=next(r for r in results if r.setup_id=='P_MOMENTUM_RECLAIM')
    assert momentum.detected and momentum.stop_level==momentum.invalidation_level==10.23
    assert momentum.trigger_level!=hod.trigger_level
    assert selected['selected_pattern_id']=='P_HOD_BREAK'
    assert results[selected['selected_candidate_index']] is hod
    assert any(r['pattern_id']=='P_MOMENTUM_RECLAIM' and r['reason']=='awaiting_reclaim_confirmation'
        for r in selected['rejected_candidates'])
    assert len(h.artifacts)==len(h.evaluated)==1
    assert h.evaluated[0][2].reason_code=='LIVE_READ_ONLY_BLOCK'
    canonical=[t for t in h.hod_triggers if t[0].get('source')=='canonical_pattern_result']
    assert len(canonical)==1 and canonical[0][2]['trigger_ready_now']
    assert 'selected_pattern=P_HOD_BREAK' in out
    no_effects(h)


def momentum_joined(reassessment,monkeypatch,tmp_path,*,position_case='complete_empty',runtime_options=None,
                    news_fault='none',peer=False):
    """Native shakeout/reclaim, coherent forming source and fresh execution cross."""
    h=hod_joined(reassessment,monkeypatch,tmp_path,market_fault='forming_source',
        position_case=position_case,runtime_options=runtime_options,news_fault=news_fault,peer=peer)
    for i in range(-4,-1):
        bar=h.streams['10s'][i]
        h.streams['10s'][i]=replace(bar,high=max(bar.open,10.25),low=10.24,close=10.25)
    h.streams['10s'][-1]=replace(h.streams['10s'][-1],open=10.25,low=10.24)
    h.streams['1m'][-1]=replace(h.streams['1m'][-1],low=10.24)
    from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY
    evaluator=TRIGGER_EVALUATOR_REGISTRY['MOMENTUM_RECLAIM'];h.momentum_triggers=[]
    def observed(payload,inputs):
        out=evaluator(payload,inputs)
        h.momentum_triggers.append((deepcopy(payload),deepcopy(inputs),deepcopy(out)))
        return out
    for family in ('MOMENTUM_RECLAIM','VWAP_RECLAIM_CONTINUATION'):
        monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,family,observed)
    return h


def test_joined_momentum_native_selected_handoff(reassessment,monkeypatch,tmp_path,capsys):
    h=momentum_joined(reassessment,monkeypatch,tmp_path)
    out=cycles(h,capsys)
    source,results=h.registry_batches[-1]
    momentum=next(r for r in results if r.setup_id=='P_MOMENTUM_RECLAIM')
    assert momentum.detected
    assert len(h.evaluated)==1,out
    intent,received,decision=h.evaluated[0]
    assert intent.setup_family_id=='VWAP_RECLAIM_CONTINUATION',(intent,out)
    assert intent.entry_price==momentum.trigger_level==max(source.indicators.ema9,source.indicators.vwap)
    assert intent.stop_loss_price==intent.invalidation_level==momentum.stop_level==10.23
    assert intent.target_model==momentum.target_suggestion=='Prior swing high'
    assert intent.take_profit_price is None and decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    index=intent.setup_metadata['canonical_result_index']
    assert results[index] is momentum
    assert h.hod_decisions[-1]['selected_candidate_index']==index
    assert len(h.strategy._pattern_registry.patterns)==len(results)==33
    artifact,built=h.artifacts[0]
    assert artifact.intents==[intent] and received==dict(built[0],decision_id=artifact.decision_id)==vars(intent)
    assert intent.setup_metadata['source_metadata']==momentum.setup_metadata
    assert source.levels.established_rth_hod==10.3 and source.levels.hod==12.
    no_effects(h)



def _closed_minutes_and_execution(source,current,*,end,source_minutes=5):
    """Existing HOD external aggregation fixture, shared with Micro."""
    bars=[]
    for bar in source[-source_minutes:]:
        for part in range(6):
            bars.append(replace(bar,timestamp=bar.timestamp+timedelta(seconds=part*10),
                open=bar.open if part==0 else bar.close,high=bar.high if part==0 else bar.close,
                low=bar.low if part==0 else bar.close,volume=bar.volume/6))
    return bars+_candles(current,step_seconds=10,end=end+timedelta(seconds=30))


def micro_joined(reassessment,monkeypatch,tmp_path,*,news_fault='none',peer=False,
                 position_case='complete_empty',runtime_options=None,market_fault='none',clock_time=(14,35,30),real_session=False):
    from src.market_data.session_pct_change import resolve_market_session_label
    moment=reassessment.life.clock.current.replace(hour=clock_time[0],minute=clock_time[1],second=clock_time[2],microsecond=0)
    session=resolve_market_session_label(moment)
    h=pmh_joined(reassessment,monkeypatch,tmp_path,news_fault=news_fault,peer=peer,
        position_case=position_case,runtime_options=runtime_options,clock_time=clock_time,context_session=session if real_session else None)
    rows=[(10.,10.02,9.98,10.,900)]*45+[
        (10.,10.2,9.99,10.18,1300),(10.18,10.45,10.16,10.42,1600),
        (10.42,10.8,10.4,10.76,2000),(10.73,10.78,10.6,10.76,850),
        (10.76,10.9,10.75,10.88,2100)]
    variations={'red_pause':(10.76,10.78,10.6,10.73,850),
        'ordinary_green_pause':(10.68,10.78,10.66,10.76,850),
        'upper_wick_pause':(10.70,10.78,10.69,10.72,850),
        'above_impulse_pause':(10.77,10.82,10.60,10.80,850),
        'lost_ema_pause':(10.73,10.78,10.1,10.76,850)}
    if market_fault in variations:rows[-2]=variations[market_fault]
    shift=.2 if market_fault=='competing_key' else 0.
    if shift:rows=[tuple(round(v+shift,2) for v in bar[:4])+(bar[4],) for bar in rows]
    end=h.life.clock.current.replace(second=0,microsecond=0)
    h.streams.clear();h.streams['1m']=_candles(rows,step_seconds=60,end=end-timedelta(minutes=1))
    # Completed five-minute bars agree exactly with the fifty one-minute bars;
    # earlier context supplies the independent, already-known PRE high12.
    grouped=[]
    for start in range(0,len(rows),5):
        chunk=rows[start:start+5]
        grouped.append((chunk[0][0],max(b[1] for b in chunk),min(b[2] for b in chunk),
            chunk[-1][3],sum(b[4] for b in chunk)))
    context=[(10.+shift,10.02+shift,9.98+shift,10.+shift,4500)]*40+grouped
    context[34]=(10.+shift,12.,9.98+shift,10.+shift,4500)
    h.streams['5m']=_candles(context,step_seconds=300,end=end-timedelta(minutes=5))
    current=[(10.76,10.77,10.74,10.75,100),(10.75,10.77,10.74,10.75,100),
        (10.75,10.77,10.74,10.75,100),(10.75,10.9,10.74,10.88,400)]
    if shift:current=[tuple(round(v+shift,2) for v in bar[:4])+(bar[4],) for bar in current]
    h.streams['10s']=_closed_minutes_and_execution(h.streams['1m'],current,end=end)
    if market_fault=='waiting_execution':h.streams['10s'][-1]=replace(h.streams['10s'][-1],high=10.77,close=10.76)
    if market_fault=='touch_execution':h.streams['10s'][-1]=replace(h.streams['10s'][-1],high=10.78,close=10.76)
    if market_fault=='future_execution':h.streams['10s'][-1]=replace(h.streams['10s'][-1],timestamp=h.life.clock.current+timedelta(seconds=12))
    if market_fault=='incomplete_pause':
        h.streams['1m'][-2]=replace(h.streams['1m'][-2],timestamp=h.life.clock.current-timedelta(seconds=45))
        h.streams['1m'][-1]=replace(h.streams['1m'][-1],timestamp=h.life.clock.current-timedelta(seconds=10))
    last=round(10.88+shift,2);previous=9.8
    for row in h.rows.values():row.update(premarket_high=12.,premarket_low=9.8,
        last_price=last,bid=round(last-.01,2),ask=round(last+.01,2),
        prev_close=previous,ref_close_rth=previous,reference_price=previous,
        gap_pct=(last/previous-1)*100,pct_change=(last/previous-1)*100,
        spread_pct=100*.02/last,dollar_volume=last*1_800_000)
    snapshot=replace(_snapshot(symbol='JPM'),last=last,bid=round(last-.01,2),ask=round(last+.01,2))
    h.core.market_data_snapshot_manager=NS(batch_snapshots=lambda symbols:fixture_quote_batch(h,snapshot,symbols))
    evaluator=TRIGGER_EVALUATOR_REGISTRY['MICRO_PULLBACK'];h.micro_triggers=[]
    def observed(payload,inputs):
        out=evaluator(payload,inputs)
        h.micro_triggers.append((deepcopy(payload),deepcopy(inputs),deepcopy(out)))
        return out
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,'MICRO_PULLBACK',observed)
    return h


@pytest.mark.parametrize('clock_time',[pytest.param(None,id='accepted_10s'),pytest.param((16,35,30),id='RTH_MID_1m')])
@pytest.mark.parametrize('market_fault',['none','red_pause','touch_execution'])
def test_joined_micro_own_pause_selected_serialized_readonly(reassessment,monkeypatch,tmp_path,capsys,market_fault,clock_time):
    h=micro_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault,clock_time=clock_time or (14,35,30),real_session=clock_time is not None)
    out=cycles(h,capsys)
    assert h.registry_batches,(h.focus_rejections,[(x[0],x[2]) for x in h.focus_calls])
    source,results=h.registry_batches[-1]
    own=next(r for r in results if r.setup_id=='P_MICRO_PULLBACK')
    assert own.detected and (own.trigger_level,own.stop_level,own.invalidation_level)==(10.78,10.6,10.6)
    assert len(h.evaluated)==1,out
    intent,received,decision=h.evaluated[0]
    assert intent.setup_family_id=='MICRO_PULLBACK'
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(10.78,10.6,10.6)
    assert intent.target_model=='Prior high / HOD' and intent.take_profit_price is None
    assert decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    index=intent.setup_metadata['canonical_result_index'];assert results[index] is own
    assert len(results)==len(h.strategy._pattern_registry.patterns)==33
    assert intent.setup_metadata['source_metadata']==own.setup_metadata
    if market_fault!='red_pause':assert own.setup_metadata['pullback_variant']=='SINGLE_GREEN_LOWER_WICK'
    artifact,built=h.artifacts[0]
    assert artifact.session_phase==('RTH_MID' if clock_time else 'MORNING')
    assert intent.setup_metadata['execution_stream']['execution_trigger_timeframe']==('1m' if clock_time else '10s')
    if clock_time:
        assert h.focus_calls and all(row['session']=='RTH_MID' for row in h.focus_calls[0][0])
    assert artifact.intents==[intent] and received==dict(built[0],decision_id=artifact.decision_id)==vars(intent)
    canonical=[t for t in h.micro_triggers if t[0].get('canonical_result_index')==index]
    assert len(canonical)==1 and canonical[0][2]['trigger_ready_now']
    assert source.levels.established_rth_hod is None  # Fifty bars do not establish the full65-minute RTH history.
    no_effects(h)


@pytest.mark.parametrize('market_fault',['ordinary_green_pause','upper_wick_pause','above_impulse_pause',
    'lost_ema_pause','incomplete_pause','waiting_execution','future_execution'])
def test_joined_micro_pause_and_execution_rejections(reassessment,monkeypatch,tmp_path,capsys,market_fault):
    h=micro_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    out=cycles(h,capsys)
    assert not [i for batch in h.batches for i in batch] and h.artifacts==h.evaluated==[],out
    own=next(r for r in h.registry_batches[-1][1] if r.setup_id=='P_MICRO_PULLBACK')
    if market_fault in {'waiting_execution','future_execution'}:
        assert own.detected
        assert not any(t[2]['trigger_ready_now'] for t in h.micro_triggers if t[0].get('source')=='canonical_pattern_result')
    else:assert not own.detected
    no_effects(h)


@pytest.mark.parametrize('clock_time',[pytest.param(None,id='accepted_10s'),pytest.param((16,35,30),id='RTH_MID_1m')])
def test_joined_micro_keeps_ready_key_competition(reassessment,monkeypatch,tmp_path,capsys,clock_time):
    h=micro_joined(reassessment,monkeypatch,tmp_path,market_fault='competing_key',clock_time=clock_time or (14,35,30),real_session=clock_time is not None)
    out=cycles(h,capsys);source,results=h.registry_batches[-1]
    own=next(r for r in results if r.setup_id=='P_MICRO_PULLBACK')
    assert own.detected and (own.trigger_level,own.stop_level)==(10.98,10.8)
    assert len(h.evaluated)==1,out
    intent,_,decision=h.evaluated[0];selected=results[intent.setup_metadata['canonical_result_index']]
    assert selected.setup_id=='P_KEY_LEVEL_BREAK' and intent.setup_family_id=='KEY_LEVEL_BREAK'
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(11.,10.95,11.)
    assert selected.stop_level==source.candles[-1].low and selected.stop_level!=own.stop_level
    assert any(t[2]['trigger_ready_now'] for t in h.micro_triggers if t[0].get('source')=='canonical_pattern_result')
    assert decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    assert h.artifacts[0][0].session_phase==('RTH_MID' if clock_time else 'MORNING')
    no_effects(h)


def _install_variant_market(h,rows,current,*,pmh,early=None,completed_source=False,execution_history_minutes=5):
    end=h.life.clock.current.replace(second=0,microsecond=0)
    h.streams.clear();h.streams['1m']=_candles(rows,step_seconds=60,
        end=end-timedelta(minutes=1) if completed_source else end)
    aggregate_rows=list(rows)
    if completed_source:
        aggregate_rows.append((current[0][0],max(b[1] for b in current),min(b[2] for b in current),
            current[-1][3],sum(b[4] for b in current)))
    grouped=[]
    for start in range(0,len(aggregate_rows),5):
        chunk=aggregate_rows[start:start+5]
        grouped.append((chunk[0][0],max(b[1] for b in chunk),min(b[2] for b in chunk),
            chunk[-1][3],sum(b[4] for b in chunk)))
    if early is None:early=(10.30,10.32,10.27,10.30,7500) if pmh==10.32 else (9.2,9.3,9.1,9.24,7500)
    h.streams['5m']=_candles([early]*40+grouped,
        step_seconds=300,end=end-timedelta(minutes=4))
    h.streams['10s']=_closed_minutes_and_execution(h.streams['1m'] if completed_source else h.streams['1m'][:-1],current,
        end=end-timedelta(seconds=10),source_minutes=execution_history_minutes)
    last=rows[-1][3];previous=9.4
    for row in h.rows.values():row.update(premarket_high=pmh,last_price=last,bid=last-.01,ask=last+.01,
        prev_close=previous,ref_close_rth=previous,reference_price=previous,
        gap_pct=(last/previous-1)*100,pct_change=(last/previous-1)*100,
        spread_pct=100*.02/last,dollar_volume=last*1_800_000)
    snapshot=replace(_snapshot(symbol='JPM'),last=last,bid=last-.01,ask=last+.01)
    h.core.market_data_snapshot_manager=NS(batch_snapshots=lambda symbols:fixture_quote_batch(h,snapshot,symbols))


def pullback_variant_joined(reassessment,monkeypatch,tmp_path,*,family,
        position_case='complete_empty',runtime_options=None,competing_first=False,news_fault='none',peer=False,market_fault='none'):
    from test_pr1082_trigger_to_intent_terminal_semantics import _rows
    h=pmh_joined(reassessment,monkeypatch,tmp_path,position_case=position_case,
        runtime_options=runtime_options,clock_time=(13,59,30),news_fault=news_fault,peer=peer)
    rows=_rows('ready' if family=='THREE_BAR_PULLBACK' else 'second_ready')
    pmh=10.3
    if family=='THREE_BAR_PULLBACK' and not competing_first:
        # Established prior support is higher than the deep three-bar retrace.
        # First/Micro retain their own EMA/depth requirements; no family is hidden.
        rows[:45]=[(10.30,10.32,10.27,10.30,1500)]*45
        rows[-5]=(10.30,10.50,10.29,10.45,3000)
        pmh=10.32
    rows[15]=(rows[15][0],pmh,rows[15][2],rows[15][3],rows[15][4]) # Observed PRE high.
    if family=='SECOND_PULLBACK':
        rows[-2]=(10.56,10.59,10.35,10.45,1000)
        rows[-1]=(10.52,10.65,10.44,10.62,1600)
        current=[(10.52,10.58,10.44,10.52,200),(10.52,10.59,10.52,10.56,200),
            (10.56,10.65,10.56,10.62,1200)]
    else:
        rows[-1]=(10.32,10.5,10.2,10.48,1600)
        current=[(10.32,10.42,10.2,10.32,200),(10.32,10.44,10.32,10.40,200),
            (10.40,10.5,10.40,10.48,1200)]
    entry,stop=(10.44,10.08) if family=='THREE_BAR_PULLBACK' else (10.59,10.35)
    if market_fault in {'waiting_execution','touch_execution'}:
        value=entry-.02 if market_fault=='waiting_execution' else entry
        current[-1]=(*current[-1][:3],value,current[-1][4])
        rows[-1]=(*rows[-1][:3],value,rows[-1][4])
    elif market_fault=='low_volume':
        current[-1]=(*current[-1][:4],1)
        rows[-1]=(*rows[-1][:4],sum(bar[4] for bar in current))
    elif market_fault=='invalidated_source':
        bar=current[0];current[0]=(bar[0],bar[1],stop-.01,bar[3],bar[4])
        bar=rows[-1];rows[-1]=(bar[0],bar[1],stop-.01,bar[3],bar[4])
    _install_variant_market(h,rows,current,pmh=pmh)
    evaluator=TRIGGER_EVALUATOR_REGISTRY[family];h.pullback_triggers=[]
    def observed(payload,inputs):
        result=evaluator(payload,inputs)
        h.pullback_triggers.append((deepcopy(payload),deepcopy(inputs),deepcopy(result)))
        return result
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,family,observed)
    return h


@pytest.mark.parametrize('family',['THREE_BAR_PULLBACK','SECOND_PULLBACK'])
def test_joined_pullback_variant_authorized_objective_real_registry_readonly(reassessment,monkeypatch,
        tmp_path,capsys,family):
    from src.strategies.ross_momentum.strategy_policy import (
        THREE_BAR_PULLBACK_DESCRIPTIVE_OBJECTIVE,SECOND_PULLBACK_DESCRIPTIVE_OBJECTIVE)
    h=pullback_variant_joined(reassessment,monkeypatch,tmp_path,family=family)
    out=cycles(h,capsys)
    assert len(h.evaluated)==1,out
    intent,received,decision=h.evaluated[0]
    source,results=h.registry_batches[-1]
    assert len(results)==len(h.strategy._pattern_registry.patterns)==33
    selected=results[intent.setup_metadata['canonical_result_index']]
    assert selected.setup_family_id==intent.setup_family_id==family
    expected=(10.44,10.08,THREE_BAR_PULLBACK_DESCRIPTIVE_OBJECTIVE) if family=='THREE_BAR_PULLBACK' else (
        10.59,10.35,SECOND_PULLBACK_DESCRIPTIVE_OBJECTIVE)
    assert (intent.entry_price,intent.stop_loss_price,intent.target_model)==expected
    assert selected.target_suggestion==intent.target_model and intent.take_profit_price is None
    assert intent.invalidation_level==selected.invalidation_level==expected[1]
    assert received==vars(intent) and decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    assert h.pullback_triggers and h.pullback_triggers[-1][2]['trigger_ready_now']
    assert source.candles[-2].timestamp+timedelta(minutes=1)<=source.observed_at_utc
    no_effects(h)


def test_joined_three_bar_preserves_genuine_first_pullback_winner(reassessment,monkeypatch,tmp_path,capsys):
    h=pullback_variant_joined(reassessment,monkeypatch,tmp_path,family='THREE_BAR_PULLBACK',competing_first=True)
    out=cycles(h,capsys)
    assert len(h.evaluated)==1,out
    intent,received,decision=h.evaluated[0]
    _,results=h.registry_batches[-1]
    third=next(r for r in results if r.setup_id=='P_THREE_BAR_PULLBACK')
    selected=results[intent.setup_metadata['canonical_result_index']]
    assert len(results)==33 and third.detected and third.target_suggestion
    assert h.pullback_triggers[-1][2]['trigger_ready_now']
    assert selected.setup_id=='P_FIRST_PULLBACK' and intent.setup_family_id=='FIRST_PULLBACK'
    assert intent.entry_price==selected.trigger_level and intent.stop_loss_price==selected.stop_level
    assert intent.target_model==selected.target_suggestion and intent.target_model!=third.target_suggestion
    assert results.index(third)!=intent.setup_metadata['canonical_result_index']
    assert received==vars(intent) and decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    no_effects(h)


@pytest.mark.parametrize('family',['THREE_BAR_PULLBACK','SECOND_PULLBACK'])
@pytest.mark.parametrize('market_fault',['waiting_execution','touch_execution','low_volume','invalidated_source'])
def test_joined_pullback_objective_preserves_native_source_and_trigger_gates(reassessment,monkeypatch,
        tmp_path,capsys,family,market_fault):
    h=pullback_variant_joined(reassessment,monkeypatch,tmp_path,family=family,market_fault=market_fault)
    cycles(h,capsys)
    _,results=h.registry_batches[-1]
    native=next(r for r in results if r.setup_family_id==family)
    assert len(results)==33
    assert not [i for batch in h.batches for i in batch if i.setup_family_id==family]
    if market_fault=='invalidated_source':
        assert not native.detected and native.target_suggestion is None
    else:
        assert native.detected and native.target_suggestion
        canonical=[result for payload,_,result in h.pullback_triggers
            if payload.get('canonical_result_index')==results.index(native)]
        assert canonical and not any(result['trigger_ready_now'] for result in canonical)
    no_effects(h)


def cup_joined(reassessment,monkeypatch,tmp_path,*,position_case='complete_empty',runtime_options=None,
        peer=False,news_fault='none',competing_key=False,competing_abcd=False,market_fault='none',clock_time=(13,59,30)):
    from test_cup_handle_pattern import _valid_cup_handle
    h=pmh_joined(reassessment,monkeypatch,tmp_path,position_case=position_case,
        runtime_options=runtime_options,clock_time=clock_time,peer=peer,news_fault=news_fault)
    rows=[(10.3,10.32,10.27,10.3,1500)]*36+[
        tuple(getattr(bar,key) for key in ('open','high','low','close','volume')) for bar in _valid_cup_handle()]
    rows[15]=(10.3,10.75,10.27,10.3,1500) # External PRE high, before the cup window.
    rows[25]=(10.3,10.8,10.27,10.3,1500) # Earlier completed RTH high, separately measured.
    if not competing_key:
        bar=rows[-2];rows[-2]=(bar[0],10.49 if competing_abcd else 10.50,10.30,bar[3],bar[4])
    rows[-1]=(10.44,10.55,10.42,10.55,1600)
    current=[(10.44,10.52,10.42,10.50,200),(10.50,10.54,10.49,10.52,200),
        (10.52,10.55,10.51,10.55,1200)]
    if competing_key:
        current=[(10.44,10.48,10.42,10.46,200),(10.46,10.48,10.45,10.48,200),
            (10.48,10.55,10.47,10.55,1200)]
    if market_fault=='forming_handle_low':
        rows[-1]=(10.44,10.55,10.25,10.55,1600)
        current[0]=(10.44,10.52,10.25,10.50,200)
    if market_fault in {'waiting_execution','touch_execution'}:
        value=10.53 if market_fault=='waiting_execution' else 10.54
        current[-1]=(*current[-1][:3],value,current[-1][4])
        rows[-1]=(*rows[-1][:3],value,rows[-1][4])
    _install_variant_market(h,rows[1:],current,pmh=10.75,early=(10.3,10.32,10.27,10.3,7500),
        completed_source=True)
    if market_fault=='forming_handle_low':
        h.streams['1m'][-1]=replace(h.streams['1m'][-1],timestamp=h.life.clock.current.replace(second=0))
    if market_fault=='future_source':
        h.streams['1m'][-1]=replace(h.streams['1m'][-1],timestamp=h.life.clock.current+timedelta(seconds=12))
    elif market_fault=='incomplete_handle_source':
        h.streams['1m'][-2]=replace(h.streams['1m'][-2],timestamp=h.life.clock.current-timedelta(seconds=45))
        h.streams['1m'][-1]=replace(h.streams['1m'][-1],timestamp=h.life.clock.current-timedelta(seconds=30))
    elif market_fault=='nan_source':h.streams['1m'][-1]=replace(h.streams['1m'][-1],high=float('nan'))
    elif market_fault=='malformed_source':
        bar=h.streams['1m'][-1];h.streams['1m'][-1]=replace(bar,high=bar.low-.01)
    elif market_fault=='future_execution':
        h.streams['10s'][-1]=replace(h.streams['10s'][-1],timestamp=h.life.clock.current+timedelta(seconds=12))
    elif market_fault=='infinite_execution':
        h.streams['10s'][-2]=replace(h.streams['10s'][-2],close=-float('inf'))
    evaluator=TRIGGER_EVALUATOR_REGISTRY['CUP_HANDLE'];h.cup_triggers=[]
    def observed(payload,inputs):
        result=evaluator(payload,inputs)
        h.cup_triggers.append((deepcopy(payload),deepcopy(inputs),deepcopy(result)))
        return result
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,'CUP_HANDLE',observed)
    return h


def test_joined_cup_authorized_objective_real_registry_readonly(reassessment,monkeypatch,tmp_path,capsys):
    from src.strategies.ross_momentum.strategy_policy import CUP_HANDLE_DESCRIPTIVE_OBJECTIVE
    h=cup_joined(reassessment,monkeypatch,tmp_path)
    out=cycles(h,capsys)
    assert len(h.evaluated)==1,out
    intent,received,decision=h.evaluated[0]
    source,results=h.registry_batches[-1]
    selected=results[intent.setup_metadata['canonical_result_index']]
    assert len(results)==33 and selected.setup_id=='P_CUP_HANDLE' and intent.setup_family_id=='CUP_HANDLE'
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(10.54,10.30,10.30)
    assert source.levels.established_rth_hod==10.8 and source.levels.premarket_high==10.75
    assert selected.target_suggestion==intent.target_model==CUP_HANDLE_DESCRIPTIVE_OBJECTIVE
    assert received==vars(intent) and intent.take_profit_price is None
    assert decision.reason_code=='LIVE_READ_ONLY_BLOCK' and h.cup_triggers[-1][2]['trigger_ready_now']
    no_effects(h)


def test_joined_cup_preserves_genuine_competing_key(reassessment,monkeypatch,tmp_path,capsys):
    h=cup_joined(reassessment,monkeypatch,tmp_path,competing_key=True)
    cycles(h,capsys)
    assert len(h.evaluated)==1
    intent,received,decision=h.evaluated[0]
    _,results=h.registry_batches[-1]
    cup=next(r for r in results if r.setup_id=='P_CUP_HANDLE')
    selected=results[intent.setup_metadata['canonical_result_index']]
    assert len(results)==33 and cup.detected and h.cup_triggers[-1][2]['trigger_ready_now']
    assert selected.setup_id=='P_KEY_LEVEL_BREAK' and intent.setup_family_id=='KEY_LEVEL_BREAK'
    assert intent.entry_price==selected.trigger_level and intent.entry_price!=cup.trigger_level
    assert intent.target_model==selected.target_suggestion and intent.target_model!=cup.target_suggestion
    assert received==vars(intent) and decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    no_effects(h)


@pytest.mark.parametrize('market_fault',['waiting_execution','touch_execution','future_source','nan_source',
    'malformed_source','future_execution','infinite_execution','incomplete_handle_source'])
def test_joined_cup_existing_contract_cannot_authorize_invalid_or_unconfirmed_inputs(reassessment,
        monkeypatch,tmp_path,capsys,market_fault):
    h=cup_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    cycles(h,capsys)
    assert not [i for batch in h.batches for i in batch if i.setup_family_id=='CUP_HANDLE']
    _,results=h.registry_batches[-1]
    native=next(r for r in results if r.setup_id=='P_CUP_HANDLE')
    source_reasons={'future_source':'FUTURE_CANDLE_DATA','nan_source':'INVALID_CANDLE_DATA',
        'malformed_source':'INVALID_CANDLE_DATA','incomplete_handle_source':'incomplete_cup_handle_structure'}
    if market_fault in source_reasons:
        assert not native.detected and native.rejection_reason==source_reasons[market_fault]
        assert native.target_suggestion is None
    else:
        assert native.detected and native.target_suggestion
        canonical=[result for payload,_,result in h.cup_triggers
            if payload.get('canonical_result_index')==results.index(native)]
        expected={'future_execution':'cup_handle_future_candle_data',
            'infinite_execution':'cup_handle_invalid_candle_data'}.get(market_fault,'awaiting_cup_handle_break')
        assert canonical and all(not result['trigger_ready_now'] and result['trigger_reason']==expected
            for result in canonical)
    no_effects(h)


def test_joined_cup_rejects_forming_final_handle_anchor(reassessment,monkeypatch,tmp_path,capsys):
    h=cup_joined(reassessment,monkeypatch,tmp_path,market_fault='forming_handle_low')
    cycles(h,capsys)
    source,results=h.registry_batches[-1]
    native=next(r for r in results if r.setup_id=='P_CUP_HANDLE')
    assert len(results)==33
    assert source.candles[-1].timestamp+timedelta(minutes=1)>source.observed_at_utc
    assert source.candles[-1].low==10.25<source.candles[-2].low
    assert not native.detected and native.rejection_reason=='incomplete_cup_handle_structure'
    assert native.target_suggestion is None
    assert not [i for batch in h.batches for i in batch if i.setup_family_id=='CUP_HANDLE']
    no_effects(h)


def test_joined_cup_retains_genuine_completed_abcd_competition(reassessment,monkeypatch,tmp_path,capsys):
    h=cup_joined(reassessment,monkeypatch,tmp_path,competing_abcd=True)
    cycles(h,capsys)
    assert len(h.evaluated)==1
    intent,received,decision=h.evaluated[0]
    _,results=h.registry_batches[-1]
    cup=next(r for r in results if r.setup_id=='P_CUP_HANDLE')
    selected=results[intent.setup_metadata['canonical_result_index']]
    assert len(results)==33 and cup.detected and h.cup_triggers[-1][2]['trigger_ready_now']
    assert intent.setup_family_id=='ABCD' and selected.setup_id=='P_ABCD'
    assert intent.entry_price==selected.trigger_level and intent.target_model==selected.target_suggestion
    assert received==vars(intent) and decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    no_effects(h)


def opening_drive_joined(reassessment,monkeypatch,tmp_path,*,position_case='complete_empty',runtime_options=None,
        peer=False,news_fault='none',market_fault='none'):
    h=pmh_joined(reassessment,monkeypatch,tmp_path,position_case=position_case,
        runtime_options=runtime_options,clock_time=(13,40,30),peer=peer,news_fault=news_fault)
    rows=[(10.,10.02,9.98,10.,1500)]*5+[(10.,10.18,9.99,10.16,1600),
        (10.16,10.32,10.15,10.30,1750),(10.30,10.46,10.28,10.42,1900),
        (10.42,10.52,10.40,10.50,1650),(10.50,10.60,10.47,10.58,1800)]
    if market_fault!='competing_stair':
        bar=rows[-2];rows[-2]=(bar[0],bar[1],10.14,bar[3],bar[4])
    end=h.life.clock.current.replace(second=0,microsecond=0)
    h.streams.clear();h.streams['1m']=_candles(rows,step_seconds=60,end=end-timedelta(minutes=1))
    current=[(10.58,10.60,10.57,10.59,300),(10.59,10.60,10.58,10.60,300),
        (10.60,10.63,10.59,10.62,1200)]
    h.streams['10s']=_closed_minutes_and_execution(h.streams['1m'],current,end=end-timedelta(seconds=10))
    groups=[]
    for start in range(0,len(rows),5):
        chunk=rows[start:start+5]
        groups.append((chunk[0][0],max(b[1] for b in chunk),min(b[2] for b in chunk),chunk[-1][3],sum(b[4] for b in chunk)))
    # Independent earlier PRE context plus exact completed RTH aggregates.
    h.streams['5m']=_candles([(10.,10.75,9.98,10.,7500)]*48+groups,step_seconds=300,end=end-timedelta(minutes=5))
    if market_fault in {'waiting_execution','touch_execution'}:
        bar=h.streams['10s'][-1]
        high=10.59 if market_fault=='waiting_execution' else 10.60
        h.streams['10s'][-1]=replace(bar,open=10.58,high=high,low=10.57,close=10.59)
    if market_fault=='missing_opening_origin':h.streams['1m']=h.streams['1m'][1:]
    elif market_fault=='premarket_reference':
        first=h.streams['1m'][0]
        h.streams['1m'].insert(0,replace(first,timestamp=first.timestamp-timedelta(minutes=1),
            open=9.,high=20.,low=8.9,close=9.,volume=1500))
        bar=h.streams['5m'][-3]
        h.streams['5m'][-3]=replace(bar,open=9.,high=20.,low=8.9,close=9.)
    if market_fault=='future_source':
        h.streams['1m'][-1]=replace(h.streams['1m'][-1],timestamp=h.life.clock.current+timedelta(seconds=12))
    elif market_fault=='incomplete_source':
        h.streams['1m'][-1]=replace(h.streams['1m'][-1],timestamp=h.life.clock.current-timedelta(seconds=30))
    elif market_fault=='nan_source':h.streams['1m'][-3]=replace(h.streams['1m'][-3],high=float('nan'))
    elif market_fault=='malformed_source':
        bar=h.streams['1m'][-3];h.streams['1m'][-3]=replace(bar,high=bar.low-.01)
    elif market_fault=='future_execution':
        h.streams['10s'][-1]=replace(h.streams['10s'][-1],timestamp=h.life.clock.current+timedelta(seconds=12))
    elif market_fault=='infinite_execution':h.streams['10s'][-1]=replace(h.streams['10s'][-1],close=-float('inf'))
    last=10.59 if market_fault in {'waiting_execution','touch_execution'} else 10.62
    for row in h.rows.values():row.update(premarket_high=10.75,last_price=last,bid=last-.01,ask=last+.01,
        prev_close=9.4,ref_close_rth=9.4,reference_price=9.4,gap_pct=(last/9.4-1)*100,
        pct_change=(last/9.4-1)*100,spread_pct=100*.02/last,dollar_volume=last*1_800_000)
    snapshot=replace(_snapshot(symbol='JPM'),last=last,bid=last-.01,ask=last+.01)
    h.core.market_data_snapshot_manager=NS(batch_snapshots=lambda symbols:fixture_quote_batch(h,snapshot,symbols))
    evaluator=TRIGGER_EVALUATOR_REGISTRY['OPENING_DRIVE'];h.opening_drive_triggers=[]
    def observed(payload,inputs):
        result=evaluator(payload,inputs)
        h.opening_drive_triggers.append((deepcopy(payload),deepcopy(inputs),deepcopy(result)))
        return result
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,'OPENING_DRIVE',observed)
    return h


def test_joined_opening_drive_native_authorized_objective_readonly(reassessment,monkeypatch,tmp_path,capsys):
    h=opening_drive_joined(reassessment,monkeypatch,tmp_path)
    cycles(h,capsys)
    source,results=h.registry_batches[-1]
    native=next(r for r in results if r.setup_id=='P_OPENING_DRIVE')
    assert len(results)==33
    assert native.detected,native.rejection_reason
    assert source.session_phase=='OPENING_0_30'
    assert (native.trigger_level,native.stop_level,native.invalidation_level)==(10.60,10.47,10.47)
    from src.strategies.ross_momentum.strategy_policy import OPENING_DRIVE_DESCRIPTIVE_OBJECTIVE
    assert native.target_suggestion==OPENING_DRIVE_DESCRIPTIVE_OBJECTIVE
    assert len(h.evaluated)==1
    intent,received,decision=h.evaluated[0]
    assert intent.setup_family_id=='OPENING_DRIVE'
    assert results[intent.setup_metadata['canonical_result_index']].setup_id=='P_OPENING_DRIVE'
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(10.60,10.47,10.47)
    assert intent.target_model==native.target_suggestion and intent.take_profit_price is None
    assert received==vars(intent) and decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    no_effects(h)


@pytest.mark.parametrize('market_fault',['future_source','incomplete_source','nan_source','malformed_source',
    'future_execution','infinite_execution','missing_opening_origin'])
def test_opening_drive_rejects_invalid_source_and_execution_facts(reassessment,monkeypatch,tmp_path,capsys,market_fault):
    h=opening_drive_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    cycles(h,capsys)
    assert not [i for batch in h.batches for i in batch if i.setup_family_id=='OPENING_DRIVE']
    _,results=h.registry_batches[-1]
    native=next(r for r in results if r.setup_id=='P_OPENING_DRIVE')
    reasons={'future_source':'FUTURE_CANDLE_DATA','incomplete_source':'incomplete_opening_drive_structure',
        'nan_source':'INVALID_CANDLE_DATA','malformed_source':'INVALID_CANDLE_DATA',
        'missing_opening_origin':'missing_opening_drive_origin'}
    if market_fault in reasons:
        assert not native.detected and native.rejection_reason==reasons[market_fault]
        assert native.target_suggestion is None
    else:
        assert native.detected
        canonical=[r for p,_,r in h.opening_drive_triggers if p.get('canonical_result_index')==results.index(native)]
        expected='opening_drive_future_candle_data' if market_fault=='future_execution' else 'opening_drive_invalid_candle_data'
        assert canonical and all(not r['trigger_ready_now'] and r['trigger_reason']==expected for r in canonical)
    no_effects(h)


@pytest.mark.parametrize('market_fault,ready',[('waiting_execution',False),('touch_execution',True)])
def test_opening_drive_retains_native_touch_confirmation(reassessment,monkeypatch,tmp_path,capsys,market_fault,ready):
    h=opening_drive_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    cycles(h,capsys)
    _,results=h.registry_batches[-1]
    native=next(r for r in results if r.setup_id=='P_OPENING_DRIVE')
    assert len(results)==33 and native.detected and native.trigger_level==10.60
    canonical=[r for p,_,r in h.opening_drive_triggers if p.get('canonical_result_index')==results.index(native)]
    assert canonical and all(r['trigger_ready_now']==ready for r in canonical)
    own=[i for batch in h.batches for i in batch if i.setup_family_id=='OPENING_DRIVE']
    if ready:
        assert len(own)==1 and own[0].entry_price==10.60
        assert h.evaluated[-1][2].reason_code=='LIVE_READ_ONLY_BLOCK'
    else:assert own==[]
    no_effects(h)


def test_opening_drive_uses_actual_rth_origin_independent_of_pre_bar(reassessment,monkeypatch,tmp_path,capsys):
    h=opening_drive_joined(reassessment,monkeypatch,tmp_path,market_fault='premarket_reference')
    cycles(h,capsys)
    source,results=h.registry_batches[-1]
    native=next(r for r in results if r.setup_id=='P_OPENING_DRIVE')
    assert source.candles[0].open==9. and source.candles[0].high==20.
    assert len(results)==33 and native.detected
    assert (native.trigger_level,native.stop_level,native.invalidation_level)==(10.60,10.47,10.47)
    assert len(h.evaluated)==1 and h.evaluated[0][0].setup_family_id=='OPENING_DRIVE'
    assert h.evaluated[0][2].reason_code=='LIVE_READ_ONLY_BLOCK'
    no_effects(h)


def test_key_original_strong_open_retains_genuine_opening_drive_winner(reassessment,monkeypatch,tmp_path,capsys):
    h=key_joined(reassessment,monkeypatch,tmp_path,market_fault='competing_opening_drive')
    cycles(h,capsys)
    source,results=h.registry_batches[-1]
    key=next(r for r in results if r.setup_id=='P_KEY_LEVEL_BREAK')
    opening=next(r for r in results if r.setup_id=='P_OPENING_DRIVE')
    assert len(results)==33 and key.detected and opening.detected
    assert h.key_triggers[-1][2]['trigger_ready_now']
    assert len(h.evaluated)==1
    intent,received,decision=h.evaluated[0]
    selected=results[intent.setup_metadata['canonical_result_index']]
    assert intent.setup_family_id=='OPENING_DRIVE' and selected is opening
    assert intent.entry_price==opening.trigger_level and intent.stop_loss_price==opening.stop_level
    assert intent.entry_price!=key.trigger_level and intent.target_model==opening.target_suggestion
    assert received==vars(intent) and decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    no_effects(h)


def _coherent_profile_streams(h,final_execution):
    """External matching minute, ten-second and five-minute profile facts."""
    source=h.streams['1m']
    source[-1]=replace(source[-1],volume=sum(row[4] for row in final_execution))
    h.streams['10s']=_closed_minutes_and_execution(source[:-1],final_execution,
        end=source[-1].timestamp+timedelta(seconds=(len(final_execution)-4)*10))
    buckets={}
    for bar in source:
        stamp=bar.timestamp.replace(minute=bar.timestamp.minute//5*5,second=0,microsecond=0)
        buckets.setdefault(stamp,[]).append(bar)
    grouped=[]
    for stamp,chunk in buckets.items():
        if not grouped and chunk[0].timestamp!=stamp:continue
        grouped.append(replace(chunk[0],timestamp=stamp,high=max(bar.high for bar in chunk),
            low=min(bar.low for bar in chunk),close=chunk[-1].close,volume=sum(bar.volume for bar in chunk)))
    first=source[0]
    earlier=_candles([(first.open,first.high,first.low,first.close,first.volume*5)]*40,step_seconds=300,
        end=grouped[0].timestamp-timedelta(minutes=5))
    h.streams['5m']=earlier+grouped


@pytest.mark.parametrize('family,competition',[(family,competition) for family in ('FIRST_PULLBACK','KEY_LEVEL_BREAK')
    for competition in (False,True)])
def test_opening_competition_profile_external_timeframes_agree(reassessment,monkeypatch,tmp_path,capsys,family,competition):
    from test_joined_core_first_pullback import first_joined
    factory=first_joined if family=='FIRST_PULLBACK' else key_joined
    h=factory(reassessment,monkeypatch,tmp_path,market_fault='competing_opening_drive' if competition else 'none')
    for minute in h.streams['1m'][-6:]:
        parts=[bar for bar in h.streams['10s'] if minute.timestamp<=bar.timestamp<minute.timestamp+timedelta(minutes=1)]
        assert len(parts)==6
        assert (parts[0].open,max(bar.high for bar in parts),min(bar.low for bar in parts),parts[-1].close)==(
            minute.open,minute.high,minute.low,minute.close)
        assert sum(bar.volume for bar in parts)==pytest.approx(minute.volume)
    five=h.streams['5m'][-1]
    minutes=[bar for bar in h.streams['1m'] if five.timestamp<=bar.timestamp<five.timestamp+timedelta(minutes=5)]
    assert len(minutes)==5
    assert (five.open,five.high,five.low,five.close)==(minutes[0].open,max(bar.high for bar in minutes),
        min(bar.low for bar in minutes),minutes[-1].close)
    assert five.volume==sum(bar.volume for bar in minutes)
    cycles(h,capsys)
    no_effects(h)


def indicator_pullback_joined(reassessment,monkeypatch,tmp_path,*,family='EMA_PULLBACK',
        position_case='complete_empty',runtime_options=None,peer=False,news_fault='none',market_fault='none'):
    from test_ema_pullback_pipeline_certification import _inputs
    h=pmh_joined(reassessment,monkeypatch,tmp_path,position_case=position_case,runtime_options=runtime_options,
        clock_time=(14,9,30),peer=peer,news_fault=news_fault)
    rows=[(10.3,10.32,10.27,10.3,1500)]*43+[
        tuple(getattr(bar,key) for key in ('open','high','low','close','volume')) for bar in _inputs().candles]
    rows[5]=(10.3,10.75,10.27,10.3,1500)
    rows[15]=(10.3,10.8,10.27,10.3,1500)
    rows[-1]=(10.35 if market_fault=='competing_key' else 10.51,10.62,10.34,10.56,1500)
    current=[(10.56,10.56,10.48,10.49,200),(10.49,10.50,10.48,10.495,200),
        (10.495,10.52,10.47,10.515,1200)]
    if family=='VWAP_PULLBACK':
        rows=[(10.25,10.27,10.23,10.25,1500)]*43+[
            (10.25,10.50,10.24,10.48,1200),(10.48,10.70,10.46,10.68,1600),
            (10.68,10.78,10.66,10.75,1800),(10.75,10.76,10.55,10.60,1100),
            (10.60,10.61,10.24,10.25,850),(10.25,10.45,10.23,10.35,1500)]
        rows[5]=(10.25,10.75,9.5,10.25,1500)
        rows[15]=(10.25,10.8,10.23,10.25,1500)
        current=[(10.35,10.72,10.34,10.70,200),(10.70,10.76,10.68,10.74,200),
            (10.74,10.81,10.73,10.79,1200)]
        if market_fault=='competing_key':
            rows[-1]=(10.25,10.65,10.23,10.55,1500)
            current=[(10.55,10.58,10.24,10.25,200),(10.25,10.27,10.24,10.26,200),
                (10.26,10.81,10.24,10.79,1200)]
    if family=='TREND_CONTINUATION_STAIR_STEP':
        from test_stair_step_pattern import _valid_candles
        rows=[(10.3,10.32,10.27,10.3,1500)]*41+[
            tuple(getattr(bar,key) for key in ('open','high','low','close','volume')) for bar in _valid_candles()]
        rows[5]=(10.3,10.75,9.5,10.3,1500)
        rows[15]=(10.3,10.8,10.27,10.3,1500)
        bar=rows[-2];rows[-2]=(bar[0],bar[1],bar[2],10.48,bar[4])
        current=[(10.61,10.64,10.60,10.62,200),(10.62,10.64,10.61,10.63,200),
            (10.63,10.69,10.62,10.67,1200)]
        if market_fault=='competing_key':
            current=[(10.61,10.63,10.47,10.48,200),(10.48,10.5,10.47,10.49,200),
                (10.49,10.69,10.47,10.67,1200)]
    if market_fault=='competing_abcd' and family=='EMA_PULLBACK':current[-1]=(10.495,10.55,10.47,10.54,1200)
    if market_fault in {'waiting_execution','equal_minimum_break','above_minimum_break'}:
        level={'EMA_PULLBACK':10.5,'VWAP_PULLBACK':10.76,'TREND_CONTINUATION_STAIR_STEP':10.64}[family]
        value={'waiting_execution':level,'equal_minimum_break':level*(1+.001),
            'above_minimum_break':level*(1+.001)+.0001}[market_fault]
        current[-1]=(*current[-1][:3],value,current[-1][4])
    elif market_fault=='invalid_breakout_shape':
        current[-1]={'EMA_PULLBACK':(10.515,10.57,10.47,10.515,1200),
            'VWAP_PULLBACK':(10.79,10.85,10.73,10.79,1200),
            'TREND_CONTINUATION_STAIR_STEP':(10.67,10.75,10.62,10.67,1200)}[family]
    _install_variant_market(h,rows,current,pmh=10.75,early=(10.3,10.32,10.27,10.3,7500),completed_source=True)
    if market_fault=='future_source':
        h.streams['1m'][-1]=replace(h.streams['1m'][-1],timestamp=h.life.clock.current+timedelta(seconds=12))
    elif market_fault=='incomplete_source':
        h.streams['1m'][-1]=replace(h.streams['1m'][-1],timestamp=h.life.clock.current-timedelta(seconds=30))
    elif market_fault=='nan_source':h.streams['1m'][-10]=replace(h.streams['1m'][-10],high=float('nan'))
    elif market_fault=='malformed_source':
        bar=h.streams['1m'][-10];h.streams['1m'][-10]=replace(bar,high=bar.low-.01)
    elif market_fault=='future_execution':
        h.streams['10s'][-1]=replace(h.streams['10s'][-1],timestamp=h.life.clock.current+timedelta(seconds=12))
    elif market_fault=='nan_execution':h.streams['10s'][-1]=replace(h.streams['10s'][-1],low=float('nan'))
    last=current[-1][3]
    bid,ask=round(last-.01,2),round(last+.01,2)
    for row in h.rows.values():row.update(last_price=last,bid=bid,ask=ask,
        spread_pct=100*(ask-bid)/last,dollar_volume=last*1_800_000,
        gap_pct=(last/9.4-1)*100,pct_change=(last/9.4-1)*100)
    snapshot=replace(_snapshot(symbol='JPM'),last=last,bid=bid,ask=ask)
    h.core.market_data_snapshot_manager=NS(batch_snapshots=lambda symbols:fixture_quote_batch(h,snapshot,symbols))
    evaluator=TRIGGER_EVALUATOR_REGISTRY[family];h.indicator_triggers=[]
    def observed(payload,inputs):
        result=evaluator(payload,inputs)
        h.indicator_triggers.append((deepcopy(payload),deepcopy(inputs),deepcopy(result)))
        return result
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,family,observed)
    if market_fault in {'competing_key','competing_abcd'}:
        other_family='KEY_LEVEL_BREAK' if market_fault=='competing_key' else 'ABCD'
        other=TRIGGER_EVALUATOR_REGISTRY[other_family];h.competing_indicator_triggers=[]
        def observed_competitor(payload,inputs):
            result=other(payload,inputs)
            h.competing_indicator_triggers.append((deepcopy(payload),deepcopy(inputs),deepcopy(result)))
            return result
        monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,other_family,observed_competitor)
    return h


def test_native_ema_pullback_authorized_objective_selected_readonly(reassessment,monkeypatch,tmp_path,capsys):
    h=indicator_pullback_joined(reassessment,monkeypatch,tmp_path)
    cycles(h,capsys)
    source,results=h.registry_batches[-1]
    native=next(r for r in results if r.setup_id=='P_EMA_PULLBACK')
    assert len(results)==33 and native.detected,native.rejection_reason
    from src.strategies.ross_momentum.strategy_policy import EMA_PULLBACK_DESCRIPTIVE_OBJECTIVE
    assert native.target_suggestion==EMA_PULLBACK_DESCRIPTIVE_OBJECTIVE
    assert len(h.evaluated)==1
    intent,received,decision=h.evaluated[0]
    assert intent.setup_family_id=='EMA_PULLBACK'
    assert results[intent.setup_metadata['canonical_result_index']] is native
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(10.5,10.29,10.29)
    assert intent.target_model==native.target_suggestion and intent.take_profit_price is None
    assert received==vars(intent) and decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    no_effects(h)


@pytest.mark.parametrize('market_fault',['future_source','incomplete_source','nan_source','malformed_source',
    'future_execution','nan_execution'])
def test_native_ema_pullback_invalid_facts_cannot_admit(reassessment,monkeypatch,tmp_path,capsys,market_fault):
    h=indicator_pullback_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    cycles(h,capsys)
    assert not [i for batch in h.batches for i in batch if i.setup_family_id=='EMA_PULLBACK']
    _,results=h.registry_batches[-1]
    native=next(r for r in results if r.setup_id=='P_EMA_PULLBACK')
    reasons={'future_source':'FUTURE_CANDLE_DATA','incomplete_source':'incomplete_ema_pullback_structure',
        'nan_source':'INVALID_CANDLE_DATA','malformed_source':'INVALID_CANDLE_DATA'}
    if market_fault in reasons:
        assert not native.detected and native.rejection_reason==reasons[market_fault]
        assert native.target_suggestion is None
    else:
        assert native.detected
        canonical=[r for p,_,r in h.indicator_triggers if p.get('canonical_result_index')==results.index(native)]
        reason='ema_pullback_future_candle_data' if market_fault=='future_execution' else 'ema_pullback_invalid_candle_data'
        assert canonical and all(not r['trigger_ready_now'] and r['trigger_reason']==reason for r in canonical)
    no_effects(h)


@pytest.mark.parametrize('market_fault,family,winner',[('competing_key','KEY_LEVEL_BREAK','KEY_LEVEL_BREAK'),
    ('competing_abcd','ABCD','EMA_PULLBACK')])
def test_ema_pullback_preserves_genuine_competing_family_selection(reassessment,monkeypatch,tmp_path,capsys,market_fault,family,winner):
    h=indicator_pullback_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    cycles(h,capsys)
    _,results=h.registry_batches[-1]
    ema=next(r for r in results if r.setup_id=='P_EMA_PULLBACK')
    assert len(results)==33 and ema.detected and h.indicator_triggers[-1][2]['trigger_ready_now']
    assert len(h.evaluated)==1
    intent,received,decision=h.evaluated[0]
    selected=results[intent.setup_metadata['canonical_result_index']]
    other=next(r for r in results if r.setup_family_id==family)
    assert other.detected
    assert any(r['trigger_ready_now'] for p,_,r in h.competing_indicator_triggers
        if p.get('canonical_result_index')==results.index(other))
    assert intent.setup_family_id==winner
    assert selected is (other if winner==family else ema)
    assert intent.entry_price==selected.trigger_level and intent.target_model==selected.target_suggestion
    assert received==vars(intent) and decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    no_effects(h)


@pytest.mark.parametrize('market_fault,ready,reason',[('waiting_execution',False,'awaiting_breakout'),
    ('equal_minimum_break',False,'awaiting_breakout'),('above_minimum_break',True,'ema_pullback_breakout_confirmed'),
    ('invalid_breakout_shape',False,'breakout_shape_invalid')])
def test_ema_pullback_preserves_registered_confirmation_boundaries(reassessment,monkeypatch,tmp_path,capsys,
        market_fault,ready,reason):
    h=indicator_pullback_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    cycles(h,capsys)
    _,results=h.registry_batches[-1]
    native=next(r for r in results if r.setup_id=='P_EMA_PULLBACK')
    assert len(results)==33 and native.detected
    canonical=[r for p,_,r in h.indicator_triggers if p.get('canonical_result_index')==results.index(native)]
    assert canonical and all(r['trigger_ready_now']==ready and r['trigger_reason']==reason for r in canonical)
    own=[i for batch in h.batches for i in batch if i.setup_family_id=='EMA_PULLBACK']
    assert len(own)==int(ready)
    no_effects(h)


def vwap_pullback_joined(*args,**kwargs):
    return indicator_pullback_joined(*args,family='VWAP_PULLBACK',**kwargs)


def test_native_vwap_pullback_authorized_objective_selected_readonly(reassessment,monkeypatch,tmp_path,capsys):
    h=indicator_pullback_joined(reassessment,monkeypatch,tmp_path,family='VWAP_PULLBACK')
    cycles(h,capsys)
    source,results=h.registry_batches[-1]
    native=next(r for r in results if r.setup_id=='P_VWAP_PULLBACK')
    assert len(results)==33 and native.detected,native.rejection_reason
    from src.strategies.ross_momentum.strategy_policy import VWAP_PULLBACK_DESCRIPTIVE_OBJECTIVE
    assert native.target_suggestion==VWAP_PULLBACK_DESCRIPTIVE_OBJECTIVE
    assert source.candles[-2].close<source.indicators.vwap<source.candles[-1].close<source.indicators.ema9
    ema=next(r for r in results if r.setup_id=='P_EMA_PULLBACK')
    momentum=next(r for r in results if r.setup_id=='P_MOMENTUM_RECLAIM')
    assert not ema.detected and not momentum.detected
    assert len(h.evaluated)==1
    intent,received,decision=h.evaluated[0]
    assert intent.setup_family_id=='VWAP_PULLBACK'
    assert results[intent.setup_metadata['canonical_result_index']] is native
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(10.76,10.23,10.23)
    assert intent.target_model==native.target_suggestion and intent.take_profit_price is None
    assert received==vars(intent) and decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    no_effects(h)


@pytest.mark.parametrize('market_fault',['future_source','incomplete_source','nan_source','malformed_source',
    'future_execution','nan_execution'])
def test_native_vwap_pullback_invalid_facts_cannot_admit(reassessment,monkeypatch,tmp_path,capsys,market_fault):
    h=vwap_pullback_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    cycles(h,capsys)
    assert not [i for batch in h.batches for i in batch if i.setup_family_id=='VWAP_PULLBACK']
    _,results=h.registry_batches[-1]
    native=next(r for r in results if r.setup_id=='P_VWAP_PULLBACK')
    reasons={'future_source':'FUTURE_CANDLE_DATA','incomplete_source':'incomplete_vwap_pullback_structure',
        'nan_source':'INVALID_CANDLE_DATA','malformed_source':'INVALID_CANDLE_DATA'}
    if market_fault in reasons:
        assert not native.detected and native.rejection_reason==reasons[market_fault]
        assert native.target_suggestion is None
    else:
        assert native.detected
        canonical=[r for p,_,r in h.indicator_triggers if p.get('canonical_result_index')==results.index(native)]
        reason='vwap_pullback_future_candle_data' if market_fault=='future_execution' else 'vwap_pullback_invalid_candle_data'
        assert canonical and all(not r['trigger_ready_now'] and r['trigger_reason']==reason for r in canonical)
    no_effects(h)


@pytest.mark.parametrize('market_fault,ready,reason',[('waiting_execution',False,'awaiting_breakout'),
    ('equal_minimum_break',False,'awaiting_breakout'),('above_minimum_break',True,'vwap_pullback_breakout_confirmed'),
    ('invalid_breakout_shape',False,'breakout_shape_invalid')])
def test_vwap_pullback_preserves_own_registered_confirmation_boundaries(reassessment,monkeypatch,tmp_path,capsys,
        market_fault,ready,reason):
    h=vwap_pullback_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    cycles(h,capsys)
    _,results=h.registry_batches[-1]
    native=next(r for r in results if r.setup_id=='P_VWAP_PULLBACK')
    assert len(results)==33 and native.detected and native.trigger_level==10.76
    canonical=[r for p,_,r in h.indicator_triggers if p.get('canonical_result_index')==results.index(native)]
    assert canonical and all(r['trigger_ready_now']==ready and r['trigger_reason']==reason for r in canonical)
    assert len([i for batch in h.batches for i in batch if i.setup_family_id=='VWAP_PULLBACK'])==int(ready)
    no_effects(h)


def test_vwap_pullback_preserves_genuine_key_winner(reassessment,monkeypatch,tmp_path,capsys):
    h=vwap_pullback_joined(reassessment,monkeypatch,tmp_path,market_fault='competing_key')
    cycles(h,capsys)
    _,results=h.registry_batches[-1]
    vwap=next(r for r in results if r.setup_id=='P_VWAP_PULLBACK')
    key=next(r for r in results if r.setup_id=='P_KEY_LEVEL_BREAK')
    assert len(results)==33 and vwap.detected and key.detected
    assert h.indicator_triggers[-1][2]['trigger_ready_now']
    assert any(r['trigger_ready_now'] for p,_,r in h.competing_indicator_triggers
        if p.get('canonical_result_index')==results.index(key)), (key.trigger_level,h.competing_indicator_triggers[-1][2])
    assert len(h.evaluated)==1
    intent,received,decision=h.evaluated[0]
    assert intent.setup_family_id=='KEY_LEVEL_BREAK'
    assert results[intent.setup_metadata['canonical_result_index']] is key
    assert intent.entry_price==key.trigger_level and intent.entry_price!=vwap.trigger_level
    assert intent.target_model==key.target_suggestion and intent.target_model!=vwap.target_suggestion
    assert received==vars(intent) and decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    no_effects(h)


def stair_step_joined(*args,**kwargs):
    return indicator_pullback_joined(*args,family='TREND_CONTINUATION_STAIR_STEP',**kwargs)


def test_native_stair_step_authorized_objective_selected_readonly(reassessment,monkeypatch,tmp_path,capsys):
    h=stair_step_joined(reassessment,monkeypatch,tmp_path)
    cycles(h,capsys)
    source,results=h.registry_batches[-1]
    native=next(r for r in results if r.setup_id=='P_TREND_CONTINUATION_STAIR_STEP')
    assert len(results)==33 and native.detected,native.rejection_reason
    assert (native.trigger_level,native.stop_level,native.invalidation_level)==(10.64,10.34,10.24)
    from src.strategies.ross_momentum.strategy_policy import TREND_CONTINUATION_STAIR_STEP_DESCRIPTIVE_OBJECTIVE
    assert native.target_suggestion==TREND_CONTINUATION_STAIR_STEP_DESCRIPTIVE_OBJECTIVE
    assert native.setup_metadata['higher_low_sequence_count']>=2
    assert len(h.evaluated)==1
    intent,received,decision=h.evaluated[0]
    assert intent.setup_family_id=='TREND_CONTINUATION_STAIR_STEP'
    assert results[intent.setup_metadata['canonical_result_index']] is native
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(10.64,10.34,10.24)
    assert intent.target_model==native.target_suggestion and intent.take_profit_price is None
    assert received==vars(intent) and decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    no_effects(h)


@pytest.mark.parametrize('market_fault',['future_source','incomplete_source','nan_source','malformed_source',
    'future_execution','nan_execution'])
def test_native_stair_step_invalid_facts_cannot_admit(reassessment,monkeypatch,tmp_path,capsys,market_fault):
    h=stair_step_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    cycles(h,capsys)
    assert not [i for batch in h.batches for i in batch if i.setup_family_id=='TREND_CONTINUATION_STAIR_STEP']
    _,results=h.registry_batches[-1]
    native=next(r for r in results if r.setup_id=='P_TREND_CONTINUATION_STAIR_STEP')
    reasons={'future_source':'FUTURE_CANDLE_DATA','incomplete_source':'incomplete_stair_step_structure',
        'nan_source':'INVALID_CANDLE_DATA','malformed_source':'INVALID_CANDLE_DATA'}
    if market_fault in reasons:
        assert not native.detected and native.rejection_reason==reasons[market_fault]
        assert native.target_suggestion is None
    else:
        assert native.detected
        canonical=[r for p,_,r in h.indicator_triggers if p.get('canonical_result_index')==results.index(native)]
        reason='stair_step_future_candle_data' if market_fault=='future_execution' else 'stair_step_invalid_candle_data'
        assert canonical and all(not r['trigger_ready_now'] and r['trigger_reason']==reason for r in canonical)
    no_effects(h)


@pytest.mark.parametrize('market_fault,ready,reason',[('waiting_execution',False,'awaiting_breakout'),
    ('equal_minimum_break',False,'awaiting_breakout'),('above_minimum_break',True,'stair_step_breakout_confirmed'),
    ('invalid_breakout_shape',False,'breakout_shape_invalid')])
def test_stair_step_preserves_own_registered_confirmation_boundaries(reassessment,monkeypatch,tmp_path,capsys,
        market_fault,ready,reason):
    h=stair_step_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    cycles(h,capsys)
    _,results=h.registry_batches[-1]
    native=next(r for r in results if r.setup_id=='P_TREND_CONTINUATION_STAIR_STEP')
    assert len(results)==33 and native.detected and native.trigger_level==10.64
    canonical=[r for p,_,r in h.indicator_triggers if p.get('canonical_result_index')==results.index(native)]
    assert canonical and all(r['trigger_ready_now']==ready and r['trigger_reason']==reason for r in canonical)
    assert len([i for batch in h.batches for i in batch if i.setup_family_id=='TREND_CONTINUATION_STAIR_STEP'])==int(ready)
    no_effects(h)


def test_stair_step_preserves_ready_key_competitor_and_actual_selection(reassessment,monkeypatch,tmp_path,capsys):
    h=stair_step_joined(reassessment,monkeypatch,tmp_path,market_fault='competing_key')
    cycles(h,capsys)
    _,results=h.registry_batches[-1]
    stair=next(r for r in results if r.setup_id=='P_TREND_CONTINUATION_STAIR_STEP')
    key=next(r for r in results if r.setup_id=='P_KEY_LEVEL_BREAK')
    assert len(results)==33 and stair.detected and key.detected
    assert h.indicator_triggers[-1][2]['trigger_ready_now']
    assert any(r['trigger_ready_now'] for p,_,r in h.competing_indicator_triggers
        if p.get('canonical_result_index')==results.index(key))
    assert len(h.evaluated)==1
    intent,received,decision=h.evaluated[0]
    assert intent.setup_family_id=='TREND_CONTINUATION_STAIR_STEP'
    assert results[intent.setup_metadata['canonical_result_index']] is stair
    assert intent.entry_price==stair.trigger_level and intent.entry_price!=key.trigger_level
    assert intent.target_model==stair.target_suggestion and intent.target_model!=key.target_suggestion
    assert received==vars(intent) and decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    no_effects(h)


def test_opening_drive_original_rising_lows_preserve_genuine_stair_winner(reassessment,monkeypatch,tmp_path,capsys):
    h=opening_drive_joined(reassessment,monkeypatch,tmp_path,market_fault='competing_stair')
    cycles(h,capsys)
    _,results=h.registry_batches[-1]
    opening=next(r for r in results if r.setup_id=='P_OPENING_DRIVE')
    stair=next(r for r in results if r.setup_id=='P_TREND_CONTINUATION_STAIR_STEP')
    assert len(results)==33 and opening.detected and stair.detected
    assert h.opening_drive_triggers[-1][2]['trigger_ready_now']
    assert len(h.evaluated)==1
    intent,received,decision=h.evaluated[0]
    assert intent.setup_family_id=='TREND_CONTINUATION_STAIR_STEP'
    assert results[intent.setup_metadata['canonical_result_index']] is stair
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(
        stair.trigger_level,stair.stop_level,stair.invalidation_level)
    assert intent.stop_loss_price!=opening.stop_level and intent.target_model!=opening.target_suggestion
    assert received==vars(intent) and decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    no_effects(h)


def measured_structure_joined(reassessment,monkeypatch,tmp_path,*,family='RANGE_BREAK',position_case='complete_empty',runtime_options=None,
        news_fault='none',peer=False,market_fault='none'):
    h=pmh_joined(reassessment,monkeypatch,tmp_path,position_case=position_case,
        runtime_options=runtime_options,clock_time=(13,59,30),news_fault=news_fault,peer=peer)
    if family=='RANGE_BREAK':
        rectangle=[(10.25,10.44,10.04,10.35,1200),(10.35,10.43,10.05,10.25,1100),
            (10.25,10.44,10.04,10.36,1000),(10.36,10.43,10.05,10.26,900),
            (10.26,10.44,10.04,10.35,1000),(10.35,10.43,10.05,10.4,1100)]
        current=[(10.4,10.42,10.39,10.4,200),(10.4,10.44,10.4,10.42,200),
            (10.42,10.5,10.41,10.48,1200)]
        rows=[(10.3,10.32,10.27,10.3,1500)]*43+rectangle+[(10.4,10.5,10.39,10.48,1600)]
    else:
        # Reuse only raw external OHLCV rows, never the component's internal
        # PatternInputs/levels/indicators/result. Actual Core rebuilds them all.
        from test_setup_family_pipeline_certification import _measured_triangle_pennant_case
        profile,execution=_measured_triangle_pennant_case(family)
        raw=[tuple(getattr(c,k) for k in ('open','high','low','close','volume')) for c in profile.candles]
        rows=[(10.3,10.32,10.27,10.3,1500)]*(50-len(raw))+raw
        current=[tuple(getattr(c,k) for k in ('open','high','low','close','volume')) for c in execution[-3:]]
    rows[15]=(10.3,10.9 if family=='PENNANT' else 10.75,10.27,10.3,1500)
    rows[25]=(10.3,11.0 if family=='PENNANT' else 10.8,10.27,10.3,1500)
    pmh=10.9 if family=='PENNANT' else 10.75
    entry=10.59 if family=='PENNANT' else 10.44
    if market_fault=='competing_pmh':
        pmh=entry;rows[15]=(10.3,pmh,10.27,10.3,1500)
    if market_fault in {'touch_execution','low_volume'}:
        if market_fault=='touch_execution':current[-1]=(*current[-1][:3],entry,current[-1][4])
        else:current[-1]=(*current[-1][:4],1)
        rows[-1]=(current[0][0],max(b[1] for b in current),min(b[2] for b in current),
            current[-1][3],sum(b[4] for b in current))
    _install_variant_market(h,rows,current,pmh=pmh,execution_history_minutes={'RANGE_BREAK':6,'ASCENDING_TRIANGLE':7,'PENNANT':5}[family])
    if market_fault=='future_source':
        h.streams['1m'][-1]=replace(h.streams['1m'][-1],timestamp=h.life.clock.current+timedelta(seconds=12))
    elif market_fault=='nan_source':h.streams['1m'][-3]=replace(h.streams['1m'][-3],low=float('nan'))
    elif market_fault=='incomplete_geometry':
        # Source has only five completed rectangle bars; the sixth is developing.
        h.streams['1m'][-2]=replace(h.streams['1m'][-2],timestamp=h.life.clock.current.replace(second=0))
        h.streams['1m']=h.streams['1m'][:-1]
    elif market_fault=='future_execution':
        h.streams['10s'][-1]=replace(h.streams['10s'][-1],timestamp=h.life.clock.current+timedelta(seconds=12))
    elif market_fault=='nan_execution':h.streams['10s'][-1]=replace(h.streams['10s'][-1],volume=float('nan'))
    elif market_fault=='forming_execution':
        h.streams['10s'][-1]=replace(h.streams['10s'][-1],timestamp=h.life.clock.current+timedelta(seconds=5))
    evaluator=TRIGGER_EVALUATOR_REGISTRY[family];h.structural_triggers=[]
    h.range_triggers=h.structural_triggers
    def observed(payload,inputs):
        result=evaluator(payload,inputs)
        h.range_triggers.append((deepcopy(payload),deepcopy(inputs),deepcopy(result)))
        return result
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,family,observed)
    return h


def range_joined(*args,**kwargs):
    return measured_structure_joined(*args,family='RANGE_BREAK',**kwargs)


def triangle_joined(*args,**kwargs):
    return measured_structure_joined(*args,family='ASCENDING_TRIANGLE',**kwargs)


def pennant_joined(*args,**kwargs):
    return measured_structure_joined(*args,family='PENNANT',**kwargs)


def test_native_measured_range_joined_full_registry_readonly(reassessment,monkeypatch,tmp_path,capsys):
    h=range_joined(reassessment,monkeypatch,tmp_path)
    out=cycles(h,capsys)
    source,results=h.registry_batches[-1]
    own=next(r for r in results if r.setup_id=='P_RANGE_BREAKOUT')
    assert own.detected,own.rejection_reason
    assert len(results)==len(h.strategy._pattern_registry.patterns)==33
    assert h.range_triggers and all(r['trigger_ready_now'] for _,_,r in h.range_triggers),[(r.get('trigger_reason'),r.get('execution_stream')) for _,_,r in h.range_triggers]
    assert len(h.evaluated)==1,h.strategy.last_symbol_terminal_outcomes
    intent,received,decision=h.evaluated[0]
    assert intent.setup_family_id=='RANGE_BREAK'
    assert results[intent.setup_metadata['canonical_result_index']] is own
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(10.44,10.04,10.04)
    assert intent.target_model==own.target_suggestion and intent.take_profit_price is None
    assert intent.setup_metadata['source_metadata']==own.setup_metadata
    assert received==vars(intent) and decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    artifact,built=h.artifacts[0]
    assert artifact.intents==[intent] and received==dict(built[0],decision_id=artifact.decision_id)
    assert h.range_triggers[-1][2]['trigger_ready_now']
    no_effects(h)


@pytest.mark.parametrize('market_fault',['touch_execution','low_volume','future_source','nan_source',
    'incomplete_geometry','future_execution','nan_execution','forming_execution'])
def test_native_range_joined_geometry_and_own_confirmation_rejections(reassessment,monkeypatch,
        tmp_path,capsys,market_fault):
    h=range_joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    cycles(h,capsys)
    _,results=h.registry_batches[-1]
    own=next(r for r in results if r.setup_id=='P_RANGE_BREAKOUT')
    assert len(results)==33
    assert not [i for batch in h.batches for i in batch if i.setup_family_id=='RANGE_BREAK']
    if market_fault in {'future_source','nan_source','incomplete_geometry'}:
        reasons={'future_source':'FUTURE_CANDLE_DATA','nan_source':'INVALID_CANDLE_DATA',
            'incomplete_geometry':'range_upper_boundary_not_flat'}
        assert not own.detected and own.target_suggestion is None
        assert own.rejection_reason==reasons[market_fault]
    else:
        assert own.detected and h.range_triggers
        canonical=[r for p,_,r in h.range_triggers if p.get('canonical_result_index')==results.index(own)]
        reasons={'touch_execution':'awaiting_range_break','low_volume':'breakout_volume_confirmation_failed',
            'future_execution':'range_future_candle_data','nan_execution':'range_invalid_candle_data',
            'forming_execution':'range_incomplete_execution_confirmation'}
        assert canonical and all(not r['trigger_ready_now'] and r['trigger_reason']==reasons[market_fault]
            for r in canonical)
    no_effects(h)


def test_native_range_preserves_genuine_pmh_competition(reassessment,monkeypatch,tmp_path,capsys):
    h=range_joined(reassessment,monkeypatch,tmp_path,market_fault='competing_pmh')
    cycles(h,capsys)
    _,results=h.registry_batches[-1]
    own=next(r for r in results if r.setup_id=='P_RANGE_BREAKOUT')
    assert own.detected and any(r['trigger_ready_now'] for _,_,r in h.range_triggers)
    assert len(results)==33 and len(h.evaluated)==1
    intent,received,decision=h.evaluated[0]
    selected=results[intent.setup_metadata['canonical_result_index']]
    assert selected.setup_id=='P_PREMARKET_HIGH_BREAK'
    assert selected.confidence>own.confidence
    assert intent.target_model==selected.target_suggestion and intent.target_model!=own.target_suggestion
    assert received==vars(intent) and decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    no_effects(h)


@pytest.mark.parametrize('family,pattern_id,entry,stop',[
    ('ASCENDING_TRIANGLE','P_ASCENDING_TRIANGLE_BREAKOUT',10.44,10.20),
    ('PENNANT','P_PENNANT_BREAK',10.59,10.40)])
def test_native_triangle_pennant_joined_selected_serialized_readonly(reassessment,monkeypatch,
        tmp_path,capsys,family,pattern_id,entry,stop):
    h=measured_structure_joined(reassessment,monkeypatch,tmp_path,family=family)
    cycles(h,capsys)
    source,results=h.registry_batches[-1]
    own=next(r for r in results if r.setup_id==pattern_id)
    assert len(results)==33 and own.detected,own.rejection_reason
    assert h.structural_triggers and h.structural_triggers[-1][2]['trigger_ready_now']
    assert len(h.evaluated)==1,h.strategy.last_symbol_terminal_outcomes
    intent,received,decision=h.evaluated[0]
    assert intent.setup_family_id==family
    assert results[intent.setup_metadata['canonical_result_index']] is own
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(entry,stop,stop)
    assert intent.take_profit_price is None and intent.target_model==own.target_suggestion
    assert intent.setup_metadata['source_metadata']==own.setup_metadata
    artifact,built=h.artifacts[0]
    assert artifact.intents==[intent] and received==dict(built[0],decision_id=artifact.decision_id)==vars(intent)
    assert decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    if family=='ASCENDING_TRIANGLE':
        assert own.setup_metadata['triangle_floor']==10.04<stop
        assert own.setup_metadata['triangle_swing_low_prices']==(10.04,10.12,10.20)
    else:
        assert own.setup_metadata['pole_low']==9.98<stop
        assert own.setup_metadata['origin_timestamp']<own.setup_metadata['formation_start_timestamp']
    no_effects(h)


@pytest.mark.parametrize('family,pattern_id,prefix',[
    ('ASCENDING_TRIANGLE','P_ASCENDING_TRIANGLE_BREAKOUT','triangle'),
    ('PENNANT','P_PENNANT_BREAK','pennant')])
@pytest.mark.parametrize('market_fault',['touch_execution','low_volume','future_source','nan_source',
    'incomplete_geometry','future_execution','nan_execution','forming_execution'])
def test_native_triangle_pennant_joined_causal_rejections(reassessment,monkeypatch,tmp_path,
        capsys,family,pattern_id,prefix,market_fault):
    h=measured_structure_joined(reassessment,monkeypatch,tmp_path,family=family,market_fault=market_fault)
    cycles(h,capsys)
    _,results=h.registry_batches[-1]
    own=next(r for r in results if r.setup_id==pattern_id)
    assert len(results)==33
    assert not [i for batch in h.batches for i in batch if i.setup_family_id==family]
    if market_fault in {'future_source','nan_source','incomplete_geometry'}:
        reason={'future_source':'FUTURE_CANDLE_DATA','nan_source':'INVALID_CANDLE_DATA',
            'incomplete_geometry':('triangle_resistance_not_flat' if prefix=='triangle'
                else 'pennant_missing_measured_impulse')}[market_fault]
        assert not own.detected and own.target_suggestion is None and own.rejection_reason==reason
    else:
        assert own.detected
        canonical=[r for p,_,r in h.structural_triggers if p.get('canonical_result_index')==results.index(own)]
        reason={'touch_execution':'awaiting_'+prefix+'_break','low_volume':'breakout_volume_confirmation_failed',
            'future_execution':prefix+'_future_candle_data','nan_execution':prefix+'_invalid_candle_data',
            'forming_execution':prefix+'_incomplete_execution_confirmation'}[market_fault]
        assert canonical and all(not r['trigger_ready_now'] and r['trigger_reason']==reason for r in canonical)
    no_effects(h)


@pytest.mark.parametrize('family',['ASCENDING_TRIANGLE','PENNANT'])
def test_native_triangle_pennant_preserve_genuine_pmh_winner(reassessment,monkeypatch,tmp_path,capsys,family):
    h=measured_structure_joined(reassessment,monkeypatch,tmp_path,family=family,market_fault='competing_pmh')
    cycles(h,capsys)
    _,results=h.registry_batches[-1]
    own=next(r for r in results if r.setup_family_id==family)
    assert len(results)==33 and own.detected and any(r['trigger_ready_now'] for _,_,r in h.structural_triggers)
    assert len(h.evaluated)==1,h.strategy.last_symbol_terminal_outcomes
    intent,received,decision=h.evaluated[0]
    selected=results[intent.setup_metadata['canonical_result_index']]
    assert selected.setup_id=='P_PREMARKET_HIGH_BREAK'
    assert selected.confidence>own.confidence
    assert intent.target_model==selected.target_suggestion and intent.target_model!=own.target_suggestion
    assert received==vars(intent) and decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    no_effects(h)


def gap_context_joined(reassessment,monkeypatch,tmp_path,*,competing=False):
    h=pmh_joined(reassessment,monkeypatch,tmp_path,clock_time=(13,59,30))
    rows=[(10.4,10.45,10.3,10.4,1500)]*50
    pmh=10.5 if competing else 11.2
    rows[15]=(10.4,pmh,10.3,10.4,1500)
    rows[21]=(10.4,10.9,10.3,10.4,1500)
    rows[25]=(10.4,11.3,10.3,10.4,1500)
    rows[-6:-1]=[(9.6,9.65,9.4,9.5,1000),(9.5,9.8,9.45,9.75,1100),
        (9.75,10.,9.7,9.95,1300),(9.95,10.3,9.9,10.25,1500),(10.25,10.6,10.2,10.5,2000)]
    previous=10.49 if competing else 10.51
    current=[(10.51,10.52,10.48,previous,200),(previous,10.52,10.48,previous,200),
             (previous,10.53,10.48,10.52,1200)]
    rows[-1]=(10.51,10.53,10.48,10.52,1600)
    _install_variant_market(h,rows,current,pmh=pmh,early=(10.4,pmh,10.3,10.4,7500))
    return h


@pytest.mark.parametrize('competing',[False,True])
def test_joined_gap_fill_context_never_becomes_entry_or_veto(reassessment,monkeypatch,tmp_path,capsys,competing):
    h=gap_context_joined(reassessment,monkeypatch,tmp_path,competing=competing)
    out=cycles(h,capsys)
    assert h.registry_batches,out
    source,results=h.registry_batches[-1]
    assert len(results)==len(h.strategy._pattern_registry.patterns)==33
    context=next(r for r in results if r.setup_id=='P_GAP_FILL_REVERSAL')
    assert context.detected and context.non_entry_signal and context.signal_class=='CONTEXT',context
    assert context.setup_metadata['session_open_price']==10.4
    assert context.trigger_level is context.stop_level is context.target_suggestion is None
    assert not any(i['setup_family_id']=='GAP_FILL' for i in h.raw_snapshots)
    if competing:
        assert h.evaluated,out
        assert all(i.setup_family_id=='PREMARKET_HIGH_BREAK' and d.reason_code=='LIVE_READ_ONLY_BLOCK'
            for i,_,d in h.evaluated),[(i.setup_family_id,d.reason_code) for i,_,d in h.evaluated]
    else:
        assert h.raw_snapshots==h.artifacts==h.evaluated==[],out
    no_effects(h)


def standalone_bull_joined(reassessment,monkeypatch,tmp_path,*,news_fault='none',peer=False,
        position_case='complete_empty',runtime_options=None,clock_time=(14,10,30),real_session=False):
    from src.strategies.common.candles.candle_types import Candle
    from test_bull_flag_production_authority import TAIL
    from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY
    from src.market_data.session_pct_change import resolve_market_session_label
    moment=reassessment.life.clock.current.replace(hour=clock_time[0],minute=clock_time[1],second=clock_time[2],microsecond=0)
    session=resolve_market_session_label(moment)
    h=pmh_joined(reassessment,monkeypatch,tmp_path,news_fault=news_fault,peer=peer,
        position_case=position_case,runtime_options=runtime_options,clock_time=clock_time,context_session=session if real_session else None)
    end=h.life.clock.current.replace(second=0,microsecond=0)
    rows=[(10.,10.02,9.98,10.,1000)]*41+TAIL
    primary=_candles(rows,end=end-timedelta(minutes=1))
    # Completed external PRE12 wick; neither RTH HOD nor an injected LevelSet.
    from src.utils.time_utils import to_ny_time
    primary=[replace(b,high=12.) if to_ny_time(b.timestamp).hour==9 and to_ny_time(b.timestamp).minute==29 else b for b in primary]
    fast=[]
    for b in primary:
        fast.extend(Candle(b.open,b.open,b.open,b.open,b.volume/10,timestamp=b.timestamp+timedelta(seconds=10*i)) for i in range(5))
        fast.append(Candle(b.open,b.high,b.low,b.close,b.volume/2,timestamp=b.timestamp+timedelta(seconds=50)))
    fast.extend([Candle(10.7,10.72,10.69,10.72,150,timestamp=end),
        Candle(10.72,10.76,10.71,10.74,150,timestamp=end+timedelta(seconds=10)),
        Candle(10.74,10.9,10.69,10.88,1800,timestamp=end+timedelta(seconds=20))])
    groups={}
    for b in primary:
        key=b.timestamp.replace(minute=(b.timestamp.minute//5)*5)
        groups.setdefault(key,[]).append(b)
    context=[Candle(items[0].open,max(b.high for b in items),min(b.low for b in items),items[-1].close,
        sum(b.volume for b in items),timestamp=stamp) for stamp,items in sorted(groups.items()) if len(items)==5]
    earlier=_candles([(10.,10.02,9.98,10.,1000)]*40,step_seconds=300,end=context[0].timestamp-timedelta(minutes=5))
    h.streams.update({'1m':primary,'10s':fast,'5m':earlier+context})
    for row in h.rows.values():row.update(premarket_high=12.,last_price=10.88,bid=10.87,ask=10.89,
        gap_pct=(10.88/9.4-1)*100,pct_change=(10.88/9.4-1)*100,spread_pct=100*.02/10.88,dollar_volume=10.88*1_800_000)
    snapshot=replace(_snapshot(symbol='JPM'),last=10.88,bid=10.87,ask=10.89)
    h.core.market_data_snapshot_manager=NS(batch_snapshots=lambda symbols:fixture_quote_batch(h,snapshot,symbols))
    h.bull_triggers=[];original=TRIGGER_EVALUATOR_REGISTRY['BULL_FLAG']
    def observed(payload,inputs):
        out=original(payload,inputs);h.bull_triggers.append((deepcopy(payload),deepcopy(inputs),deepcopy(out)));return out
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY,'BULL_FLAG',observed)
    return h


def test_standalone_bull_actual_full_registry_core_handoff(reassessment,monkeypatch,tmp_path,capsys):
    from src.setup_engine.setup_families.bull_flag import BullFlagPattern
    h=standalone_bull_joined(reassessment,monkeypatch,tmp_path)
    out=cycles(h,capsys)
    source,results=h.registry_batches[-1]
    standalone=BullFlagPattern().evaluate(source) # Diagnostic original native owner, never injected.
    wired=next(r for r in results if r.setup_id=='P_BULL_FLAG')
    assert standalone.detected and (standalone.trigger_level,standalone.stop_level)==(10.79,10.63)
    assert wired.detected,(wired.rejection_reason,h.strategy.last_symbol_terminal_outcomes,out)
    assert len(results)==33 and len(h.evaluated)==1
    intent,serialized,decision=h.evaluated[0]
    assert intent.setup_family_id=='BULL_FLAG' and not intent.relationship_context
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(10.79,10.63,10.63)
    assert intent.target_model=='Measured move' and intent.take_profit_price is None
    assert serialized==vars(intent) and decision.reason_code=='LIVE_READ_ONLY_BLOCK'
    no_effects(h)


@pytest.mark.parametrize('fault',['missing_security','future_clock','missing_clock','unknown_session','missing_rvol','unconfirmed','active_parent'])
def test_standalone_bull_active_optin_preserves_native_and_relationship_guards(reassessment,monkeypatch,tmp_path,capsys,fault):
    from src.execution.trade_management_engine import TradeManagementEngine
    from src.setup_engine.setup_families.bull_flag import BullFlagPattern
    h=standalone_bull_joined(reassessment,monkeypatch,tmp_path)
    cycles(h,capsys)
    source=h.registry_batches[-1][0];now=source.observed_at_utc
    manager=TradeManagementEngine();security='conId:123';pattern=BullFlagPattern()
    assert pattern.evaluate(source).detected
    if fault=='missing_security':security=''
    elif fault=='future_clock':source=replace(source,observed_at_utc=now+timedelta(seconds=1))
    elif fault=='missing_clock':source=replace(source,observed_at_utc=None);now=None
    elif fault=='unknown_session':source=replace(source,session_label='UNKNOWN')
    elif fault=='missing_rvol':source=replace(source,liquidity_context=replace(source.liquidity_context,rvol=None))
    elif fault=='unconfirmed':source=replace(source,candles=source.candles[:-1]+[replace(source.candles[-1],close=10.79)])
    else:
        # A genuinely armed composed parent remains authoritative. Its different
        # occurrence cannot be escaped through the standalone opt-in.
        from test_ross_bullflag_micro_management import composed_inputs
        prior,prior_now=composed_inputs()
        assert manager.compose_bull_flag(pattern,prior,security_id=security,now=prior_now).detected
    result=manager.compose_bull_flag(pattern,source,security_id=security,now=now,allow_standalone=True)
    assert not result.detected,(fault,result)
    no_effects(h)
