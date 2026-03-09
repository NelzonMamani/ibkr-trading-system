from datetime import datetime, timezone

from src.scanner.session_pct_change import (
    compute_phase_aware_rvol,
    normalize_session_label,
    resolve_market_session_context,
)


def test_phase_aware_rvol_differs_by_phase() -> None:
    pre = compute_phase_aware_rvol(session_label="PRE", session_volume=50_000, avg_volume_20d=1_000_000)
    rth_open = compute_phase_aware_rvol(session_label="RTH_OPEN", session_volume=50_000, avg_volume_20d=1_000_000)
    rth_mid = compute_phase_aware_rvol(session_label="RTH_MID", session_volume=50_000, avg_volume_20d=1_000_000)
    rth_late = compute_phase_aware_rvol(session_label="RTH_LATE", session_volume=50_000, avg_volume_20d=1_000_000)

    assert pre.rvol_phase == 1.0
    assert rth_open.rvol_phase == 0.12
    assert rth_mid.rvol_phase == 0.14
    assert rth_late.rvol_phase == 0.25


def test_session_classification_still_correct() -> None:
    assert normalize_session_label("REG") == "RTH_OPEN"
    assert resolve_market_session_context(datetime(2024, 1, 2, 13, 45, tzinfo=timezone.utc)).phase == "PRE"
    assert resolve_market_session_context(datetime(2024, 1, 2, 14, 45, tzinfo=timezone.utc)).phase == "RTH_OPEN"
    assert resolve_market_session_context(datetime(2024, 1, 2, 17, 0, tzinfo=timezone.utc)).phase == "RTH_MID"
    assert resolve_market_session_context(datetime(2024, 1, 2, 20, 0, tzinfo=timezone.utc)).phase == "RTH_LATE"
