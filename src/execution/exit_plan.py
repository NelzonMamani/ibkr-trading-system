from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ExitPlan:
    name: str
    stop_offset_pct: float
    target_r_multiple: float
    max_hold_ticks_by_trader: dict[str, int]
    momentum_fail_ticks_by_trader: dict[str, int]
    momentum_min_r_multiple: float


_DEFAULT_MAX_HOLD = {
    "SCALPER": 4,
    "MOMENTUM": 6,
    "MANUAL": 8,
}
_DEFAULT_MOMENTUM_FAIL = {
    "SCALPER": 3,
    "MOMENTUM": 4,
    "MANUAL": 6,
}

_EXIT_PLANS = {
    "GAP_AND_GO": ExitPlan(
        name="GAP_AND_GO",
        stop_offset_pct=0.015,
        target_r_multiple=1.0,
        max_hold_ticks_by_trader=_DEFAULT_MAX_HOLD,
        momentum_fail_ticks_by_trader=_DEFAULT_MOMENTUM_FAIL,
        momentum_min_r_multiple=0.35,
    ),
    "PREMARKET_HIGH_BREAK": ExitPlan(
        name="PREMARKET_HIGH_BREAK",
        stop_offset_pct=0.015,
        target_r_multiple=1.0,
        max_hold_ticks_by_trader=_DEFAULT_MAX_HOLD,
        momentum_fail_ticks_by_trader=_DEFAULT_MOMENTUM_FAIL,
        momentum_min_r_multiple=0.35,
    ),
    "ORB_BREAKOUT": ExitPlan(
        name="ORB_BREAKOUT",
        stop_offset_pct=0.012,
        target_r_multiple=1.0,
        max_hold_ticks_by_trader=_DEFAULT_MAX_HOLD,
        momentum_fail_ticks_by_trader=_DEFAULT_MOMENTUM_FAIL,
        momentum_min_r_multiple=0.30,
    ),
    "ORB_1M": ExitPlan(
        name="ORB_1M",
        stop_offset_pct=0.012,
        target_r_multiple=1.0,
        max_hold_ticks_by_trader=_DEFAULT_MAX_HOLD,
        momentum_fail_ticks_by_trader=_DEFAULT_MOMENTUM_FAIL,
        momentum_min_r_multiple=0.30,
    ),
    "HOD_BREAK": ExitPlan(
        name="HOD_BREAK",
        stop_offset_pct=0.012,
        target_r_multiple=1.0,
        max_hold_ticks_by_trader=_DEFAULT_MAX_HOLD,
        momentum_fail_ticks_by_trader=_DEFAULT_MOMENTUM_FAIL,
        momentum_min_r_multiple=0.30,
    ),
    "VWAP_RECLAIM": ExitPlan(
        name="VWAP_RECLAIM",
        stop_offset_pct=0.012,
        target_r_multiple=1.0,
        max_hold_ticks_by_trader=_DEFAULT_MAX_HOLD,
        momentum_fail_ticks_by_trader=_DEFAULT_MOMENTUM_FAIL,
        momentum_min_r_multiple=0.30,
    ),
    "FIRST_PULLBACK": ExitPlan(
        name="FIRST_PULLBACK",
        stop_offset_pct=0.012,
        target_r_multiple=1.0,
        max_hold_ticks_by_trader=_DEFAULT_MAX_HOLD,
        momentum_fail_ticks_by_trader=_DEFAULT_MOMENTUM_FAIL,
        momentum_min_r_multiple=0.30,
    ),
    "MICRO_PULLBACK": ExitPlan(
        name="MICRO_PULLBACK",
        stop_offset_pct=0.012,
        target_r_multiple=1.0,
        max_hold_ticks_by_trader=_DEFAULT_MAX_HOLD,
        momentum_fail_ticks_by_trader=_DEFAULT_MOMENTUM_FAIL,
        momentum_min_r_multiple=0.30,
    ),
    "BULL_FLAG": ExitPlan(
        name="BULL_FLAG",
        stop_offset_pct=0.012,
        target_r_multiple=1.0,
        max_hold_ticks_by_trader=_DEFAULT_MAX_HOLD,
        momentum_fail_ticks_by_trader=_DEFAULT_MOMENTUM_FAIL,
        momentum_min_r_multiple=0.30,
    ),
    "MOMO_BREAKOUT": ExitPlan(
        name="MOMO_BREAKOUT",
        stop_offset_pct=0.012,
        target_r_multiple=1.0,
        max_hold_ticks_by_trader=_DEFAULT_MAX_HOLD,
        momentum_fail_ticks_by_trader=_DEFAULT_MOMENTUM_FAIL,
        momentum_min_r_multiple=0.30,
    ),
    "ORB_BREAK": ExitPlan(
        name="ORB_BREAK",
        stop_offset_pct=0.012,
        target_r_multiple=1.0,
        max_hold_ticks_by_trader=_DEFAULT_MAX_HOLD,
        momentum_fail_ticks_by_trader=_DEFAULT_MOMENTUM_FAIL,
        momentum_min_r_multiple=0.30,
    ),
    "FIRST_PULLBACK_LONG": ExitPlan(
        name="FIRST_PULLBACK_LONG",
        stop_offset_pct=0.012,
        target_r_multiple=1.0,
        max_hold_ticks_by_trader=_DEFAULT_MAX_HOLD,
        momentum_fail_ticks_by_trader=_DEFAULT_MOMENTUM_FAIL,
        momentum_min_r_multiple=0.30,
    ),
}

