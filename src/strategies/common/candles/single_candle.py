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


def detect_inverted_hammer(candle: Candle) -> Optional[CandleEvidence]:
    if candle.range == 0:
        return None
    upper_wick_ratio = candle.upper_wick / candle.range
    lower_wick_ratio = candle.lower_wick / candle.range
    if upper_wick_ratio >= 0.6 and lower_wick_ratio <= 0.2 and candle.is_bullish:
        return CandleEvidence(
            pattern_name="Inverted Hammer",
            direction=Direction.LONG,
            confidence=0.55,
            rationale="Bullish body with long upper wick",
        )
    return None


def detect_hanging_man(candle: Candle) -> Optional[CandleEvidence]:
    if candle.range == 0:
        return None
    lower_wick_ratio = candle.lower_wick / candle.range
    upper_wick_ratio = candle.upper_wick / candle.range
    if lower_wick_ratio >= 0.6 and upper_wick_ratio <= 0.2 and candle.is_bearish:
        return CandleEvidence(
            pattern_name="Hanging Man",
            direction=Direction.SHORT,
            confidence=0.55,
            rationale="Bearish body with long lower wick",
        )
    return None


def detect_dragonfly_doji(candle: Candle, tolerance: float = 0.1) -> Optional[CandleEvidence]:
    if candle.range == 0:
        return None
    body_ratio = candle.body / candle.range
    upper_wick_ratio = candle.upper_wick / candle.range
    if body_ratio <= tolerance and upper_wick_ratio <= 0.1:
        return CandleEvidence(
            pattern_name="Dragonfly Doji",
            direction=Direction.LONG,
            confidence=0.5,
            rationale="Doji with long lower wick",
        )
    return None


def detect_gravestone_doji(candle: Candle, tolerance: float = 0.1) -> Optional[CandleEvidence]:
    if candle.range == 0:
        return None
    body_ratio = candle.body / candle.range
    lower_wick_ratio = candle.lower_wick / candle.range
    if body_ratio <= tolerance and lower_wick_ratio <= 0.1:
        return CandleEvidence(
            pattern_name="Gravestone Doji",
            direction=Direction.SHORT,
            confidence=0.5,
            rationale="Doji with long upper wick",
        )
    return None


def detect_spinning_top(candle: Candle, max_body_ratio: float = 0.3) -> Optional[CandleEvidence]:
    if candle.range == 0:
        return None
    body_ratio = candle.body / candle.range
    if body_ratio <= max_body_ratio:
        direction = Direction.NEUTRAL
        return CandleEvidence(
            pattern_name="Spinning Top",
            direction=direction,
            confidence=0.4,
            rationale="Small body with upper/lower wicks",
        )
    return None


def detect_marubozu_bull(candle: Candle, tolerance: float = 0.1) -> Optional[CandleEvidence]:
    evidence = detect_marubozu(candle, tolerance=tolerance)
    if evidence and candle.is_bullish:
        return CandleEvidence(
            pattern_name="Marubozu Bull",
            direction=Direction.LONG,
            confidence=evidence.confidence,
            rationale=evidence.rationale,
        )
    return None


def detect_marubozu_bear(candle: Candle, tolerance: float = 0.1) -> Optional[CandleEvidence]:
    evidence = detect_marubozu(candle, tolerance=tolerance)
    if evidence and candle.is_bearish:
        return CandleEvidence(
            pattern_name="Marubozu Bear",
            direction=Direction.SHORT,
            confidence=evidence.confidence,
            rationale=evidence.rationale,
        )
    return None


def detect_long_lower_wick_rejection(candle: Candle, min_ratio: float = 0.6) -> Optional[CandleEvidence]:
    if candle.range == 0:
        return None
    if candle.lower_wick / candle.range >= min_ratio:
        return CandleEvidence(
            pattern_name="Long Lower Wick Rejection",
            direction=Direction.LONG,
            confidence=0.45,
            rationale="Lower wick rejection",
        )
    return None


def detect_long_upper_wick_rejection(candle: Candle, min_ratio: float = 0.6) -> Optional[CandleEvidence]:
    if candle.range == 0:
        return None
    if candle.upper_wick / candle.range >= min_ratio:
        return CandleEvidence(
            pattern_name="Long Upper Wick Rejection",
            direction=Direction.SHORT,
            confidence=0.45,
            rationale="Upper wick rejection",
        )
    return None


def detect_wide_range_bar(candle: Candle, avg_range: float, multiplier: float = 1.5) -> Optional[CandleEvidence]:
    if avg_range <= 0:
        return None
    if candle.range >= avg_range * multiplier:
        direction = Direction.LONG if candle.is_bullish else Direction.SHORT
        return CandleEvidence(
            pattern_name="Wide Range Expansion Bar",
            direction=direction,
            confidence=0.55,
            rationale="Wide range expansion bar",
        )
    return None


def detect_narrow_range_bar(candle: Candle, avg_range: float, ratio: float = 0.5) -> Optional[CandleEvidence]:
    if avg_range <= 0:
        return None
    if candle.range <= avg_range * ratio:
        return CandleEvidence(
            pattern_name="Narrow Range Bar",
            direction=Direction.NEUTRAL,
            confidence=0.4,
            rationale="Narrow range contraction bar",
        )
    return None
