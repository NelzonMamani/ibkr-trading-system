from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from src.config.config_resolver import get_config
from src.utils.time_utils import to_ny_time

_DEFAULT_ENTRY_CUTOFF_MINUTES = 30
_DEFAULT_MANAGE_UNTIL_MINUTES = 5
_DEFAULT_HARD_FLAT_BUFFER_MINUTES = 1


@dataclass(frozen=True)
class TradingWindowPolicy:
    window_start: datetime
    entry_cutoff: datetime
    manage_until: datetime
    hard_flat_time: datetime
    window_end: datetime
    tradable_now: bool


@dataclass(frozen=True)
class TradingWindowDecision:
    inside_window: bool
    allow_new_entries: bool
    allow_management: bool
    force_exit_mode: bool
    force_flat: bool
    reason: str


def _with_time(base: datetime, local_time: time) -> datetime:
    return base.replace(
        hour=local_time.hour,
        minute=local_time.minute,
        second=local_time.second,
        microsecond=0,
    )


def build_trading_window_policy(
    now: datetime,
    *,
    entry_cutoff_minutes: int = _DEFAULT_ENTRY_CUTOFF_MINUTES,
    manage_until_minutes: int = _DEFAULT_MANAGE_UNTIL_MINUTES,
    hard_flat_buffer_minutes: int = _DEFAULT_HARD_FLAT_BUFFER_MINUTES,
) -> TradingWindowPolicy:
    ny_now = to_ny_time(now)
    session_windows = get_config("MARKET_SESSION_WINDOWS_LOCAL")
    window_start = _with_time(ny_now, session_windows["REGULAR_START"])
    window_end = _with_time(ny_now, session_windows["REGULAR_END"])

    if window_end <= window_start:
        window_end = window_end + timedelta(days=1)

    hard_flat_time = window_end - timedelta(minutes=max(1, hard_flat_buffer_minutes))
    manage_until = window_end - timedelta(minutes=max(2, manage_until_minutes))
    entry_cutoff = window_end - timedelta(minutes=max(3, entry_cutoff_minutes))

    if entry_cutoff < window_start:
        entry_cutoff = window_start + timedelta(minutes=1)
    if manage_until <= entry_cutoff:
        manage_until = entry_cutoff + timedelta(minutes=1)
    if hard_flat_time <= manage_until:
        hard_flat_time = manage_until + timedelta(minutes=1)
    if hard_flat_time >= window_end:
        hard_flat_time = window_end - timedelta(minutes=1)
    if manage_until >= hard_flat_time:
        manage_until = hard_flat_time - timedelta(minutes=1)

    tradable_now = window_start <= ny_now < window_end
    return TradingWindowPolicy(
        window_start=window_start,
        entry_cutoff=entry_cutoff,
        manage_until=manage_until,
        hard_flat_time=hard_flat_time,
        window_end=window_end,
        tradable_now=tradable_now,
    )


def resolve_trading_window_decision(
    policy: TradingWindowPolicy,
    now: datetime,
) -> TradingWindowDecision:
    ny_now = to_ny_time(now)
    if not policy.tradable_now:
        return TradingWindowDecision(
            inside_window=False,
            allow_new_entries=False,
            allow_management=False,
            force_exit_mode=True,
            force_flat=True,
            reason="outside_window_force_flat",
        )

    if ny_now >= policy.hard_flat_time:
        return TradingWindowDecision(
            inside_window=True,
            allow_new_entries=False,
            allow_management=False,
            force_exit_mode=True,
            force_flat=True,
            reason="hard_flat_window",
        )

    if ny_now >= policy.manage_until:
        return TradingWindowDecision(
            inside_window=True,
            allow_new_entries=False,
            allow_management=True,
            force_exit_mode=False,
            force_flat=False,
            reason="manage_only_window",
        )

    if ny_now >= policy.entry_cutoff:
        return TradingWindowDecision(
            inside_window=True,
            allow_new_entries=False,
            allow_management=True,
            force_exit_mode=False,
            force_flat=False,
            reason="entry_cutoff_window",
        )

    return TradingWindowDecision(
        inside_window=True,
        allow_new_entries=True,
        allow_management=True,
        force_exit_mode=False,
        force_flat=False,
        reason="inside_window_normal",
    )