_DEFAULT_PLAN = ExitPlan(
    name="DEFAULT",
    stop_offset_pct=0.02,
    target_r_multiple=1.0,
    max_hold_ticks_by_trader=_DEFAULT_MAX_HOLD,
    momentum_fail_ticks_by_trader=_DEFAULT_MOMENTUM_FAIL,
    momentum_min_r_multiple=0.30,
)


def resolve_exit_plan(
    pattern_name: Optional[str],
    strategy_name: Optional[str] = None,
) -> ExitPlan:
    normalized_pattern = (pattern_name or "").upper()
    if normalized_pattern in _EXIT_PLANS:
        return _EXIT_PLANS[normalized_pattern]

    normalized_strategy = (strategy_name or "").upper()
    if "GAPANDGO" in normalized_strategy:
        return _EXIT_PLANS["GAP_AND_GO"]
    if "MOMENTUM" in normalized_strategy:
        return _EXIT_PLANS.get("HOD_BREAK", _DEFAULT_PLAN)

    return _DEFAULT_PLAN


def resolve_max_hold_ticks(
    trader_type: str,
    pattern_name: Optional[str] = None,
    strategy_name: Optional[str] = None,
    fallback: int = 10,
) -> int:
    plan = resolve_exit_plan(pattern_name, strategy_name)
    normalized = (trader_type or "").upper()
    return plan.max_hold_ticks_by_trader.get(normalized, fallback)


def resolve_momentum_fail_ticks(
    trader_type: str,
    pattern_name: Optional[str] = None,
    strategy_name: Optional[str] = None,
    fallback: int = 4,
) -> int:
    plan = resolve_exit_plan(pattern_name, strategy_name)
    normalized = (trader_type or "").upper()
    return plan.momentum_fail_ticks_by_trader.get(normalized, fallback)


def compute_stop_price(
    entry_price: float,
    direction: str,
    pattern_name: Optional[str] = None,
    strategy_name: Optional[str] = None,
) -> float:
    plan = resolve_exit_plan(pattern_name, strategy_name)
    normalized_direction = (direction or "").upper()
    if normalized_direction == "SHORT":
        return round(entry_price * (1 + plan.stop_offset_pct), 2)
    return round(entry_price * (1 - plan.stop_offset_pct), 2)


def compute_take_profit_price(
    entry_price: float,
    stop_loss_price: float,
    direction: str,
    pattern_name: Optional[str] = None,
    strategy_name: Optional[str] = None,
) -> float:
    plan = resolve_exit_plan(pattern_name, strategy_name)
    normalized_direction = (direction or "").upper()
    risk_amount = max(abs(entry_price - stop_loss_price), 0.01)
    if normalized_direction == "SHORT":
        return round(entry_price - (risk_amount * plan.target_r_multiple), 2)
    return round(entry_price + (risk_amount * plan.target_r_multiple), 2)
