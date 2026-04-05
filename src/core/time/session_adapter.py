from __future__ import annotations

from datetime import datetime, time

from src.utils.time_utils import to_ny_time


def resolve_canonical_session(now: datetime, regime: str) -> str:
    """Map runtime clock to legacy canonical session labels."""
    _ = regime  # compatibility signature; regime may inform future mappings.
    ny_now = to_ny_time(now)
    current_time = ny_now.time()

    if time(4, 0) <= current_time < time(9, 30):
        return "PRE"
    if time(9, 30) <= current_time < time(10, 30):
        return "RTH_OPEN"
    if time(10, 30) <= current_time < time(11, 30):
        return "RTH_MID"
    if time(11, 30) <= current_time < time(15, 30):
        return "RTH_MID"
    if time(15, 30) <= current_time < time(16, 0):
        return "RTH_LATE"
    if time(16, 0) <= current_time < time(20, 0):
        return "AH"

    return "CLOSED"
