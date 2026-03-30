"""Canonical trigger evaluator registry for setup-family dispatch."""

from __future__ import annotations

from collections.abc import Callable

from src.strategies.common.triggers.trigger_first_pullback import evaluate_first_pullback_trigger
from src.strategies.common.triggers.trigger_flat_top_breakout import evaluate_flat_top_breakout_trigger
from src.strategies.common.triggers.trigger_micro_pullback import evaluate_micro_pullback_trigger
from src.strategies.common.triggers.trigger_orb import evaluate_orb_trigger

TriggerEvaluator = Callable[[dict, dict], dict]

TRIGGER_EVALUATOR_REGISTRY: dict[str, TriggerEvaluator] = {
    "OPENING_RANGE_BREAKOUT": evaluate_orb_trigger,
    "ORB": evaluate_orb_trigger,
    "FIRST_PULLBACK": evaluate_first_pullback_trigger,
    "MICRO_PULLBACK": evaluate_micro_pullback_trigger,
    "FLAT_TOP_BREAKOUT": evaluate_flat_top_breakout_trigger,
}


def resolve_trigger_evaluator(setup_family_id: str | None) -> TriggerEvaluator | None:
    key = str(setup_family_id or "").upper()
    return TRIGGER_EVALUATOR_REGISTRY.get(key)
