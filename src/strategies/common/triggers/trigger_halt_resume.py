"""Shared trigger evaluator for HALT_RESUME family."""

from __future__ import annotations


def _safe_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def evaluate_halt_resume_trigger(pattern_result, inputs):
    payload = pattern_result if isinstance(pattern_result, dict) else {}
    candles = list((inputs or {}).get("candles") or [])
    trigger_level = _safe_float(payload.get("trigger_level"))
    stop_level = _safe_float(payload.get("stop_level") or payload.get("invalidation_level"))

    base = {
        "trigger_type": "XL_HALT_RESUME_BREAK",
        "trigger_price_reference": trigger_level,
        "invalidation_price_reference": stop_level,
        "trigger_level": trigger_level,
        "stop_level": stop_level,
    }
    if len(candles) < 2:
        out = {
            **base,
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "insufficient_candles",
            "trigger_quality_flags": ["BLOCKED"],
        }
        print(f"[TRIGGER][HALT_RESUME] fired=False reason={out['trigger_reason']}")
        return out
    if trigger_level is None:
        out = {
            **base,
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_trigger_level",
            "trigger_quality_flags": ["BLOCKED"],
        }
        print(f"[TRIGGER][HALT_RESUME] fired=False reason={out['trigger_reason']}")
        return out

    prev = candles[-2]
    last = candles[-1]
    prev_close = _safe_float(prev.get("close") if isinstance(prev, dict) else getattr(prev, "close", None))
    last_close = _safe_float(last.get("close") if isinstance(last, dict) else getattr(last, "close", None))
    last_high = _safe_float(last.get("high") if isinstance(last, dict) else getattr(last, "high", None))
    if prev_close is None or last_close is None or last_high is None:
        out = {
            **base,
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_price_fields",
            "trigger_quality_flags": ["BLOCKED"],
        }
        print(f"[TRIGGER][HALT_RESUME] fired=False reason={out['trigger_reason']}")
        return out

    fired = bool(prev_close <= trigger_level and last_close > trigger_level and last_high >= trigger_level)
    out = {
        **base,
        "trigger_state": "FIRED" if fired else "ARMED",
        "trigger_ready_now": fired,
        "trigger_reason": "halt_resume_break_confirmed" if fired else "awaiting_halt_resume_break",
        "trigger_quality_flags": [],
    }
    print(f"[TRIGGER][HALT_RESUME] fired={fired} reason={out['trigger_reason']}")
    return out
