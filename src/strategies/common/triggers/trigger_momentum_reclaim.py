"""Shared trigger evaluator for MOMENTUM_RECLAIM family."""

from __future__ import annotations


def _safe_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _read(obj, field: str):
    if isinstance(obj, dict):
        return obj.get(field)
    return getattr(obj, field, None)


def evaluate_momentum_reclaim_trigger(pattern_result, inputs):
    payload = pattern_result if isinstance(pattern_result, dict) else {}
    levels = inputs if isinstance(inputs, dict) else {}
    candles = list(levels.get("candles") or [])

    trigger_level = _safe_float(payload.get("trigger_level"))
    invalidation_level = _safe_float(payload.get("invalidation_level")) or _safe_float(payload.get("stop_level"))

    base = {
        "trigger_type": "XL_MOMENTUM_RECLAIM",
        "trigger_price_reference": trigger_level,
        "invalidation_price_reference": invalidation_level,
    }

    if len(candles) < 2:
        return {
            **base,
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_candles",
        }

    if trigger_level is None:
        return {
            **base,
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_trigger_level",
        }

    prev = candles[-2]
    last = candles[-1]
    prev_close = _safe_float(_read(prev, "close"))
    last_close = _safe_float(_read(last, "close"))
    last_open = _safe_float(_read(last, "open"))
    last_high = _safe_float(_read(last, "high"))
    if prev_close is None or last_close is None or last_open is None or last_high is None:
        return {
            **base,
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_price_fields",
        }

    crossed_reclaim = prev_close <= trigger_level and last_close > trigger_level
    continuation_confirmed = last_close >= last_open or last_high >= trigger_level
    fired = crossed_reclaim and continuation_confirmed
    reason = "momentum_reclaim_confirmed" if fired else "awaiting_reclaim_confirmation"

    return {
        **base,
        "trigger_state": "FIRED" if fired else "ARMED",
        "trigger_ready_now": fired,
        "trigger_reason": reason,
    }
