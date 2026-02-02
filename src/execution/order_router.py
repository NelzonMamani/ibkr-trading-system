"""Execution router enforcing mode law for Epoch 5."""

from __future__ import annotations

from typing import List

from src.core_engine.events import ExecutionEvent, RiskDecisionRecord
from src.core_engine.state import RunMode


def execute_intents(
    mode: RunMode,
    decisions: List[RiskDecisionRecord],
) -> List[ExecutionEvent]:
    events: List[ExecutionEvent] = []
    for decision in decisions:
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
