from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RecoveryAction:
    symbol: str
    action_type: str
    severity: str
    requires_manual_intervention: bool
    safe_to_auto_apply: bool
    rationale: str


@dataclass
class RecoveryPlan:
    actions: list[RecoveryAction]
    critical_count: int
    warning_count: int
    auto_actions_count: int
    manual_required_count: int
    summary: str


def _extract(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _action(symbol: str, action_type: str, severity: str, *, manual: bool, auto: bool, rationale: str) -> RecoveryAction:
    return RecoveryAction(
        symbol=str(symbol or "UNKNOWN").upper(),
        action_type=action_type,
        severity=severity,
        requires_manual_intervention=manual,
        safe_to_auto_apply=auto,
        rationale=rationale,
    )


def build_recovery_plan(position_snapshot: Any, position_verdict: Any, fill_verdict: Any) -> RecoveryPlan:
    actions: list[RecoveryAction] = []

    mismatches = list(_extract(position_snapshot, "mismatches", []) or [])
    for mismatch in mismatches:
        mismatch_type = str(_extract(mismatch, "mismatch_type", "") or "").upper()
        symbol = str(_extract(mismatch, "symbol", "UNKNOWN") or "UNKNOWN").upper()
        if mismatch_type == "BROKER_ONLY_POSITION":
            actions.append(
                _action(
                    symbol,
                    "ATTACH_BROKER_POSITION",
                    "WARNING",
                    manual=False,
                    auto=True,
                    rationale="Broker is source of truth; attach broker-reported position into runtime state.",
                )
            )
        elif mismatch_type == "SYSTEM_ONLY_POSITION":
            actions.append(
                _action(
                    symbol,
                    "MARK_SYSTEM_POSITION_INVALID",
                    "CRITICAL",
                    manual=True,
                    auto=False,
                    rationale="System tracks position absent at broker; manual investigation required.",
                )
            )
        elif mismatch_type == "QUANTITY_MISMATCH":
            actions.append(
                _action(
                    symbol,
                    "FLAG_QUANTITY_MISMATCH",
                    "WARNING",
                    manual=True,
                    auto=False,
                    rationale="Broker and runtime quantities differ; cannot auto-correct without execution proof.",
                )
            )

    stalled = bool(_extract(fill_verdict, "execution_stalled", False))
    stalled_symbols = list(_extract(fill_verdict, "stalled_symbols", []) or [])
    if stalled and not stalled_symbols:
        stalled_symbols = ["UNKNOWN"]
    for symbol in stalled_symbols:
        actions.append(
            _action(
                symbol,
                "FLAG_EXECUTION_STALLED",
                "CRITICAL",
                manual=True,
                auto=False,
                rationale="Order lifecycle appears stalled without authoritative execDetails progression.",
            )
        )

    if not actions and bool(_extract(position_verdict, "healthy", False)) and not stalled:
        actions.append(
            _action(
                "SYSTEM",
                "NO_ACTION",
                "INFO",
                manual=False,
                auto=False,
                rationale="No mismatches detected; recovery intervention not required.",
            )
        )

    critical_count = sum(1 for action in actions if action.severity.upper() == "CRITICAL")
    warning_count = sum(1 for action in actions if action.severity.upper() == "WARNING")
    auto_actions_count = sum(1 for action in actions if action.safe_to_auto_apply)
    manual_required_count = sum(1 for action in actions if action.requires_manual_intervention)
    blocked = manual_required_count > 0

    print(
        "[RECOVERY][PLAN] "
        f"actions={len(actions)} critical={critical_count} warning={warning_count}"
    )

    summary = (
        f"auto_applied={auto_actions_count} manual_required={manual_required_count} blocked={blocked}"
    )
    return RecoveryPlan(
        actions=actions,
        critical_count=critical_count,
        warning_count=warning_count,
        auto_actions_count=auto_actions_count,
        manual_required_count=manual_required_count,
        summary=summary,
    )


def apply_recovery_actions(plan: RecoveryPlan, orchestrator: Any) -> None:
    auto_applied = 0
    for action in plan.actions:
        if action.action_type == "ATTACH_BROKER_POSITION" and action.safe_to_auto_apply:
            if hasattr(orchestrator, "attach_broker_position_from_recovery"):
                orchestrator.attach_broker_position_from_recovery(symbol=action.symbol)
            print(f"[RECOVERY][ACTION] symbol={action.symbol} type=ATTACH_BROKER_POSITION")
            auto_applied += 1
            continue

        if action.action_type != "NO_ACTION":
            print(f"[RECOVERY][MANUAL_REQUIRED] symbol={action.symbol} reason={action.rationale}")

    print(
        "[RECOVERY][SUMMARY] "
        f"auto_applied={auto_applied} manual_required={plan.manual_required_count} blocked={plan.manual_required_count > 0}"
    )
