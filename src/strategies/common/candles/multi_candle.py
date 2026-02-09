"""Multi-candle recognisers for evidence tagging."""

from __future__ import annotations

from typing import List, Optional

from src.strategies.common.candles.candle_evidence import CandleEvidence
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_types import Direction


def _last_n(candles: List[Candle], n: int) -> List[Candle]:
    if len(candles) < n:
        return []
    return candles[-n:]


def detect_engulfing(candles: List[Candle]) -> Optional[CandleEvidence]:
    pair = _last_n(candles, 2)
    if len(pair) < 2:
        return None
    first, second = pair
    if first.is_bearish and second.is_bullish:
        if second.close > first.open and second.open < first.close:
            return CandleEvidence(
                pattern_name="Bullish Engulfing",
                direction=Direction.LONG,
                confidence=0.65,
                rationale="Bullish candle engulfs prior bearish candle",
            )
    if first.is_bullish and second.is_bearish:
        if second.open > first.close and second.close < first.open:
            return CandleEvidence(
                pattern_name="Bearish Engulfing",
                direction=Direction.SHORT,
                confidence=0.65,
                rationale="Bearish candle engulfs prior bullish candle",
            )
    return None


def detect_morning_evening_star(candles: List[Candle]) -> Optional[CandleEvidence]:
    trio = _last_n(candles, 3)
    if len(trio) < 3:
        return None
    first, second, third = trio
    if first.is_bearish and third.is_bullish and second.body <= first.body * 0.4:
        return CandleEvidence(
            pattern_name="Morning Star",
            direction=Direction.LONG,
            confidence=0.6,
            rationale="Bearish candle, small body, bullish confirmation",
        )
    if first.is_bullish and third.is_bearish and second.body <= first.body * 0.4:
        return CandleEvidence(
            pattern_name="Evening Star",
            direction=Direction.SHORT,
            confidence=0.6,
            rationale="Bullish candle, small body, bearish confirmation",
        )
    return None


def detect_three_soldiers_crows(candles: List[Candle]) -> Optional[CandleEvidence]:
    trio = _last_n(candles, 3)
    if len(trio) < 3:
        return None
    if all(candle.is_bullish for candle in trio):
        return CandleEvidence(
            pattern_name="Three White Soldiers",
            direction=Direction.LONG,
            confidence=0.7,
            rationale="Three consecutive bullish candles",
        )
    if all(candle.is_bearish for candle in trio):
        return CandleEvidence(
            pattern_name="Three Black Crows",
            direction=Direction.SHORT,
            confidence=0.7,
            rationale="Three consecutive bearish candles",
        )
    return None


def detect_tweezer(candles: List[Candle]) -> Optional[CandleEvidence]:
    pair = _last_n(candles, 2)
    if len(pair) < 2:
        return None
    first, second = pair
    if abs(first.high - second.high) <= (first.range * 0.1):
        return CandleEvidence(
            pattern_name="Tweezer Top",
            direction=Direction.SHORT,
            confidence=0.55,
            rationale="Matching highs across two candles",
        )
    if abs(first.low - second.low) <= (first.range * 0.1):
        return CandleEvidence(
            pattern_name="Tweezer Bottom",
            direction=Direction.LONG,
            confidence=0.55,
            rationale="Matching lows across two candles",
        )
    return None


def detect_inside_bar(candles: List[Candle]) -> Optional[CandleEvidence]:
    pair = _last_n(candles, 2)
    if len(pair) < 2:
        return None
    first, second = pair
    if second.high <= first.high and second.low >= first.low:
        return CandleEvidence(
            pattern_name="Inside Bar",
            direction=Direction.NEUTRAL,
            confidence=0.4,
            rationale="Second candle inside previous range",
        )
    return None


def detect_outside_bar(candles: List[Candle]) -> Optional[CandleEvidence]:
    pair = _last_n(candles, 2)
    if len(pair) < 2:
        return None
    first, second = pair
    if second.high >= first.high and second.low <= first.low:
        direction = Direction.LONG if second.is_bullish else Direction.SHORT
        return CandleEvidence(
            pattern_name="Outside Bar",
            direction=direction,
            confidence=0.45,
            rationale="Second candle engulfs prior range",
        )
    return None


def detect_rising_falling_three_methods(candles: List[Candle]) -> Optional[CandleEvidence]:
    sequence = _last_n(candles, 5)
    if len(sequence) < 5:
        return None
    first, second, third, fourth, fifth = sequence
    middle_bodies = [second, third, fourth]
    if first.is_bullish and fifth.is_bullish:
        if all(candle.close <= first.close for candle in middle_bodies) and fifth.close > first.close:
            return CandleEvidence(
                pattern_name="Rising Three Methods",
                direction=Direction.LONG,
                confidence=0.6,
                rationale="Bullish continuation with controlled pullback",
            )
    if first.is_bearish and fifth.is_bearish:
        if all(candle.close >= first.close for candle in middle_bodies) and fifth.close < first.close:
            return CandleEvidence(
                pattern_name="Falling Three Methods",
                direction=Direction.SHORT,
                confidence=0.6,
                rationale="Bearish continuation with controlled pullback",
            )
    return None


def detect_micro_pullback_sequence(candles: List[Candle]) -> Optional[CandleEvidence]:
    trio = _last_n(candles, 3)
    if len(trio) < 2:
        return None
    reds = [candle for candle in trio if candle.is_bearish]
    if 1 <= len(reds) <= 2 and trio[-1].is_bullish:
        return CandleEvidence(
            pattern_name="Micro Pullback Sequence",
            direction=Direction.LONG,
            confidence=0.45,
            rationale="Short pullback followed by bullish resumption",
        )
    return None


def detect_tight_flag_compression(candles: List[Candle]) -> Optional[CandleEvidence]:
    trio = _last_n(candles, 3)
    if len(trio) < 3:
        return None
    ranges = [candle.range for candle in trio]
    if max(ranges) > 0 and max(ranges) <= min(ranges) * 1.5:
        return CandleEvidence(
            pattern_name="Tight Flag Compression Sequence",
            direction=Direction.NEUTRAL,
            confidence=0.4,
            rationale="Tight consolidation sequence",
        )
    return None


def detect_gap_and_go_sequence(candles: List[Candle]) -> Optional[CandleEvidence]:
    pair = _last_n(candles, 2)
    if len(pair) < 2:
        return None
    first, second = pair
    if second.open > first.high and second.close > second.open:
        return CandleEvidence(
            pattern_name="Gap-and-Go Opening Sequence",
            direction=Direction.LONG,
            confidence=0.55,
            rationale="Gap up and continuation",
        )
    return None


def detect_failed_break_sequence(candles: List[Candle], direction: Direction) -> Optional[CandleEvidence]:
    pair = _last_n(candles, 2)
    if len(pair) < 2:
        return None
    probe, failure = pair
    if direction == Direction.LONG and failure.close < probe.close:
        return CandleEvidence(
            pattern_name="Failed Breakout Sequence",
            direction=Direction.SHORT,
            confidence=0.45,
            rationale="Breakout failure",
        )
    if direction == Direction.SHORT and failure.close > probe.close:
        return CandleEvidence(
            pattern_name="Failed Breakdown Sequence",
            direction=Direction.LONG,
            confidence=0.45,
            rationale="Breakdown failure",
        )
    return None
