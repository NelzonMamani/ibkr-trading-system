from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.config.runtime_config import RunMode


@dataclass(slots=True)
class EntryBlockReason:
    source: str
    reason_code: str
    severity: str
    message: str


@dataclass(slots=True)
class EntryAdmissionVerdict:
    entries_allowed: bool
    hard_blocked: bool
    reasons: list[EntryBlockReason] = field(default_factory=list)
    rationale: str = "entries_allowed"


def _is_truthy_flag(verdict: Any, key: str) -> bool:
    if verdict is None:
        return False
    if isinstance(verdict, dict):
        return bool(verdict.get(key, False))
    return bool(getattr(verdict, key, False))


def evaluate_entry_admission(
    *,
    run_mode: RunMode,
    position_truth_verdict: Any,
    fill_authority_verdict: Any,
    lifecycle_authority_verdict: Any,
) -> EntryAdmissionVerdict:
    reasons: list[EntryBlockReason] = []

    if run_mode == RunMode.READ_ONLY:
        reasons.append(
            EntryBlockReason(
                source="RUN_MODE",
                reason_code="READ_ONLY_MODE",
                severity="CRITICAL",
                message="READ_ONLY mode disallows entry execution.",
            )
        )

    if run_mode in {RunMode.PAPER, RunMode.LIVE, RunMode.READ_ONLY}:
        if _is_truthy_flag(position_truth_verdict, "block_new_entries"):
            reasons.append(
                EntryBlockReason(
                    source="POSITION_TRUTH",
                    reason_code="POSITION_TRUTH_BLOCK_NEW_ENTRIES",
                    severity="CRITICAL",
                    message="Position truth authority blocked new entries.",
                )
            )
        if _is_truthy_flag(fill_authority_verdict, "execution_stalled"):
            reasons.append(
                EntryBlockReason(
                    source="FILL_AUTHORITY",
                    reason_code="EXECUTION_STALLED",
                    severity="CRITICAL",
                    message="Fill authority detected stalled execution.",
                )
            )
        if _is_truthy_flag(lifecycle_authority_verdict, "block_new_entries"):
            reasons.append(
                EntryBlockReason(
                    source="LIFECYCLE_AUTHORITY",
                    reason_code="LIFECYCLE_BLOCK_NEW_ENTRIES",
                    severity="CRITICAL",
                    message="Lifecycle authority blocked new entries.",
                )
            )

    hard_blocked = any(reason.severity == "CRITICAL" for reason in reasons)
    entries_allowed = not hard_blocked

    if entries_allowed:
        rationale = "entries_allowed"
    else:
        reason_codes = {reason.reason_code for reason in reasons}
        if reason_codes == {"READ_ONLY_MODE"}:
            rationale = "blocked_by_read_only_mode"
        elif len(reason_codes) > 1:
            rationale = "blocked_by_multiple_authorities"
        elif "POSITION_TRUTH_BLOCK_NEW_ENTRIES" in reason_codes:
            rationale = "blocked_by_position_truth"
        elif "EXECUTION_STALLED" in reason_codes:
            rationale = "blocked_by_fill_authority"
        elif "LIFECYCLE_BLOCK_NEW_ENTRIES" in reason_codes:
            rationale = "blocked_by_lifecycle_authority"
        else:
            rationale = "blocked_by_multiple_authorities"

    return EntryAdmissionVerdict(
        entries_allowed=entries_allowed,
        hard_blocked=hard_blocked,
        reasons=reasons,
        rationale=rationale,
    )
