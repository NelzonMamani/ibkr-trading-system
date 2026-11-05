"""Shared trigger evaluator for MICRO_PULLBACK family."""

from __future__ import annotations

from math import isfinite

from src.strategies.common.triggers.trigger_abcd_continuation import abcd_candle_rejection

def _safe_float(value):
    try:
        parsed = None if value is None or isinstance(value, bool) else float(value)
        return parsed if parsed is not None and isfinite(parsed) else None
    except (TypeError, ValueError, OverflowError):
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
    # Unbound component projections historically supply high/close only. Actual
    # V1 binds a full execution stream and original clock before dispatch.
    if "execution_stream" in result_payload:
        stream = result_payload.get("execution_stream")
        rejection = abcd_candle_rejection(candles,
            observed_at_utc=stream.get("observed_at_utc") if isinstance(stream, dict) else None,
            require_clock=True)
        if rejection:
            return {"trigger_type": "PULLBACK_HIGH_BREAK", "trigger_state": "BLOCKED",
                    "trigger_ready_now": False, "trigger_reason": "micro_pullback_" + rejection.lower()}
        for field in ("spread", "rvol"):
            value = levels.get(field)
            numeric = _safe_float(value)
            if value is not None and (numeric is None or numeric < 0):
                return {"trigger_type": "PULLBACK_HIGH_BREAK", "trigger_state": "BLOCKED",
                        "trigger_ready_now": False, "trigger_reason": "invalid_liquidity_" + field}
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
