"""Shared trigger evaluator for CUP_HANDLE family."""

from __future__ import annotations


def _safe_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def evaluate_cup_handle_trigger(pattern_result, inputs):
    payload = pattern_result if isinstance(pattern_result, dict) else {}
    candles = list((inputs or {}).get("candles") or [])
    trigger_level = _safe_float(payload.get("trigger_level"))
    stop_level = _safe_float(payload.get("stop_level") or payload.get("invalidation_level"))

    base = {
        "trigger_type": "XL_CUP_HANDLE_BREAK",
        "trigger_price_reference": trigger_level,
        "invalidation_price_reference": stop_level,
        "trigger_level": trigger_level,
        "stop_level": stop_level,
    }
    if not candles:
        out = {
            **base,
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_candles",
            "trigger_quality_flags": ["BLOCKED"],
        }
        print(f"[TRIGGER][CUP_HANDLE] fired=False reason={out['trigger_reason']}")
        return out
    if trigger_level is None:
        out = {
            **base,
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_trigger_level",
            "trigger_quality_flags": ["BLOCKED"],
        }
        print(f"[TRIGGER][CUP_HANDLE] fired=False reason={out['trigger_reason']}")
        return out

    last = candles[-1]
    prev = candles[-2] if len(candles) > 1 else None
    last_close = _safe_float(last.get("close") if isinstance(last, dict) else getattr(last, "close", None))
    last_high = _safe_float(last.get("high") if isinstance(last, dict) else getattr(last, "high", None))
    prev_close = _safe_float(prev.get("close") if isinstance(prev, dict) else getattr(prev, "close", None))
    if last_close is None or last_high is None:
        out = {
            **base,
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_price_fields",
            "trigger_quality_flags": ["BLOCKED"],
        }
        print(f"[TRIGGER][CUP_HANDLE] fired=False reason={out['trigger_reason']}")
        return out

    fired = bool(prev_close is not None and prev_close <= trigger_level and last_close > trigger_level and last_high >= trigger_level)
    out = {
        **base,
        "trigger_state": "FIRED" if fired else "ARMED",
        "trigger_ready_now": fired,
        "trigger_reason": "cup_handle_break_confirmed" if fired else "awaiting_cup_handle_break",
        "trigger_quality_flags": [],
    }
    print(f"[TRIGGER][CUP_HANDLE] fired={fired} reason={out['trigger_reason']}")
    return out
