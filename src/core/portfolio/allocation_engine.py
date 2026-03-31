from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.config.config_resolver import get_config
from src.core.portfolio.allocation_policy import (
    ARBITRATION_APPROVE_NEW_ENTRY,
    ARBITRATION_APPROVE_SCALE_IN,
    ARBITRATION_DEFER_LOWER_PRIORITY,
    ARBITRATION_DENY_CRITICAL_DRIFT,
    ARBITRATION_DENY_GLOBAL_PORTFOLIO_CAP,
    ARBITRATION_DENY_INCOMPATIBLE_OPEN_POSITION,
    ARBITRATION_DENY_KILL_SWITCH,
    ARBITRATION_DENY_MAX_STRATEGY_POSITIONS,
    ARBITRATION_DENY_SCALE_IN_NOT_ALLOWED,
    ARBITRATION_DENY_STRATEGY_BUDGET,
    ARBITRATION_PASS_EXIT_REDUCTION,
    ArbitrationDecision,
    PortfolioAllocationSnapshot,
)
from src.core.portfolio.budget_registry import StrategyBudgetRegistry
from src.models.data_models import RiskDecision, TradeIntent


@dataclass(frozen=True)
class AllocationCandidate:
    candidate_id: str
    symbol: str
    strategy_name: str
    direction: str
    requested_trade_value: float
    confidence: float
    classification: str
    is_exit_reduction: bool


