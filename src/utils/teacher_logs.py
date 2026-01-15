"""Teacher-style logs for strategy explainability."""

from __future__ import annotations

from typing import Iterable

from src.strategies.ross_momentum.patterns.pattern_evaluator import PatternEvaluationSummary
from src.strategies.strategy_contracts import StrategyDecision, TradeIntent


def log_strategy_header(strategy_name: str, symbol: str) -> None:
    print(f"[STRATEGY] {strategy_name} evaluating symbol={symbol}")


def log_pattern_summary(summary: PatternEvaluationSummary) -> None:
    detected = [result for result in summary.all_results if result.detected]
    print(
        f"[STRATEGY] Pattern summary: {len(detected)} detected / "
        f"{len(summary.all_results)} total"
    )
    if summary.best_long_setup:
        print(
            f"[STRATEGY] Best long: {summary.best_long_setup.pattern_name} "
            f"conf={summary.best_long_setup.confidence:.2f}"
        )
    if summary.best_short_setup:
        print(
            f"[STRATEGY] Best short: {summary.best_short_setup.pattern_name} "
            f"conf={summary.best_short_setup.confidence:.2f}"
        )
    if summary.conflict_flag:
        print("[STRATEGY] Conflict detected between long and short setups")
    if summary.veto_flags:
        print(f"[STRATEGY] Veto flags: {', '.join(summary.veto_flags)}")


def log_intent_summary(intents: Iterable[TradeIntent]) -> None:
    intents_list = list(intents)
    if not intents_list:
        print("[STRATEGY] No intents emitted")
        return
    for intent in intents_list:
        print(
            "[STRATEGY] Intent emitted "
            f"symbol={intent.symbol} direction={intent.direction.value} "
            f"entry={intent.entry_model} stop={intent.stop_model}"
        )


def log_decision(decision: StrategyDecision) -> None:
    print(
        f"[STRATEGY] Decision {decision.decision_type.value} "
        f"conf={decision.confidence:.2f} rationale={decision.rationale_text}"
    )
