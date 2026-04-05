from __future__ import annotations

from datetime import datetime, time

from src.utils.time_utils import to_ny_time


def resolve_calendar_session(now: datetime) -> str:
    ny_now = to_ny_time(now)
    t = ny_now.time()
    weekday = ny_now.weekday()  # 0=Mon, 6=Sun

    if weekday >= 5:
        return "WEEKEND"

    if t < time(4, 0):
        return "OVN"

    if time(4, 0) <= t < time(9, 30):
        return "PRE"

    if time(9, 30) <= t < time(16, 0):
        return "RTH"

    if time(16, 0) <= t < time(20, 0):
        return "AH"

    return "OVN"

