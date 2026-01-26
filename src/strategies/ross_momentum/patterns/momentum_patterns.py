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
    name = "Micro Pullback"
    family = PatternFamily.PULLBACK
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        candles = inputs.candles
        if len(candles) < 6:
            return self._rejected("insufficient candles", inputs)

        last = candles[-1]
        red_seq = []
        for candle in reversed(candles[:-1]):
            if candle.close < candle.open and len(red_seq) < 3:
                red_seq.append(candle)
                continue
            break
        if len(red_seq) not in {2, 3}:
            return self._rejected("no 2-3 red candle pullback", inputs)

        impulse_idx = len(candles) - len(red_seq) - 2
        if impulse_idx < 0:
            return self._rejected("missing impulse candle", inputs)
        impulse = candles[impulse_idx]
        impulse_body = abs(impulse.close - impulse.open)
        impulse_range = impulse.high - impulse.low
        if impulse_body <= 0 or impulse_range <= 0:
            return self._rejected("invalid impulse candle", inputs)

        max_body_ratio = max(abs(c.close - c.open) / impulse_body for c in red_seq)
        pullback_high = max(c.high for c in red_seq)
        pullback_low = min(c.low for c in red_seq)
        pullback_range_ratio = (pullback_high - pullback_low) / impulse_range
        if max_body_ratio > 0.30:
            return self._rejected("pullback bodies too large", inputs)
        if pullback_range_ratio > 0.50:
            return self._rejected("pullback range too deep", inputs)

        last_red = red_seq[0]
        if last.close <= last_red.high:
            return self._rejected("no break above last red high", inputs)

        volume_avg = _avg_volume(candles)
        volume_ok = last.volume >= volume_avg
        confidence = 0.68 if volume_ok else 0.58
        tags = ["micro_pullback", "volume_confirmed" if volume_ok else "volume_soft"]
        risk_flags = []
        if pullback_range_ratio >= 0.40:
            risk_flags.append("PAUSE_TOPPING_RISK")
            tags.append("topping_risk_warning")

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
            "Micro pullback with controlled red bodies after impulse.\n"
            f"body_ratio_max={max_body_ratio:.2f} pullback_range_ratio={pullback_range_ratio:.2f}."
        )
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=confidence,
            rationale=rationale,
            entry_zone="Break above last red high",
            stop_suggestion="Below pullback low",
            target_suggestion="Resume impulse",
            setup_quality_tags=tags,
            risk_flags=risk_flags,
        )


class BullFlagPattern(PatternBase):
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


class HighTightFlagPattern(PatternBase):
    name = "High Tight Flag"
    family = PatternFamily.PULLBACK
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        candles = inputs.candles
        if len(candles) < 10:
            return self._rejected("insufficient candles", inputs)
        impulse = candles[-10:-6]
        flag = candles[-6:-1]
        impulse_gain = impulse[-1].close - impulse[0].open
        if impulse_gain <= 0:
            return self._rejected("no impulse move", inputs)
        if impulse_gain < impulse[0].open * 0.05:
            return self._rejected("impulse too small", inputs)
        flag_range = max(c.high for c in flag) - min(c.low for c in flag)
        if flag_range > impulse_gain * 0.35:
            return self._rejected("flag too wide", inputs)
        last = candles[-1]
        confidence = 0.7
        rationale = (
            "High tight flag after sharp impulse.\n"
            f"Impulse gain={impulse_gain:.2f}, flag range={flag_range:.2f}."
        )
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=confidence,
            rationale=rationale,
            entry_zone="Break above tight flag high",
            stop_suggestion="Below flag low",
            target_suggestion="Continuation extension",
            setup_quality_tags=["high_tight_flag"],
        )
