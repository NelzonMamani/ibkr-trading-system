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
    candles = list((inputs or {}).get("candles") or [])
    level = _safe_float(payload.get("trigger_level"))
    stop_level = _safe_float(payload.get("stop_level"))

    base = {
        "trigger_type": "XL_MOMENTUM_RECLAIM",
        "trigger_price_reference": level,
        "invalidation_price_reference": level,
        "trigger_level": level,
        "stop_level": stop_level,
    }
    if len(candles) < 2:
        out = {
            **base,
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_candles",
            "trigger_quality_flags": ["BLOCKED"],
        }
        print(f"[TRIGGER][MOMENTUM_RECLAIM] fired=False reason={out['trigger_reason']}")
        return out
    if level is None:
        out = {
            **base,
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_trigger_level",
            "trigger_quality_flags": ["BLOCKED"],
        }
        print(f"[TRIGGER][MOMENTUM_RECLAIM] fired=False reason={out['trigger_reason']}")
        return out

    prev = candles[-2]
    last = candles[-1]
    prev_close = _safe_float(_read(prev, "close"))
    last_close = _safe_float(_read(last, "close"))
    last_open = _safe_float(_read(last, "open"))
    last_high = _safe_float(_read(last, "high"))
    if None in {prev_close, last_close, last_open, last_high}:
        out = {
            **base,
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_price_fields",
            "trigger_quality_flags": ["BLOCKED"],
        }
        print(f"[TRIGGER][MOMENTUM_RECLAIM] fired=False reason={out['trigger_reason']}")
        return out

    continuation_ok = bool(last_close >= last_open and last_high >= level)
    fired = bool(prev_close <= level and last_close > level and continuation_ok)
    reason = "momentum_reclaim_confirmed" if fired else "awaiting_reclaim_confirmation"
    out = {
        **base,
        "trigger_state": "FIRED" if fired else "ARMED",
        "trigger_ready_now": fired,
        "trigger_reason": reason,
        "trigger_quality_flags": [],
    }
    print(f"[TRIGGER][MOMENTUM_RECLAIM] fired={fired} reason={reason}")
    return out

