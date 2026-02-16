from __future__ import annotations

import importlib
from pathlib import Path

from src.strategy_policy_v2.selection_plans import ScannerPlan


def _strategy_entries() -> list[tuple[str, object]]:
    root = Path("TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES")
    entries: list[tuple[str, object]] = []
    for directory in sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith("P")):
        strategy_id, raw_slug = directory.name.split("_", 1)
        if not ("P01" <= strategy_id <= "P20"):
            continue
        slug = raw_slug.lower()
        module = importlib.import_module(f"src.strategies.{slug}.strategy_policy_v2")
        entries.append((slug, module.POLICY_V2.selection_plan))
    return entries


def test_non_scanner_plans_cannot_use_ibkr_top_gainers_defaults() -> None:
    for slug, selection_plan in _strategy_entries():
        if isinstance(selection_plan, ScannerPlan):
            continue
        assert getattr(selection_plan, "universe_source", "") != "IBKR_TOP_GAINERS", slug
        assert getattr(selection_plan, "ibkr_scan_code", "") != "TOP_PERC_GAIN", slug


def test_long_horizon_and_value_styles_are_not_scanner_plans() -> None:
    for slug, selection_plan in _strategy_entries():
        if any(token in slug for token in ("long_horizon", "buffett", "value")):
            assert not isinstance(selection_plan, ScannerPlan), slug
