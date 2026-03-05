"""Shared setup family implementations."""

from src.setup_engine.setup_families.breakouts import (
    ConsolidationBreakoutPattern,
    OpeningRangeBreakoutPattern,
    PremarketHighBreakPattern,
)
from src.setup_engine.setup_families.momentum import BullFlagPattern, MicroPullbackPattern
from src.setup_engine.setup_families.placeholders import (
    ClimaxTopPattern,
    EngulfingPattern,
    FailedOrbFakeoutPattern,
    GapFillReversalPattern,
    LongUpperWickPattern,
    MarubozuPattern,
    ThreeSoldiersCrowsPattern,
    VolumeClimaxPattern,
)
from src.setup_engine.setup_families.pullbacks import (
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
from src.setup_engine.setup_families.reversals import FailedBreakoutPattern

__all__ = [
    "VolumeClimaxPattern",
    "ThreeSoldiersCrowsPattern",
    "MarubozuPattern",
    "LongUpperWickPattern",
    "GapFillReversalPattern",
    "FailedOrbFakeoutPattern",
    "EngulfingPattern",
    "ClimaxTopPattern",
    "AscendingTriangleBreakoutPattern",
    "BullFlagPattern",
    "ConsolidationBreakoutPattern",
    "EmaPullbackPattern",
    "FailedBreakoutPattern",
    "FlatTopBreakoutPattern",
    "HODBreakPattern",
    "LiquiditySweepReclaimPattern",
    "MicroPullbackPattern",
    "OpeningDrivePattern",
    "OpeningRangeBreakoutPattern",
    "PennantBreakPattern",
    "PremarketHighBreakPattern",
    "RangeBreakoutPattern",
    "SecondPullbackPattern",
    "ThreeBarPullbackPattern",
    "TrendContinuationStairStepPattern",
    "VwapPullbackPattern",
]
