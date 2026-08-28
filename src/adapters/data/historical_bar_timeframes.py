from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntradayTimeframeRequest:
    logical_timeframe: str
    bar_size_setting: str
    bar_seconds: int
    requested_bars: int
    duration_seconds: int


_TIMEFRAME_SPECS = {
    "10s": ("10 secs", 10),
    "1m": ("1 min", 60),
    "5m": ("5 mins", 300),
}

_ALIASES = {
    "10s": "10s",
    "s10": "10s",
    "10sec": "10s",
    "10secs": "10s",
    "10second": "10s",
    "10seconds": "10s",
    "1m": "1m",
    "m1": "1m",
    "1min": "1m",
    "1mins": "1m",
    "1minute": "1m",
    "1minutes": "1m",
    "5m": "5m",
    "m5": "5m",
    "5min": "5m",
    "5mins": "5m",
    "5minute": "5m",
    "5minutes": "5m",
}


def normalize_intraday_timeframe(timeframe: str | None) -> str:
    normalized = str(timeframe or "").strip().lower().replace("_", "").replace("-", "").replace(" ", "")
    logical = _ALIASES.get(normalized)
    if logical is None:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return logical


def resolve_intraday_timeframe_request(
    *,
    timeframe: str | None,
    requested_bars: int,
) -> IntradayTimeframeRequest:
    logical = normalize_intraday_timeframe(timeframe)
    bar_size_setting, bar_seconds = _TIMEFRAME_SPECS[logical]
    bars_requested = max(int(requested_bars), 2)
    duration_seconds = max(bars_requested * bar_seconds * 2, 1800)
    return IntradayTimeframeRequest(
        logical_timeframe=logical,
        bar_size_setting=bar_size_setting,
        bar_seconds=bar_seconds,
        requested_bars=bars_requested,
        duration_seconds=duration_seconds,
    )
