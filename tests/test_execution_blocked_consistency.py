"""Regression controls: real owners, synthetic facts, no operational dispatch.

Failing-before evidence remains on test/execution-blocked-consistency.
Reuse the native joined exposure control; do not manufacture risk decisions.
"""
from copy import deepcopy

import pytest

from src.config.runtime_config import RunMode
from src.risk.risk_engine import RiskEngine
from src.execution.execution_engine import ExecutionEngine
from src.ibkr.mutation_audit import snapshot as mutations
from src.strategies.ross_momentum.ross_momentum_risk_overlay import RossMomentumRiskOverlay
from test_broker_registry_exposure_admission import (
    _run_exposure_control, no_external_activity, reassessment, lifecycle, _reset_config,
)
from test_key_level_break_production_handoff import forbid_io


def decision_fields(decision):
    return dict(allowed=decision.allowed, size=decision.max_position_size,
        execution_blocked=decision.execution_blocked, level=decision.risk_level,
        reason=decision.reason_code, code=decision.decision_code, action=decision.overall_action)


@pytest.mark.parametrize("case,quantity,eligible,mode",[
    ("overlay_gap_rejection",2,False,RunMode.PAPER),
    ("overlay_gap_rejection",2,False,RunMode.LIVE),
    ("overlay_gap_rejection",2,False,RunMode.READ_ONLY),
    ("eligible_allowed",2,True,RunMode.PAPER),
    ("lifecycle_cap_rejection",3,True,RunMode.PAPER),
    ("lifecycle_cap_rejection",3,True,RunMode.LIVE),
    ("lifecycle_cap_rejection",3,True,RunMode.READ_ONLY),
])
def test_actual_denial_marker_and_execution_admission(reassessment,monkeypatch,tmp_path,capsys,
        no_external_activity,case,quantity,eligible,mode):
    decisions=[]
    overlays=[]
    engines=[]
    evaluate=RiskEngine.evaluate_trade_intent
    blocked=RossMomentumRiskOverlay._blocked_decision
    initialize=ExecutionEngine.__init__
    def observe_risk(self,*args,**kwargs):
        result=evaluate(self,*args,**kwargs)
        decisions.append(result)
        return result
    def observe_overlay(self,*args,**kwargs):
        result=blocked(self,*args,**kwargs)
        overlays.append(deepcopy(decision_fields(result)))
        return result
    def observe_engine(self,*args,**kwargs):
        initialize(self,*args,**kwargs)
        engines.append(self)
    monkeypatch.setattr(RiskEngine,"evaluate_trade_intent",observe_risk)
    monkeypatch.setattr(RossMomentumRiskOverlay,"_blocked_decision",observe_overlay)
    monkeypatch.setattr(ExecutionEngine,"__init__",observe_engine)
    outcome=_run_exposure_control(reassessment,monkeypatch,tmp_path,capsys,
        quantity,quantity,no_external_activity,eligible)
    decision=next(d for d in reversed(decisions) if d.run_mode=="PAPER")
    engine=next(e for e in reversed(engines) if e.run_mode.value=="PAPER")
    fields=decision_fields(decision)
    print("MARKER_CONTROL",case,fields)
    readonly=[d for d in decisions if d.run_mode=="READ_ONLY"]
    assert readonly and all(not d.allowed and d.execution_blocked for d in readonly)
    assert {d.reason_code for d in readonly}=={
        "LIVE_READ_ONLY_BLOCK" if quantity==2 else "CAPITAL_PORTFOLIO_LIMIT"}
    assert decision.decision_id and outcome["reserved_after"]==0
    assert engine.capital_authority.active_reservations=={}
    assert engine.strategy_allocation_authority.active_reservations=={}
    if case=="eligible_allowed":
        assert decision.allowed and not decision.execution_blocked
        assert decision.max_position_size==1 and decision.overall_action=="ALLOW"
        assert decision.decision_code=="APPROVE" and outcome["capital_admitted"]
        # Existing helper already reached its hard pre-route barrier, proving
        # the valid comparison is not masked by an unrelated rejection.
        assert not overlays
    else:
        assert not decision.allowed and decision.max_position_size==0
        assert decision.risk_level=="BLOCKED"
        assert decision.decision_code=="REJECT" and decision.overall_action=="BLOCK"
        expected="ROSS_BLOCK_GAP_OUT_OF_RANGE" if not eligible else "CAPITAL_PORTFOLIO_LIMIT"
        assert decision.reason_code==expected
        before=deepcopy(decision_fields(decision))
        # Feed the REAL denied output to the actual execution owner, despite
        # the normal caller withholding it. No risk result/permission patched.
        reason={RunMode.PAPER:"INVALID_ORDER_QUANTITY",
            RunMode.LIVE:"Risk engine blocked this trade; no execution attempted.",
            RunMode.READ_ONLY:"LIVE_READ_ONLY_BLOCK"}[mode]
        # Owner-level mode branch controls with a fresh fixture per case;
        # not full startup/broker proof and no clearing idempotency history.
        engine.run_mode=mode
        try:
            result=engine.execute_trade(decision)
        finally:
            engine.run_mode=RunMode.PAPER
            # Snapshot before cleanup so release cannot hide a forbidden
            # reservation; still retire owned synthetic state on every exit.
            pending_capital=deepcopy(engine.capital_authority.active_reservations)
            pending_allocation=deepcopy(engine.strategy_allocation_authority.active_reservations)
            engine.capital_authority.release_reservation(reason="OFFLINE_MARKER_CONTROL_END")
            engine.strategy_allocation_authority.release_reservation(reason="OFFLINE_MARKER_CONTROL_END")
        assert pending_capital==pending_allocation=={}
        print("DENIED_EXECUTION",case,mode.value,result.status,result.rationale,
            result.attempted,result.requested_quantity,result.filled_quantity)
        assert not result.attempted and result.status=="BLOCKED"
        assert result.rationale==reason and result.filled_quantity==0
        # Existing display normalization yields 1 even for denied size0;
        # no order is constructed/sent. Preserve/report, do not repair here.
        assert result.requested_quantity==1 and decision.max_position_size==0
        assert decision_fields(decision)==before
        assert engine.capital_authority.active_reservations=={}
        assert engine.strategy_allocation_authority.active_reservations=={}
        if not eligible:
            assert len(overlays)==1
            assert overlays[0]==dict(allowed=False,size=0,execution_blocked=True,
                level="BLOCKED",reason=expected,code="APPROVE",action="ALLOW")
            assert fields["execution_blocked"] is True
        else:
            assert not overlays and fields["execution_blocked"] is True
    assert mutations()=={"place":0,"modify":0,"cancel":0}
    assert no_external_activity==[]
    # Retained failing-before invariant after all safety/cleanup evidence.
    # No xfail or suppression; now satisfied by the owner-local correction.
    if not decision.allowed:
        assert decision.execution_blocked is True, fields


