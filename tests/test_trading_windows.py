from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.core.time.trading_windows import (
    build_trading_window_policy,
    parse_ibkr_trading_hours,
    resolve_trading_window_decision,
)


ET = ZoneInfo("America/New_York")


def test_parse_ibkr_trading_hours_standard_day() -> None:
    segments = parse_ibkr_trading_hours(
        trading_hours="20260403:0400-2000",
        timezone_id="America/New_York",
        label="TEST",
    )
    assert len(segments) == 1
    assert segments[0].start_dt == datetime(2026, 4, 3, 4, 0, tzinfo=ET)
    assert segments[0].end_dt == datetime(2026, 4, 3, 20, 0, tzinfo=ET)


def test_parse_ibkr_trading_hours_closed_day() -> None:
    segments = parse_ibkr_trading_hours(
        trading_hours="20260405:CLOSED",
        timezone_id="America/New_York",
    )
    assert segments == []


def test_parse_ibkr_trading_hours_multiple_segments() -> None:
    segments = parse_ibkr_trading_hours(
        trading_hours="20260403:0400-0900,0930-1600;20260404:CLOSED",
        timezone_id="America/New_York",
    )
    assert len(segments) == 2
    assert segments[0].start_dt == datetime(2026, 4, 3, 4, 0, tzinfo=ET)
    assert segments[0].end_dt == datetime(2026, 4, 3, 9, 0, tzinfo=ET)
    assert segments[1].start_dt == datetime(2026, 4, 3, 9, 30, tzinfo=ET)
    assert segments[1].end_dt == datetime(2026, 4, 3, 16, 0, tzinfo=ET)


def test_parse_ibkr_trading_hours_overnight_segment() -> None:
    segments = parse_ibkr_trading_hours(
        trading_hours="20260403:2000-0400",
        timezone_id="America/New_York",
    )
    assert len(segments) == 1
    assert segments[0].start_dt == datetime(2026, 4, 3, 20, 0, tzinfo=ET)
    assert segments[0].end_dt == datetime(2026, 4, 4, 4, 0, tzinfo=ET)


def test_trading_window_policy_decisions() -> None:
    segments = parse_ibkr_trading_hours(
        trading_hours="20260403:0930-1600",
        timezone_id="America/New_York",
    )

    before_start = datetime(2026, 4, 3, 9, 0, tzinfo=ET)
    outside_policy = build_trading_window_policy(segments=segments, now=before_start)
    outside_decision = resolve_trading_window_decision(outside_policy, before_start)
    assert outside_decision.inside_window is False
    assert outside_decision.allow_new_entries is False

    inside_entry = datetime(2026, 4, 3, 10, 0, tzinfo=ET)
    entry_policy = build_trading_window_policy(segments=segments, now=inside_entry)
    entry_decision = resolve_trading_window_decision(entry_policy, inside_entry)
    assert entry_decision.allow_new_entries is True
    assert entry_decision.allow_management is True

    between_entry_and_manage = datetime(2026, 4, 3, 15, 56, tzinfo=ET)
    entry_block_decision = resolve_trading_window_decision(entry_policy, between_entry_and_manage)
    assert entry_block_decision.allow_new_entries is False
    assert entry_block_decision.allow_management is True

    between_manage_and_hard_flat = datetime(2026, 4, 3, 15, 59, tzinfo=ET)
    force_exit_decision = resolve_trading_window_decision(entry_policy, between_manage_and_hard_flat)
    assert force_exit_decision.force_exit_mode is True
    assert force_exit_decision.force_flat is False

    after_hard_flat = datetime(2026, 4, 3, 16, 1, tzinfo=ET)
    hard_flat_decision = resolve_trading_window_decision(entry_policy, after_hard_flat)
    assert hard_flat_decision.force_flat is True


def test_trading_window_policy_invariants_invalid_buffers() -> None:
    segments = parse_ibkr_trading_hours(
        trading_hours="20260403:0930-0931",
        timezone_id="America/New_York",
    )
    with pytest.raises(ValueError):
        build_trading_window_policy(
            segments=segments,
            now=datetime(2026, 4, 3, 9, 30, tzinfo=ET),
            entry_buffer_minutes=5,
            manage_buffer_minutes=2,
            hard_flat_buffer_minutes=0,
        )
