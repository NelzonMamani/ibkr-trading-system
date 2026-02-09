"""StrategyBase adapter for Mean Reversion registry integration."""

from __future__ import annotations

from typing import Optional

from src.strategies.mean_reversion.adapters import policy_decision_to_strategy_decision
from src.strategies.mean_reversion.mean_reversion_strategy_policy import (
    MarketRegimeFacts,
    MeanReversionPolicyConfig,
    MeanReversionStrategyPolicy,
    ScannerFacts,
)
from src.strategies.strategy_base import StrategyBase
from src.strategies.strategy_contracts import (
    ExecutionMode,
    StrategyDecision,
    StrategyExecutionProfile,
    StrategyFoundationComponents,
    StrategyInput,
)


class MeanReversionStrategyAdapter(StrategyBase):
    strategy_id = "mean_reversion"
    strategy_name = "Mean Reversion"
    version = "1.0"
    foundation_components = StrategyFoundationComponents()
    execution_profile = StrategyExecutionProfile(
        supported_modes=[
            ExecutionMode.SIM,
            ExecutionMode.PAPER,
            ExecutionMode.READ_ONLY,
            ExecutionMode.LIVE,
        ]
    )

    def __init__(self, policy_config: Optional[MeanReversionPolicyConfig] = None) -> None:
        self._policy_config = policy_config or MeanReversionPolicyConfig()
        self._policy = MeanReversionStrategyPolicy(cfg=self._policy_config, risk_engine=None)

    def evaluate(self, symbol: str, inputs: StrategyInput) -> StrategyDecision:
        facts = self._facts_from_inputs(symbol, inputs)
        regime = MarketRegimeFacts()
        decision = self._policy.evaluate_symbol(facts, regime)
        return policy_decision_to_strategy_decision(
            decision,
            strategy_id=self.strategy_id,
        )

    @staticmethod
    def _facts_from_inputs(symbol: str, inputs: StrategyInput) -> ScannerFacts:
        key_levels = dict(inputs.market_context.key_levels or {})
        return ScannerFacts(
            symbol=symbol,
            last=float(inputs.market_context.price or 0.0),
            vwap=key_levels.get("vwap"),
            ema9=key_levels.get("ema9"),
            ema20=key_levels.get("ema20"),
            atr=key_levels.get("atr"),
            hod=key_levels.get("hod"),
            lod=key_levels.get("lod"),
            spread=inputs.market_context.spread,
            rvol=inputs.market_context.rvol,
            has_fresh_news=bool(inputs.news_context),
            minutes_since_open=None,
        )
