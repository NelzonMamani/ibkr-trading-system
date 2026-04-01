"""Canonical trigger evaluator registry for setup-family dispatch."""

from __future__ import annotations

from collections.abc import Callable

from src.strategies.common.triggers.trigger_abcd_continuation import evaluate_abcd_continuation_trigger
from src.strategies.common.triggers.trigger_bull_flag import evaluate_bull_flag_trigger
from src.strategies.common.triggers.trigger_cup_handle import evaluate_cup_handle_trigger
from src.strategies.common.triggers.trigger_ema_pullback import evaluate_ema_pullback_trigger
from src.strategies.common.triggers.trigger_first_pullback import evaluate_first_pullback_trigger
from src.strategies.common.triggers.trigger_flat_top_breakout import evaluate_flat_top_breakout_trigger
from src.strategies.common.triggers.trigger_hod_break import evaluate_hod_break_trigger
from src.strategies.common.triggers.trigger_key_level_break import evaluate_key_level_break_trigger
from src.strategies.common.triggers.trigger_micro_pullback import evaluate_micro_pullback_trigger
from src.strategies.common.triggers.trigger_momentum_reclaim import evaluate_momentum_reclaim_trigger
from src.strategies.common.triggers.trigger_opening_drive import evaluate_opening_drive_trigger
from src.strategies.common.triggers.trigger_orb import evaluate_orb_trigger
from src.strategies.common.triggers.trigger_parabolic_exhaustion import evaluate_parabolic_exhaustion_trigger
from src.strategies.common.triggers.trigger_premarket_high_break import evaluate_premarket_high_break_trigger
from src.strategies.common.triggers.trigger_stair_step import evaluate_stair_step_trigger
from src.strategies.common.triggers.trigger_vwap_pullback import evaluate_vwap_pullback_trigger

TriggerEvaluator = Callable[[dict, dict], dict]

TRIGGER_EVALUATOR_REGISTRY: dict[str, TriggerEvaluator] = {
    "OPENING_RANGE_BREAKOUT": evaluate_orb_trigger,
    "ORB": evaluate_orb_trigger,
    "OPENING_DRIVE": evaluate_opening_drive_trigger,
    "PREMARKET_HIGH_BREAK": evaluate_premarket_high_break_trigger,
    "FIRST_PULLBACK": evaluate_first_pullback_trigger,
    "MICRO_PULLBACK": evaluate_micro_pullback_trigger,
    "FLAT_TOP_BREAKOUT": evaluate_flat_top_breakout_trigger,
    "KEY_LEVEL_BREAK": evaluate_key_level_break_trigger,
    "HOD_BREAK": evaluate_hod_break_trigger,
    "ABCD": evaluate_abcd_continuation_trigger,
    "BULL_FLAG": evaluate_bull_flag_trigger,
    "CUP_HANDLE": evaluate_cup_handle_trigger,
    "EMA_PULLBACK": evaluate_ema_pullback_trigger,
    "MOMENTUM_RECLAIM": evaluate_momentum_reclaim_trigger,
    "PARABOLIC_EXHAUSTION": evaluate_parabolic_exhaustion_trigger,
    "TREND_CONTINUATION_STAIR_STEP": evaluate_stair_step_trigger,
    "VWAP_PULLBACK": evaluate_vwap_pullback_trigger,
}


def resolve_trigger_evaluator(setup_family_id: str | None) -> TriggerEvaluator | None:
    key = str(setup_family_id or "").upper()
    return TRIGGER_EVALUATOR_REGISTRY.get(key)
