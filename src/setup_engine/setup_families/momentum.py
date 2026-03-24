"""Shared momentum setup family implementations."""

from __future__ import annotations

from statistics import mean
from typing import List

from src.strategies.common.candles.candle_evidence import evidence_tags
from src.strategies.common.candles.multi_candle import detect_engulfing, detect_three_soldiers_crows
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
        if len(candles) < 7:
            return self._rejected("insufficient candles", inputs)
        ema9 = inputs.indicators.ema9
        if ema9 is None:
            return self._rejected("missing EMA9", inputs)
        trigger = candles[-1]
        if trigger.close < ema9:
            return self._rejected("price below EMA9", inputs)
        if trigger.close <= trigger.open:
            return self._rejected("no continuation close", inputs)

        pullback: list = []
        cursor = len(candles) - 2
        while cursor >= 0 and len(pullback) < 3:
            candle = candles[cursor]
            if candle.close <= candle.open:
                pullback.insert(0, candle)
                cursor -= 1
                continue
            break
        if not pullback:
            return self._rejected("no 1-3 bar pullback", inputs)
        impulse = candles[max(0, cursor - 2) : cursor + 1]
        if len(impulse) < 2:
            return self._rejected("missing initial impulse", inputs)
        impulse_gain = impulse[-1].close - impulse[0].open
        min_impulse = max(abs(impulse[0].open) * 0.003, 0.05)
        if impulse_gain <= min_impulse:
            return self._rejected("missing initial impulse", inputs)
        impulse_high = max(c.high for c in impulse)
        impulse_low = min(c.low for c in impulse)
        pullback_low = min(c.low for c in pullback)
        depth = (impulse_high - pullback_low) / max(impulse_high - impulse_low, 1e-9)
        if depth > 0.45:
            return self._rejected("pullback too deep", inputs)
        pullback_high = max(c.high for c in pullback)
        if trigger.close <= pullback_high:
            return self._rejected("no continuation close", inputs)

        volume_avg = _avg_volume(candles)
        volume_ok = trigger.volume >= volume_avg
        confidence = 0.65 if volume_ok else 0.55
        tags = ["volume_confirmed" if volume_ok else "volume_soft", "continuation_confirmed"]

        candle_evidence = [
            evidence
            for evidence in [
                detect_long_wick(trigger),
                detect_engulfing(candles),
                detect_three_soldiers_crows(candles),
            ]
            if evidence
        ]
        tags.extend(evidence_tags(candle_evidence))

        rationale = (
            "Impulse, controlled 1-3 bar pullback, and continuation close back through pullback highs.\n"
            f"Impulse gain={impulse_gain:.2f}, pullback depth={depth:.2%}, close={trigger.close:.2f}, EMA9={ema9:.2f}."
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
