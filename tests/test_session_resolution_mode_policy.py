from datetime import datetime, timezone

import pytest

from src.config.config_resolver import set_config_overrides
from src.scanner.session_pct_change import resolve_market_session_context


@pytest.fixture(autouse=True)
def _clear_overrides_after_test():
    yield
    set_config_overrides(None)


@pytest.mark.parametrize("run_mode", ["SIM", "PAPER", "READ_ONLY"])
@pytest.mark.parametrize(
    ("timestamp_utc", "expected_phase"),
    [
        (datetime(2024, 1, 3, 12, 0, tzinfo=timezone.utc), "PRE"),
        (datetime(2024, 1, 3, 15, 0, tzinfo=timezone.utc), "RTH_OPEN"),
        (datetime(2024, 1, 3, 22, 0, tzinfo=timezone.utc), "AH"),
        (datetime(2024, 1, 3, 2, 0, tzinfo=timezone.utc), "CLOSED"),
        (datetime(2024, 1, 6, 17, 0, tzinfo=timezone.utc), "WEEKEND"),
    ],
)
def test_nonlive_modes_use_time_based_session_resolution(
    run_mode: str,
    timestamp_utc: datetime,
    expected_phase: str,
) -> None:
    set_config_overrides({"RUN_MODE": run_mode, "RUN_MODE_EFFECTIVE": run_mode})

    session = resolve_market_session_context(timestamp_utc)

    assert session.phase == expected_phase


def test_live_mode_uses_same_time_based_session_resolution() -> None:
    set_config_overrides({"RUN_MODE": "LIVE", "RUN_MODE_EFFECTIVE": "LIVE"})

    session = resolve_market_session_context(datetime(2024, 1, 6, 17, 0, tzinfo=timezone.utc))

    assert session.phase == "WEEKEND"
