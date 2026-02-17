from __future__ import annotations

import importlib
from pathlib import Path

from src.strategy_policy_v2.policy_v2 import StrategyPolicyV2
from src.strategy_policy_v2.selection_plans import EventPlan, PortfolioPlan, ScannerPlan, ScreenerPlan


def _policies() -> list[tuple[str, StrategyPolicyV2]]:
    root = Path("TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES")
    entries: list[tuple[str, StrategyPolicyV2]] = []
    for directory in sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith("P")):
        strategy_id, raw_slug = directory.name.split("_", 1)
        if not ("P01" <= strategy_id <= "P20"):
            continue
        slug = raw_slug.lower()
        module = importlib.import_module(f"src.strategies.{slug}.strategy_policy_v2")
        entries.append((slug, module.POLICY_V2))
    return entries


def test_policy_v2_required_sections_present() -> None:
    for slug, policy in _policies():
        assert policy.identity is not None, slug
        assert policy.selection_plan is not None, slug
        assert policy.mode_semantics is not None, slug
        assert policy.session_semantics is not None, slug
        assert policy.risk_model is not None, slug
        assert policy.execution_model is not None, slug
        assert policy.intent_contract is not None, slug
        assert isinstance(policy.selection_plan, (ScannerPlan, ScreenerPlan, PortfolioPlan, EventPlan)), slug


def test_selection_plan_constraints_by_type() -> None:
    for slug, policy in _policies():
        selection = policy.selection_plan
        if isinstance(selection, ScannerPlan):
            assert selection.top_n > 0, slug
            assert selection.watchlist_limit_k > 0, slug
            assert selection.focus_limit_m > 0, slug
            assert len(selection.session_allowlist) > 0, slug
        else:
            universe_source = getattr(selection, "universe_source", "")
            assert universe_source != "IBKR_TOP_GAINERS", slug
