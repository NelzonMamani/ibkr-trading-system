from datetime import datetime

from src.core.time.trading_windows import (
    IBKR_TRADING_HOURS,
    SESSION_FALLBACK,
    build_trading_window_policy,
    resolve_trading_window_decision,
)


def test_ibkr_trading_hours_enforced_over_session() -> None:
    policy = build_trading_window_policy(
        symbol="AAPL",
        now=datetime(2026, 4, 3, 14, 0),
        run_mode="LIVE",
        trading_hours="20260403:0930-1600",
        liquid_hours=None,
        timezone="America/New_York",
    )

    outside_decision = resolve_trading_window_decision(
        policy=policy,
        now=datetime(2026, 4, 3, 22, 1),
    )
    assert outside_decision.allow_entries is False
    assert outside_decision.force_flat is True

    inside_decision = resolve_trading_window_decision(
        policy=policy,
        now=datetime(2026, 4, 3, 15, 0),
    )
    assert inside_decision.allow_entries is True
    assert inside_decision.force_flat is False


def test_session_fallback_only_when_ibkr_unavailable_and_not_live() -> None:
    policy = build_trading_window_policy(
        symbol="AAPL",
        now=datetime(2026, 4, 3, 14, 0),
        run_mode="PAPER",
        trading_hours=None,
        liquid_hours=None,
        timezone="America/New_York",
    )
    assert policy.source == SESSION_FALLBACK


def test_trading_hours_primary_even_when_empty() -> None:
    try:
        build_trading_window_policy(
            symbol="AAPL",
            now=datetime(2026, 4, 3, 14, 0),
            run_mode="PAPER",
            trading_hours="20260403:CLOSED",
            liquid_hours=None,
            timezone="America/New_York",
        )
    except ValueError as exc:
        assert "THA violation" in str(exc)
    else:
        raise AssertionError("Expected strict THA invariant failure")


def test_overnight_and_multi_segment_support() -> None:
    policy = build_trading_window_policy(
        symbol="ES",
        now=datetime(2026, 4, 3, 2, 0),
        run_mode="LIVE",
        trading_hours="20260402:1800-1700;20260403:1800-1700",
        liquid_hours=None,
        timezone="America/New_York",
    )
    assert policy.source == IBKR_TRADING_HOURS
    assert len(policy.segments) == 2
