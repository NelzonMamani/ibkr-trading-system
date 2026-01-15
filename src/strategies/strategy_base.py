"""Abstract strategy base for deterministic evaluation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, List

from src.strategies.strategy_contracts import StrategyDecision, StrategyInput, StrategyRiskPayload


class StrategyBase(ABC):
    strategy_id: str
    strategy_name: str
    version: str

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
