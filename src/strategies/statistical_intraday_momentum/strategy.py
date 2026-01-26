"""StrategyBase adapter for Statistical Intraday Momentum."""

from __future__ import annotations

from src.strategies.statistical_intraday_momentum.strategy_policy import (
    StatisticalIntradayMomentumPolicy,
)
from src.strategies.strategy_base import StrategyBase
from src.strategies.strategy_contracts import (
    DecisionType,
    StrategyDecision,
    StrategyInput,
)


class StatisticalIntradayMomentumStrategy(StrategyBase):
    strategy_id = "statistical_intraday_momentum"
    strategy_name = "StatisticalIntradayMomentum"
    version = "1.0"

    def __init__(self, policy: StatisticalIntradayMomentumPolicy | None = None) -> None:
        self._policy = policy or StatisticalIntradayMomentumPolicy()

    def evaluate(self, symbol: str, inputs: StrategyInput) -> StrategyDecision:
        print(
            "[STAT][STRATEGY] Evaluating statistical intraday momentum "
            f"symbol={symbol} session={inputs.session_context.value}"
        )
        return StrategyDecision(
            symbol=symbol,
            strategy_id=self.strategy_id,
            decision_type=DecisionType.NO_ACTION,
            confidence=0.0,
            rationale_text="Statistical strategy wiring-only placeholder.",
            risk_flags=["READINESS_ONLY"],
            intents=[],
        )
