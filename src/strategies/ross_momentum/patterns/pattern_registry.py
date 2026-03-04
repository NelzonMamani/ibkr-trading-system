"""Registry of enabled Ross Momentum patterns."""

from __future__ import annotations

from typing import List

from src.config.config_resolver import get_config

from src.strategies.ross_momentum.patterns.additional_patterns import (
    build_additional_heuristic_patterns,
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
            FailedBreakoutPattern(),
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
