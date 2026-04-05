from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


_DEFAULT_ENTRY_BUFFER_MINUTES = 5
_DEFAULT_MANAGE_BUFFER_MINUTES = 2
_DEFAULT_HARD_FLAT_BUFFER_MINUTES = 0


@dataclass(frozen=True)
class TradingWindowSegment:
    label: str
    start_dt: datetime
    end_dt: datetime
    timezone: str
    source: str
    tradable: bool = True

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["start_dt"] = self.start_dt.isoformat()
        payload["end_dt"] = self.end_dt.isoformat()
        return payload


@dataclass(frozen=True)
class TradingWindowPolicy:
    window_start: datetime | None
    window_end: datetime | None
    entry_cutoff: datetime | None
    manage_until: datetime | None
    hard_flat_time: datetime | None
    entry_buffer_minutes: int
    manage_buffer_minutes: int
    hard_flat_buffer_minutes: int
    source_window_label: str
    tradable_now: bool
    current_window_label: str
    next_open: datetime | None
    next_close: datetime | None
    reason: str

    def to_dict(self) -> dict:
        payload = asdict(self)
        for key in ("window_start", "window_end", "entry_cutoff", "manage_until", "hard_flat_time", "next_open", "next_close"):
            value = payload[key]
            payload[key] = value.isoformat() if isinstance(value, datetime) else None
        return payload


@dataclass(frozen=True)
class TradingWindowDecision:
    inside_window: bool
    allow_new_entries: bool
    allow_management: bool
    force_exit_mode: bool
    force_flat: bool
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def parse_ibkr_trading_hours(
    *,
    trading_hours: str | None,
    timezone_id: str | None,
    label: str = "IBKR_TRADING_HOURS",
    source: str = "IBKR_CONTRACT_DETAILS",
) -> list[TradingWindowSegment]:
    if not trading_hours:
        return []

    tz_name = str(timezone_id or "UTC")
    tz = ZoneInfo(tz_name)
    segments: list[TradingWindowSegment] = []

    for block in str(trading_hours).split(";"):
        day_key, sep, day_payload = block.strip().partition(":")
        if not sep:
            continue
        if day_payload.upper() == "CLOSED":
            continue

        for idx, span in enumerate(day_payload.split(","), start=1):
            start_raw, dash, end_raw = span.strip().partition("-")
            if not dash:
                continue
            start_dt = _parse_ibkr_timestamp(day_key, start_raw, tz)
            end_dt = _parse_ibkr_timestamp(day_key, end_raw, tz)
            if end_dt <= start_dt:
                end_dt = end_dt + timedelta(days=1)
            segments.append(
                TradingWindowSegment(
                    label=f"{label}_{day_key}_{idx}",
                    start_dt=start_dt,
                    end_dt=end_dt,
                    timezone=tz_name,
                    source=source,
                    tradable=True,
                )
            )

    return sorted(segments, key=lambda item: item.start_dt)


