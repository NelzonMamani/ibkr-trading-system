"""Health state tracking for the orchestrator."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class HealthStatus(str, Enum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class HealthSnapshot:
    status: HealthStatus
    reasons: List[str] = field(default_factory=list)


def evaluate_health(
    storage_ok: bool = True,
    data_quality_flags: List[str] | None = None,
    critical_reasons: List[str] | None = None,
) -> HealthSnapshot:
    reasons: List[str] = []
    if data_quality_flags:
        reasons.extend(sorted(set(data_quality_flags)))
    if critical_reasons:
        reasons.extend(sorted(set(critical_reasons)))
        return HealthSnapshot(status=HealthStatus.CRITICAL, reasons=reasons)
    if not storage_ok:
        reasons.append("storage_failure")
        return HealthSnapshot(status=HealthStatus.DEGRADED, reasons=reasons)
    if reasons:
        return HealthSnapshot(status=HealthStatus.DEGRADED, reasons=reasons)
    return HealthSnapshot(status=HealthStatus.OK, reasons=reasons)
