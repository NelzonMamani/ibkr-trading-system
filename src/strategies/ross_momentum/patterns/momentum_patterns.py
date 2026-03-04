"""Momentum-related Ross patterns."""

from __future__ import annotations

from statistics import mean
from typing import List

from src.strategies.common.candles.candle_evidence import evidence_tags
from src.strategies.common.candles.multi_candle import (
    detect_engulfing,
    detect_three_soldiers_crows,
)
from src.strategies.common.candles.single_candle import detect_long_wick
from src.strategies.ross_momentum.patterns.pattern_base import PatternBase
from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult


def _avg_volume(candles: List, lookback: int = 5) -> float:
    if len(candles) < 1:
        return 0.0
    sample = candles[-lookback:] if len(candles) >= lookback else candles
    return mean(candle.volume for candle in sample)


class MicroPullbackPattern(PatternBase):
    pattern_id = "P_MICRO_PULLBACK"
    name = "Micro Pullback"
    family = PatternFamily.PULLBACK
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        candles = inputs.candles
        if len(candles) < 5:
            return self._rejected("insufficient candles", inputs)
        ema9 = inputs.indicators.ema9
        if ema9 is None:
            return self._rejected("missing EMA9", inputs)
        last = candles[-1]
        if last.close < ema9:
            return self._rejected("price below EMA9", inputs)

        pullback = candles[-4:-1]
        pullback_down = all(c.close <= c.open for c in pullback)
        if not pullback_down:
            return self._rejected("no 1-3 bar pullback", inputs)

        volume_avg = _avg_volume(candles)
        volume_ok = last.volume >= volume_avg
        confidence = 0.65 if volume_ok else 0.55
        tags = ["volume_confirmed" if volume_ok else "volume_soft"]

        candle_evidence = [
            evidence
            for evidence in [
                detect_long_wick(last),
                detect_engulfing(candles),
                detect_three_soldiers_crows(candles),
            ]
            if evidence
        ]
        tags.extend(evidence_tags(candle_evidence))

        rationale = (
            "Price holding above EMA9 with 1-3 bar pullback.\n"
            f"Last close={last.close:.2f}, EMA9={ema9:.2f}."
        )
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=confidence,
            rationale=rationale,
            entry_zone="Break of pullback high",
            stop_suggestion="Below pullback low",
            target_suggestion="Prior high / HOD",
            setup_quality_tags=tags,
        )


class BullFlagPattern(PatternBase):
    pattern_id = "P_BULL_FLAG"
    name = "Bull Flag"
    family = PatternFamily.PULLBACK
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        candles = inputs.candles
        if len(candles) < 8:
            return self._rejected("insufficient candles", inputs)
        ema20 = inputs.indicators.ema20
        if ema20 is None:
            return self._rejected("missing EMA20", inputs)
        recent = candles[-8:]
        impulse = recent[:3]
        flag = recent[3:]
        impulse_gain = impulse[-1].close - impulse[0].open
        if impulse_gain <= 0:
            return self._rejected("no impulse move", inputs)
        flag_range = max(c.high for c in flag) - min(c.low for c in flag)
        if flag_range > impulse_gain * 0.7:
            return self._rejected("flag too wide", inputs)
        if recent[-1].close < ema20:
            return self._rejected("price below EMA20", inputs)

        volume_avg = _avg_volume(candles)
        volume_ok = recent[-1].volume >= volume_avg
        confidence = 0.66 if volume_ok else 0.55
        tags = ["flag_structure", "volume_confirmed" if volume_ok else "volume_soft"]

        rationale = (
            "Impulse move followed by tight consolidation above EMA20.\n"
            f"Impulse gain={impulse_gain:.2f}, flag range={flag_range:.2f}."
        )
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=confidence,
            rationale=rationale,
            entry_zone="Break above flag high",
            stop_suggestion="Below flag low",
            target_suggestion="Measured move",
            setup_quality_tags=tags,
        )
