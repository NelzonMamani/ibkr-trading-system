"""Pattern base class and logging helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult


class PatternBase(ABC):
    name: str
    pattern_id: str = ""
    family: PatternFamily
    direction_bias: Direction

    @abstractmethod
    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        """Evaluate pattern deterministically and return a PatternResult."""

    def _rejected(
        self,
        reason: str,
        inputs: PatternInputs,
        confidence: float = 0.0,
        direction: Optional[Direction] = None,
    ) -> PatternResult:
        dir_value = direction or self.direction_bias
        rationale = f"Rejected: {reason}"
        print(
            f"[PATTERN] {inputs.symbol} {self.name} not detected (reason={reason})"
        )
        return PatternResult(
            setup_id=self.pattern_id or self.name,
            pattern_name=self.name,
            pattern_family=self.family,
            detected=False,
            direction=dir_value,
            confidence=confidence,
            setup_quality_tags=[],
            tags=[],
            entry_zone=None,
            stop_suggestion=None,
            target_suggestion=None,
            rationale_text=rationale,
            risk_flags=[],
            data_quality_flags=inputs.data_quality_flags,
            rejection_reason=reason,
        )

    def _detected(
        self,
        inputs: PatternInputs,
        direction: Direction,
        confidence: float,
        rationale: str,
        entry_zone: Optional[str] = None,
        stop_suggestion: Optional[str] = None,
        target_suggestion: Optional[str] = None,
        setup_quality_tags: Optional[list[str]] = None,
        risk_flags: Optional[list[str]] = None,
    ) -> PatternResult:
        setup_quality_tags = setup_quality_tags or []
        risk_flags = risk_flags or []
        vwap = inputs.indicators.vwap
        if vwap is not None and inputs.candles:
            last_close = inputs.candles[-1].close
            setup_quality_tags.append("VWAP_ABOVE" if last_close >= vwap else "VWAP_BELOW")
        print(
            f"[PATTERN] {inputs.symbol} {self.name} DETECTED {direction.value} "
            f"conf={confidence:.2f}"
        )
        for line in rationale.split("\n"):
            print(f"  - {line}")
        return PatternResult(
            setup_id=self.pattern_id or self.name,
            pattern_name=self.name,
            pattern_family=self.family,
            detected=True,
            direction=direction,
            confidence=confidence,
            setup_quality_tags=setup_quality_tags,
            tags=setup_quality_tags,
            entry_zone=entry_zone,
            stop_suggestion=stop_suggestion,
            target_suggestion=target_suggestion,
            rationale_text=rationale,
            risk_flags=risk_flags,
            data_quality_flags=inputs.data_quality_flags,
        )
