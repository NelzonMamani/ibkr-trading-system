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




def _reason_code(raw_reason: str | None) -> str:
    reason = (raw_reason or "").upper()
    if "HOD" in reason and ("NOT" in reason or "FAIL" in reason or "REJECT" in reason):
        return "HOD_NOT_BROKEN"
    if "VOLUME" in reason:
        return "INSUFFICIENT_VOLUME"
    if "SPREAD" in reason:
        return "SPREAD_TOO_WIDE"
    if "RVOL" in reason or "RELATIVE VOLUME" in reason:
        return "RVOL_TOO_LOW"
    return "STRUCTURE_INVALID"


def _log_setup_eval(
    *,
    symbol: str,
    pattern_name: str,
    scanner_rvol: float | None,
    gap_pct: float | None,
    hod_pct: float | None,
    volume: float | None,
    decision: str,
    reason: str,
) -> None:
    print(
        "[ROSS][SETUP_EVAL] "
        f"symbol={symbol} "
        f"pattern={pattern_name} "
        f"scanner_rvol={scanner_rvol} "
        f"gap_pct={gap_pct} "
        f"hod_pct={hod_pct} "
        f"volume={volume} "
        f"decision={decision} "
        f"reason={reason}"
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

        scanner_rvol = getattr(inputs.market_context, "rvol", None)
        gap_pct = None
        hod_pct = None
        volume = getattr(inputs.market_context, "volume", None)
        if inputs.news_context:
            gap_pct = inputs.news_context.get("gap_pct")
            hod_pct = inputs.news_context.get("hod_pct")

        for result in summary.all_results:
            decision = "TRIGGER" if result.detected else "REJECT"
            reason = "SETUP_DETECTED" if result.detected else _reason_code(result.rejection_reason)
            _log_setup_eval(
                symbol=symbol,
                pattern_name=result.pattern_name,
                scanner_rvol=scanner_rvol,
                gap_pct=gap_pct,
                hod_pct=hod_pct,
                volume=volume,
                decision=decision,
                reason=reason,
            )
            if result.detected:
                print(
                    "[ROSS][SETUP_TRIGGER] "
                    f"symbol={symbol} pattern={result.pattern_name} reason={reason}"
                )
            else:
                print(
                    "[ROSS][SETUP_REJECT] "
                    f"symbol={symbol} pattern={result.pattern_name} reason={reason}"
                )

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
