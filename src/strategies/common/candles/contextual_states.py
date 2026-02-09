"""Contextual candlestick state classifiers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.strategies.common.candles.candle_types import Candle


class ContextState(str, Enum):
    ABOVE = "above"
    BELOW = "below"
    RECLAIM = "reclaim"
    REJECT = "reject"
    HOLD = "hold"
    FAIL = "fail"
    BREAK = "break"
    ACCEPTANCE = "acceptance"


@dataclass(frozen=True)
class ContextualState:
    context: str
    state: ContextState
    reference: float | None


def candle_vs_level(candle: Candle, level: float, tolerance: float = 0.0) -> ContextualState:
    if candle.close > level + tolerance:
        return ContextualState("level", ContextState.ABOVE, level)
    if candle.close < level - tolerance:
        return ContextualState("level", ContextState.BELOW, level)
    return ContextualState("level", ContextState.HOLD, level)


def candle_vs_level_break_reclaim(candle: Candle, previous_close: float, level: float) -> ContextualState:
    if previous_close < level <= candle.close:
        return ContextualState("level", ContextState.RECLAIM, level)
    if previous_close > level >= candle.close:
        return ContextualState("level", ContextState.FAIL, level)
    return candle_vs_level(candle, level)


def candle_vs_range(candle: Candle, range_high: float, range_low: float) -> ContextualState:
    if candle.close > range_high:
        return ContextualState("range", ContextState.BREAK, range_high)
    if candle.close < range_low:
        return ContextualState("range", ContextState.FAIL, range_low)
    return ContextualState("range", ContextState.HOLD, None)
