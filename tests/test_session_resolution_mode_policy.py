from datetime import datetime, timezone

import pytest

from src.config.config_resolver import set_config_overrides
from src.core.time.calendar_session import resolve_calendar_session
from src.scanner.session_pct_change import resolve_market_session_context


@pytest.fixture(autouse=True)
def _clear_overrides_after_test():
    yield
    set_config_overrides(None)


def test_nonlive_sim_mode_uses_clock_session_logic() -> None:
    set_config_overrides({"RUN_MODE": "SIM", "RUN_MODE_EFFECTIVE": "SIM"})

    session = resolve_market_session_context(datetime(2024, 1, 6, 17, 0, tzinfo=timezone.utc))

    assert session.coarse == "WEEKEND"
    assert session.phase == "WEEKEND"
    assert session.source == "TIME"
    assert resolve_calendar_session(datetime(2024, 1, 6, 17, 0, tzinfo=timezone.utc)) == "WEEKEND"


def test_nonlive_paper_mode_uses_clock_session_logic() -> None:
    set_config_overrides({"RUN_MODE": "PAPER", "RUN_MODE_EFFECTIVE": "PAPER"})

    session = resolve_market_session_context(datetime(2024, 1, 1, 7, 0, tzinfo=timezone.utc))

    assert session.coarse == "OVN"
    assert session.phase == "OVN"
    assert session.source == "TIME"
    assert resolve_calendar_session(datetime(2024, 1, 1, 7, 0, tzinfo=timezone.utc)) == "OVN"


def test_nonlive_read_only_mode_uses_clock_session_logic() -> None:
    set_config_overrides({"RUN_MODE": "READ_ONLY", "RUN_MODE_EFFECTIVE": "READ_ONLY"})

    session = resolve_market_session_context(datetime(2024, 1, 1, 7, 0, tzinfo=timezone.utc))

    assert session.coarse == "OVN"
    assert session.phase == "OVN"
    assert session.source == "TIME"


def test_live_mode_still_uses_real_market_session_logic() -> None:
    set_config_overrides({"RUN_MODE": "LIVE", "RUN_MODE_EFFECTIVE": "LIVE"})

    session = resolve_market_session_context(datetime(2024, 1, 6, 17, 0, tzinfo=timezone.utc))

    assert session.coarse == "WEEKEND"
    assert session.phase == "WEEKEND"
    assert session.source == "TIME"
