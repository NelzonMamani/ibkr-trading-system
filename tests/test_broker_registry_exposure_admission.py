"""Bounded synthetic owner-level admission research, never broker execution.

USD cap35: held2*10 + native new1*10.91=30.91; held3*10 +10.91=40.91.
Only broker/system quantities vary. Actual policy/owners decide every outcome.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta, timezone
from types import SimpleNamespace as NS

import pytest

from src.config import config_resolver
from src.core.active_trade_registry import ActiveTrade
from src.core.engines.trade_lifecycle_engine import LifecycleEvent
from src.core.event_collector import EventCollector
from src.core.intent import build_decision_artifact
from src.execution.execution_engine import ExecutionEngine
from src.execution.execution_providers import PaperExecutionProvider
from src.ibkr.position_snapshot import BrokerPositionResult
from src.ibkr.mutation_audit import snapshot as mutation_snapshot
from test_joined_core_bull_micro import joined, lifecycle, reassessment, _reset_config
from test_key_level_break_production_handoff import forbid_io


class AdmissionBoundary(BaseException):
    """Hard stop before route/provider; ordinary error handling cannot suppress it."""


@pytest.fixture(autouse=True)
def no_external_activity(monkeypatch, forbid_io):
    from ibapi.client import EClient
    import socket
    import sys
    import urllib.request
    attempts=[]
    def forbidden(*args,**kwargs):
        attempts.append("forbidden_external_or_mutation")
        pytest.fail("external provider/broker/mutation forbidden")
    for name in ("reqPositions","reqPositionsMulti","reqAllOpenOrders","reqOpenOrders",
                 "reqExecutions","reqContractDetails","reqGlobalCancel"):
        monkeypatch.setattr(EClient,name,forbidden)
    monkeypatch.setattr(socket.socket,"connect_ex",forbidden)
    monkeypatch.setattr(socket.socket,"sendto",forbidden)
    monkeypatch.setattr(urllib.request,"urlopen",forbidden)
    if sessions:=sys.modules.get("requests.sessions"):
        monkeypatch.setattr(sessions.Session,"request",forbidden)
    for name in ("place_order","place_stop_order","place_target_order","modify_stop_order","cancel_order","cancel"):
        monkeypatch.setattr(PaperExecutionProvider,name,forbidden)
    return attempts


class AccountBoundary(PaperExecutionProvider):
    # Synthetic complete account facts only, not an approval or broker request.
    def get_account_summary(self):
        return {"NetLiquidation":1000.,"AvailableFunds":1000.,"BuyingPower":1000.}


@pytest.mark.parametrize("broker_qty,system_qty",[(2,2),(3,2),(3,3)])
def test_real_broker_registry_exposure_admission(reassessment,monkeypatch,tmp_path,capsys,broker_qty,system_qty,no_external_activity):
    h=joined(reassessment,monkeypatch,tmp_path,position_case="complete_empty")
    # Real empty startup recovery happens before synthetic held-fill facts arrive.
    # No recovery result/permission is forced or patched.
    paper_overrides=dict(config_resolver._CONFIG_OVERRIDES)
    paper_overrides.update(RUN_MODE="PAPER",RUN_MODE_EFFECTIVE="PAPER",EXECUTION_ENABLED=True,
        EXECUTION_ENABLED_EFFECTIVE=True,IBKR_READONLY_ENABLED=False,RISK_ACCOUNT_EQUITY=1000.,
        RISK_MAX_TOTAL_EXPOSURE_PCT=3.5,LIFECYCLE_MAX_PORTFOLIO_EXPOSURE=35.,
        STRATEGY_CAPITAL_DEFAULT_ALLOCATION_PCT=1.)
    config_resolver.set_config_overrides(paper_overrides)
    class Price:
        def price_for(self,*args): return 10.91
        def get_price(self,*args): return 10.91
    provider=AccountBoundary(price_feed=Price(),trade_registry=h.core.trade_registry,
        event_collector=EventCollector(),run_mode=h.core.run_mode)
    engine=ExecutionEngine(provider=provider,trade_registry=h.core.trade_registry,
        trade_lifecycle_engine=h.core.trade_lifecycle_engine,price_feed=Price())
    engine.relationship_manager=h.manager
    assert engine.startup_recovery_complete(),engine.startup_recovery_result
    h.core.trade_registry.register_trade(ActiveTrade(symbol="SYNTH_MATCH",trader_type="SYNTHETIC",
        entry_tick=0,entry_price=10.,direction="LONG",quantity=system_qty,stop_loss_price=9.))
    life=h.core.trade_lifecycle_engine
    life.apply_entry_fill(event=LifecycleEvent(event_id="synthetic-held-fill",lifecycle_trade_id="synthetic-held",
        symbol="SYNTH_MATCH",side="LONG",event_type="ENTRY_FILL",quantity=system_qty,price=10.,
        timestamp=h.life.clock.current.isoformat(),order_id="synthetic-held",execution_id="synthetic-fill"),
        strategy_name="SYNTHETIC",stop_price=9.)
    engine.capital_authority.recover_from_lifecycle(life.get_open_lifecycle_trades())
    engine.strategy_allocation_authority.recover_from_lifecycle(life.get_open_lifecycle_trades())
    def positions():
        return BrokerPositionResult((NS(symbol="SYNTH_MATCH",position=broker_qty,con_id=987,
            avgCost=10.,marketPrice=10.,account="SYNTHETIC_TEST"),),"COMPLETE","SYNTHETIC_TEST",
            h.life.clock.now(timezone.utc))
    h.core.connection_manager._ibkr_connection_manager.existing_client=NS(position_snapshot=positions)
    # Formation still uses accepted joined READ_ONLY Core. The later PAPER risk/
    # admission call is explicitly an owner-level control, not PAPER Core proof.
    config_resolver.set_config_overrides(dict(paper_overrides,RUN_MODE="READ_ONLY",RUN_MODE_EFFECTIVE="READ_ONLY",
        EXECUTION_ENABLED=False,EXECUTION_ENABLED_EFFECTIVE=False,IBKR_READONLY_ENABLED=True))
    assert h.core.run_once()
    capsys.readouterr()
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once()
    formation_log=capsys.readouterr().out
    raw=[i for batch in h.batches for i in batch]
    assert len(raw)==1,formation_log
    intent=raw[0]
    truth,verdict=h.truth[-1]
    assert not verdict.block_new_entries
    assert [m.mismatch_type for m in truth.mismatches]==(["QUANTITY_MISMATCH"] if broker_qty!=system_qty else [])
    config_resolver.set_config_overrides(paper_overrides)
    # A fresh real artifact for this separate mode evaluation, never arbitrary ID.
    intent.decision_id=None
    artifact=build_decision_artifact(strategy_name=intent.strategy_name,run_mode="PAPER",session_phase="RTH_OPEN",
        intents=[intent],source="offline-exposure-control",created_at=h.life.clock.current.isoformat())
    intent.decision_id=artifact.decision_id
    received=deepcopy(vars(intent))
    decision=h.core.risk_engine.evaluate_trade_intent(intent)
    registry_exposure=h.core.risk_engine._total_exposure()
    lifecycle_exposure=life.build_portfolio_state().total_exposure
    context=engine._capital_portfolio_context(intent.symbol)
    boundaries=[]
    def stop_before_route(order):
        boundaries.append(order)
        raise AdmissionBoundary()
    monkeypatch.setattr(engine,"_route_order",stop_before_route)
    execution_calls=[]
    execute=engine.execute_trade
    def observed_execute(value):
        execution_calls.append(value)
        return execute(value)
    monkeypatch.setattr(engine,"execute_trade",observed_execute)
    result=None
    try:
        try:
            if decision.allowed and not decision.execution_blocked:
                result=engine.execute_trade(decision)
        except AdmissionBoundary:
            pass
        capital=getattr(decision,"capital_decision",None)
        allocation=getattr(decision,"strategy_allocation_decision",None)
        print("EXPOSURE_CONTROL",{"broker_qty":broker_qty,"system_qty":system_qty,
            "truth":truth.snapshot_status,"warning":verdict.warning_mismatch_count,
            "registry":registry_exposure,"lifecycle":lifecycle_exposure,"context":context,
            "used":engine.capital_authority.total_used_exposure,"risk_allowed":decision.allowed,
            "risk_reason":decision.reason_code,"size":decision.max_position_size,
            "execution_blocked":decision.execution_blocked,"action":decision.overall_action,"code":decision.decision_code,
            "capital":asdict(capital) if capital else None,"allocation":asdict(allocation) if allocation else None,
            "result":result.rationale if result else None,"boundary":bool(boundaries),
            "risk_limits":decision.evaluated_limits})
        assert registry_exposure==lifecycle_exposure==system_qty*10.
        assert context["current_total_exposure"]==engine.capital_authority.total_used_exposure==system_qty*10.
        assert decision.decision_id==artifact.decision_id and vars(intent)==received
        assert mutation_snapshot()=={"place":0,"modify":0,"cancel":0}
        # Do not alter gap25 or loosen its actual4..20 gate to force admission.
        assert intent.gap_percent==25. and h.core.risk_engine.ross_overlay.min_gap==4.
        assert h.core.risk_engine.ross_overlay.max_gap==20.
        assert (intent.symbol,intent.direction,intent.entry_price,intent.stop_loss_price)==("JPM","LONG",10.91,10.81)
        assert intent.relationship_context["security_id"]=="conId:123"
        assert truth.broker_positions["SYNTH_MATCH"].con_id==987
        assert truth.broker_positions["SYNTH_MATCH"].quantity==broker_qty
        assert truth.system_positions["SYNTH_MATCH"].quantity==system_qty
        assert verdict.healthy==(broker_qty==system_qty) and verdict.require_reconciliation==(broker_qty!=system_qty)
        assert verdict.warning_mismatch_count==int(broker_qty!=system_qty)
        assert getattr(intent,"quantity",1)==1 and decision.evaluated_limits["max_position_size"]==1
        assert decision.evaluated_limits["max_total_exposure"]==35.
        assert decision.evaluated_limits["trade_value"]==10.91
        assert decision.evaluated_limits["lifecycle_total_exposure"]==system_qty*10.
        assert not decision.allowed and decision.max_position_size==0
        assert decision.overall_action=="BLOCK" and decision.decision_code=="REJECT"
        # Existing Ross overlay omits this marker; do not fake it true or
        # confuse it with an allowed order. Report the inconsistency separately.
        assert decision.execution_blocked==(system_qty==3)
        assert decision.reason_code==("CAPITAL_PORTFOLIO_LIMIT" if system_qty==3 else "ROSS_BLOCK_GAP_OUT_OF_RANGE")
        assert allocation is capital is None and not boundaries and result is None and not execution_calls
        assert engine._relationship_open_orders==[] and engine.position_records=={}
        assert not engine.capital_authority.active_reservations and not engine.strategy_allocation_authority.active_reservations
        assert no_external_activity==[]
        assert system_qty*10.+10.91==pytest.approx(30.91 if system_qty==2 else 40.91)
        assert broker_qty*10.+10.91==pytest.approx(30.91 if broker_qty==2 else 40.91)
    finally:
        engine.capital_authority.release_reservation(reason="OFFLINE_CONTROL_END")
        engine.strategy_allocation_authority.release_reservation(reason="OFFLINE_CONTROL_END")
        assert engine.capital_authority.active_reservations=={}
        assert engine.strategy_allocation_authority.active_reservations=={}
        assert mutation_snapshot()=={"place":0,"modify":0,"cancel":0}
