from __future__ import annotations

from dataclasses import is_dataclass
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any


def catalogue_strategy_entries() -> list[tuple[str, str]]:
    repo_root = Path(__file__).resolve().parents[2]
    strategies_dir = repo_root / "TRADING_OS_MASTER_CATALOGUE" / "03_STRATEGIES"
    entries: list[tuple[str, str]] = []
    for child in sorted(strategies_dir.iterdir()):
        if not child.is_dir() or "_" not in child.name:
            continue
        strategy_id, slug = child.name.split("_", 1)
        if "P01" <= strategy_id <= "P20":
            entries.append((strategy_id, slug.lower()))
    return entries


def _resolve_policy_module(slug: str) -> ModuleType:
    module_name = f"src.strategies.{slug}.strategy_policy"
    if slug == "mean_reversion":
        module_name = "src.strategies.mean_reversion.strategy_policy"
    return import_module(module_name)


def load_strategy_policy(slug: str) -> Any:
    module = _resolve_policy_module(slug)
    if hasattr(module, "POLICY"):
        return getattr(module, "POLICY")

    preferred = [
        "RossMomentumPolicy",
        "StatisticalIntradayMomentumPolicy",
        "MeanReversionStrategyPolicy",
        "StrategyPolicy",
    ]
    for cls_name in preferred:
        cls = getattr(module, cls_name, None)
        if cls is not None:
            return cls()

    for value in module.__dict__.values():
        if is_dataclass(value) and hasattr(value, "name"):
            return value

    raise AssertionError(f"No strategy policy object found in module {module.__name__}")


def stock_selection_of(policy: Any) -> Any:
    if hasattr(policy, "stock_selection"):
        return getattr(policy, "stock_selection")
    return policy


def universe_marker(policy: Any) -> str | None:
    selection = stock_selection_of(policy)
    universe = getattr(selection, "universe", None)
    if universe is not None and hasattr(universe, "source"):
        source = getattr(universe, "source")
        return str(getattr(source, "value", source))
    source = selection.get("universe_source") if isinstance(selection, dict) else getattr(selection, "universe_source", None)
    if source is None:
        source = getattr(policy, "universe_source", None)
    if source is None:
        return None
    return str(getattr(source, "value", source))
