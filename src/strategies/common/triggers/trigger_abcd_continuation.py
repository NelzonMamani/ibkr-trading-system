"""Shared trigger evaluator for ABCD continuation family."""

from __future__ import annotations


def _safe_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def evaluate_abcd_continuation_trigger(pattern_result, inputs):
    levels = inputs if isinstance(inputs, dict) else {}
    candles = list(levels.get("candles") or [])
    if not candles:
        payload = {
            "trigger_type": "XL_ABCD_CONTINUATION",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_candles",
        }
        print(f"[TRIGGER] ABCD state={payload['trigger_state']} reason={payload['trigger_reason']}")
        return payload

    result_payload = pattern_result if isinstance(pattern_result, dict) else {}
    trigger_level = _safe_float(result_payload.get("trigger_level"))
    if trigger_level is None:
        payload = {
            "trigger_type": "XL_ABCD_CONTINUATION",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_trigger_level",
        }
        print(f"[TRIGGER] ABCD state={payload['trigger_state']} reason={payload['trigger_reason']}")
        return payload

    last = candles[-1]
    last_close = _safe_float(last.get("close") if isinstance(last, dict) else getattr(last, "close", None))
    last_high = _safe_float(last.get("high") if isinstance(last, dict) else getattr(last, "high", None))
    if last_close is None and last_high is None:
        payload = {
            "trigger_type": "XL_ABCD_CONTINUATION",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_price_fields",
        }
        print(f"[TRIGGER] ABCD state={payload['trigger_state']} reason={payload['trigger_reason']}")
        return payload

    fired = bool(last_close is not None and last_high is not None and last_close > trigger_level and last_high >= trigger_level)
    payload = {
        "trigger_type": "XL_ABCD_CONTINUATION",
        "trigger_state": "FIRED" if fired else "ARMED",
        "trigger_ready_now": fired,
        "trigger_reason": "abcd_continuation_break_fired" if fired else "awaiting_abcd_continuation_break",
    }
    print(f"[TRIGGER] ABCD state={payload['trigger_state']} reason={payload['trigger_reason']}")
    return payload
