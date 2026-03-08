from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_gap_pct(session_open_price: float | None, prior_close: float | None) -> float | None:
    if session_open_price is None or prior_close in {None, 0}:
        return None
    return round((session_open_price - prior_close) / prior_close, 6)


def compute_time_normalized_rvol(
    *,
    scanner_rvol: float | None,
    session_progress: float | None = None,
) -> float | None:
    """Placeholder telemetry model. Keeps scanner flow non-breaking.

    If session_progress is known in (0, 1], the RVOL is normalized by expected
    progress; otherwise scanner_rvol is passed through unchanged.
    """
    if scanner_rvol is None:
        return None
    if session_progress is None or session_progress <= 0:
        return round(scanner_rvol, 4)
    return round(scanner_rvol / max(session_progress, 0.05), 4)


def _ema(values: Sequence[float], period: int) -> float | None:
    if not values:
        return None
    alpha = 2.0 / (period + 1.0)
    ema = float(values[0])
    for value in values[1:]:
        ema = (float(value) * alpha) + (ema * (1.0 - alpha))
    return round(ema, 4)


def _whole_half_levels(reference_price: float | None, *, width: int = 4) -> list[float]:
    if reference_price is None or reference_price <= 0:
        return []
    anchor = int(reference_price)
    levels: set[float] = set()
    for whole in range(anchor - width, anchor + width + 1):
        if whole > 0:
            levels.add(float(whole))
            levels.add(round(whole + 0.5, 2))
    return sorted(levels)


@dataclass(frozen=True)
class StructureLevels:
    premarket_high: float | None
    premarket_low: float | None
    prior_close: float | None
    prior_day_high: float | None
    prior_day_low: float | None
    multi_day_high: float | None
    multi_day_low: float | None
    whole_half_levels: list[float]
    vwap: float | None
    ema9: float | None
    ema20: float | None


def compute_structure_levels(
    *,
    quote: dict[str, Any],
    intraday: dict[str, Any],
    history_closes: Sequence[float] | None = None,
) -> StructureLevels:
    last_price = _safe_float(quote.get("last_price"))
    day_high = _safe_float(quote.get("day_high"))
    day_low = _safe_float(quote.get("day_low"))
    prior_close = _safe_float(quote.get("prior_close"))

    # Additive defaults: fall back to day range when premarket bars are unavailable.
    premarket_high = _safe_float(intraday.get("premarket_high")) or day_high
    premarket_low = _safe_float(intraday.get("premarket_low")) or day_low
    prior_day_high = _safe_float(intraday.get("prior_day_high")) or day_high
    prior_day_low = _safe_float(intraday.get("prior_day_low")) or day_low

    rolling = [float(v) for v in (history_closes or []) if _safe_float(v) is not None]
    multi_day_high = max(rolling) if rolling else prior_day_high
    multi_day_low = min(rolling) if rolling else prior_day_low

    vwap = _safe_float(quote.get("vwap"))
    series = rolling + ([last_price] if last_price is not None else [])
    ema9 = _ema(series[-20:], 9) if series else None
    ema20 = _ema(series[-40:], 20) if series else None

    return StructureLevels(
        premarket_high=premarket_high,
        premarket_low=premarket_low,
        prior_close=prior_close,
        prior_day_high=prior_day_high,
        prior_day_low=prior_day_low,
        multi_day_high=multi_day_high,
        multi_day_low=multi_day_low,
        whole_half_levels=_whole_half_levels(last_price),
        vwap=vwap,
        ema9=ema9,
        ema20=ema20,
    )
