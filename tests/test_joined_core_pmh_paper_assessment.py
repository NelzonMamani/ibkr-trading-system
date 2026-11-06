"""Bounded test-only PAPER eligibility; stops before any provider routing.

Real canonical news/cache/Focus/detector/trigger/V1/Core/risk/execution/capital.
Synthetic external facts, existing startup seams and an unsuppressible route
barrier. No scoped capital enrollment or permission/result injection.
"""
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace as NS

import pytest

from src.config.runtime_config import RunMode
from src.core import orchestrator as core_module
from src.execution.execution_engine import ExecutionEngine
from src.ibkr.mutation_audit import snapshot as mutation_snapshot
from test_broker_registry_exposure_admission import (
    AccountBoundary, AdmissionBoundary, _install_eligible_market_facts,
    no_external_activity,
)
from test_joined_core_pmh_readonly import (
    pmh_joined, reassessment, lifecycle, _reset_config, forbid_io,
)


def paper_pmh(reassessment,monkeypatch,tmp_path,position_case,*,peer=False,news_fault="none"):
    import test_joined_core_bull_micro as joined_module
    _install_eligible_market_facts(reassessment,monkeypatch)
    # Coherent new external fixture facts; thresholds and candle anchors unchanged.
    last=10.53
    previous=9.4
    gap=(last/previous-1)*100
    facts=dict(prev_close=previous,ref_close_rth=previous,reference_price=previous,
        last_price=last,gap_pct=gap,pct_change=(last/previous-1)*100,pct_change_resolved=True,
        bid=10.52,ask=10.54,spread_pct=100*.02/last,dollar_volume=last*2_000_000)
    reassessment.row.update(facts)
    peer_facts=dict(gap_pct=12.,prev_close=last/1.12,reference_price=last/1.12,
        ref_close_rth=last/1.12,pct_change=12.)
    row_factory=joined_module._row
    def scanner_row(symbol):
        row=row_factory(symbol)
        for key,value in facts.items():setattr(row,key,value)
        if symbol=='PEER':
            for key,value in peer_facts.items():setattr(row,key,value)
        return row
    monkeypatch.setattr(joined_module,'_row',scanner_row)
    # Same external adapter-construction seam as existing joined PAPER controls.
    # Empty synthetic startup inventory; no SDK client or broker connection.
    monkeypatch.setattr(core_module,'IbkrLiveBroker',lambda **kw:NS())
    providers=[]
    def provider_boundary(**kw):
        provider=AccountBoundary(price_feed=NS(price_for=lambda *a:10.3,get_price=lambda *a:10.3),
            event_collector=core_module.EventCollector(),trade_registry=kw['trade_registry'],run_mode=kw['run_mode'])
        providers.append(provider)
        return provider
    monkeypatch.setattr(core_module,'IbkrExecutionProvider',provider_boundary)
    h=pmh_joined(reassessment,monkeypatch,tmp_path,position_case=position_case,peer=peer,news_fault=news_fault,
        runtime_options=dict(run_mode='PAPER',config_overrides=dict(EXECUTION_ENABLED=True,
            RISK_PROFILE='MICRO',IBKR_READONLY_ENABLED=False,IBKR_ORDER_SUBMISSION_ENABLED=True,
            IBKR_ORDER_TRANSLATION_ENABLED=True,IBKR_API_WRITE_ALLOWED=True)))
    if peer:h.rows['PEER'].update(peer_facts)
    from src.execution import execution_engine as execution_module
    monkeypatch.setattr(execution_module,'datetime',h.life.clock)
    engine=h.core.execution_engine
    assert h.core.run_mode==engine.run_mode==RunMode.PAPER
    assert h.core.runtime_mode_manager.allow_orders and engine.startup_recovery_complete()
    assert len(providers)==1 and engine.provider is providers[0]
    h.execution_calls=[];h.execution_results=[];h.reserves=[];h.boundaries=[];h.defaults=[]
    defaults=h.strategy._apply_intent_contract_defaults
    def observe_defaults(intent,context,**kw):
        before=deepcopy(vars(context))
        out=defaults(intent,context,**kw)
        h.defaults.append((before,deepcopy(vars(out))))
        return out
    monkeypatch.setattr(h.strategy,'_apply_intent_contract_defaults',observe_defaults)
    for authority,label in ((engine.capital_authority,'capital'),(engine.strategy_allocation_authority,'allocation')):
        reserve=type(authority).reserve.__get__(authority)
        def observe_reserve(*args,_reserve=reserve,_label=label,**kw):
            out=_reserve(*args,**kw)
            h.reserves.append(_label)
            return out
        monkeypatch.setattr(authority,'reserve',observe_reserve)
    execute=ExecutionEngine.execute_trade
    def observe_execute(decision):
        h.execution_calls.append(decision)
        out=execute(engine,decision)
        h.execution_results.append(out)
        return out
    monkeypatch.setattr(engine,'execute_trade',observe_execute)
    def stop_before_route(order):
        h.boundaries.append(deepcopy(order))
        raise AdmissionBoundary()
    monkeypatch.setattr(engine,'_route_order',stop_before_route)
    return h


