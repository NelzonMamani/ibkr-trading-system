"""Pattern base class and logging helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


def _slugify(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")

from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult


class PatternBase(ABC):
    name: str
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
            symbol=inputs.symbol,
            setup_id=_slugify(self.name),
            detected=False,
            direction=dir_value,
            confidence=confidence,
            rationale_text=rationale,
            entry_zone=None,
            stop_suggestion=None,
            target_suggestion=None,
            setup_quality_tags=[],
            risk_flags=[],
            data_quality_flags=list(inputs.data_quality_flags),
            rejection_reason=reason,
            pattern_name=self.name,
            pattern_family=self.family,
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
        if inputs.candles and inputs.indicators.vwap is not None:
            last_close = inputs.candles[-1].close
            vwap_tag = "VWAP_ABOVE" if last_close >= inputs.indicators.vwap else "VWAP_BELOW"
            if vwap_tag not in setup_quality_tags:
                setup_quality_tags.append(vwap_tag)
        print(
            f"[PATTERN] {inputs.symbol} {self.name} DETECTED {direction.value} "
            f"conf={confidence:.2f}"
        )
        for line in rationale.split("\n"):
            print(f"  - {line}")
        return PatternResult(
            symbol=inputs.symbol,
            setup_id=_slugify(self.name),
            detected=True,
            direction=direction,
            confidence=confidence,
            rationale_text=rationale,
            entry_zone=entry_zone,
            stop_suggestion=stop_suggestion,
            target_suggestion=target_suggestion,
            setup_quality_tags=setup_quality_tags,
            risk_flags=risk_flags,
            data_quality_flags=list(inputs.data_quality_flags),
            pattern_name=self.name,
            pattern_family=self.family,
        )
