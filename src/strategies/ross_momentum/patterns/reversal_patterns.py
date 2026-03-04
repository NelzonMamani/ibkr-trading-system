"""Reversal/caution Ross patterns."""

from __future__ import annotations

from src.strategies.ross_momentum.patterns.pattern_base import PatternBase
from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult


class FailedBreakoutPattern(PatternBase):
    pattern_id = "P_FAILED_BREAKOUT"
    name = "Failed Breakout"
    family = PatternFamily.REVERSAL
    direction_bias = Direction.SHORT

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        level = inputs.levels.hod or inputs.levels.premarket_high
        if level is None:
            return self._rejected("missing reference level", inputs)
        if len(inputs.candles) < 3:
            return self._rejected("insufficient candles", inputs)
        previous = inputs.candles[-2]
        last = inputs.candles[-1]
        if previous.close <= level:
            return self._rejected("no prior breakout", inputs)
        if last.close >= level:
            return self._rejected("breakout still holding", inputs)
        confidence = 0.62
        rationale = (
            "Breakout failed and price reclaimed below key level.\n"
            f"Key level={level:.2f}, last close={last.close:.2f}."
        )
        return self._detected(
            inputs,
            direction=Direction.SHORT,
            confidence=confidence,
            rationale=rationale,
            entry_zone="Below failed breakout level",
            stop_suggestion="Above failed breakout level",
            target_suggestion="Back to VWAP / consolidation",
            setup_quality_tags=["failed_breakout", "avoid_entry"],
            risk_flags=["FAILED_BREAKOUT", "AVOID_ENTRY"],
        )
