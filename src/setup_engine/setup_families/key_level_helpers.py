"""Reusable key-level helpers for shared setup families and triggers."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Any


@dataclass(frozen=True)
class KeyLevelCandidate:
    level_type: str
    level_price: float
    source: str


_LEVEL_ALIASES: dict[str, tuple[str, str]] = {
    "PREMARKET_HIGH": ("PREMARKET_HIGH", "session_context"),
    "PMH": ("PREMARKET_HIGH", "session_context"),
    "HOD": ("HOD", "session_context"),
    "PRIOR_DAY_HIGH": ("PRIOR_DAY_HIGH", "daily_reference"),
    "PRIOR_HIGH": ("PRIOR_DAY_HIGH", "daily_reference"),
    "MULTI_DAY_HIGH": ("MULTI_DAY_HIGH", "daily_reference"),
    "MULTIDAY_HIGH": ("MULTI_DAY_HIGH", "daily_reference"),
    "RESISTANCE_MULTI_DAY": ("MULTI_DAY_HIGH", "derived_resistance"),
}



def _safe_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None



def classify_level_type(raw_level_name: str) -> tuple[str, str]:
    key = str(raw_level_name or "").strip().upper()
    return _LEVEL_ALIASES.get(key, (key, "key_levels"))



def round_number_levels_around_price(price: float, *, band: int = 1) -> list[KeyLevelCandidate]:
    """Return deterministic whole/half-dollar candidates around current price.

    Conservative rounding: use floor(price) anchor and include +/- `band` dollars.
    """

    if price <= 0:
        return []
    anchor = floor(price)
    levels: list[KeyLevelCandidate] = []
    for offset in range(-band, band + 1):
        whole = float(anchor + offset)
        half = whole + 0.5
        if whole > 0:
            levels.append(KeyLevelCandidate("WHOLE_DOLLAR", whole, "round_number"))
        if half > 0:
            levels.append(KeyLevelCandidate("HALF_DOLLAR", half, "round_number"))
    return sorted(levels, key=lambda item: item.level_price)



def level_candidates_for_inputs(inputs: Any) -> list[KeyLevelCandidate]:
    levels = getattr(inputs, "levels", None)
    if levels is None:
        return []

    candidates: list[KeyLevelCandidate] = []
    premarket_high = _safe_float(getattr(levels, "premarket_high", None))
    hod = _safe_float(getattr(levels, "hod", None))
    prior_close = _safe_float(getattr(levels, "prior_close", None))

    if premarket_high is not None:
        candidates.append(KeyLevelCandidate("PREMARKET_HIGH", premarket_high, "session_context"))
    if hod is not None:
        candidates.append(KeyLevelCandidate("HOD", hod, "session_context"))

    key_levels = getattr(levels, "key_levels", {}) or {}
    for raw_name, raw_price in key_levels.items():
        parsed = _safe_float(raw_price)
        if parsed is None:
            continue
        level_type, source = classify_level_type(str(raw_name))
        candidates.append(KeyLevelCandidate(level_type, parsed, source))

    last_price = None
    candles = list(getattr(inputs, "candles", []) or [])
    if candles:
        candle = candles[-1]
        last_price = _safe_float(getattr(candle, "close", None))
        if last_price is None and isinstance(candle, dict):
            last_price = _safe_float(candle.get("close"))
    if last_price is None and prior_close is not None:
        last_price = prior_close
    if last_price is not None:
        candidates.extend(round_number_levels_around_price(last_price, band=1))

    uniq: dict[tuple[str, float], KeyLevelCandidate] = {}
    for candidate in candidates:
        uniq[(candidate.level_type, round(candidate.level_price, 4))] = candidate
    return sorted(uniq.values(), key=lambda item: item.level_price)



def nearest_relevant_key_level(*, inputs: Any, reference_price: float) -> KeyLevelCandidate | None:
    candidates = level_candidates_for_inputs(inputs)
    if not candidates:
        return None
    return min(candidates, key=lambda c: abs(c.level_price - reference_price))
