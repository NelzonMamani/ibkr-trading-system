"""Shared trigger evaluator for FLAT_TOP_BREAKOUT family."""

from __future__ import annotations


def _safe_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def evaluate_flat_top_breakout_trigger(pattern_result, inputs):
    levels = inputs if isinstance(inputs, dict) else {}
    candles = list(levels.get("candles") or [])
    if not candles:
        return {
            "trigger_type": "BREAKOUT_HIGH",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_candles",
            "trigger_price_reference": None,
            "invalidation_price_reference": None,
            "trigger_quality_flags": ["BLOCKED", "MISSING_CANDLES"],
        }

    payload = pattern_result if isinstance(pattern_result, dict) else {}
    trigger_level = _safe_float(payload.get("trigger_level"))
    invalidation_level = _safe_float(payload.get("invalidation_level") or payload.get("stop_level"))
    if trigger_level is None:
        return {
            "trigger_type": "BREAKOUT_HIGH",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_trigger_level",
            "trigger_price_reference": None,
            "invalidation_price_reference": invalidation_level,
            "trigger_quality_flags": ["BLOCKED", "MISSING_TRIGGER_REFERENCE"],
        }

    last = candles[-1]
    last_close = _safe_float(last.get("close") if isinstance(last, dict) else getattr(last, "close", None))
    last_high = _safe_float(last.get("high") if isinstance(last, dict) else getattr(last, "high", None))
    if last_close is None and last_high is None:
        return {
            "trigger_type": "BREAKOUT_HIGH",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "malformed_price_payload",
            "trigger_price_reference": trigger_level,
            "invalidation_price_reference": invalidation_level,
            "trigger_quality_flags": ["BLOCKED", "MALFORMED_PRICE_PAYLOAD"],
        }

    fired = (
        last_close is not None
        and last_high is not None
        and last_close >= trigger_level
        and last_high >= trigger_level
    )
    flags = []
    if invalidation_level is None:
        flags.append("MISSING_INVALIDATION_REFERENCE")
    if (
        invalidation_level is not None
        and last_close is not None
        and last_close <= invalidation_level
    ):
        flags.append("NEAR_INVALIDATION")

    return {
        "trigger_type": "BREAKOUT_HIGH",
        "trigger_state": "FIRED" if fired else "ARMED",
        "trigger_ready_now": fired,
        "trigger_reason": "breakout_already_through_level" if fired else "breakout_not_cleared",
        "trigger_price_reference": trigger_level,
        "invalidation_price_reference": invalidation_level,
        "trigger_quality_flags": flags,
    }
