"""Shared pullback and continuation setup family implementations."""

from __future__ import annotations

from src.strategies.common.patterns.pattern_hod_break import detect_hod_break
from src.strategies.common.patterns.pattern_ema_pullback import detect_ema_pullback
from src.strategies.common.patterns.pattern_flat_top_breakout import detect_flat_top_breakout
from src.strategies.common.patterns.pattern_opening_drive import detect_opening_drive
from src.strategies.common.patterns.pattern_vwap_pullback import detect_vwap_pullback
from src.strategies.common.patterns.pattern_trend_continuation_stair_step import (
    detect_trend_continuation_stair_step,
)
from src.strategies.ross_momentum.patterns.pattern_base import PatternBase
from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult


class _SimpleLongPattern(PatternBase):
    pattern_id = ""
    name = ""
    family = PatternFamily.BREAKOUT
    direction_bias = Direction.LONG

    def _check(self, inputs: PatternInputs) -> tuple[bool, str]:
        if len(inputs.candles) < 5:
            return False, "insufficient candles"
        return True, "ok"

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        ok, reason = self._check(inputs)
        if not ok:
            return self._rejected(reason, inputs)
        last = inputs.candles[-1]
        prev = inputs.candles[-2]
        if last.close <= prev.close:
            return self._rejected("no continuation close", inputs)
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=0.58,
            rationale=f"{self.name} heuristic continuation trigger.",
            setup_quality_tags=[self.pattern_id.lower()],
        )


class RangeBreakoutPattern(_SimpleLongPattern):
    pattern_id = "P_RANGE_BREAKOUT"
    name = "Range / Rectangle Breakout"


class FlatTopBreakoutPattern(_SimpleLongPattern):
    pattern_id = "P_FLAT_TOP_BREAKOUT"
    name = "Flat Top Breakout"

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        return detect_flat_top_breakout(inputs)


class AscendingTriangleBreakoutPattern(_SimpleLongPattern):
    pattern_id = "P_ASCENDING_TRIANGLE_BREAKOUT"
    name = "Ascending Triangle Breakout"


class PennantBreakPattern(_SimpleLongPattern):
    pattern_id = "P_PENNANT_BREAK"
    name = "Pennant Break"


class EmaPullbackPattern(_SimpleLongPattern):
    pattern_id = "P_EMA_PULLBACK"
    name = "EMA Pullback"
    family = PatternFamily.PULLBACK

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        return detect_ema_pullback(inputs)


class VwapPullbackPattern(_SimpleLongPattern):
    pattern_id = "P_VWAP_PULLBACK"
    name = "VWAP Pullback"
    family = PatternFamily.PULLBACK

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        return detect_vwap_pullback(inputs)


class ThreeBarPullbackPattern(_SimpleLongPattern):
    pattern_id = "P_THREE_BAR_PULLBACK"
    name = "Three-Bar Pullback"
    family = PatternFamily.PULLBACK


class TrendContinuationStairStepPattern(_SimpleLongPattern):
    pattern_id = "P_TREND_CONTINUATION_STAIR_STEP"
    name = "Trend Continuation (Stair-Step)"

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        return detect_trend_continuation_stair_step(inputs)


class SecondPullbackPattern(_SimpleLongPattern):
    pattern_id = "P_SECOND_PULLBACK"
    name = "Second Pullback"
    family = PatternFamily.PULLBACK


class LiquiditySweepReclaimPattern(_SimpleLongPattern):
    pattern_id = "P_LIQUIDITY_SWEEP_RECLAIM"
    name = "Liquidity Sweep Reclaim"


class HODBreakPattern(_SimpleLongPattern):
    pattern_id = "P_HOD_BREAK"
    name = "High of Day Break"

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        return detect_hod_break(inputs)


class OpeningDrivePattern(_SimpleLongPattern):
    pattern_id = "P_OPENING_DRIVE"
    name = "Opening Drive"

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        return detect_opening_drive(inputs)