@pytest.mark.parametrize("cause",["max_attempts","cooldown","short","gap","float","rvol","confidence"])
def test_each_shared_ross_rejection_caller_retains_metadata_and_blocks(cause,no_external_activity):
    from src.models.data_models import TradeIntent
    from src.strategies.ross_momentum.ross_momentum_risk_overlay import RiskContext
    overlay=RossMomentumRiskOverlay()
    intent=TradeIntent(symbol="SYNTH",direction="LONG",strategy_name="ross_momentum",
        trader_type="SCALPER",confidence=overlay.confidence_floor,
        rationale="synthetic helper compatibility",stop_loss_price=9.,take_profit_price=12.,
        gap_percent=(overlay.min_gap+overlay.max_gap)/2,
        float_millions=overlay.float_ceiling,rvol=overlay.rvol_floor)
    tick=100
    if cause=="max_attempts":
        for attempt in range(overlay.max_attempts_per_symbol):
            assert overlay.evaluate(intent,RiskContext(tick+attempt*(overlay.cooldown_ticks+1))) is None
        tick+=overlay.max_attempts_per_symbol*(overlay.cooldown_ticks+1)
    elif cause=="cooldown":
        assert overlay.evaluate(intent,RiskContext(tick)) is None
    elif cause=="short": intent.direction="SHORT"
    elif cause=="gap": intent.gap_percent=overlay.max_gap+1
    elif cause=="float": intent.float_millions=overlay.float_ceiling+1
    elif cause=="rvol": intent.rvol=overlay.rvol_floor-1
    else: intent.confidence=overlay.confidence_floor-.01
    before=deepcopy(vars(intent))
    result=overlay.evaluate(intent,RiskContext(tick))
    expected={"max_attempts":"ROSS_BLOCK_MAX_ATTEMPTS","cooldown":"ROSS_BLOCK_COOLDOWN_ACTIVE",
        "short":"ROSS_BLOCK_SHORT","gap":"ROSS_BLOCK_GAP_OUT_OF_RANGE",
        "float":"ROSS_BLOCK_FLOAT_TOO_HIGH","rvol":"ROSS_BLOCK_LOW_RVOL",
        "confidence":"ROSS_BLOCK_LOW_CONFIDENCE"}[cause]
    assert result.reason_code==expected and result.rationale
    assert not result.allowed and result.max_position_size==0
    assert result.risk_level=="BLOCKED" and result.execution_blocked
    assert (result.symbol,result.trader_type,result.strategy_name,result.direction,
        result.stop_loss_price,result.take_profit_price)==(
        intent.symbol,intent.trader_type,intent.strategy_name,intent.direction,9.,12.)
    assert vars(intent)==before
    event=overlay._event_collector._cycle_events[-1]
    assert event.event_type=="TRADE_BLOCKED"
    assert event.payload["reason_code"]==expected
    assert event.payload["human_readable_rationale"]==result.rationale
    assert no_external_activity==[] and mutations()=={"place":0,"modify":0,"cancel":0}
