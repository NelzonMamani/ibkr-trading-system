"""Shared trigger evaluator for OPENING_DRIVE family."""

from __future__ import annotations


def _safe_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def evaluate_opening_drive_trigger(pattern_result, inputs):
    candles = list((inputs or {}).get("candles") or [])
    trigger_level = _safe_float((pattern_result or {}).get("trigger_level"))
    stop_level = _safe_float((pattern_result or {}).get("invalidation_level") or (pattern_result or {}).get("stop_level"))

    if trigger_level is None:
        payload = {
            "trigger_type": "XL_OPENING_DRIVE_BREAK",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_trigger_level",
            "trigger_price_reference": None,
            "invalidation_price_reference": stop_level,
            "trigger_quality_flags": ["BLOCKED"],
        }
        print(f"[TRIGGER][OPENING_DRIVE] fired=False reason={payload['trigger_reason']}")
        return payload
    if not candles:
        payload = {
            "trigger_type": "XL_OPENING_DRIVE_BREAK",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_candles",
            "trigger_price_reference": trigger_level,
            "invalidation_price_reference": stop_level,
            "trigger_quality_flags": ["BLOCKED"],
        }
        print(f"[TRIGGER][OPENING_DRIVE] fired=False reason={payload['trigger_reason']}")
        return payload

    last = candles[-1]
    last_high = _safe_float(last.get("high") if isinstance(last, dict) else getattr(last, "high", None))
    last_close = _safe_float(last.get("close") if isinstance(last, dict) else getattr(last, "close", None))
    if last_high is None and last_close is None:
        payload = {
            "trigger_type": "XL_OPENING_DRIVE_BREAK",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_price_fields",
            "trigger_price_reference": trigger_level,
            "invalidation_price_reference": stop_level,
            "trigger_quality_flags": ["BLOCKED"],
        }
        print(f"[TRIGGER][OPENING_DRIVE] fired=False reason={payload['trigger_reason']}")
        return payload

    ready = (last_high is not None and last_high >= trigger_level) or (last_close is not None and last_close >= trigger_level)
    payload = {
        "trigger_type": "XL_OPENING_DRIVE_BREAK",
        "trigger_state": "FIRED" if ready else "ARMED",
        "trigger_ready_now": ready,
        "trigger_reason": "opening_drive_break_fired" if ready else "opening_drive_armed",
        "trigger_price_reference": trigger_level,
        "invalidation_price_reference": stop_level,
        "trigger_quality_flags": [],
    }
    print(f"[TRIGGER][OPENING_DRIVE] fired={ready} reason={payload['trigger_reason']}")
    return payload