@pytest.mark.parametrize('position_case',['complete_empty','unknown','partial','quantity_warning_larger','five'])
def test_joined_pmh_paper_admission_stops_before_provider(reassessment,monkeypatch,tmp_path,capsys,
        no_external_activity,position_case):
    h=paper_pmh(reassessment,monkeypatch,tmp_path,position_case)
    engine=h.core.execution_engine
    try:
        assert h.core.run_once()
        capsys.readouterr()
        h.life.clock.current+=timedelta(seconds=11)
        reached=False
        try:assert h.core.run_once()
        except AdmissionBoundary:reached=True
        out=capsys.readouterr().out
        raw=[i for batch in h.batches for i in batch]
        print('PMH_PAPER_ASSESSMENT',dict(position_case=position_case,raw=len(raw),
            artifacts=len(h.artifacts),risk=[(d.reason_code,d.allowed,d.max_position_size) for _,_,d in h.evaluated],
            executions=len(h.execution_calls),reserves=h.reserves,boundary=reached,
            results=[(r.status,r.rationale) for r in h.execution_results]))
        assert len(raw)==1 and raw[0].setup_family_id=='PREMARKET_HIGH_BREAK',out
        intent=raw[0]
        source,results=h.registry_batches[-1]
        index=intent.setup_metadata['canonical_result_index'];selected=results[index]
        assert selected.setup_id=='P_PREMARKET_HIGH_BREAK' and selected.detected
        assert intent.entry_price==selected.trigger_level==10.3
        assert intent.stop_loss_price==selected.stop_level==10.3-max(.01,10.3*.001)
        assert intent.invalidation_level==selected.invalidation_level==10.3
        assert intent.take_profit_price is None and intent.target_model==selected.target_suggestion
        assert intent.setup_metadata['execution_stream']['observed_at_utc']==source.observed_at_utc.isoformat()
        assert no_external_activity==[] and mutation_snapshot()==dict(place=0,modify=0,cancel=0)
        assert not engine.position_records and not engine._relationship_open_orders
        assert not h.manager.snapshot_positions()
        assert engine.capital_authority.capital_scope is None and engine.capital_authority._capital_writer is None
        assert engine.capital_authority.total_used_exposure==0
        assert h.core.storage_engine._store.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='capital_owner_state'").fetchone() is None
        if position_case=='complete_empty':
            assert all(v.healthy and not v.block_new_entries for _,v in h.truth)
            assert len(h.artifacts)==len(h.evaluated)==1
            artifact,built=h.artifacts[0];_,received,decision=h.evaluated[0]
            assert artifact.run_mode=='PAPER'
            assert intent.decision_id==artifact.decision_id==decision.decision_id
            assert received==dict(built[0],decision_id=artifact.decision_id)
            overlay=h.core.risk_engine.ross_overlay
            gap=(10.53/9.4-1)*100
            assert overlay.min_gap<=gap<=overlay.max_gap
            assert h.rows['JPM']['gap_pct']==h.rows['JPM']['pct_change']==pytest.approx(gap)
            assert h.rows['JPM']['prev_close']==h.rows['JPM']['reference_price']==9.4
            assert h.rows['JPM']['last_price']==10.53
            assert intent.float_millions==8. and intent.rvol==10.
            assert intent.confidence>=overlay.confidence_floor
            assert len(h.defaults)==1
            context,formed=h.defaults[0]
            assert context['gap_pct']==pytest.approx(gap)
            assert not formed['relationship_context'] and formed['gap_percent']==pytest.approx(gap)
            assert intent.gap_percent==received['gap_percent']==pytest.approx(gap)
            assert decision.allowed and not decision.execution_blocked,out
            assert reached and len(h.boundaries)==len(h.execution_calls)==1,out
            request=h.boundaries[0]
            assert request.quantity==decision.max_position_size==1
            assert request.setup_family_id==intent.setup_family_id
            assert request.stop_loss_price==intent.stop_loss_price and request.invalidation_level==intent.invalidation_level
            assert request.target_model==intent.target_model and request.take_profit_price is None
            assert request.client_order_id.startswith(artifact.decision_id)
            assert h.reserves==['allocation','capital'] and h.execution_results==[]
            assert decision.capital_decision.executable and decision.strategy_allocation_decision.executable
            assert engine.capital_authority.total_reserved_capital==pytest.approx(10.3)
        else:
            snapshot,verdict=h.truth[-1]
            assert verdict.block_new_entries
            if position_case=='quantity_warning_larger':
                assert snapshot.broker_positions['SYNTH_MATCH'].quantity==3
                assert snapshot.system_positions['SYNTH_MATCH'].quantity==2
                assert verdict.warning_mismatch_count==1 and not verdict.block_exits
            elif position_case=='five':
                assert len(snapshot.mismatches)==verdict.critical_mismatch_count==5
            else:assert snapshot.snapshot_status=='UNKNOWN' and not verdict.healthy
            assert h.artifacts==h.evaluated==h.execution_calls==h.boundaries==h.reserves==[]
            assert not reached and intent.decision_id is None
            assert 'POSITION_TRUTH_BLOCK_NEW_ENTRIES' in out
    finally:
        # Test-only cleanup AFTER the unsent request barrier, through actual owners.
        # No simulated terminal broker outcome or production recovery permission.
        for authority in (engine.capital_authority,engine.strategy_allocation_authority):
            for reservation in list(authority.active_reservations.values()):
                authority.release_reservation(decision_id=reservation.decision_id,reason='OFFLINE_UNSENT_FIXTURE_CLEANUP')
            assert not authority.active_reservations
        assert engine.capital_authority.total_reserved_capital==0
        assert no_external_activity==[] and mutation_snapshot()==dict(place=0,modify=0,cancel=0)
