"""Functional candlestick behaviours (E18 foundation primitives)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from src.strategies.common.candles.candle_types import Candle


@dataclass(frozen=True)
class BehaviourEvidence:
    name: str
    detected: bool
    measurements: dict[str, float]
    explanation: str | None = None


def range_expansion(candle: Candle, avg_range: float, multiplier: float = 1.5) -> BehaviourEvidence:
    ratio = candle.range / avg_range if avg_range else 0.0
    detected = ratio >= multiplier if avg_range else False
    return BehaviourEvidence(
        name="range_expansion",
        detected=detected,
        measurements={"range_ratio": ratio, "avg_range": avg_range},
        explanation="Range expansion relative to average" if detected else None,
    )


def range_contraction(candles: Sequence[Candle]) -> BehaviourEvidence:
    if len(candles) < 2:
        return BehaviourEvidence("range_contraction", False, {"count": len(candles)})
    ranges = [candle.range for candle in candles]
    detected = all(ranges[i] <= ranges[i - 1] for i in range(1, len(ranges)))
    return BehaviourEvidence(
        name="range_contraction",
        detected=detected,
        measurements={"ranges": sum(ranges), "count": len(ranges)},
        explanation="Sequential narrowing" if detected else None,
    )


def body_dominance(candle: Candle, min_ratio: float = 0.6) -> BehaviourEvidence:
    ratio = candle.body / candle.range if candle.range else 0.0
    detected = ratio >= min_ratio if candle.range else False
    return BehaviourEvidence(
        name="body_dominance",
        detected=detected,
        measurements={"body_ratio": ratio},
        explanation="Body dominates candle range" if detected else None,
    )


def wick_rejection_strength(candle: Candle, min_ratio: float = 1.0) -> BehaviourEvidence:
    if candle.body == 0:
        ratio = float("inf")
    else:
        ratio = max(candle.upper_wick, candle.lower_wick) / candle.body
    detected = ratio >= min_ratio
    return BehaviourEvidence(
        name="wick_rejection_strength",
        detected=detected,
        measurements={"wick_to_body_ratio": ratio},
        explanation="Strong wick rejection" if detected else None,
    )


def close_location_value(candle: Candle) -> BehaviourEvidence:
    if candle.range == 0:
        clv = 0.0
    else:
        clv = (candle.close - candle.low) / candle.range
    return BehaviourEvidence(
        name="close_location_value",
        detected=True,
        measurements={"clv": clv},
    )


def open_location_value(candle: Candle) -> BehaviourEvidence:
    if candle.range == 0:
        olv = 0.0
    else:
        olv = (candle.open - candle.low) / candle.range
    return BehaviourEvidence(
        name="open_location_value",
        detected=True,
        measurements={"olv": olv},
    )


def momentum_continuity(candles: Sequence[Candle], min_count: int = 2) -> BehaviourEvidence:
    if len(candles) < min_count:
        return BehaviourEvidence("momentum_continuity", False, {"count": len(candles)})
    closes = [candle.close for candle in candles]
    detected = all(closes[i] >= closes[i - 1] for i in range(1, len(closes)))
    return BehaviourEvidence(
        name="momentum_continuity",
        detected=detected,
        measurements={"count": len(closes)},
        explanation="Higher closes sequence" if detected else None,
    )


def exhaustion_bar(candle: Candle, avg_range: float, multiplier: float = 2.0) -> BehaviourEvidence:
    ratio = candle.range / avg_range if avg_range else 0.0
    detected = ratio >= multiplier if avg_range else False
    return BehaviourEvidence(
        name="exhaustion_bar",
        detected=detected,
        measurements={"range_ratio": ratio, "avg_range": avg_range},
        explanation="Large range exhaustion bar" if detected else None,
    )


def compression_count(candles: Sequence[Candle], max_range: float) -> BehaviourEvidence:
    detected = all(candle.range <= max_range for candle in candles) if candles else False
    return BehaviourEvidence(
        name="compression_count",
        detected=detected,
        measurements={"count": len(candles), "max_range": max_range},
        explanation="Compression within range band" if detected else None,
    )


def breakout_failure(candles: Sequence[Candle]) -> BehaviourEvidence:
    if len(candles) < 2:
        return BehaviourEvidence("breakout_failure", False, {"count": len(candles)})
    probe, failure = candles[-2], candles[-1]
    detected = probe.high > failure.high and failure.close < probe.close
    return BehaviourEvidence(
        name="breakout_failure",
        detected=detected,
        measurements={"probe_high": probe.high, "failure_close": failure.close},
        explanation="Breakout probe failed" if detected else None,
    )


def reclaim_and_hold(candles: Sequence[Candle]) -> BehaviourEvidence:
    if len(candles) < 2:
        return BehaviourEvidence("reclaim_and_hold", False, {"count": len(candles)})
    reclaim, hold = candles[-2], candles[-1]
    detected = hold.close >= reclaim.close >= reclaim.open
    return BehaviourEvidence(
        name="reclaim_and_hold",
        detected=detected,
        measurements={"reclaim_close": reclaim.close, "hold_close": hold.close},
        explanation="Reclaim and hold" if detected else None,
    )


def average_range(candles: Iterable[Candle]) -> float:
    ranges = [candle.range for candle in candles]
    return sum(ranges) / len(ranges) if ranges else 0.0
