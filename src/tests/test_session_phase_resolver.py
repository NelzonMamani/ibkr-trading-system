from datetime import datetime, timezone

from src.scanner import session_pct_change
from src.scanner.session_pct_change import resolve_market_session_context


def test_resolve_market_session_phase_rth_open_mid_late() -> None:
    open_ctx = resolve_market_session_context(datetime(2025, 1, 6, 14, 45, tzinfo=timezone.utc))
    mid_ctx = resolve_market_session_context(datetime(2025, 1, 6, 16, 30, tzinfo=timezone.utc))
    late_ctx = resolve_market_session_context(datetime(2025, 1, 6, 20, 0, tzinfo=timezone.utc))

    assert open_ctx.coarse == "RTH"
    assert open_ctx.phase == "RTH"
    assert mid_ctx.phase == "RTH"
    assert late_ctx.phase == "RTH"


def test_resolve_market_session_phase_weekend() -> None:
    ctx = resolve_market_session_context(datetime(2025, 1, 4, 15, 0, tzinfo=timezone.utc))
    assert ctx.coarse == "WEEKEND"
    assert ctx.phase == "WEEKEND"


def test_resolve_market_session_phase_pre_from_required_timestamp() -> None:
    ctx = resolve_market_session_context(datetime(2024, 1, 4, 9, 42, tzinfo=timezone.utc))
    assert ctx.phase == "PRE"


def test_resolve_market_session_phase_paper_mode_uses_time_based_logic(monkeypatch) -> None:
    original_get_config = session_pct_change.get_config

    def _fake_get_config(name: str):
        if name in {"RUN_MODE_EFFECTIVE", "RUN_MODE"}:
            return "PAPER"
        return original_get_config(name)

    monkeypatch.setattr(session_pct_change, "get_config", _fake_get_config)
    ctx = resolve_market_session_context(datetime(2024, 1, 4, 9, 42, tzinfo=timezone.utc))
    assert ctx.phase == "PRE"
