"""Shared pullback and continuation setup family implementations."""

from __future__ import annotations

from src.strategies.ross_momentum.patterns.pattern_base import PatternBase
from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.strategy_contracts import SessionContext


class _StructuredLongPattern(PatternBase):
    pattern_id = ""
    name = ""
    family = PatternFamily.BREAKOUT
    direction_bias = Direction.LONG
    trigger_name = "break_of_pattern_resistance"

    def _session_valid(self, inputs: PatternInputs) -> bool:
        return True

    def _structural_valid(self, inputs: PatternInputs) -> tuple[bool, str, float | None, float | None]:
        candles = inputs.candles
        if len(candles) < 5:
            return False, "insufficient candles", None, None
        structure = candles[-5:-1]
        trigger = candles[-1]
        trigger_level = max(c.high for c in structure)
        stop_level = min(c.low for c in structure)
        if trigger.close <= trigger_level:
            return False, "no break above structure", trigger_level, stop_level
        if (trigger_level - stop_level) <= 0:
            return False, "invalid range", trigger_level, stop_level
        return True, "ok", trigger_level, stop_level

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        if not self._session_valid(inputs):
            return self._rejected("session_incompatible", inputs, session_valid=False)
        ok, reason, trigger_level, stop_level = self._structural_valid(inputs)
        if not ok:
            return self._rejected(reason, inputs, structural_notes=[self.name])
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=0.63,
            rationale=f"{self.name} structure and breakout trigger confirmed.",
            setup_quality_tags=[self.pattern_id.lower(), "structure_confirmed"],
            trigger_type=self.trigger_name,
            trigger_level=trigger_level,
            entry_reference=f"break>{trigger_level:.4f}",
            stop_reference=f"below_structure_low<{stop_level:.4f}",
            invalidation_reference=f"close_below<{stop_level:.4f}",
            required_confirmations=["volume_context_ok", "spread_ok"],
            structural_notes=[f"trigger_level={trigger_level:.4f}", f"stop_level={stop_level:.4f}"],
        )


class RangeBreakoutPattern(_StructuredLongPattern):
    pattern_id = "P_RANGE_BREAKOUT"
    name = "Range / Rectangle Breakout"
    trigger_name = "break_of_pattern_resistance"


class FlatTopBreakoutPattern(_StructuredLongPattern):
    pattern_id = "P_FLAT_TOP_BREAKOUT"
    name = "Flat Top Breakout"
    trigger_name = "break_of_pattern_resistance"


class AscendingTriangleBreakoutPattern(_StructuredLongPattern):
    pattern_id = "P_ASCENDING_TRIANGLE_BREAKOUT"
    name = "Ascending Triangle Breakout"
    trigger_name = "break_of_pattern_resistance"


class PennantBreakPattern(_StructuredLongPattern):
    pattern_id = "P_PENNANT_BREAK"
    name = "Pennant Break"
    trigger_name = "break_of_pattern_resistance"


class EmaPullbackPattern(_StructuredLongPattern):
    pattern_id = "P_EMA_PULLBACK"
    name = "EMA Pullback"
    family = PatternFamily.PULLBACK
    trigger_name = "reclaim_and_hold"

    def _structural_valid(self, inputs: PatternInputs) -> tuple[bool, str, float | None, float | None]:
        ema9 = inputs.indicators.ema9
        if ema9 is None:
            return False, "missing_ema9", None, None
        if len(inputs.candles) < 4:
            return False, "insufficient candles", None, None
        candles = inputs.candles[-4:]
        if min(c.low for c in candles[:-1]) > ema9:
            return False, "no_pullback_to_ema", ema9, min(c.low for c in candles)
        if candles[-1].close <= ema9:
            return False, "reclaim_not_confirmed", ema9, min(c.low for c in candles)
        return True, "ok", ema9, min(c.low for c in candles)


class VwapPullbackPattern(_StructuredLongPattern):
    pattern_id = "P_VWAP_PULLBACK"
    name = "VWAP Pullback"
    family = PatternFamily.PULLBACK
    trigger_name = "reclaim_and_hold"

    def _structural_valid(self, inputs: PatternInputs) -> tuple[bool, str, float | None, float | None]:
        vwap = inputs.indicators.vwap
        if vwap is None:
            return False, "missing_vwap", None, None
        if len(inputs.candles) < 4:
            return False, "insufficient candles", None, None
        candles = inputs.candles[-4:]
        if min(c.low for c in candles[:-1]) > vwap:
            return False, "no_pullback_to_vwap", vwap, min(c.low for c in candles)
        if candles[-1].close <= vwap:
            return False, "reclaim_not_confirmed", vwap, min(c.low for c in candles)
        return True, "ok", vwap, min(c.low for c in candles)


