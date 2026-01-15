"""Health state machine for Epoch 5."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class HealthStatus(str, Enum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"


@dataclass
class HealthSnapshot:
    status: HealthStatus
    triggers: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if not self.triggers:
            return self.status.value
        return f"{self.status.value} ({', '.join(self.triggers)})"


def combine_health(triggers: Iterable[tuple[HealthStatus, str]]) -> HealthSnapshot:
    status = HealthStatus.OK
    reasons: list[str] = []
    for severity, reason in triggers:
        reasons.append(reason)
        if severity == HealthStatus.CRITICAL:
            status = HealthStatus.CRITICAL
        elif severity == HealthStatus.DEGRADED and status == HealthStatus.OK:
            status = HealthStatus.DEGRADED
    return HealthSnapshot(status=status, triggers=reasons)
