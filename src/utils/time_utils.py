"""Time utilities for deterministic session labeling."""

from __future__ import annotations

from datetime import datetime, timezone

from src.core_engine.state import SessionState


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def resolve_session_state(now: datetime | None = None) -> SessionState:
    moment = now or utc_now()
    hour = moment.hour + moment.minute / 60.0
    if 12.0 <= hour < 14.0:
        return SessionState.PRE
    if 14.0 <= hour < 21.5:
        return SessionState.REG
    if 21.5 <= hour < 23.0:
        return SessionState.AFTER
    return SessionState.AFTER
