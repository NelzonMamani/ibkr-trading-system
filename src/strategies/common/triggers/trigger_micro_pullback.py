"""Shared trigger evaluator for MICRO_PULLBACK family."""

from __future__ import annotations


def _safe_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def evaluate_micro_pullback_trigger(pattern_result, inputs):
    levels = inputs if isinstance(inputs, dict) else {}
    candles = list(levels.get("candles") or [])
    if not candles:
        payload = {
            "trigger_type": "PULLBACK_HIGH_BREAK",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_candles",
            "trigger_price_reference": None,
            "invalidation_price_reference": None,
            "execution_refinement_mode": "FAST_MICRO_PULLBACK",
        }
        print(f"[TRIGGER] MICRO_PULLBACK state={payload['trigger_state']} reason={payload['trigger_reason']}")
        return payload

    result_payload = pattern_result if isinstance(pattern_result, dict) else {}
    trigger_level = _safe_float(result_payload.get("trigger_level"))
    invalidation_level = _safe_float(result_payload.get("invalidation_level") or result_payload.get("stop_level"))

    if trigger_level is None:
        payload = {
            "trigger_type": "PULLBACK_HIGH_BREAK",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_trigger_level",
            "trigger_price_reference": None,
            "invalidation_price_reference": invalidation_level,
            "execution_refinement_mode": "FAST_MICRO_PULLBACK",
        }
        print(f"[TRIGGER] MICRO_PULLBACK state={payload['trigger_state']} reason={payload['trigger_reason']}")
        return payload

    if invalidation_level is None:
        payload = {
            "trigger_type": "PULLBACK_HIGH_BREAK",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_invalidation_level",
            "trigger_price_reference": trigger_level,
            "invalidation_price_reference": None,
            "execution_refinement_mode": "FAST_MICRO_PULLBACK",
        }
        print(f"[TRIGGER] MICRO_PULLBACK state={payload['trigger_state']} reason={payload['trigger_reason']}")
        return payload

    last = candles[-1]
    last_close = _safe_float(last.get("close") if isinstance(last, dict) else getattr(last, "close", None))
    last_high = _safe_float(last.get("high") if isinstance(last, dict) else getattr(last, "high", None))

    price = last_close
    if last_high is not None and last_close is not None:
        price = max(last_close, last_high)
    fired = price is not None and price >= trigger_level

    payload = {
        "trigger_type": "PULLBACK_HIGH_BREAK",
        "trigger_state": "FIRED" if fired else "ARMED",
        "trigger_ready_now": fired,
        "trigger_reason": "micro_pullback_break_fired" if fired else "micro_pullback_armed",
        "trigger_price_reference": trigger_level,
        "invalidation_price_reference": invalidation_level,
        "execution_refinement_mode": "FAST_MICRO_PULLBACK",
    }
    print(f"[TRIGGER] MICRO_PULLBACK state={payload['trigger_state']} reason={payload['trigger_reason']}")
    return payload
