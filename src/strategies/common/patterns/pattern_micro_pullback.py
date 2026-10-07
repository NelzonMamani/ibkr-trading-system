"""Compatibility entry point for the existing armed-readiness profile."""
from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import PatternResult


def detect_micro_pullback(inputs: PatternInputs) -> PatternResult:
    # Lazy import avoids package registry cycles; no second detector algorithm.
    from src.setup_engine.setup_families.micro_pullback import MicroPullbackPattern
    return MicroPullbackPattern().evaluate_readiness(inputs)
