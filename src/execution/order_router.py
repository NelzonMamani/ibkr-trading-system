"""Mode-safe order routing for Epoch 5."""
from __future__ import annotations

from typing import List

from src.execution.order_tracker import ExecutionEvent, ExecutionSummary, summarize_events
from src.risk.limits import RiskDecision, RiskDecisionType
from src.strategies.strategy_contracts import TradeIntent
from src.utils.logging import normalize_mode_label


def route_orders(
    intents: List[TradeIntent],
    decisions: List[RiskDecision],
    mode_label: str,
) -> List[ExecutionEvent]:
    mode = normalize_mode_label(mode_label)
    events: List[ExecutionEvent] = []

    for intent, decision in zip(intents, decisions):
        if decision.decision != RiskDecisionType.ALLOW:
            events.append(
                ExecutionEvent(
                    symbol=intent.symbol,
                    event_type="BLOCKED",
                    detail=f"Risk blocked: {decision.triggered_rules}",
                )
            )
            continue

        if mode in {"READONLY", "SIM"}:
            events.append(
                ExecutionEvent(
                    symbol=intent.symbol,
                    event_type="WOULD_PLACE",
                    detail=f"Would place order for {intent.symbol}",
                )
            )
            continue

        events.append(
            ExecutionEvent(
                symbol=intent.symbol,
                event_type="SUBMITTED",
                detail=f"Submitted order for {intent.symbol}",
            )
        )

    summary = summarize_events(events)
    if mode in {"READONLY", "SIM"}:
        print(
            "[EXECUTION] READONLY/SIM summary: "
            f"would_place={summary.would_place} blocked={summary.blocked}"
        )
    else:
        print(
            "[EXECUTION] LIVE summary: "
            f"submitted={summary.submitted} blocked={summary.blocked}"
        )
    for event in events:
        if event.event_type == "WOULD_PLACE":
            print(f"[EXECUTION] WOULD PLACE {event.symbol}")
        elif event.event_type == "SUBMITTED":
            print(f"[EXECUTION] SUBMITTED {event.symbol}")
        else:
            print(f"[EXECUTION] BLOCKED {event.symbol}")
    return events
