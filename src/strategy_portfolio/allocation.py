"""Capital allocation governance utilities (not wired)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .reason_codes import ReasonCode


@dataclass(frozen=True)
class AllocationConfig:
    strategy_id: str
    allocation_pct: float
    max_allocation_usd: float | None = None
    enabled: bool = True


@dataclass(frozen=True)
class AllocationResult:
    strategy_id: str
    enabled: bool
    budget_usd: float
    reason_codes: list[str] = field(default_factory=list)


def compute_global_risk_budget(
    account_equity: float,
    global_max_risk_pct: float | None = None,
    global_max_risk_usd: float | None = None,
) -> float:
    if global_max_risk_pct is None and global_max_risk_usd is None:
        raise ValueError("Must supply global_max_risk_pct or global_max_risk_usd")
    if global_max_risk_usd is not None:
        return max(global_max_risk_usd, 0.0)
    if global_max_risk_pct is None:
        raise ValueError("global_max_risk_pct is required when usd cap is absent")
    return max(account_equity * global_max_risk_pct, 0.0)


def allocate(
    global_budget_usd: float,
    configs: list[AllocationConfig],
) -> list[AllocationResult]:
    results: list[AllocationResult] = []
    for config in configs:
        if not config.enabled:
            results.append(
                AllocationResult(
                    strategy_id=config.strategy_id,
                    enabled=False,
                    budget_usd=0.0,
                    reason_codes=[ReasonCode.ALLOCATION_DISABLED.value],
                )
            )
            continue

        budget = max(global_budget_usd * config.allocation_pct, 0.0)
        if config.max_allocation_usd is not None:
            budget = min(budget, max(config.max_allocation_usd, 0.0))

        results.append(
            AllocationResult(
                strategy_id=config.strategy_id,
                enabled=True,
                budget_usd=budget,
            )
        )
    return results
