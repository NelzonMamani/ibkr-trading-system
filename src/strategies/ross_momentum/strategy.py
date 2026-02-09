# strategy.py
"""Ross Cameron Retail Confirmation Momentum strategy."""

from __future__ import annotations

from typing import List

from src.strategies.ross_momentum.decision_policy import (
    IntentPolicyConfig,
    build_trade_intents,
)
from src.strategies.ross_momentum.patterns.pattern_evaluator import PatternEvaluator
from src.strategies.strategy_base import StrategyBase
from src.strategies.strategy_contracts import (
    DecisionType,
    ExecutionMode,
    StrategyDecision,
    StrategyExecutionProfile,
    StrategyFoundationComponents,
    StrategyInput,
)
from src.utils.teacher_logs import (
    log_decision,
    log_intent_summary,
    log_pattern_summary,
    log_strategy_header,
)


class RossMomentumStrategy(StrategyBase):
    strategy_id = "ross_momentum"
    strategy_name = "Ross Momentum"
    version = "2.1"
    foundation_components = StrategyFoundationComponents()
    execution_profile = StrategyExecutionProfile(
        supported_modes=[
            ExecutionMode.SIM,
            ExecutionMode.PAPER,
            ExecutionMode.READ_ONLY,
            ExecutionMode.LIVE,
        ]
    )

    def __init__(self, policy_config: IntentPolicyConfig | None = None) -> None:
        self._evaluator = PatternEvaluator()
        self._policy_config = policy_config or IntentPolicyConfig()

    def evaluate(self, symbol: str, inputs: StrategyInput) -> StrategyDecision:
        log_strategy_header(self.strategy_name, symbol)
        if not inputs.pattern_inputs:
            decision = StrategyDecision(
                symbol=symbol,
                strategy_id=self.strategy_id,
                decision_type=DecisionType.NO_ACTION,
                confidence=0.0,
                rationale_text="No pattern inputs provided",
                risk_flags=["missing_pattern_inputs"],
                intents=[],
            )
            log_decision(decision)
            return decision

        summary = self._evaluator.evaluate(inputs.pattern_inputs)
        log_pattern_summary(summary)
        intents = build_trade_intents(
            strategy_id=self.strategy_id,
            symbol=symbol,
            summary=summary,
            config=self._policy_config,
        )
        confidence = max(
            [result.confidence for result in summary.all_results if result.detected],
            default=0.0,
        )
        decision_type = (
            DecisionType.EMIT_INTENT
            if intents
            else DecisionType.WATCH
            if summary.best_long_setup or summary.best_short_setup
            else DecisionType.NO_ACTION
        )
        rationale = summary.combined_rationale_text
        decision = StrategyDecision(
            symbol=symbol,
            strategy_id=self.strategy_id,
            decision_type=decision_type,
            confidence=confidence,
            rationale_text=rationale,
            risk_flags=summary.veto_flags,
            intents=intents,
        )
        log_intent_summary(intents)
        log_decision(decision)
        return decision
