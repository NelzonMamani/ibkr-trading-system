"""
System-level configuration (logging, sessions, persistence).
"""

from __future__ import annotations
import os
from datetime import date, datetime, time


# Sleep interval (in seconds) between orchestrator cycles. Kept short for
# demonstration while remaining safe to run locally.
CYCLE_SLEEP_SECONDS: int = 3

# Market sessions considered "open" for educational checks. The orchestrator
# does not yet act on these, but they show how we might gate behaviour.
ACTIVE_SESSIONS = ["PRE", "REGULAR", "AFTER"]


def _parse_dates(raw: str) -> set[date]:
    dates: set[date] = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            dates.add(datetime.strptime(item, "%Y-%m-%d").date())
        except ValueError:
            print(f"[SESSION] Invalid calendar date '{item}' (expected YYYY-MM-DD)")
    return dates


def _get_market_holidays() -> set[date]:
    raw = (os.getenv("MARKET_HOLIDAYS") or "").strip()
    return _parse_dates(raw)


def _get_market_half_days() -> set[date]:
    raw = (os.getenv("MARKET_HALF_DAYS") or "").strip()
    return _parse_dates(raw)


def _get_early_close_time(default: time = time(13, 0)) -> time:
    raw = (os.getenv("MARKET_EARLY_CLOSE_TIME") or "").strip()
    if not raw:
        return default
    try:
        hour, minute = raw.split(":")
        return time(int(hour), int(minute))
    except ValueError:
        print(f"[SESSION] Invalid MARKET_EARLY_CLOSE_TIME='{raw}' (expected HH:MM)")
        return default


def get_current_market_session(now: datetime | None = None) -> str:
    """Return a simple market session indicator based on local time.

    This teaching helper uses broad time windows to map to common US equity
    sessions:
    - PRE:    04:00 - 09:30 local
    - REGULAR:09:30 - 16:00 local
    - AFTER:  16:00 - 20:00 local
    - CLOSED: all other times
    """

    current_dt = now or datetime.now()
    today = current_dt.date()
    now_time = current_dt.time()

    holidays = _get_market_holidays()
    half_days = _get_market_half_days()
    if today in holidays:
        return "CLOSED"

    pre_start = time(4, 0)
    regular_start = time(9, 30)
    regular_end = time(16, 0)
    after_end = time(20, 0)
    if today in half_days:
        early_close = _get_early_close_time()
        regular_end = early_close
        after_end = early_close

    if pre_start <= now_time < regular_start:
        return "PRE"
    if regular_start <= now_time < regular_end:
        return "REGULAR"
    if regular_end <= now_time < after_end:
        return "AFTER"
    return "CLOSED"
