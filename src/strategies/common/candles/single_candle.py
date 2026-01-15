"""Single-candle recognisers for evidence tagging."""

from __future__ import annotations

from typing import Optional

from src.strategies.common.candles.candle_evidence import CandleEvidence
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_types import Direction


def detect_doji(candle: Candle, tolerance: float = 0.1) -> Optional[CandleEvidence]:
    if candle.range == 0:
        return None
    body_ratio = candle.body / candle.range
    if body_ratio <= tolerance:
        return CandleEvidence(
            pattern_name="Doji",
            direction=Direction.NEUTRAL,
            confidence=0.5,
            rationale="Small body relative to range",
        )
    return None


def detect_hammer(candle: Candle) -> Optional[CandleEvidence]:
    if candle.range == 0:
        return None
    lower_wick_ratio = candle.lower_wick / candle.range
    upper_wick_ratio = candle.upper_wick / candle.range
    if lower_wick_ratio >= 0.6 and upper_wick_ratio <= 0.2:
        return CandleEvidence(
            pattern_name="Hammer",
            direction=Direction.LONG,
            confidence=0.6,
            rationale="Long lower wick with small upper wick",
        )
    return None


def detect_shooting_star(candle: Candle) -> Optional[CandleEvidence]:
    if candle.range == 0:
        return None
    upper_wick_ratio = candle.upper_wick / candle.range
    lower_wick_ratio = candle.lower_wick / candle.range
    if upper_wick_ratio >= 0.6 and lower_wick_ratio <= 0.2:
        return CandleEvidence(
            pattern_name="Shooting Star",
            direction=Direction.SHORT,
            confidence=0.6,
            rationale="Long upper wick with small lower wick",
        )
    return None


def detect_marubozu(candle: Candle, tolerance: float = 0.1) -> Optional[CandleEvidence]:
    if candle.range == 0:
        return None
    wick_ratio = (candle.upper_wick + candle.lower_wick) / candle.range
    if wick_ratio <= tolerance:
        direction = Direction.LONG if candle.is_bullish else Direction.SHORT
        return CandleEvidence(
            pattern_name="Marubozu",
            direction=direction,
            confidence=0.65,
            rationale="Very small wicks with full body",
        )
    return None


def detect_long_wick(candle: Candle, min_ratio: float = 0.6) -> Optional[CandleEvidence]:
    if candle.range == 0:
        return None
    if candle.upper_wick / candle.range >= min_ratio:
        return CandleEvidence(
            pattern_name="Long Upper Wick",
            direction=Direction.SHORT,
            confidence=0.45,
            rationale="Upper wick dominates the range",
        )
    if candle.lower_wick / candle.range >= min_ratio:
        return CandleEvidence(
            pattern_name="Long Lower Wick",
            direction=Direction.LONG,
            confidence=0.45,
            rationale="Lower wick dominates the range",
        )
    return None
