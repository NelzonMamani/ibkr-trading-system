from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.core.time.session_adapter import resolve_canonical_session


NY_TZ = ZoneInfo("America/New_York")


def dt(hour: int, minute: int = 0) -> datetime:
    ny_time = datetime(2026, 1, 15, hour, minute, tzinfo=NY_TZ)
    return ny_time.astimezone(timezone.utc)


def test_session_adapter_mapping() -> None:
    assert resolve_canonical_session(dt(5, 0), regime="NORMAL") == "PRE"
    assert resolve_canonical_session(dt(9, 45), regime="NORMAL") == "RTH_OPEN"
    assert resolve_canonical_session(dt(12, 0), regime="NORMAL") == "RTH_MID"
    assert resolve_canonical_session(dt(15, 45), regime="NORMAL") == "RTH_LATE"
    assert resolve_canonical_session(dt(17, 0), regime="NORMAL") == "AH"