class PortfolioAllocationEngine:
    def __init__(self, budget_registry: StrategyBudgetRegistry):
        self._budget_registry = budget_registry

    def classify_candidate(self, intent: TradeIntent, open_positions: dict[str, tuple[str, str]]) -> tuple[str, bool]:
        action = str(getattr(intent, "intent_action", "ENTRY") or "ENTRY").upper()
        if action in {"EXIT", "REDUCE", "SCALE_OUT", "RISK_EXIT", "PROTECTIVE_EXIT"}:
            return "SCALE_OUT_HINT", True
        existing = open_positions.get(str(intent.symbol).upper())
        if existing is None:
            return "NEW_ENTRY", False
        existing_strategy, existing_direction = existing
        if existing_strategy == str(intent.strategy_name).lower() and existing_direction == str(intent.direction).upper():
            return "SCALE_IN", False
        return "UNCLASSIFIED", False

    def build_snapshot(
        self,
        *,
        total_exposure: float,
        kill_switch_active: bool,
        drift_detected: bool,
        strategy_exposure: dict[str, float],
        strategy_open_positions: dict[str, int],
    ) -> PortfolioAllocationSnapshot:
        portfolio_cap = float(get_config("LIFECYCLE_MAX_PORTFOLIO_EXPOSURE") or 1000.0)
        return PortfolioAllocationSnapshot(
            total_portfolio_exposure=float(total_exposure),
            remaining_portfolio_capacity=max(0.0, portfolio_cap - float(total_exposure)),
            total_open_positions=sum(strategy_open_positions.values()),
            per_strategy_exposure={k: float(v) for k, v in strategy_exposure.items()},
            per_strategy_open_positions={k: int(v) for k, v in strategy_open_positions.items()},
            kill_switch_active=kill_switch_active,
            drift_detected=drift_detected,
        )

    def arbitrate(
        self,
        *,
        candidates: Iterable[AllocationCandidate],
        snapshot: PortfolioAllocationSnapshot,
    ) -> list[ArbitrationDecision]:
        ordered = sorted(
            candidates,
            key=lambda c: (
                self._budget_registry.get_budget(c.strategy_name).priority_rank,
                0 if c.classification == "SCALE_IN" else 1,
                -float(c.confidence),
                str(c.symbol),
                str(c.candidate_id),
            ),
        )
        decisions: list[ArbitrationDecision] = []
        remaining_capacity = float(snapshot.remaining_portfolio_capacity)
        strategy_exposure = dict(snapshot.per_strategy_exposure)
        strategy_positions = dict(snapshot.per_strategy_open_positions)

        for candidate in ordered:
            budget = self._budget_registry.get_budget(candidate.strategy_name)
            before = remaining_capacity
            if candidate.is_exit_reduction:
                decisions.append(
                    ArbitrationDecision(
                        candidate_id=candidate.candidate_id,
                        symbol=candidate.symbol,
                        strategy_name=candidate.strategy_name,
                        requested_trade_value=candidate.requested_trade_value,
                        approved=True,
                        approval_type="FULL",
                        approved_trade_value=candidate.requested_trade_value,
                        reason_code=ARBITRATION_PASS_EXIT_REDUCTION,
                        rationale="Exit/reduction action bypasses capacity consumption.",
                        priority_rank=budget.priority_rank,
                        portfolio_capacity_before=before,
                        portfolio_capacity_after=before,
                        classification=candidate.classification,
                    )
                )
                continue
            if snapshot.kill_switch_active:
                decisions.append(self._deny(candidate, budget.priority_rank, before, ARBITRATION_DENY_KILL_SWITCH, "Kill switch active."))
                continue
            if snapshot.drift_detected:
                decisions.append(self._deny(candidate, budget.priority_rank, before, ARBITRATION_DENY_CRITICAL_DRIFT, "Critical lifecycle drift detected."))
                continue
            if not budget.enabled:
                decisions.append(self._deny(candidate, budget.priority_rank, before, ARBITRATION_DEFER_LOWER_PRIORITY, "Strategy budget disabled."))
                continue
            if candidate.classification == "SCALE_IN" and not budget.allow_scale_in:
                decisions.append(self._deny(candidate, budget.priority_rank, before, ARBITRATION_DENY_SCALE_IN_NOT_ALLOWED, "Scale-in disabled by strategy budget."))
                continue
            if candidate.classification == "UNCLASSIFIED":
                decisions.append(self._deny(candidate, budget.priority_rank, before, ARBITRATION_DENY_INCOMPATIBLE_OPEN_POSITION, "No compatible open lifecycle position."))
                continue
            if candidate.classification == "NEW_ENTRY" and not budget.allow_new_entries:
                decisions.append(self._deny(candidate, budget.priority_rank, before, ARBITRATION_DEFER_LOWER_PRIORITY, "New entries disabled for strategy."))
                continue
            if candidate.classification == "NEW_ENTRY" and strategy_positions.get(candidate.strategy_name, 0) >= int(budget.max_open_positions):
                decisions.append(self._deny(candidate, budget.priority_rank, before, ARBITRATION_DENY_MAX_STRATEGY_POSITIONS, "Max open positions reached."))
                continue

            projected_strategy = float(strategy_exposure.get(candidate.strategy_name, 0.0)) + candidate.requested_trade_value
            if projected_strategy > float(budget.max_gross_exposure):
                decisions.append(self._deny(candidate, budget.priority_rank, before, ARBITRATION_DENY_STRATEGY_BUDGET, "Requested value exceeds strategy budget."))
                continue
            if candidate.requested_trade_value > remaining_capacity:
                # Explicit deterministic defer for lower-priority losers once capacity is consumed.
                code = ARBITRATION_DENY_GLOBAL_PORTFOLIO_CAP if remaining_capacity <= 0 else ARBITRATION_DEFER_LOWER_PRIORITY
                decisions.append(self._deny(candidate, budget.priority_rank, before, code, "Insufficient portfolio capacity."))
                continue

            remaining_capacity = max(0.0, remaining_capacity - candidate.requested_trade_value)
            strategy_exposure[candidate.strategy_name] = projected_strategy
            if candidate.classification == "NEW_ENTRY":
                strategy_positions[candidate.strategy_name] = strategy_positions.get(candidate.strategy_name, 0) + 1
            decisions.append(
                ArbitrationDecision(
                    candidate_id=candidate.candidate_id,
                    symbol=candidate.symbol,
                    strategy_name=candidate.strategy_name,
                    requested_trade_value=candidate.requested_trade_value,
                    approved=True,
                    approval_type="FULL",
                    approved_trade_value=candidate.requested_trade_value,
                    reason_code=(ARBITRATION_APPROVE_SCALE_IN if candidate.classification == "SCALE_IN" else ARBITRATION_APPROVE_NEW_ENTRY),
                    rationale="Approved by deterministic portfolio allocation.",
                    priority_rank=budget.priority_rank,
                    portfolio_capacity_before=before,
                    portfolio_capacity_after=remaining_capacity,
                    classification=candidate.classification,
                )
            )
        return decisions

    @staticmethod
    def _deny(candidate: AllocationCandidate, priority_rank: int, before: float, code: str, rationale: str) -> ArbitrationDecision:
        return ArbitrationDecision(
            candidate_id=candidate.candidate_id,
            symbol=candidate.symbol,
            strategy_name=candidate.strategy_name,
            requested_trade_value=candidate.requested_trade_value,
            approved=False,
            approval_type="DENIED" if code != ARBITRATION_DEFER_LOWER_PRIORITY else "DEFERRED",
            approved_trade_value=0.0,
            reason_code=code,
            rationale=rationale,
            priority_rank=priority_rank,
            portfolio_capacity_before=before,
            portfolio_capacity_after=before,
            classification=candidate.classification,
        )


def candidate_from_decision(risk_decision: RiskDecision, intent: TradeIntent, classification: str, is_exit_reduction: bool) -> AllocationCandidate:
    quantity = int(getattr(intent, "quantity", None) or getattr(risk_decision, "max_position_size", 0) or 0)
    entry_price = float(getattr(intent, "entry_price", None) or getattr(intent, "stop_loss_price", None) or 0.0)
    requested_value = max(0.0, float(quantity) * max(0.0, entry_price))
    return AllocationCandidate(
        candidate_id=str(getattr(risk_decision, "intent_id", None) or getattr(intent, "decision_id", None) or f"{intent.symbol}:{intent.strategy_name}"),
        symbol=str(intent.symbol).upper(),
        strategy_name=str(intent.strategy_name).lower(),
        direction=str(intent.direction).upper(),
        requested_trade_value=requested_value,
        confidence=float(getattr(intent, "confidence", 0.0) or 0.0),
        classification=classification,
        is_exit_reduction=is_exit_reduction,
    )
