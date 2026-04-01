"""Shared trigger evaluator for HOD_BREAK family."""

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


def evaluate_hod_break_trigger(pattern_result, inputs):
    payload = pattern_result if isinstance(pattern_result, dict) else {}
    values = inputs if isinstance(inputs, dict) else {}
    candles = list(values.get("candles") or [])
    trigger_level = _safe_float(payload.get("trigger_level"))
    invalidation_level = _safe_float(payload.get("invalidation_level"))
    stop_level = _safe_float(payload.get("stop_level"))

    base = {
        "trigger_type": "XL_HOD_BREAK",
        "trigger_price_reference": trigger_level,
        "invalidation_price_reference": invalidation_level,
        "trigger_level": trigger_level,
        "stop_level": stop_level,
        "level_type": "HOD",
    }

    if len(candles) < 2:
        out = {**base, "trigger_state": "BLOCKED", "trigger_ready_now": False, "trigger_reason": "missing_candles"}
        print(f"[TRIGGER][HOD_BREAK] fired=False reason={out['trigger_reason']}")
        return out
    if trigger_level is None:
        out = {**base, "trigger_state": "BLOCKED", "trigger_ready_now": False, "trigger_reason": "missing_trigger_level"}
        print(f"[TRIGGER][HOD_BREAK] fired=False reason={out['trigger_reason']}")
        return out

    last = candles[-1]
    prev = candles[-2]
    prev_close = _safe_float(_read(prev, "close"))
    last_close = _safe_float(_read(last, "close"))
    last_high = _safe_float(_read(last, "high"))
    last_open = _safe_float(_read(last, "open"))
    if None in {prev_close, last_close, last_high, last_open}:
        out = {**base, "trigger_state": "BLOCKED", "trigger_ready_now": False, "trigger_reason": "missing_price_fields"}
        print(f"[TRIGGER][HOD_BREAK] fired=False reason={out['trigger_reason']}")
        return out

    body = abs(last_close - last_open)
    upper_wick = max(last_high - max(last_close, last_open), 0.0)
    breakout_shape_ok = not (last_high >= trigger_level and last_close <= trigger_level) and not (
        body > 0 and upper_wick > body * 1.8
    )

    fired = prev_close <= trigger_level and last_close > trigger_level and last_high >= trigger_level and breakout_shape_ok
    reason = "hod_break_confirmed" if fired else "awaiting_hod_break"
    state = "FIRED" if fired else "ARMED"
    out = {
        **base,
        "trigger_state": state,
        "trigger_ready_now": fired,
        "trigger_reason": reason,
        "invalidation_price_reference": invalidation_level if invalidation_level is not None else stop_level,
    }
    print(f"[TRIGGER][HOD_BREAK] fired={fired} reason={reason}")
    return out
