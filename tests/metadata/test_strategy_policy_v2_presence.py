from __future__ import annotations

import importlib
from pathlib import Path


def _catalogue_slugs() -> list[str]:
    root = Path("TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES")
    strategy_dirs = sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith("P"))
    slugs: list[str] = []
    for directory in strategy_dirs:
        strategy_id, raw_slug = directory.name.split("_", 1)
        if "P01" <= strategy_id <= "P20":
            slugs.append(raw_slug.lower())
    return slugs


def test_every_catalogue_strategy_has_policy_v2_module() -> None:
    for slug in _catalogue_slugs():
        module = importlib.import_module(f"src.strategies.{slug}.strategy_policy_v2")
        assert hasattr(module, "POLICY_V2")
