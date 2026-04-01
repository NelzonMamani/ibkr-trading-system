"""Shared trigger evaluator for PARABOLIC_EXHAUSTION family."""

from __future__ import annotations


def _safe_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _read(item, field: str):
    if isinstance(item, dict):
        return item.get(field)
    return getattr(item, field, None)


def evaluate_parabolic_exhaustion_trigger(pattern_result, inputs):
    payload = pattern_result if isinstance(pattern_result, dict) else {}
    levels = inputs if isinstance(inputs, dict) else {}
    candles = list(levels.get("candles") or [])
    trigger_level = _safe_float(payload.get("trigger_level"))

    base = {
        "trigger_type": "XL_PARABOLIC_EXHAUSTION",
        "trigger_price_reference": trigger_level,
        "invalidation_price_reference": None,
    }

    if len(candles) < 2:
        return {**base, "trigger_state": "BLOCKED", "trigger_ready_now": False, "trigger_reason": "missing_candles"}

    last = candles[-1]
    prev = candles[-2]
    lo = _safe_float(_read(last, "low"))
    hi = _safe_float(_read(last, "high"))
    cl = _safe_float(_read(last, "close"))
    prev_hi = _safe_float(_read(prev, "high"))
    if None in {lo, hi, cl, prev_hi}:
        return {**base, "trigger_state": "BLOCKED", "trigger_ready_now": False, "trigger_reason": "missing_price_fields"}

    wick_base = max(hi - lo, 1e-9)
    upper_wick_ratio = (hi - cl) / wick_base
    rejection = upper_wick_ratio >= 0.4
    failed_continuation = hi <= prev_hi
    fired = rejection or failed_continuation

    return {
        **base,
        "trigger_state": "FIRED" if fired else "ARMED",
        "trigger_ready_now": fired,
        "trigger_reason": "exhaustion_confirmed" if fired else "awaiting_exhaustion_confirmation",
    }
