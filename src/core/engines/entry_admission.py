from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from src.config.runtime_config import RunMode


@dataclass(frozen=True)
class EntryAdmissionVerdict:
    entries_allowed: bool
    hard_blocked: bool
    reasons: list[str]
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_blocked(verdict: Mapping[str, Any] | None) -> bool:
    if not verdict:
        return False
    return bool(
        verdict.get("hard_blocked")
        or verdict.get("blocked")
        or verdict.get("execution_stalled")
        or verdict.get("halted")
        or verdict.get("healthy") is False
    )


def _reason(verdict: Mapping[str, Any] | None, fallback: str) -> str:
    if not verdict:
        return fallback
    for key in ("rationale", "reason", "code", "status"):
        value = verdict.get(key)
        if value:
            return str(value)
    return fallback


def evaluate_entry_admission(
    *,
    run_mode: RunMode,
    position_truth_verdict: Mapping[str, Any] | None = None,
    fill_authority_verdict: Mapping[str, Any] | None = None,
    lifecycle_authority_verdict: Mapping[str, Any] | None = None,
) -> EntryAdmissionVerdict:
    if run_mode == RunMode.SIM:
        return EntryAdmissionVerdict(
            entries_allowed=True,
            hard_blocked=False,
            reasons=[],
            rationale="sim_mode_unrestricted",
        )

    reasons: list[str] = []

    if _is_blocked(position_truth_verdict):
        reasons.append(_reason(position_truth_verdict, "position_truth_blocked"))
    if _is_blocked(fill_authority_verdict):
        reasons.append(_reason(fill_authority_verdict, "fill_authority_blocked"))
    if _is_blocked(lifecycle_authority_verdict):
        reasons.append(_reason(lifecycle_authority_verdict, "lifecycle_authority_blocked"))

    hard_blocked = len(reasons) > 0
    return EntryAdmissionVerdict(
        entries_allowed=not hard_blocked,
        hard_blocked=hard_blocked,
        reasons=reasons,
        rationale="entry_authorities_cleared" if not hard_blocked else "entry_blocked_by_authority",
    )
