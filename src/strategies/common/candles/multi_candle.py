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
