"""Execution router enforcing mode law for Epoch 5."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from src.core_engine.events import ExecutionEvent, RiskDecisionRecord
from src.core_engine.state import RunMode


@dataclass(frozen=True)
class RouterAccountSnapshot:
    available_funds: float


def execute_intents(
    mode: RunMode,
    decisions: List[RiskDecisionRecord],
) -> List[ExecutionEvent]:
    events: List[ExecutionEvent] = []
    for decision in decisions:
        account = RouterAccountSnapshot(available_funds=float(decision.available_funds))
        order_value = float(decision.order_value)
        risk_allowed = bool(decision.risk_allowed)
        print(
            f"[CAPITAL] available_funds={account.available_funds} "
            f"order_value={order_value} "
            f"risk_allowed={risk_allowed}"
        )
        if mode in {RunMode.SIM, RunMode.READ_ONLY}:
            action = "WOULD_PLACE"
            detail = f"mode={mode.value}; decision={decision.decision}"
        elif decision.decision == "ALLOW":
            action = "SUBMITTED"
            detail = "submitted 1-share order"
        elif decision.decision == "ALLOW_WITH_CONSTRAINTS":
            action = "SUBMITTED"
            detail = f"submitted with constraints={decision.constraints}"
        else:
            action = "SKIPPED"
            detail = f"decision={decision.decision}"
        events.append(
            ExecutionEvent(
                symbol=decision.symbol,
                intent_id=decision.intent_id,
                action=action,
                detail=detail,
            )
        )
    return events
