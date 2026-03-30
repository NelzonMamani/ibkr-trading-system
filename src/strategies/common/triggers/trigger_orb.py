"""Shared trigger evaluator for ORB family."""

from __future__ import annotations


def _safe_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def evaluate_orb_trigger(pattern_result, inputs):
    levels = inputs if isinstance(inputs, dict) else {}
    candles = list(levels.get("candles") or [])
    if not candles:
        return {
            "trigger_type": "XL_ORB_BREAK",
            "trigger_ready_now": False,
            "trigger_reason": "missing_candles",
        }

    range_info = levels.get("active_breakout_range") if isinstance(levels.get("active_breakout_range"), dict) else {}
    orh = _safe_float(range_info.get("upper"))
    if orh is None:
        key_levels = levels.get("key_levels") if isinstance(levels.get("key_levels"), dict) else {}
        orh = _safe_float(key_levels.get("OPENING_RANGE_HIGH"))
    if orh is None:
        return {
            "trigger_type": "XL_ORB_BREAK",
            "trigger_ready_now": False,
            "trigger_reason": "missing_orh",
        }

    last = candles[-1]
    prev = candles[-2] if len(candles) > 1 else None
    last_close = _safe_float(last.get("close") if isinstance(last, dict) else getattr(last, "close", None))
    last_high = _safe_float(last.get("high") if isinstance(last, dict) else getattr(last, "high", None))
    prev_low = _safe_float(prev.get("low") if isinstance(prev, dict) else getattr(prev, "low", None)) if prev is not None else None

    broke_and_held = last_high is not None and last_close is not None and last_high > orh and last_close > orh
    if broke_and_held:
        return {
            "trigger_type": "XL_ORB_BREAK",
            "trigger_ready_now": True,
            "trigger_reason": "break_and_hold_above_orh",
        }

    reclaimed = (
        prev_low is not None
        and prev_low <= orh
        and last_close is not None
        and last_close > orh
    )
    if reclaimed:
        return {
            "trigger_type": "XL_ORB_RETEST",
            "trigger_ready_now": True,
            "trigger_reason": "retest_and_reclaim_orh",
        }

    return {
        "trigger_type": "XL_ORB_BREAK",
        "trigger_ready_now": False,
        "trigger_reason": "orb_trigger_not_ready",
    }
