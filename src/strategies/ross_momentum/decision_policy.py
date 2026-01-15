"""Trade intent generation policy for Ross Momentum."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from src.strategies.ross_momentum.patterns.pattern_evaluator import PatternEvaluationSummary
from src.strategies.ross_momentum.patterns.pattern_types import Direction
from src.strategies.strategy_contracts import Direction as IntentDirection
from src.strategies.strategy_contracts import TimeInForcePolicy, TradeIntent


@dataclass(frozen=True)
class IntentPolicyConfig:
    min_confidence: float = 0.6


def build_trade_intents(
    strategy_id: str,
    symbol: str,
    summary: PatternEvaluationSummary,
    config: IntentPolicyConfig | None = None,
) -> List[TradeIntent]:
    config = config or IntentPolicyConfig()
    intents: List[TradeIntent] = []
    if summary.conflict_flag:
        return intents

    for setup in [summary.best_long_setup, summary.best_short_setup]:
        if setup is None:
            continue
        if setup.confidence < config.min_confidence:
            continue
        direction = (
            IntentDirection.LONG if setup.direction == Direction.LONG else IntentDirection.SHORT
        )
        intent_id = f"{strategy_id}:{symbol}:{setup.pattern_name.replace(' ', '_')}"
        invalidations = []
        if summary.veto_flags:
            invalidations.append("veto_flags_present")
        intents.append(
            TradeIntent(
                intent_id=intent_id,
                symbol=symbol,
                direction=direction,
                entry_model=setup.entry_zone or "Breakout trigger",
                stop_model=setup.stop_suggestion or "Structure-based stop",
                target_model=setup.target_suggestion,
                time_in_force_policy=TimeInForcePolicy.DAY,
                invalidations=invalidations,
                rationale_text=setup.rationale_text,
                risk_flags=setup.risk_flags,
            )
        )

    return intents
