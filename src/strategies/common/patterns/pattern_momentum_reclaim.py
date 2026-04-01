"""Shared MOMENTUM_RECLAIM pattern detection."""

from __future__ import annotations

from src.setup_engine.setup_families.ross_families import MomentumReclaimPattern
from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import PatternResult


def detect_momentum_reclaim(inputs: PatternInputs) -> PatternResult:
    """Detect momentum reclaim continuation via canonical shared setup implementation."""
    return MomentumReclaimPattern().evaluate(inputs)

