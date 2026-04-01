"""Shared trigger evaluator for MOMENTUM_RECLAIM family."""

from __future__ import annotations


def _safe_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def evaluate_momentum_reclaim_trigger(pattern_result, inputs):
    payload = pattern_result if isinstance(pattern_result, dict) else {}
    levels = inputs if isinstance(inputs, dict) else {}
    candles = list(levels.get("candles") or [])
    vwap_level = _safe_float(levels.get("vwap"))
    trigger_level = _safe_float(payload.get("trigger_level")) or vwap_level
    invalidation_level = _safe_float(payload.get("invalidation_level")) or vwap_level

    base = {
        "trigger_type": "RECLAIM",
        "trigger_price_reference": trigger_level,
        "invalidation_price_reference": invalidation_level,
    }
    if not candles:
        return {
            **base,
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_candles",
            "trigger_quality_flags": ["BLOCKED"],
        }
    if trigger_level is None:
        return {
            **base,
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_trigger_level",
            "trigger_quality_flags": ["BLOCKED"],
        }

    last = candles[-1]
    last_close = _safe_float(last.get("close") if isinstance(last, dict) else getattr(last, "close", None))
    last_high = _safe_float(last.get("high") if isinstance(last, dict) else getattr(last, "high", None))
    if last_close is None or last_high is None:
        return {
            **base,
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_price_fields",
            "trigger_quality_flags": ["BLOCKED"],
        }

    fired = bool(last_close > trigger_level and last_high >= trigger_level)
    return {
        **base,
        "trigger_state": "FIRED" if fired else "ARMED",
        "trigger_ready_now": fired,
        "trigger_reason": "momentum_reclaim_confirmed" if fired else "awaiting_momentum_reclaim",
        "trigger_quality_flags": [],
    }

