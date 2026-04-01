"""Shared momentum setup family implementations."""

from __future__ import annotations

from dataclasses import replace
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
        if len(candles) < 5:
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
        if depth > 0.65:
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
        if len(candles) < 9:
            return self._rejected("insufficient candles", inputs)
        ema9 = inputs.indicators.ema9
        ema20 = inputs.indicators.ema20
        vwap = inputs.indicators.vwap
        if ema9 is None or ema20 is None or vwap is None:
            return self._rejected("missing trend indicators", inputs)

        recent = candles[-9:]
        impulse = recent[:3]
        flag = recent[3:-1]
        breakout = recent[-1]
        impulse_gain = impulse[-1].close - impulse[0].open
        impulse_low = min(c.low for c in impulse)
        impulse_range = max(c.high for c in impulse) - impulse_low
        min_impulse = max(abs(impulse[0].open) * 0.004, 0.08)
        if impulse_gain <= min_impulse or impulse_range <= min_impulse:
            return self._rejected("no impulse move", inputs)
        if any(b.close < b.open for b in impulse):
            return self._rejected("impulse candles not strong", inputs)

        if len(flag) > 5:
            return self._rejected("flag too long", inputs)
        if not flag:
            return self._rejected("missing flag consolidation", inputs)
        flag_range = max(c.high for c in flag) - min(c.low for c in flag)
        if flag_range > impulse_range * 0.45:
            return self._rejected("flag too wide", inputs)
        if min(c.low for c in flag) < impulse_low + (impulse_range * 0.25):
            return self._rejected("flag breakdown invalidation", inputs)
        lower_highs = sum(1 for idx in range(1, len(flag)) if flag[idx].high <= flag[idx - 1].high)
        tight_flag = flag_range <= max(abs(flag[0].close) * 0.003, 0.06)
        if lower_highs < max(len(flag) - 2, 1) and not tight_flag:
            return self._rejected("flag structure invalid", inputs)

        if breakout.close <= max(c.high for c in flag):
            return self._rejected("no breakout close", inputs)
        if breakout.close < ema20 or breakout.close < vwap or ema9 <= ema20:
            return self._rejected("price below EMA20", inputs)

        flag_vol_start = mean(c.volume for c in flag[: max(1, len(flag) // 2)])
        flag_vol_end = mean(c.volume for c in flag[max(1, len(flag) // 2) :])
        if flag_vol_end > flag_vol_start * 1.05:
            return self._rejected("volume increasing during flag", inputs)

        volume_avg = _avg_volume(candles[:-1] or candles)
        breakout_volume_ok = breakout.volume >= volume_avg
        confidence = 0.70 if breakout_volume_ok else 0.6
        tags = [
            "flag_structure",
            "volume_declining_in_flag",
            "breakout_volume_confirmed" if breakout_volume_ok else "breakout_volume_soft",
        ]

        flag_high = max(c.high for c in flag)
        flag_low = min(c.low for c in flag)

        rationale = (
            "Impulse move followed by controlled bull-flag consolidation and breakout above flag highs.\n"
            f"Impulse gain={impulse_gain:.2f}, impulse range={impulse_range:.2f}, flag range={flag_range:.2f}, "
            f"flag_high={flag_high:.2f}, flag_low={flag_low:.2f}."
        )
        result = self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=confidence,
            rationale=rationale,
            entry_zone="Break above flag high",
            stop_suggestion="Below flag low",
            target_suggestion="Measured move",
            setup_quality_tags=tags,
        )
        print(f"[PATTERN][BULL_FLAG] detected=True symbol={inputs.symbol}")
        return replace(
            result,
            setup_family_id="BULL_FLAG",
            trigger_type="BULL_FLAG_BREAKOUT",
            trigger_mode="BREAKOUT_CONTINUATION",
            trigger_level=float(flag_high),
            stop_level=float(flag_low),
            invalidation_level=float(flag_low),
            signal_class="ENTRY",
        )
