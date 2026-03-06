from datetime import datetime, timezone

from src.scanner.session_pct_change import resolve_market_session_context


def test_resolve_market_session_phase_rth_open_mid_late() -> None:
    open_ctx = resolve_market_session_context(datetime(2025, 1, 6, 14, 45, tzinfo=timezone.utc))
    mid_ctx = resolve_market_session_context(datetime(2025, 1, 6, 16, 30, tzinfo=timezone.utc))
    late_ctx = resolve_market_session_context(datetime(2025, 1, 6, 20, 0, tzinfo=timezone.utc))

    assert open_ctx.coarse == "RTH"
    assert open_ctx.phase == "RTH_OPEN"
    assert mid_ctx.phase == "RTH_MID"
    assert late_ctx.phase == "RTH_LATE"


def test_resolve_market_session_phase_weekend() -> None:
    ctx = resolve_market_session_context(datetime(2025, 1, 4, 15, 0, tzinfo=timezone.utc))
    assert ctx.coarse == "CLOSED"
    assert ctx.phase == "WEEKEND"
