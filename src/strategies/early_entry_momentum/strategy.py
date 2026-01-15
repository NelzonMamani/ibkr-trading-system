"""Early Entry Momentum Continuation strategy."""

from __future__ import annotations

from src.strategies.ross_momentum.decision_policy import (
    IntentPolicyConfig,
    build_trade_intents,
)
from src.strategies.ross_momentum.patterns.pattern_evaluator import PatternEvaluator
from src.strategies.strategy_base import StrategyBase
from src.strategies.strategy_contracts import DecisionType, StrategyDecision, StrategyInput
from src.utils.teacher_logs import (
    log_decision,
    log_intent_summary,
    log_pattern_summary,
    log_strategy_header,
)


class EarlyEntryMomentumStrategy(StrategyBase):
    strategy_id = "Early_Entry_Momentum_Continuation"
    strategy_name = "Early Entry Momentum Continuation"
    version = "1.0"

    def __init__(self) -> None:
        self._evaluator = PatternEvaluator()
        self._policy_config = IntentPolicyConfig(min_confidence=0.55)

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
