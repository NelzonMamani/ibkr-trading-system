"""
System-level configuration (logging, sessions, persistence).
"""

from __future__ import annotations
from datetime import datetime, time

from src.config.config_resolver import get_config


# Sleep interval (in seconds) between orchestrator cycles.
CYCLE_SLEEP_SECONDS: int = get_config("CYCLE_SLEEP_SECONDS")

# Market sessions considered "open" for educational checks.
ACTIVE_SESSIONS = list(get_config("ACTIVE_SESSIONS"))


def get_current_market_session(now: datetime | None = None) -> str:
    """Return a simple market session indicator based on local time."""

    current_dt = now or datetime.now()
    today = current_dt.date()
    now_time = current_dt.time()

    holidays = set(get_config("MARKET_HOLIDAYS"))
    half_days = set(get_config("MARKET_HALF_DAYS"))
    if today in holidays:
        return "CLOSED"

    windows = get_config("MARKET_SESSION_WINDOWS_LOCAL")
    pre_start: time = windows["PRE_START"]
    regular_start: time = windows["REGULAR_START"]
    regular_end: time = windows["REGULAR_END"]
    after_end: time = windows["AFTER_END"]

    if today in half_days:
        early_close = get_config("MARKET_EARLY_CLOSE_TIME")
        regular_end = early_close
        after_end = early_close

    if pre_start <= now_time < regular_start:
        return "PRE"
    if regular_start <= now_time < regular_end:
        return "REGULAR"
    if regular_end <= now_time < after_end:
        return "AFTER"
    return "CLOSED"
