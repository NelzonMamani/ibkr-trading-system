"""Shared trigger evaluator for MOMENTUM_RECLAIM family."""

from __future__ import annotations

from math import isfinite
from src.strategies.common.triggers.trigger_abcd_continuation import abcd_candle_rejection


def _safe_float(value):
    try:
        number = None if value is None or isinstance(value, bool) else float(value)
        return number if number is not None and isfinite(number) else None
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

    stream = payload.get("execution_stream")
    rejection = abcd_candle_rejection(candles,
        observed_at_utc=stream.get("observed_at_utc") if isinstance(stream, dict) else None,
        require_clock=isinstance(stream, dict))
    if rejection:
        return {**base, "trigger_state": "BLOCKED", "trigger_ready_now": False,
                "trigger_reason": "momentum_reclaim_" + rejection.lower()}
    if invalidation_level is None or not 0 < invalidation_level < trigger_level:
        return {**base, "trigger_state": "BLOCKED", "trigger_ready_now": False,
                "trigger_reason": "invalid_invalidation_level"}
    if _safe_float(_read(candles[-1], "low")) <= invalidation_level:
        return {**base, "trigger_state": "INVALIDATED", "trigger_ready_now": False,
                "trigger_reason": "shakeout_low_lost"}

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
