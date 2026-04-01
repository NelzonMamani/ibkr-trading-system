"""Shared trigger evaluator for PREMARKET_HIGH_BREAK family."""

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


def evaluate_premarket_high_break_trigger(pattern_result, inputs):
    payload = pattern_result if isinstance(pattern_result, dict) else {}
    candles = list((inputs or {}).get("candles") or [])
    trigger_level = _safe_float(payload.get("trigger_level"))
    invalidation_level = _safe_float(payload.get("invalidation_level"))

    if trigger_level is None:
        out = {
            "trigger_type": "XL_PREMARKET_HIGH_BREAK",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_trigger_level",
            "trigger_price_reference": None,
            "invalidation_price_reference": invalidation_level,
        }
        print(f"[TRIGGER][PMH_BREAK] fired=False reason={out['trigger_reason']}")
        return out

    if len(candles) < 2:
        out = {
            "trigger_type": "XL_PREMARKET_HIGH_BREAK",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_candles",
            "trigger_price_reference": trigger_level,
            "invalidation_price_reference": invalidation_level or trigger_level,
        }
        print(f"[TRIGGER][PMH_BREAK] fired=False reason={out['trigger_reason']}")
        return out

    last = candles[-1]
    prev = candles[-2]
    last_close = _safe_float(_read(last, "close"))
    prev_close = _safe_float(_read(prev, "close"))
    last_low = _safe_float(_read(last, "low"))
    prev_low = _safe_float(_read(prev, "low"))

    if last_close is None or prev_close is None:
        out = {
            "trigger_type": "XL_PREMARKET_HIGH_BREAK",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_price_fields",
            "trigger_price_reference": trigger_level,
            "invalidation_price_reference": invalidation_level or trigger_level,
        }
        print(f"[TRIGGER][PMH_BREAK] fired=False reason={out['trigger_reason']}")
        return out

    reclaim_detected = (
        (prev_low is not None and prev_low < trigger_level) or (last_low is not None and last_low < trigger_level)
    ) and last_close > trigger_level
    fire_break = last_close > trigger_level and prev_close <= trigger_level
    hold_above = last_close >= trigger_level and prev_close >= trigger_level
    fired = fire_break or reclaim_detected
    armed = hold_above and not fired
    if fire_break:
        reason = "pmh_break_confirmed"
    elif reclaim_detected:
        reason = "pmh_reclaim_confirmed"
    elif hold_above:
        reason = "pmh_holding_above_level"
    else:
        reason = "awaiting_pmh_acceptance"

    out = {
        "trigger_type": "XL_PREMARKET_HIGH_BREAK",
        "trigger_state": "FIRED" if fired else "ARMED",
        "trigger_ready_now": fired,
        "trigger_reason": reason,
        "trigger_price_reference": trigger_level,
        "invalidation_price_reference": invalidation_level or trigger_level,
        "trigger_level": trigger_level,
        "trigger_armed": armed,
    }
    print(f"[TRIGGER][PMH_BREAK] fired={fired} reason={reason}")
    return out
