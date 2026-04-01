"""Shared trigger evaluator for KEY_LEVEL_BREAK family."""

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


def evaluate_key_level_break_trigger(pattern_result, inputs):
    payload = pattern_result if isinstance(pattern_result, dict) else {}
    levels = inputs if isinstance(inputs, dict) else {}
    candles = list(levels.get("candles") or [])
    if len(candles) < 2:
        return {
            "trigger_type": "XL_KEY_LEVEL_BREAK",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_candles",
        }

    trigger_level = _safe_float(payload.get("trigger_level"))
    if trigger_level is None:
        return {
            "trigger_type": "XL_KEY_LEVEL_BREAK",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_trigger_level",
        }

    last = candles[-1]
    prev = candles[-2]
    last_close = _safe_float(_read(last, "close"))
    last_high = _safe_float(_read(last, "high"))
    last_volume = _safe_float(_read(last, "volume"))
    prev_close = _safe_float(_read(prev, "close"))
    prev_volume = _safe_float(_read(prev, "volume"))
    if last_close is None or prev_close is None or last_high is None:
        return {
            "trigger_type": "XL_KEY_LEVEL_BREAK",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_price_fields",
        }

    level_type = (payload.get("setup_metadata") or {}).get("level_type") or payload.get("level_type")
    selected_level_source = (payload.get("setup_metadata") or {}).get("selected_level_source")

    broke_now = prev_close <= trigger_level and last_close > trigger_level and last_high >= trigger_level
    volume_ok = True
    if last_volume is not None and prev_volume is not None:
        volume_ok = last_volume >= prev_volume

    fired = broke_now and volume_ok
    state = "FIRED" if fired else "ARMED"
    reason = "key_level_break_confirmed" if fired else "awaiting_decisive_break_and_acceptance"
    trigger = {
        "trigger_type": "XL_KEY_LEVEL_BREAK",
        "trigger_state": state,
        "trigger_ready_now": fired,
        "trigger_reason": reason,
        "trigger_level": trigger_level,
        "trigger_price_reference": trigger_level,
        "invalidation_price_reference": _safe_float(payload.get("invalidation_level")) or trigger_level,
        "stop_level": _safe_float(payload.get("stop_level")),
        "level_type": level_type,
        "selected_level_source": selected_level_source,
    }
    print(
        "[TRIGGER][KEY_LEVEL_BREAK] "
        f"fired={fired} level={trigger_level} reason={reason} level_type={level_type}"
    )
    return trigger
