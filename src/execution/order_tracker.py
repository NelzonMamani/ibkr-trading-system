"""Execution event tracking for Epoch 5."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class ExecutionEvent:
    symbol: str
    event_type: str
    detail: str


@dataclass(frozen=True)
class ExecutionSummary:
    intents_received: int
    allowed: int
    would_place: int
    submitted: int
    blocked: int


def summarize_events(events: List[ExecutionEvent]) -> ExecutionSummary:
    submitted = sum(1 for event in events if event.event_type == "SUBMITTED")
    would_place = sum(1 for event in events if event.event_type == "WOULD_PLACE")
    blocked = sum(1 for event in events if event.event_type == "BLOCKED")
    allowed = would_place + submitted
    return ExecutionSummary(
        intents_received=len(events),
        allowed=allowed,
        would_place=would_place,
        submitted=submitted,
        blocked=blocked,
    )
