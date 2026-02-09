"""Abstract strategy base for deterministic evaluation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable, List

from src.strategies.strategy_contracts import StrategyDecision, StrategyInput, StrategyRiskPayload


@dataclass(frozen=True)
class StrategyMetadata:
    strategy_id: str
    strategy_name: str
    version: str
    description: str | None = None


class StrategyBase(ABC):
    strategy_id: str
    strategy_name: str
    version: str
    description: str | None = None

    @classmethod
    def metadata(cls) -> StrategyMetadata:
        """Return canonical strategy metadata."""
        return StrategyMetadata(
            strategy_id=cls.strategy_id,
            strategy_name=cls.strategy_name,
            version=cls.version,
            description=getattr(cls, "description", None),
        )

    def get_metadata(self) -> StrategyMetadata:
        """Return canonical strategy metadata for this instance."""
        return self.__class__.metadata()

    def initialise(self, context: dict | None = None) -> None:
        """Hook for strategy initialisation (stateless by default)."""

    @abstractmethod
    def evaluate(self, symbol: str, inputs: StrategyInput) -> StrategyDecision:
        """Evaluate a symbol deterministically and return a StrategyDecision."""

    def summarise_cycle(self, results: Iterable[StrategyDecision]) -> str:
        """Return a deterministic summary string for a cycle."""
        decisions: List[StrategyDecision] = list(results)
        return (
            f"{self.strategy_name} cycle summary: {len(decisions)} symbols evaluated"
        )

    def to_risk_payload(self, decision: StrategyDecision) -> StrategyRiskPayload:
        """Shape the Strategy → Risk handoff payload."""
        return StrategyRiskPayload(
            strategy_id=self.strategy_id,
            symbol=decision.symbol,
            intents=decision.intents,
            decision_type=decision.decision_type,
            confidence=decision.confidence,
            rationale_text=decision.rationale_text,
            risk_flags=decision.risk_flags,
        )
