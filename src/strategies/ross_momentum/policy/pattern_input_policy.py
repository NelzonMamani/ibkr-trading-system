"""Ross pattern input policy section."""

from __future__ import annotations

from dataclasses import dataclass

from src.strategies.ross_momentum.strategy_policy import POLICY_V2


@dataclass(frozen=True)
class PatternInputPolicy:
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]

    @classmethod
    def from_policy_v2(cls) -> "PatternInputPolicy":
        requirements = POLICY_V2.data_requirements
        return cls(
            required_fields=tuple(requirements.required_fields),
            optional_fields=tuple(requirements.optional_fields),
        )
