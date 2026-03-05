"""Registry of enabled Ross Momentum setup families."""

from __future__ import annotations

from typing import List

from src.config.config_resolver import get_config
from src.setup_engine.setup_families import (
    AscendingTriangleBreakoutPattern,
    BullFlagPattern,
    VolumeClimaxPattern,
    ThreeSoldiersCrowsPattern,
    MarubozuPattern,
    LongUpperWickPattern,
    GapFillReversalPattern,
    EngulfingPattern,
    ClimaxTopPattern,
    ConsolidationBreakoutPattern,
    EmaPullbackPattern,
    FailedBreakoutPattern,
    FailedOrbFakeoutPattern,
    FlatTopBreakoutPattern,
    HODBreakPattern,
    LiquiditySweepReclaimPattern,
    MicroPullbackPattern,
    OpeningDrivePattern,
    OpeningRangeBreakoutPattern,
    PennantBreakPattern,
    PremarketHighBreakPattern,
    RangeBreakoutPattern,
    SecondPullbackPattern,
    ThreeBarPullbackPattern,
    TrendContinuationStairStepPattern,
    VwapPullbackPattern,
)
from src.strategies.ross_momentum.patterns.pattern_base import PatternBase
from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import PatternResult


def build_additional_heuristic_patterns() -> List[PatternBase]:
    """Optional experimental families; kept empty for deterministic runtime behavior."""
    return []


class RossPatternRegistry:
    def __init__(self) -> None:
        self._patterns: List[PatternBase] = [
            PremarketHighBreakPattern(),
            OpeningRangeBreakoutPattern(),
            MicroPullbackPattern(),
            BullFlagPattern(),
            ConsolidationBreakoutPattern(),
            RangeBreakoutPattern(),
            FlatTopBreakoutPattern(),
            AscendingTriangleBreakoutPattern(),
            PennantBreakPattern(),
            EmaPullbackPattern(),
            VwapPullbackPattern(),
            ThreeBarPullbackPattern(),
            TrendContinuationStairStepPattern(),
            SecondPullbackPattern(),
            LiquiditySweepReclaimPattern(),
            HODBreakPattern(),
            OpeningDrivePattern(),
            FailedBreakoutPattern(),
            EngulfingPattern(),
            LongUpperWickPattern(),
            MarubozuPattern(),
            ThreeSoldiersCrowsPattern(),
            ClimaxTopPattern(),
            FailedOrbFakeoutPattern(),
            GapFillReversalPattern(),
            VolumeClimaxPattern(),
        ]

        if get_config("ROSS_ENABLE_ADDITIONAL_HEURISTIC_PATTERNS"):
            print(
                "[ROSS][WARN] Enabling additional heuristic placeholder patterns. "
                "These are experimental and may false-positive."
            )
            self._patterns.extend(build_additional_heuristic_patterns())

    @property
    def patterns(self) -> List[PatternBase]:
        return list(self._patterns)

    def run(self, inputs: PatternInputs) -> List[PatternResult]:
        return [pattern.evaluate(inputs) for pattern in self._patterns]

    @property
    def pattern_ids(self) -> List[str]:
        return [getattr(pattern, "pattern_id", "") or pattern.name for pattern in self._patterns]
