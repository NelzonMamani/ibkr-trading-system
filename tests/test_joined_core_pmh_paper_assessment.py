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


def paper_pmh(reassessment,monkeypatch,tmp_path,position_case):
    import test_joined_core_bull_micro as joined_module
    _install_eligible_market_facts(reassessment,monkeypatch)
    # Coherent new external fixture facts; thresholds and candle anchors unchanged.
    previous=9.4
    last=10.53
    gap=(last/previous-1)*100
    facts=dict(prev_close=previous,ref_close_rth=previous,reference_price=previous,
        last_price=last,gap_pct=gap,pct_change=gap,pct_change_resolved=True,
        bid=10.52,ask=10.54,spread_pct=100*.02/last,dollar_volume=last*2_000_000)
    reassessment.row.update(facts)
    row_factory=joined_module._row
    def scanner_row(symbol):
        row=row_factory(symbol)
        for key,value in facts.items():setattr(row,key,value)
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
    h=pmh_joined(reassessment,monkeypatch,tmp_path,position_case=position_case,
        runtime_options=dict(run_mode='PAPER',config_overrides=dict(EXECUTION_ENABLED=True,
            RISK_PROFILE='MICRO',IBKR_READONLY_ENABLED=False,IBKR_ORDER_SUBMISSION_ENABLED=True,
            IBKR_ORDER_TRANSLATION_ENABLED=True,IBKR_API_WRITE_ALLOWED=True)))
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
            # Preserve the demonstrated actual handoff block, not a forced pass.
            assert not formed['relationship_context'] and formed['gap_percent'] is None
            assert intent.gap_percent is None and received['gap_percent'] is None
            assert not decision.allowed and decision.execution_blocked and decision.max_position_size==0
            assert decision.reason_code=='ROSS_BLOCK_GAP_OUT_OF_RANGE'
            assert decision.decision_code=='REJECT' and decision.overall_action=='BLOCK'
            assert 'gap_percent=None' in decision.rationale
            assert not reached and h.boundaries==h.execution_calls==h.reserves==h.execution_results==[]
            assert getattr(decision,'capital_decision',None) is None
            assert getattr(decision,'strategy_allocation_decision',None) is None
            assert 'ORDER_SUBMITTED' not in out
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
