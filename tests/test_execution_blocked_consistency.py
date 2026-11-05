"""Investigation only: real owners, synthetic facts, no operational dispatch.

One unmarked red invariant intentionally preserves the demonstrated marker gap.
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
            assert overlays[0]==dict(allowed=False,size=0,execution_blocked=False,
                level="BLOCKED",reason=expected,code="APPROVE",action="ALLOW")
            assert fields["execution_blocked"] is False  # factual before state
        else:
            assert not overlays and fields["execution_blocked"] is True
    assert mutations()=={"place":0,"modify":0,"cancel":0}
    assert no_external_activity==[]
    # Deliberately failing-before invariant after all safety/cleanup evidence.
    # No xfail, no production repair, no silent acceptance of inconsistent data.
    if not decision.allowed:
        assert decision.execution_blocked is True, fields
