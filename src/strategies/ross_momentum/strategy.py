# strategy.py
"""Ross Cameron Retail Confirmation Momentum strategy."""

from __future__ import annotations

from dataclasses import replace
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



def _resolve_ross_pattern_cadence(phase: str) -> tuple[str, str, bool]:
    normalized = (phase or "").upper()
    mapping = {
        "RTH_OPEN": ("1m", "10s", True),
        "RTH_MID": ("3m", "30s", True),
        "RTH_LATE": ("5m", "1m", True),
        "PRE": ("1m", "10s", True),
        "AH": ("5m", "1m", False),
        "OVN": ("5m", "1m", False),
        "CLOSED": ("5m", "1m", False),
        "WEEKEND": ("5m", "1m", False),
    }
    return mapping.get(normalized, ("1m", "10s", False))


def _resolve_session_phase(inputs: StrategyInput) -> str:
    if inputs.news_context and isinstance(inputs.news_context, dict):
        phase = inputs.news_context.get("session_phase")
        if phase:
            return str(phase).upper()
    session = getattr(inputs, "session_context", None)
    if session and hasattr(session, "value"):
        value = str(session.value).upper()
        if value == "REGULAR":
            return "RTH_OPEN"
        if value == "AFTER":
            return "AH"
        return value
    return "PRE"



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
    phase: str,
    structure_tf: str,
    trigger_tf: str,
) -> None:
    print(
        "[ROSS][SETUP_EVAL] "
        f"symbol={symbol} "
        f"pattern={pattern_name} "
        f"scanner_rvol={scanner_rvol} "
        f"gap_pct={gap_pct} "
        f"hod_pct={hod_pct} "
        f"volume={volume} "
        f"phase={phase} "
        f"structure_tf={structure_tf} "
        f"trigger_tf={trigger_tf} "
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

        session_phase = _resolve_session_phase(inputs)
        structure_tf, trigger_tf, pattern_supported = _resolve_ross_pattern_cadence(session_phase)
        print(
            "[ROSS][CADENCE] "
            f"phase={session_phase} structure_tf={structure_tf} trigger_tf={trigger_tf}"
        )
        if not pattern_supported:
            print(
                "[ROSS][CADENCE][WARN] "
                f"phase={session_phase} pattern_support=limited execution_disabled=true"
            )
        pattern_inputs = [replace(item, timeframe=structure_tf) for item in inputs.pattern_inputs]
        summary = self._evaluator.evaluate(pattern_inputs)
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
                phase=session_phase,
                structure_tf=structure_tf,
                trigger_tf=trigger_tf,
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
