from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Callable, Iterable
from zoneinfo import ZoneInfo


IBKR_TRADING_HOURS = "IBKR_TRADING_HOURS"
IBKR_LIQUID_HOURS = "IBKR_LIQUID_HOURS"
SESSION_FALLBACK = "SESSION_FALLBACK"
UNAVAILABLE = "UNAVAILABLE"

WINDOWS_TIMEZONE_ALIASES = {
    "GMT Summer Time": "Europe/London",
    "GMT Standard Time": "Europe/London",
    "Eastern Standard Time": "America/New_York",
}


@dataclass(frozen=True)
class TradingWindowSegment:
    start: datetime
    end: datetime

    def contains(self, instant: datetime) -> bool:
        return self.start <= instant < self.end


@dataclass(frozen=True)
class TradingWindowPolicy:
    symbol: str
    source: str
    timezone: str
    segments: tuple[TradingWindowSegment, ...]


@dataclass(frozen=True)
class TradingWindowDecision:
    symbol: str
    source: str
    in_window: bool
    allow_entries: bool
    force_flat: bool


def _normalize_timezone_name(tz_name: str | None) -> str:
    if not tz_name:
        return "America/New_York"
    normalized = str(tz_name).strip()
    return WINDOWS_TIMEZONE_ALIASES.get(normalized, normalized)


def _default_session_segment(now: datetime, tz_name: str) -> TradingWindowSegment:
    tz_name = _normalize_timezone_name(tz_name)
    tz = ZoneInfo(tz_name)
    local_now = now.astimezone(tz)
    day = local_now.date()
    start = datetime.combine(day, time(9, 30), tzinfo=tz)
    end = datetime.combine(day, time(16, 0), tzinfo=tz)
    return TradingWindowSegment(start=start, end=end)


def _parse_ibkr_hours(raw_hours: str | None, tz_name: str, now: datetime) -> list[TradingWindowSegment]:
    if not raw_hours:
        return []

    tz_name = _normalize_timezone_name(tz_name)
    tz = ZoneInfo(tz_name)
    local_now = now.astimezone(tz)
    accepted_dates = {
        (local_now.date() + timedelta(days=offset)).strftime("%Y%m%d")
        for offset in (-1, 0, 1)
    }
    segments: list[TradingWindowSegment] = []

    for token in str(raw_hours).split(";"):
        token = token.strip()
        if not token or ":" not in token:
            continue
        date_part, session_part = token.split(":", 1)
        if date_part not in accepted_dates:
            continue
        if session_part == "CLOSED":
            continue
        for slot in session_part.split(","):
            slot = slot.strip()
            if not slot or "-" not in slot:
                continue
            start_hhmm, end_hhmm = slot.split("-", 1)
            if len(start_hhmm) != 4 or len(end_hhmm) != 4:
                continue
            year = int(date_part[0:4])
            month = int(date_part[4:6])
            day = int(date_part[6:8])
            start_dt = datetime(
                year,
                month,
                day,
                int(start_hhmm[0:2]),
                int(start_hhmm[2:4]),
                tzinfo=tz,
            )
            end_dt = datetime(
                year,
                month,
                day,
                int(end_hhmm[0:2]),
                int(end_hhmm[2:4]),
                tzinfo=tz,
            )
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)
            segments.append(TradingWindowSegment(start=start_dt, end=end_dt))

    segments.sort(key=lambda segment: segment.start)
    return segments


def _resolve_symbol_window_segments(
    *,
    symbol: str,
    now: datetime,
    run_mode: str,
    trading_hours: str | None,
    liquid_hours: str | None,
    timezone: str | None,
    session_segment_resolver: Callable[[datetime, str], TradingWindowSegment] = _default_session_segment,
) -> tuple[list[TradingWindowSegment], str, str]:
    tz_name = _normalize_timezone_name(timezone)

    # Primary authority
    if trading_hours is not None:
        segments = _parse_ibkr_hours(trading_hours, tz_name, now)
        return segments, IBKR_TRADING_HOURS, tz_name

    # Secondary authority
    if liquid_hours is not None:
        segments = _parse_ibkr_hours(liquid_hours, tz_name, now)
        return segments, IBKR_LIQUID_HOURS, tz_name

    # Session fallback is intentionally restricted.
    mode = str(run_mode).upper()
    if mode != "LIVE":
        return [session_segment_resolver(now, tz_name)], SESSION_FALLBACK, tz_name

    return [], UNAVAILABLE, tz_name


def build_trading_window_policy(
    *,
    symbol: str,
    now: datetime,
    run_mode: str,
    trading_hours: str | None,
    liquid_hours: str | None,
    timezone: str | None,
) -> TradingWindowPolicy:
    segments, source, tz_name = _resolve_symbol_window_segments(
        symbol=symbol,
        now=now,
        run_mode=run_mode,
        trading_hours=trading_hours,
        liquid_hours=liquid_hours,
        timezone=timezone,
    )
    if not segments:
        raise ValueError("THA violation: No trading window segments available")
    return TradingWindowPolicy(
        symbol=symbol,
        source=source,
        timezone=tz_name,
        segments=tuple(segments),
    )


def resolve_trading_window_decision(
    *,
    policy: TradingWindowPolicy,
    now: datetime,
) -> TradingWindowDecision:
    tz = ZoneInfo(_normalize_timezone_name(policy.timezone))
    local_now = now.astimezone(tz)
    in_window = any(segment.contains(local_now) for segment in policy.segments)

    # Strict safety: outside authoritative window means force flat.
    if not in_window:
        return TradingWindowDecision(
            symbol=policy.symbol,
            source=policy.source,
            in_window=False,
            allow_entries=False,
            force_flat=True,
        )

    return TradingWindowDecision(
        symbol=policy.symbol,
        source=policy.source,
        in_window=True,
        allow_entries=True,
        force_flat=False,
    )


def format_tha_source_log(*, symbol: str, source: str, segments: Iterable[TradingWindowSegment]) -> str:
    segment_count = len(list(segments))
    return f"[THA][SOURCE] symbol={symbol} source={source} segments={segment_count}"
