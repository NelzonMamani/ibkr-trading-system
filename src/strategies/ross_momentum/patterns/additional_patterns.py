"""Optional heuristic placeholder patterns for Ross Momentum.

These are intentionally disabled by default because they are simplistic and can
false-positive. Enable only for explicit experimentation.
"""

from __future__ import annotations

from src.strategies.ross_momentum.patterns.pattern_base import PatternBase
from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult


class _SimpleLongPattern(PatternBase):
    """Heuristic placeholder: detects any green candle as LONG.

    This is intentionally naive and should not be used in production decisions.
    """

    name = "Simple Long Placeholder"
    family = PatternFamily.BREAKOUT
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        if not inputs.candles:
            return self._rejected("insufficient candles", inputs)
        last = inputs.candles[-1]
        if last.close <= last.open:
            return self._rejected("last candle not green", inputs)
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=0.51,
            rationale=(
                "Heuristic placeholder fired because the last candle is green. "
                "This is not a production-grade Ross setup and is for experimentation only."
            ),
            setup_quality_tags=["HEURISTIC_PLACEHOLDER", "EXPERIMENT_ONLY"],
            risk_flags=["UNSAFE_HEURISTIC"],
        )


def build_additional_heuristic_patterns() -> list[PatternBase]:
    """Factory for optional heuristic placeholder patterns."""
    return [_SimpleLongPattern()]
