"""Time utilities for deterministic session labeling."""

from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from src.core_engine.state import SessionState
from src.config.config_resolver import get_config

NY_TZ = ZoneInfo("America/New_York")
UK_TZ = ZoneInfo("Europe/London")


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


def to_ny_time(now_utc: datetime) -> datetime:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(NY_TZ)


def to_uk_time(now_utc: datetime) -> datetime:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(UK_TZ)


def market_session_phase(now_utc: datetime) -> str:
    """
    Determine US market session phase using America/New_York as authority.

    Phases: PREMARKET, OPENING_0_30, MORNING, MIDDAY, LATE, POWER_HOUR, CLOSED.
    """

    ny_time = to_ny_time(now_utc)
    if ny_time.weekday() >= 5:
        return "CLOSED"
    holidays = set(get_config("MARKET_HOLIDAYS"))
    half_days = set(get_config("MARKET_HALF_DAYS"))
    if ny_time.date() in holidays:
        return "CLOSED"

    ny_t = ny_time.time()
    pre_start = time(4, 0)
    open_start = time(9, 30)
    opening_end = time(10, 0)
    morning_end = time(12, 0)
    midday_end = time(14, 30)
    late_end = time(15, 0)
    close_time = time(16, 0)
    if ny_time.date() in half_days:
        close_time = get_config("MARKET_EARLY_CLOSE_TIME")

    if ny_t < pre_start or ny_t >= close_time:
        return "CLOSED"
    if pre_start <= ny_t < open_start:
        return "PREMARKET"
    if open_start <= ny_t < opening_end:
        return "OPENING_0_30"
    if opening_end <= ny_t < morning_end:
        return "MORNING"
    if morning_end <= ny_t < midday_end:
        return "MIDDAY"
    if midday_end <= ny_t < late_end:
        return "LATE"
    return "POWER_HOUR"
