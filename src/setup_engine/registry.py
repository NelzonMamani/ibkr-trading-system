"""Canonical setup family registry and status model."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Type

from src.setup_engine.setup_families.breakouts import (
    ConsolidationBreakoutPattern,
    OpeningRangeBreakoutPattern,
    PremarketHighBreakPattern,
)
from src.setup_engine.setup_families.momentum import BullFlagPattern, MicroPullbackPattern
from src.setup_engine.setup_families.pullbacks import (
    AscendingTriangleBreakoutPattern,
    EmaPullbackPattern,
    FlatTopBreakoutPattern,
    HODBreakPattern,
    OpeningDrivePattern,
    PennantBreakPattern,
    RangeBreakoutPattern,
    SecondPullbackPattern,
    ThreeBarPullbackPattern,
    TrendContinuationStairStepPattern,
    VwapPullbackPattern,
)
from src.setup_engine.setup_families.ross_families import (
    ABCDPattern,
    CupHandlePattern,
    FailedOrbFakeoutPattern,
    FirstPullbackPattern,
    GapFillReversalPattern,
    GapGoPattern,
    HaltResumePattern,
    KeyLevelBreakPattern,
    MomentumReclaimPattern,
    OpeningFakeoutPattern,
    ParabolicExhaustionPattern,
)
from src.strategies.ross_momentum.patterns.pattern_base import PatternBase


class SetupImplementationStatus(str, Enum):
    TRADE_READY = "TRADE_READY"
    DISABLED = "DISABLED"
    SPEC_ONLY = "SPEC_ONLY"


@dataclass(frozen=True)
class SetupFamilyImplementation:
    setup_id: str
    pattern_cls: Type[PatternBase]
    status: SetupImplementationStatus
    reason: str = ""


CANONICAL_SETUP_REGISTRY: Dict[str, SetupFamilyImplementation] = {
    "GAP_GO": SetupFamilyImplementation("GAP_GO", GapGoPattern, SetupImplementationStatus.TRADE_READY),
    "ORB": SetupFamilyImplementation("ORB", OpeningRangeBreakoutPattern, SetupImplementationStatus.TRADE_READY),
    "FIRST_PULLBACK": SetupFamilyImplementation("FIRST_PULLBACK", FirstPullbackPattern, SetupImplementationStatus.TRADE_READY),
    "MICRO_PULLBACK": SetupFamilyImplementation("MICRO_PULLBACK", MicroPullbackPattern, SetupImplementationStatus.TRADE_READY),
    "BULL_FLAG": SetupFamilyImplementation("BULL_FLAG", BullFlagPattern, SetupImplementationStatus.TRADE_READY),
    "KEY_LEVEL_BREAK": SetupFamilyImplementation("KEY_LEVEL_BREAK", KeyLevelBreakPattern, SetupImplementationStatus.TRADE_READY),
    "ABCD": SetupFamilyImplementation("ABCD", ABCDPattern, SetupImplementationStatus.TRADE_READY),
    "CUP_HANDLE": SetupFamilyImplementation("CUP_HANDLE", CupHandlePattern, SetupImplementationStatus.TRADE_READY),
    "MOMENTUM_RECLAIM": SetupFamilyImplementation("MOMENTUM_RECLAIM", MomentumReclaimPattern, SetupImplementationStatus.TRADE_READY),
    "PREMARKET_HIGH_BREAK": SetupFamilyImplementation("PREMARKET_HIGH_BREAK", PremarketHighBreakPattern, SetupImplementationStatus.TRADE_READY),
    "HALT_RESUME": SetupFamilyImplementation("HALT_RESUME", HaltResumePattern, SetupImplementationStatus.TRADE_READY),
    "PARABOLIC_EXHAUSTION": SetupFamilyImplementation("PARABOLIC_EXHAUSTION", ParabolicExhaustionPattern, SetupImplementationStatus.TRADE_READY),
    "GAP_FILL": SetupFamilyImplementation("GAP_FILL", GapFillReversalPattern, SetupImplementationStatus.TRADE_READY),
    "GAP_CONTINUATION": SetupFamilyImplementation("GAP_CONTINUATION", GapGoPattern, SetupImplementationStatus.TRADE_READY),
    "OPENING_DRIVE": SetupFamilyImplementation("OPENING_DRIVE", OpeningDrivePattern, SetupImplementationStatus.TRADE_READY),
    "OPENING_FAKEOUT": SetupFamilyImplementation("OPENING_FAKEOUT", OpeningFakeoutPattern, SetupImplementationStatus.TRADE_READY),
    "CONSOLIDATION_BREAKOUT": SetupFamilyImplementation("CONSOLIDATION_BREAKOUT", ConsolidationBreakoutPattern, SetupImplementationStatus.TRADE_READY),
    "FLAT_TOP_BREAKOUT": SetupFamilyImplementation("FLAT_TOP_BREAKOUT", FlatTopBreakoutPattern, SetupImplementationStatus.TRADE_READY),
    "ASCENDING_TRIANGLE": SetupFamilyImplementation("ASCENDING_TRIANGLE", AscendingTriangleBreakoutPattern, SetupImplementationStatus.TRADE_READY),
    "PENNANT": SetupFamilyImplementation("PENNANT", PennantBreakPattern, SetupImplementationStatus.TRADE_READY),
    "RANGE_BREAK": SetupFamilyImplementation("RANGE_BREAK", RangeBreakoutPattern, SetupImplementationStatus.TRADE_READY),
    "HOD_BREAK": SetupFamilyImplementation("HOD_BREAK", HODBreakPattern, SetupImplementationStatus.TRADE_READY),
    "EMA_PULLBACK": SetupFamilyImplementation("EMA_PULLBACK", EmaPullbackPattern, SetupImplementationStatus.TRADE_READY),
    "VWAP_PULLBACK": SetupFamilyImplementation("VWAP_PULLBACK", VwapPullbackPattern, SetupImplementationStatus.TRADE_READY),
    "THREE_BAR_PULLBACK": SetupFamilyImplementation("THREE_BAR_PULLBACK", ThreeBarPullbackPattern, SetupImplementationStatus.TRADE_READY),
    "TREND_CONTINUATION_STAIR_STEP": SetupFamilyImplementation("TREND_CONTINUATION_STAIR_STEP", TrendContinuationStairStepPattern, SetupImplementationStatus.TRADE_READY),
    "SECOND_PULLBACK": SetupFamilyImplementation("SECOND_PULLBACK", SecondPullbackPattern, SetupImplementationStatus.TRADE_READY),
    "FAILED_ORB_FAKEOUT": SetupFamilyImplementation("FAILED_ORB_FAKEOUT", FailedOrbFakeoutPattern, SetupImplementationStatus.TRADE_READY),
}


def build_tradeable_patterns() -> list[PatternBase]:
    patterns: list[PatternBase] = []
    for spec in CANONICAL_SETUP_REGISTRY.values():
        if spec.status == SetupImplementationStatus.TRADE_READY:
            patterns.append(spec.pattern_cls())
    return patterns
