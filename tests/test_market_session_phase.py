from datetime import datetime, timezone

from src.utils.time_utils import market_session_phase, to_ny_time, to_uk_time


def test_market_session_phase_us_dst_transition() -> None:
    # After US DST starts (2024-03-10), 14:00 UTC == 10:00 ET (OPENING_0_30/MORNING).
    now = datetime(2024, 3, 11, 14, 0, tzinfo=timezone.utc)
    assert market_session_phase(now) == "MORNING"

    # Before US DST starts, 14:00 UTC == 09:00 ET (PREMARKET).
    before_dst = datetime(2024, 3, 8, 14, 0, tzinfo=timezone.utc)
    assert market_session_phase(before_dst) == "PREMARKET"


def test_market_session_phase_uk_dst_transition() -> None:
    # UK DST starts later than US; ensure NY session still correct.
    now = datetime(2024, 3, 29, 14, 0, tzinfo=timezone.utc)
    assert market_session_phase(now) == "MORNING"

    # After UK DST starts, NY session remains the same, UK time shifts.
    after_uk_dst = datetime(2024, 4, 1, 14, 0, tzinfo=timezone.utc)
    assert market_session_phase(after_uk_dst) == "MORNING"


def test_time_conversions_include_uk_and_ny() -> None:
    sample = datetime(2024, 4, 1, 14, 0, tzinfo=timezone.utc)
    ny_time = to_ny_time(sample)
    uk_time = to_uk_time(sample)
    assert ny_time.tzinfo is not None
    assert uk_time.tzinfo is not None
