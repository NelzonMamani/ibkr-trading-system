"""
Central teaching-focused configuration for the trading system.

This module captures the baseline defaults we expect to use across the
application. Values are intentionally safe and annotated to explain their
purpose to new contributors during Phase 4.
"""

from datetime import datetime, time

# Runtime mode defaults to SIM to keep all behaviour safe by default. The
# runtime_config module still owns authoritative runtime selection, but this
# value provides a simple, central reference for teaching purposes.
RUN_MODE: str = "SIM"

# Sleep interval (in seconds) between orchestrator cycles. Kept short for
# demonstration while remaining safe to run locally.
CYCLE_SLEEP_SECONDS: int = 3

# Market sessions considered "open" for educational checks. The orchestrator
# does not yet act on these, but they show how we might gate behaviour.
ACTIVE_SESSIONS = ["PRE", "REGULAR", "AFTER"]


def get_current_market_session() -> str:
    """Return a simple market session indicator based on local time.

    This teaching helper uses broad time windows to map to common US equity
    sessions:
    - PRE:    04:00 - 09:30 local
    - REGULAR:09:30 - 16:00 local
    - AFTER:  16:00 - 20:00 local
    - CLOSED: all other times
    """

    now = datetime.now().time()

    pre_start = time(4, 0)
    regular_start = time(9, 30)
    regular_end = time(16, 0)
    after_end = time(20, 0)

    if pre_start <= now < regular_start:
        return "PRE"
    if regular_start <= now < regular_end:
        return "REGULAR"
    if regular_end <= now < after_end:
        return "AFTER"
    return "CLOSED"