class ThreeBarPullbackPattern(_StructuredLongPattern):
    pattern_id = "P_THREE_BAR_PULLBACK"
    name = "Three-Bar Pullback"
    family = PatternFamily.PULLBACK
    trigger_name = "break_of_pullback_high"

    def _structural_valid(self, inputs: PatternInputs) -> tuple[bool, str, float | None, float | None]:
        if len(inputs.candles) < 5:
            return False, "insufficient candles", None, None
        bars = inputs.candles[-5:]
        pullback = bars[1:4]
        if not all(c.close <= c.open for c in pullback):
            return False, "not_three_bar_pullback", None, None
        trigger_level = max(c.high for c in pullback)
        stop_level = min(c.low for c in pullback)
        if bars[-1].close <= trigger_level:
            return False, "trigger_not_broken", trigger_level, stop_level
        return True, "ok", trigger_level, stop_level


class TrendContinuationStairStepPattern(_StructuredLongPattern):
    pattern_id = "P_TREND_CONTINUATION_STAIR_STEP"
    name = "Trend Continuation (Stair-Step)"
    trigger_name = "break_of_pattern_resistance"

    def _structural_valid(self, inputs: PatternInputs) -> tuple[bool, str, float | None, float | None]:
        if len(inputs.candles) < 5:
            return False, "insufficient candles", None, None
        bars = inputs.candles[-5:]
        lows = [c.low for c in bars[:-1]]
        if not (lows[0] <= lows[1] <= lows[2] <= lows[3]):
            return False, "higher_lows_not_present", None, None
        trigger_level = max(c.high for c in bars[:-1])
        stop_level = lows[-1]
        if bars[-1].close <= trigger_level:
            return False, "no_break_of_stair_step_resistance", trigger_level, stop_level
        return True, "ok", trigger_level, stop_level


class SecondPullbackPattern(_StructuredLongPattern):
    pattern_id = "P_SECOND_PULLBACK"
    name = "Second Pullback"
    family = PatternFamily.PULLBACK
    trigger_name = "break_of_pullback_high"

    def _structural_valid(self, inputs: PatternInputs) -> tuple[bool, str, float | None, float | None]:
        if len(inputs.candles) < 6:
            return False, "insufficient candles", None, None
        bars = inputs.candles[-6:]
        down_bars = [idx for idx, c in enumerate(bars[:-1]) if c.close <= c.open]
        if len(down_bars) < 2:
            return False, "second_pullback_missing", None, None
        second = down_bars[-1]
        trigger_level = max(c.high for c in bars[second: -1])
        stop_level = min(c.low for c in bars[second: -1])
        if bars[-1].close <= trigger_level:
            return False, "trigger_not_broken", trigger_level, stop_level
        return True, "ok", trigger_level, stop_level


class LiquiditySweepReclaimPattern(_StructuredLongPattern):
    pattern_id = "P_LIQUIDITY_SWEEP_RECLAIM"
    name = "Liquidity Sweep Reclaim"


class HODBreakPattern(_StructuredLongPattern):
    pattern_id = "P_HOD_BREAK"
    name = "High of Day Break"
    trigger_name = "break_of_hod"

    def _session_valid(self, inputs: PatternInputs) -> bool:
        return inputs.session_context == SessionContext.REGULAR

    def _structural_valid(self, inputs: PatternInputs) -> tuple[bool, str, float | None, float | None]:
        hod = inputs.levels.hod
        if hod is None:
            return False, "missing_hod", None, None
        if not inputs.candles:
            return False, "insufficient candles", hod, None
        trigger = inputs.candles[-1]
        stop_level = min(c.low for c in inputs.candles[-3:])
        if trigger.close <= hod:
            return False, "hod_not_broken", hod, stop_level
        return True, "ok", hod, stop_level


class OpeningDrivePattern(_StructuredLongPattern):
    pattern_id = "P_OPENING_DRIVE"
    name = "Opening Drive"
    trigger_name = "break_above_level"

    def _session_valid(self, inputs: PatternInputs) -> bool:
        return inputs.session_context == SessionContext.REGULAR

    def _structural_valid(self, inputs: PatternInputs) -> tuple[bool, str, float | None, float | None]:
        if len(inputs.candles) < 5:
            return False, "insufficient candles", None, None
        bars = inputs.candles[-5:]
        if not all(c.close >= c.open for c in bars[:-1]):
            return False, "opening_drive_not_persistent", None, None
        trigger_level = max(c.high for c in bars[:-1])
        stop_level = min(c.low for c in bars[:-1])
        if bars[-1].close <= trigger_level:
            return False, "trigger_not_broken", trigger_level, stop_level
        return True, "ok", trigger_level, stop_level
