"""Canonical Bull Flag structure and breakout implementation."""

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


class BullFlagPattern(PatternBase):
    pattern_id = "P_BULL_FLAG"
    name = "Bull Flag"
    family = PatternFamily.PULLBACK
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        return self._evaluate(inputs, require_breakout=True)

    def evaluate_formation(self, inputs: PatternInputs) -> PatternResult:
        """Parent monitoring only; a valid formation is never entry permission."""
        return self._evaluate(inputs, require_breakout=False)

    def _evaluate(self, inputs: PatternInputs, *, require_breakout: bool) -> PatternResult:
        candles = inputs.candles
        if len(candles) < (9 if require_breakout else 8):
            return self._rejected("insufficient candles", inputs)
        ema9 = inputs.indicators.ema9
        ema20 = inputs.indicators.ema20
        vwap = inputs.indicators.vwap
        if ema9 is None or ema20 is None or vwap is None:
            return self._rejected("missing trend indicators", inputs)

        recent = candles[-9:] if require_breakout else candles[-8:]
        impulse = recent[:3]
        flag = recent[3:-1] if require_breakout else recent[3:]
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

        if require_breakout and breakout.close <= max(c.high for c in flag):
            return self._rejected("no breakout close", inputs)
        if breakout.close < ema20 or breakout.close < vwap or ema9 <= ema20:
            return self._rejected("price below EMA20", inputs)

        flag_vol_start = mean(c.volume for c in flag[: max(1, len(flag) // 2)])
        flag_vol_end = mean(c.volume for c in flag[max(1, len(flag) // 2) :])
        if flag_vol_end > flag_vol_start * 1.05:
            return self._rejected("volume increasing during flag", inputs)

        volume_avg = _avg_volume(candles[:-1] or candles)
        breakout_volume_ok = require_breakout and breakout.volume >= volume_avg
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
        if not require_breakout:
            rationale = "Bull flag formation armed; no entry confirmation. " + rationale.split("\n", 1)[1]
            tags = ["flag_structure", "volume_declining_in_flag", "parent_armed"]
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
            signal_class="ENTRY" if require_breakout else "CONTEXT",
            non_entry_signal=not require_breakout,
            setup_metadata={
                "parent_state": "CONFIRMED" if require_breakout else "ARMED",
                "symbol": inputs.symbol,
                "session": inputs.session_label or str(inputs.session_context.value),
                "structure_timeframe": inputs.primary_timeframe,
                "origin_timestamp": getattr(impulse[0], "timestamp", None),
                "structure_completed_timestamp": getattr(flag[-1], "timestamp", None),
                "flag_high": float(flag_high), "flag_low": float(flag_low),
                "impulse_high": float(max(c.high for c in impulse)),
                "impulse_low": float(impulse_low),
                "timeframe_provenance": dict(inputs.timeframe_provenance or {}),
            },
        )