def build_trading_window_policy(
    *,
    segments: list[TradingWindowSegment],
    now: datetime,
    entry_buffer_minutes: int = _DEFAULT_ENTRY_BUFFER_MINUTES,
    manage_buffer_minutes: int = _DEFAULT_MANAGE_BUFFER_MINUTES,
    hard_flat_buffer_minutes: int = _DEFAULT_HARD_FLAT_BUFFER_MINUTES,
    source_label: str = "UNAVAILABLE",
) -> TradingWindowPolicy:
    if now.tzinfo is None:
        raise ValueError("Trading window resolution requires timezone-aware 'now'.")

    active = next((segment for segment in segments if segment.tradable and segment.start_dt <= now <= segment.end_dt), None)
    future = [segment for segment in segments if segment.tradable and segment.start_dt > now]
    latest = [segment for segment in segments if segment.tradable and segment.end_dt < now]

    if active is None:
        next_open = min((segment.start_dt for segment in future), default=None)
        next_close = min((segment.end_dt for segment in future), default=None)
        if next_open is None and latest:
            next_close = max(segment.end_dt for segment in latest)
        return TradingWindowPolicy(
            window_start=None,
            window_end=None,
            entry_cutoff=None,
            manage_until=None,
            hard_flat_time=None,
            entry_buffer_minutes=entry_buffer_minutes,
            manage_buffer_minutes=manage_buffer_minutes,
            hard_flat_buffer_minutes=hard_flat_buffer_minutes,
            source_window_label=source_label,
            tradable_now=False,
            current_window_label="NONE",
            next_open=next_open,
            next_close=next_close,
            reason="outside_tradable_window",
        )

    window_start = active.start_dt
    window_end = active.end_dt
    entry_cutoff = window_end - timedelta(minutes=max(0, entry_buffer_minutes))
    manage_until = window_end - timedelta(minutes=max(0, manage_buffer_minutes))
    hard_flat_time = window_end - timedelta(minutes=max(0, hard_flat_buffer_minutes))
    _validate_policy_invariants(
        window_start=window_start,
        window_end=window_end,
        entry_cutoff=entry_cutoff,
        manage_until=manage_until,
        hard_flat_time=hard_flat_time,
    )
    return TradingWindowPolicy(
        window_start=window_start,
        window_end=window_end,
        entry_cutoff=entry_cutoff,
        manage_until=manage_until,
        hard_flat_time=hard_flat_time,
        entry_buffer_minutes=entry_buffer_minutes,
        manage_buffer_minutes=manage_buffer_minutes,
        hard_flat_buffer_minutes=hard_flat_buffer_minutes,
        source_window_label=active.label,
        tradable_now=True,
        current_window_label=active.label,
        next_open=None,
        next_close=window_end,
        reason="inside_tradable_window",
    )


def resolve_trading_window_decision(policy: TradingWindowPolicy, now: datetime) -> TradingWindowDecision:
    if not policy.tradable_now or policy.window_start is None or policy.window_end is None:
        return TradingWindowDecision(
            inside_window=False,
            allow_new_entries=False,
            allow_management=False,
            force_exit_mode=False,
            force_flat=False,
            reason="outside_tradable_window",
        )

    assert policy.entry_cutoff is not None
    assert policy.manage_until is not None
    assert policy.hard_flat_time is not None

    if now <= policy.entry_cutoff:
        return TradingWindowDecision(True, True, True, False, False, "entry_and_management_allowed")

    if policy.entry_cutoff < now <= policy.manage_until:
        return TradingWindowDecision(True, False, True, False, False, "entry_cutoff_reached")

    if policy.manage_until < now <= policy.hard_flat_time:
        return TradingWindowDecision(True, False, False, True, False, "force_exit_mode")

    return TradingWindowDecision(True, False, False, True, True, "hard_flat_enforced")


def _parse_ibkr_timestamp(day_key: str, hhmm: str, tz: ZoneInfo) -> datetime:
    hhmm_clean = str(hhmm or "").strip()
    if len(day_key) != 8 or len(hhmm_clean) != 4 or not day_key.isdigit() or not hhmm_clean.isdigit():
        raise ValueError(f"Unsupported IBKR trading-hours token: {day_key}:{hhmm}")
    year = int(day_key[0:4])
    month = int(day_key[4:6])
    day = int(day_key[6:8])
    hour = int(hhmm_clean[0:2])
    minute = int(hhmm_clean[2:4])
    return datetime(year, month, day, hour, minute, tzinfo=tz)


def _validate_policy_invariants(
    *,
    window_start: datetime,
    window_end: datetime,
    entry_cutoff: datetime,
    manage_until: datetime,
    hard_flat_time: datetime,
) -> None:
    if not (window_start < window_end):
        raise ValueError("Invalid trading window: window_start must be before window_end.")
    if not (window_start < entry_cutoff <= manage_until <= hard_flat_time <= window_end):
        raise ValueError(
            "Invalid trading window buffers: expected window_start < entry_cutoff <= manage_until <= hard_flat_time <= window_end."
        )
