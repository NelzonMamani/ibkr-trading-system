"""Breakout-related Ross patterns."""

from __future__ import annotations

from statistics import mean
from typing import List

from src.strategies.common.candles.candle_evidence import evidence_tags
from src.strategies.common.candles.single_candle import detect_marubozu
from src.strategies.ross_momentum.patterns.pattern_base import PatternBase
from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.strategy_contracts import SessionContext


def _avg_volume(candles: List, lookback: int = 5) -> float:
    if len(candles) < 1:
        return 0.0
    sample = candles[-lookback:] if len(candles) >= lookback else candles
    return mean(candle.volume for candle in sample)


class PremarketHighBreakPattern(PatternBase):
    name = "Premarket High Break"
    family = PatternFamily.BREAKOUT
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        level = inputs.levels.premarket_high
        if level is None:
            return self._rejected("missing premarket high", inputs)
        if not inputs.candles:
            return self._rejected("no candles", inputs)
        last = inputs.candles[-1]
        if last.close <= level:
            return self._rejected("price below premarket high", inputs)
        rvol = inputs.liquidity_context.rvol or 0.0
        volume_ok = rvol >= 1.5
        confidence = 0.7 if volume_ok else 0.55
        tags = ["premarket_break", "rvol_ok" if volume_ok else "rvol_soft"]
        candle_evidence = [e for e in [detect_marubozu(last)] if e]
        tags.extend(evidence_tags(candle_evidence))
        rationale = (
            "Break above premarket high with momentum.\n"
            f"Premarket high={level:.2f}, last close={last.close:.2f}."
        )
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=confidence,
            rationale=rationale,
            entry_zone="Retest of premarket high or continuation",
            stop_suggestion="Below premarket high",
            target_suggestion="HOD extension",
            setup_quality_tags=tags,
        )


class OpeningRangeBreakoutPattern(PatternBase):
    name = "Opening Range Breakout"
    family = PatternFamily.BREAKOUT
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        if inputs.session_context != SessionContext.REGULAR:
            return self._rejected("not regular session", inputs)
        if len(inputs.candles) < 6:
            return self._rejected("insufficient candles", inputs)
        opening_range = inputs.candles[:5]
        range_high = max(candle.high for candle in opening_range)
        range_low = min(candle.low for candle in opening_range)
        last = inputs.candles[-1]
        if last.close <= range_high:
            return self._rejected("no breakout above opening range", inputs)
        volume_avg = _avg_volume(inputs.candles)
        volume_ok = last.volume >= volume_avg
        confidence = 0.68 if volume_ok else 0.55
        tags = ["opening_range_break", "volume_confirmed" if volume_ok else "volume_soft"]
        rationale = (
            "Break above opening range high.\n"
            f"Range high={range_high:.2f}, last close={last.close:.2f}."
        )
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=confidence,
            rationale=rationale,
            entry_zone="Break above opening range high",
            stop_suggestion=f"Below range low ({range_low:.2f})",
            target_suggestion="Measured move",
            setup_quality_tags=tags,
        )


class ConsolidationBreakoutPattern(PatternBase):
    name = "Consolidation Breakout"
    family = PatternFamily.RANGE
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        candles = inputs.candles
        if len(candles) < 8:
            return self._rejected("insufficient candles", inputs)
        consolidation = candles[-6:-1]
        last = candles[-1]
        range_high = max(c.high for c in consolidation)
        range_low = min(c.low for c in consolidation)
        range_width = range_high - range_low
        if range_width <= 0:
            return self._rejected("invalid consolidation range", inputs)
        if range_width > (range_high * 0.01):
            return self._rejected("consolidation too wide", inputs)
        if last.close <= range_high:
            return self._rejected("no breakout from consolidation", inputs)

        volume_avg = _avg_volume(candles)
        volume_ok = last.volume >= volume_avg
        confidence = 0.67 if volume_ok else 0.55
        tags = ["tight_consolidation", "volume_confirmed" if volume_ok else "volume_soft"]
        rationale = (
            "Tight consolidation followed by breakout.\n"
            f"Range high={range_high:.2f}, range width={range_width:.4f}."
        )
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=confidence,
            rationale=rationale,
            entry_zone="Break above consolidation high",
            stop_suggestion="Below consolidation low",
            target_suggestion="Range expansion",
            setup_quality_tags=tags,
        )
