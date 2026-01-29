"""Core engine state definitions for Epoch 5."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class RunMode(str, Enum):
    SIM = "SIM"
    READONLY = "READONLY"
    LIVE_1SHARE = "LIVE_1SHARE"

    @classmethod
    def from_value(cls, value: str | None) -> "RunMode":
        if not value:
            return cls.READONLY
        normalized = value.strip().upper()
        if normalized in {"LIVE_1SHARE", "LIVE-1SHARE", "LIVE_MICRO", "LIVE_ONE_SHARE"}:
            return cls.LIVE_1SHARE
        if normalized in {"READONLY", "READ_ONLY", "LIVE_READ_ONLY", "LIVE_READONLY"}:
            return cls.READONLY
        if normalized in {"SIM", "SIMULATION"}:
            return cls.SIM
        raise ValueError(f"Unknown run mode: {value}")


class SessionState(str, Enum):
    PRE = "PRE"
    REG = "REG"
    AFTER = "AFTER"


def resolve_session_state(now: datetime | None = None) -> SessionState:
    moment = now or datetime.now(timezone.utc)
    hour = moment.hour + moment.minute / 60.0
    if 12.0 <= hour < 14.0:
        return SessionState.PRE
    if 14.0 <= hour < 21.5:
        return SessionState.REG
    if 21.5 <= hour < 23.0:
        return SessionState.AFTER
    return SessionState.AFTER


@dataclass(frozen=True)
class CycleContext:
    cycle_id: int
    mode: RunMode
    session: SessionState
    timestamp: str
