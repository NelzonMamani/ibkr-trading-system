from __future__ import annotations

from dataclasses import dataclass

from src.config.config_resolver import ConfigResolutionError
from src.config.config_resolver import get_config
from src.core.portfolio.allocation_policy import StrategyCapitalBudget


DEFAULT_BUDGET = StrategyCapitalBudget(
    strategy_name="DEFAULT",
    enabled=True,
    max_gross_exposure=1000.0,
    max_open_positions=1,
    priority_rank=999,
    allow_scale_in=False,
    allow_new_entries=True,
    notes="Safe fallback budget.",
)


@dataclass
class StrategyBudgetRegistry:
    by_strategy: dict[str, StrategyCapitalBudget]
    fallback_budget: StrategyCapitalBudget

    def get_budget(self, strategy_name: str) -> StrategyCapitalBudget:
        key = str(strategy_name or "").strip().lower()
        budget = self.by_strategy.get(key)
        if budget is not None:
            return budget
        return StrategyCapitalBudget(
            strategy_name=key or self.fallback_budget.strategy_name,
            enabled=self.fallback_budget.enabled,
            max_gross_exposure=self.fallback_budget.max_gross_exposure,
            max_open_positions=self.fallback_budget.max_open_positions,
            priority_rank=self.fallback_budget.priority_rank,
            allow_scale_in=self.fallback_budget.allow_scale_in,
            allow_new_entries=self.fallback_budget.allow_new_entries,
            notes=self.fallback_budget.notes,
        )


def load_strategy_budget_registry() -> StrategyBudgetRegistry:
    def _safe_get(name: str, default):
        try:
            return get_config(name)
        except ConfigResolutionError:
            print(f"[PORTFOLIO][BUDGET] default_applied key={name} value={default}")
            return default

    raw_budgets = _safe_get("STRATEGY_CAPITAL_BUDGETS", {}) or {}
    priority_order = _safe_get("STRATEGY_PRIORITY_ORDER", ["ross_momentum"]) or ["ross_momentum"]
    max_open_positions = _safe_get("STRATEGY_MAX_OPEN_POSITIONS", {}) or {}
    allow_scale_in = _safe_get("STRATEGY_ALLOW_SCALE_IN", {}) or {}

    fallback_raw = raw_budgets.get("default") if isinstance(raw_budgets, dict) else None
    fallback_budget = StrategyCapitalBudget(
        strategy_name="default",
        enabled=bool((fallback_raw or {}).get("enabled", True)),
        max_gross_exposure=float((fallback_raw or {}).get("max_gross_exposure", 1000.0)),
        max_open_positions=int((fallback_raw or {}).get("max_open_positions", 1)),
        priority_rank=int((fallback_raw or {}).get("priority_rank", 999)),
        allow_scale_in=bool((fallback_raw or {}).get("allow_scale_in", False)),
        allow_new_entries=bool((fallback_raw or {}).get("allow_new_entries", True)),
        notes=(fallback_raw or {}).get("notes", "Config missing; conservative fallback applied."),
    )

    strategies = set(priority_order)
    if isinstance(raw_budgets, dict):
        strategies.update(k for k in raw_budgets.keys() if k != "default")

    by_strategy: dict[str, StrategyCapitalBudget] = {}
    if not strategies:
        print("[PORTFOLIO][BUDGET] default_applied strategy=ross_momentum")
        by_strategy["ross_momentum"] = StrategyCapitalBudget(
            strategy_name="ross_momentum",
            enabled=True,
            max_gross_exposure=1000.0,
            max_open_positions=1,
            priority_rank=1,
            allow_scale_in=False,
            allow_new_entries=True,
            notes="Default Ross budget applied because config missing.",
        )
        return StrategyBudgetRegistry(by_strategy=by_strategy, fallback_budget=fallback_budget)

    priority_map = {str(name).strip().lower(): i + 1 for i, name in enumerate(priority_order)}
    for strategy in sorted(str(s).strip().lower() for s in strategies if str(s).strip()):
        raw = raw_budgets.get(strategy, {}) if isinstance(raw_budgets, dict) else {}
        by_strategy[strategy] = StrategyCapitalBudget(
            strategy_name=strategy,
            enabled=bool(raw.get("enabled", True)),
            max_gross_exposure=float(raw.get("max_gross_exposure", fallback_budget.max_gross_exposure)),
            max_open_positions=int(max_open_positions.get(strategy, raw.get("max_open_positions", fallback_budget.max_open_positions))),
            priority_rank=int(raw.get("priority_rank", priority_map.get(strategy, fallback_budget.priority_rank))),
            allow_scale_in=bool(allow_scale_in.get(strategy, raw.get("allow_scale_in", fallback_budget.allow_scale_in))),
            allow_new_entries=bool(raw.get("allow_new_entries", True)),
            notes=raw.get("notes"),
        )
    if "ross_momentum" not in by_strategy:
        print("[PORTFOLIO][BUDGET] default_applied strategy=ross_momentum")
        by_strategy["ross_momentum"] = StrategyCapitalBudget(
            strategy_name="ross_momentum",
            enabled=True,
            max_gross_exposure=1000.0,
            max_open_positions=1,
            priority_rank=1,
            allow_scale_in=False,
            allow_new_entries=True,
            notes="Default Ross budget applied.",
        )

    return StrategyBudgetRegistry(by_strategy=by_strategy, fallback_budget=fallback_budget)
