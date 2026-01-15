"""Session-aware setup gating rules for Ross Momentum."""
from __future__ import annotations

from src.strategies.strategy_contracts import SessionContext


def allow_session_trade(session: SessionContext, allow_after_hours: bool) -> bool:
    if session == SessionContext.AFTER:
        return allow_after_hours
    return True
