from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from src.strategies.ross_momentum.strategy_policy_v2 import POLICY_V2
from src.strategy_policy_v2.selection_plans import ScannerPlan


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
        return
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        for child in value.values():
            yield from _iter_strings(child)
        return
    if isinstance(value, (list, tuple, set)):
        for child in value:
            yield from _iter_strings(child)


def test_ross_policy_v2_core_sections_not_empty() -> None:
    assert isinstance(POLICY_V2.selection_plan, ScannerPlan)
    assert POLICY_V2.selection_plan.top_n > 0
    assert POLICY_V2.selection_plan.watchlist_limit_k > 0
    assert POLICY_V2.selection_plan.focus_limit_m > 0

    assert len(POLICY_V2.setup_families.families) >= 1
    assert len(POLICY_V2.pattern_catalog.patterns) >= 1
    assert len(POLICY_V2.trigger_model.entries) >= 1
    assert len(POLICY_V2.exit_model.rules) >= 1


def test_ross_policy_v2_session_and_intent_contract() -> None:
    sessions = set(POLICY_V2.session_semantics.sessions)
    assert "PRE" in sessions
    assert "RTH" in sessions

    emitted = set(POLICY_V2.intent_contract.emitted_intents)
    assert "DECISION_INTENT" in emitted


def test_ross_policy_v2_has_no_placeholders_or_todos() -> None:
    disallowed = ("placeholder", "todo")
    for text in _iter_strings(POLICY_V2):
        lowered = text.lower()
        assert all(token not in lowered for token in disallowed), text
