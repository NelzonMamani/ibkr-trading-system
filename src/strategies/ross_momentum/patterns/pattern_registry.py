"""Registry of enabled Ross Momentum patterns."""

from __future__ import annotations

from typing import List

from src.strategies.ross_momentum.patterns.additional_patterns import (
    AscendingTriangleBreakoutPattern,
    EmaPullbackPattern,
    FlatTopBreakoutPattern,
    HODBreakPattern,
    LiquiditySweepReclaimPattern,
    OpeningDrivePattern,
    PennantBreakPattern,
    RangeBreakoutPattern,
    SecondPullbackPattern,
    ThreeBarPullbackPattern,
    TrendContinuationStairStepPattern,
    VwapPullbackPattern,
)
from src.strategies.ross_momentum.patterns.breakout_patterns import (
    ConsolidationBreakoutPattern,
    OpeningRangeBreakoutPattern,
    PremarketHighBreakPattern,
)
from src.strategies.ross_momentum.patterns.momentum_patterns import (
    BullFlagPattern,
    MicroPullbackPattern,
)
from src.strategies.ross_momentum.patterns.pattern_base import PatternBase
from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import PatternResult
from src.strategies.ross_momentum.patterns.reversal_patterns import FailedBreakoutPattern


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
        ]

    @property
    def patterns(self) -> List[PatternBase]:
        return list(self._patterns)

    def run(self, inputs: PatternInputs) -> List[PatternResult]:
        return [pattern.evaluate(inputs) for pattern in self._patterns]

    @property
    def pattern_ids(self) -> List[str]:
        return [getattr(pattern, "pattern_id", "") or pattern.name for pattern in self._patterns]
