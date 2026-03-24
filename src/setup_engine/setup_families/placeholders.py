"""Shared placeholder setup families for policy reconciliation compatibility."""

from __future__ import annotations

from src.strategies.ross_momentum.patterns.pattern_base import PatternBase
from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult


class _PlaceholderPattern(PatternBase):
    pattern_id = ""
    name = ""
    family = PatternFamily.CANDLE
    direction_bias = Direction.NEUTRAL
    is_placeholder = True

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        return self._rejected("placeholder_family_not_enabled", inputs, direction=Direction.NEUTRAL)


class EngulfingPattern(_PlaceholderPattern):
    pattern_id = "C_ENGULFING"
    name = "Engulfing"


class LongUpperWickPattern(_PlaceholderPattern):
    pattern_id = "C_LONG_UPPER_WICK"
    name = "Long Upper Wick"


class MarubozuPattern(_PlaceholderPattern):
    pattern_id = "C_MARUBOZU"
    name = "Marubozu"


class ThreeSoldiersCrowsPattern(_PlaceholderPattern):
    pattern_id = "C_THREE_SOLDIERS_CROWS"
    name = "Three Soldiers / Crows"


class ClimaxTopPattern(_PlaceholderPattern):
    pattern_id = "P_CLIMAX_TOP"
    name = "Climax Top"
    family = PatternFamily.REVERSAL
    direction_bias = Direction.SHORT


class FailedOrbFakeoutPattern(_PlaceholderPattern):
    pattern_id = "P_FAILED_ORB_FAKEOUT"
    name = "Failed ORB Fakeout"
    family = PatternFamily.REVERSAL


class GapFillReversalPattern(_PlaceholderPattern):
    pattern_id = "P_GAP_FILL_REVERSAL"
    name = "Gap Fill Reversal"
    family = PatternFamily.REVERSAL


class VolumeClimaxPattern(_PlaceholderPattern):
    pattern_id = "P_VOLUME_CLIMAX"
    name = "Volume Climax"
    family = PatternFamily.VOL_EVENT
