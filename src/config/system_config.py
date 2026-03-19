"""
System-level configuration (logging, sessions, persistence).
"""

from __future__ import annotations
from datetime import datetime

from src.config.config_resolver import get_config
from src.scanner.session_pct_change import resolve_market_session_label


# Sleep interval (in seconds) between orchestrator cycles.
CYCLE_SLEEP_SECONDS: int = get_config("CYCLE_SLEEP_SECONDS")

# Market sessions considered "open" for educational checks.
ACTIVE_SESSIONS = list(get_config("ACTIVE_SESSIONS"))


def get_current_market_session(now: datetime | None = None) -> str:
    """Return the canonical market session from the US/Eastern session classifier."""
    return resolve_market_session_label(now)
