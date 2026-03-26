"""E22 strategy scalability and arbitration layer (additive, default-off)."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Dict, Iterable, List, Sequence, Tuple

from src.models.data_models import TradeIntent


_DIRECTION_PRIORITY = {
    "EXIT": 0,
    "REDUCE": 1,
    "LONG": 2,
    "SHORT": 2,
    "NEUTRAL": 3,
}


@dataclass(frozen=True)
class E22PolicyConfig:
    enabled: bool = False
    max_strategies_per_cycle: int = 20
    max_intents_per_cycle: int = 200
    max_positions_per_cycle: int = 50
    max_position_per_symbol: int = 1
    symbol_exclusivity: bool = True
    strategy_priority: Dict[str, int] = field(default_factory=dict)
    strategy_max_intents: Dict[str, int] = field(default_factory=dict)
    merge_policy: str = "WINNER_TAKE_ALL"


@dataclass(frozen=True)
class SuppressedIntent:
    strategy_name: str
    symbol: str
    direction: str
    reason_code: str
    context: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ArbitrationDecisionArtifact:
    policy: Dict[str, object]
    allowed_intents: List[TradeIntent]
    suppressed_intents: List[SuppressedIntent]
    suppression_counts_by_reason_code: Dict[str, int]
    strategy_order: List[str]


class StrategyScheduler:
    """Deterministically orders strategies and enforces strategy-count budget."""

    @staticmethod
    def schedule(strategy_names: Iterable[str], config: E22PolicyConfig) -> Tuple[List[str], List[SuppressedIntent]]:
        names = sorted(set(strategy_names), key=lambda name: (-config.strategy_priority.get(name, 0), name))
        allowed_names = names[: max(config.max_strategies_per_cycle, 0)]
        suppressed: List[SuppressedIntent] = []
        for name in names[max(config.max_strategies_per_cycle, 0) :]:
            suppressed.append(
                SuppressedIntent(
                    strategy_name=name,
                    symbol="*",
                    direction="*",
                    reason_code="BUDGET_DENY",
                    context={"cap": "max_strategies_per_cycle", "max": config.max_strategies_per_cycle},
                )
            )
        return allowed_names, suppressed


class IntentArbitrator:
    """Deterministic arbitration with reason-coded suppression events."""

    @staticmethod
    def _sort_key(intent: TradeIntent, config: E22PolicyConfig) -> tuple:
        stable_hash = hashlib.sha256(
            f"{intent.strategy_name}|{intent.symbol}|{intent.direction}|{intent.trader_type}".encode("utf-8")
        ).hexdigest()
        return (
            -config.strategy_priority.get(intent.strategy_name, 0),
            _DIRECTION_PRIORITY.get(intent.direction, 99),
            -(intent.confidence or 0.0),
            intent.symbol,
            intent.strategy_name,
            intent.trader_type,
            stable_hash,
        )

    def arbitrate(self, intents: Sequence[TradeIntent], config: E22PolicyConfig) -> ArbitrationDecisionArtifact:
        scheduled_strategies, scheduler_suppressed = StrategyScheduler.schedule(
            (intent.strategy_name for intent in intents),
            config,
        )
        allowed_strategy_set = set(scheduled_strategies)
        ordered = sorted(intents, key=lambda intent: self._sort_key(intent, config))

        allowed: List[TradeIntent] = []
        suppressed: List[SuppressedIntent] = list(scheduler_suppressed)
        per_strategy_count: Dict[str, int] = {}
        seen_symbols: set[str] = set()
        symbol_position_budget: Dict[str, int] = {}

        for intent in ordered:
            if intent.strategy_name not in allowed_strategy_set:
                suppressed.append(
                    SuppressedIntent(
                        strategy_name=intent.strategy_name,
                        symbol=intent.symbol,
                        direction=intent.direction,
                        reason_code="BUDGET_DENY",
                        context={"policy": "strategy_not_scheduled"},
                    )
                )
                continue

            strategy_limit = config.strategy_max_intents.get(intent.strategy_name)
            current_strategy_count = per_strategy_count.get(intent.strategy_name, 0)
            if strategy_limit is not None and current_strategy_count >= strategy_limit:
                suppressed.append(
                    SuppressedIntent(
                        strategy_name=intent.strategy_name,
                        symbol=intent.symbol,
                        direction=intent.direction,
                        reason_code="BUDGET_DENY",
                        context={"cap": "strategy_max_intents", "max": strategy_limit},
                    )
                )
                continue

            if config.symbol_exclusivity and intent.symbol in seen_symbols:
                suppressed.append(
                    SuppressedIntent(
                        strategy_name=intent.strategy_name,
                        symbol=intent.symbol,
                        direction=intent.direction,
                        reason_code="SYMBOL_EXCLUSIVITY_CONFLICT",
                        context={"policy": "symbol_exclusivity", "tie_break": "priority_direction_confidence_hash"},
                    )
                )
                continue

            requested_quantity = int(getattr(intent, "quantity", None) or getattr(intent, "requested_quantity", None) or 1)
            if requested_quantity <= 0:
                requested_quantity = 1

            used_symbol_budget = symbol_position_budget.get(intent.symbol, 0)
            if used_symbol_budget + requested_quantity > max(config.max_position_per_symbol, 0):
                suppressed.append(
                    SuppressedIntent(
                        strategy_name=intent.strategy_name,
                        symbol=intent.symbol,
                        direction=intent.direction,
                        reason_code="SYMBOL_POSITION_LIMIT",
                        context={
                            "cap": "max_position_per_symbol",
                            "max": config.max_position_per_symbol,
                            "requested": requested_quantity,
                            "already_allocated": used_symbol_budget,
                            "merge_policy": config.merge_policy,
                        },
                    )
                )
                continue

            if len(allowed) >= max(config.max_intents_per_cycle, 0):
                suppressed.append(
                    SuppressedIntent(
                        strategy_name=intent.strategy_name,
                        symbol=intent.symbol,
                        direction=intent.direction,
                        reason_code="BUDGET_DENY",
                        context={"cap": "max_intents_per_cycle", "max": config.max_intents_per_cycle},
                    )
                )
                continue

            if len({allowed_intent.symbol for allowed_intent in allowed}) >= max(config.max_positions_per_cycle, 0):
                suppressed.append(
                    SuppressedIntent(
                        strategy_name=intent.strategy_name,
                        symbol=intent.symbol,
                        direction=intent.direction,
                        reason_code="PORTFOLIO_EXPOSURE_LIMIT",
                        context={"cap": "max_positions_per_cycle", "max": config.max_positions_per_cycle},
                    )
                )
                continue

            allowed.append(intent)
            per_strategy_count[intent.strategy_name] = current_strategy_count + 1
            seen_symbols.add(intent.symbol)
            symbol_position_budget[intent.symbol] = used_symbol_budget + requested_quantity

        suppression_counts: Dict[str, int] = {}
        for item in suppressed:
            suppression_counts[item.reason_code] = suppression_counts.get(item.reason_code, 0) + 1

        return ArbitrationDecisionArtifact(
            policy={
                "enabled": config.enabled,
                "max_strategies_per_cycle": config.max_strategies_per_cycle,
                "max_intents_per_cycle": config.max_intents_per_cycle,
                "max_positions_per_cycle": config.max_positions_per_cycle,
                "max_position_per_symbol": config.max_position_per_symbol,
                "symbol_exclusivity": config.symbol_exclusivity,
                "merge_policy": config.merge_policy,
            },
            allowed_intents=allowed,
            suppressed_intents=suppressed,
            suppression_counts_by_reason_code=dict(sorted(suppression_counts.items())),
            strategy_order=scheduled_strategies,
        )


def apply_e22_arbitration_layer(
    intents: Sequence[TradeIntent],
    config: E22PolicyConfig,
) -> tuple[List[TradeIntent], ArbitrationDecisionArtifact | None]:
    if not config.enabled:
        return list(intents), None
    artifact = IntentArbitrator().arbitrate(intents, config)
    return list(artifact.allowed_intents), artifact

