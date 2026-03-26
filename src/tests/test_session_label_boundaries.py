from datetime import datetime
from zoneinfo import ZoneInfo

from src.core_engine.state import SessionState, resolve_session_state
from src.scanner.session_pct_change import resolve_market_session_context


def _ny_dt(hour: int, minute: int) -> datetime:
    return datetime(2026, 3, 9, hour, minute, tzinfo=ZoneInfo("America/New_York"))


def test_core_session_state_boundaries() -> None:
    assert resolve_session_state(_ny_dt(3, 59)) == SessionState.OVERNIGHT
    assert resolve_session_state(_ny_dt(4, 0)) == SessionState.PRE
    assert resolve_session_state(_ny_dt(9, 29)) == SessionState.PRE
    assert resolve_session_state(_ny_dt(9, 30)) == SessionState.REG
    assert resolve_session_state(_ny_dt(15, 59)) == SessionState.REG
    assert resolve_session_state(_ny_dt(16, 0)) == SessionState.AFTER
    assert resolve_session_state(_ny_dt(19, 59)) == SessionState.AFTER
    assert resolve_session_state(_ny_dt(20, 0)) == SessionState.OVERNIGHT


def test_scanner_session_context_boundaries() -> None:
    assert resolve_market_session_context(_ny_dt(3, 59)).phase == "CLOSED"
    assert resolve_market_session_context(_ny_dt(4, 0)).phase == "PRE"
    assert resolve_market_session_context(_ny_dt(9, 29)).phase == "PRE"
    assert resolve_market_session_context(_ny_dt(9, 30)).phase == "RTH"
    assert resolve_market_session_context(_ny_dt(15, 59)).phase == "RTH"
    assert resolve_market_session_context(_ny_dt(16, 0)).phase == "AH"
    assert resolve_market_session_context(_ny_dt(19, 59)).phase == "AH"
    assert resolve_market_session_context(_ny_dt(20, 0)).phase == "CLOSED"
