"""Core engine state definitions for Epoch 5."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from enum import Enum

from zoneinfo import ZoneInfo


class RunMode(str, Enum):
    SIM = "SIM"
    READ_ONLY = "READ_ONLY"
    PAPER = "PAPER"
    LIVE = "LIVE"

    @classmethod
    def from_value(cls, value: str | None) -> "RunMode":
        if not value:
            raise ValueError("RUN_MODE is required and cannot be empty")
        normalized = value.strip().upper()
        if normalized in {"LIVE_1SHARE", "LIVE-1SHARE", "LIVE_MICRO", "LIVE_ONE_SHARE"}:
            return cls.LIVE
        if normalized in {"READONLY", "READ_ONLY", "LIVE_READ_ONLY", "LIVE_READONLY"}:
            return cls.READ_ONLY
        if normalized in {"PAPER"}:
            return cls.PAPER
        if normalized in {"LIVE"}:
            return cls.LIVE
        if normalized in {"SIM", "SIMULATION"}:
            return cls.SIM
        raise ValueError(f"Unknown run mode: {value}")


class SessionState(str, Enum):
    PRE = "PRE"
    REG = "REG"
    AFTER = "AFTER"
    OVERNIGHT = "OVERNIGHT"


NY_TZ = ZoneInfo("America/New_York")


def resolve_session_state(now: datetime | None = None) -> SessionState:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    ny_time = moment.astimezone(NY_TZ).time()

    if time(4, 0) <= ny_time < time(9, 30):
        return SessionState.PRE
    if time(9, 30) <= ny_time < time(16, 0):
        return SessionState.REG
    if time(16, 0) <= ny_time < time(20, 0):
        return SessionState.AFTER
    return SessionState.OVERNIGHT


@dataclass(frozen=True)
class CycleContext:
    cycle_id: int
    mode: RunMode
    session: SessionState
    timestamp: str
