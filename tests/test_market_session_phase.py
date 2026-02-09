from datetime import date, datetime, time, timezone

from src.config.config_resolver import set_config_overrides

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


def test_market_session_phase_respects_holidays_and_half_days() -> None:
    set_config_overrides(
        {
            "MARKET_HOLIDAYS": {date(2024, 1, 1)},
            "MARKET_HALF_DAYS": {date(2024, 7, 3)},
            "MARKET_EARLY_CLOSE_TIME": time(13, 0),
        }
    )
    try:
        holiday = datetime(2024, 1, 1, 15, 0, tzinfo=timezone.utc)
        assert market_session_phase(holiday) == "CLOSED"

        half_day = datetime(2024, 7, 3, 18, 0, tzinfo=timezone.utc)
        assert market_session_phase(half_day) == "CLOSED"
    finally:
        set_config_overrides(None)
