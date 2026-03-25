"""Canonical setup -> pattern -> confirm -> trigger -> intent pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.strategies.ross_momentum.pattern_engine import PatternEvaluation
from src.strategies.ross_momentum.setup_engine import SetupEvaluation
from src.strategies.ross_momentum.trigger_engine import TriggerEvaluation


@dataclass(frozen=True)
class ConfirmationResult:
    confirmations_passed: list[str] = field(default_factory=list)
    confirmations_failed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    block_trade: bool = False


@dataclass(frozen=True)
class NoSignalDecision:
    symbol: str
    failed_stage: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


def evaluate_confirmations(setup: SetupEvaluation, pattern: PatternEvaluation, market_context: Any) -> ConfirmationResult:
    passed: list[str] = []
    failed: list[str] = []
    warnings: list[str] = []

    if pattern.impulse_high is not None and pattern.impulse_low is not None and pattern.impulse_high > pattern.impulse_low:
        passed.append("IMPULSE_EXPANSION")
    else:
        failed.append("NO_IMPULSE_EXPANSION")

    if pattern.volume_assessment == "PULLBACK_LIGHT":
        passed.append("PULLBACK_VOLUME_LIGHTER")
    else:
        failed.append("PULLBACK_VOLUME_NOT_LIGHT")

    price = float(getattr(market_context, "price", 0.0) or 0.0)
    structure_level = pattern.pullback_high or 0.0
    if price >= structure_level:
        passed.append("PRICE_AT_OR_ABOVE_STRUCTURE")
    else:
        warnings.append("PRICE_BELOW_TRIGGER_LEVEL")

    spread = float(getattr(market_context, "spread", 0.0) or 0.0)
    if spread > max(0.25, price * 0.01):
        failed.append("SPREAD_TOO_WIDE")

    for disqualifier in setup.disqualifiers:
        if disqualifier in {"SPREAD_TOO_WIDE"}:
            failed.append(disqualifier)

    return ConfirmationResult(
        confirmations_passed=passed,
        confirmations_failed=sorted(set(failed)),
        warnings=warnings,
        block_trade=bool(failed),
    )


def build_no_signal(symbol: str, stage: str, reason: str, details: dict[str, Any] | None = None) -> NoSignalDecision:
    return NoSignalDecision(symbol=symbol, failed_stage=stage, reason=reason, details=details or {})


def summarize_cycle(results: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        "focus_symbols_evaluated": len(results),
        "setup_families_detected": 0,
        "patterns_detected": 0,
        "triggers_fired": 0,
        "intents_emitted": 0,
        "dominant_failure_stage": "NONE",
        "dominant_rejection_reason": "NONE",
    }
    failures: dict[str, int] = {}
    reasons: dict[str, int] = {}
    for item in results:
        if item.get("setup_detected"):
            summary["setup_families_detected"] += 1
        if item.get("pattern_detected"):
            summary["patterns_detected"] += 1
        if item.get("triggered"):
            summary["triggers_fired"] += 1
        if item.get("intent_emitted"):
            summary["intents_emitted"] += 1
        stage = item.get("failed_stage")
        reason = item.get("reason")
        if stage:
            failures[stage] = failures.get(stage, 0) + 1
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1
    if failures:
        summary["dominant_failure_stage"] = max(failures, key=failures.get)
    if reasons:
        summary["dominant_rejection_reason"] = max(reasons, key=reasons.get)
    return summary


def trigger_to_terminal(trigger: TriggerEvaluation) -> tuple[str, str]:
    if trigger.triggered:
        return "NONE", "NONE"
    return "TRIGGER", trigger.rejection_reason or "TRIGGER_NOT_FIRED"
