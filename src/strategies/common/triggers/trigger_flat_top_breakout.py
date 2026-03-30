"""Shared trigger evaluator for FLAT_TOP_BREAKOUT family."""

from __future__ import annotations


def _safe_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def evaluate_flat_top_breakout_trigger(pattern_result, inputs):
    payload = pattern_result if isinstance(pattern_result, dict) else {}
    levels = inputs if isinstance(inputs, dict) else {}
    candles = list(levels.get("candles") or [])
    if not candles:
        result = {
            "trigger_type": "BREAKOUT_HIGH",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_candles",
            "trigger_price_reference": None,
            "invalidation_price_reference": None,
            "trigger_event_emitted": False,
            "execution_refinement_mode": "NONE",
            "trigger_quality_flags": ["BLOCKED"],
        }
        print(f"[TRIGGER] FLAT_TOP_BREAKOUT state={result['trigger_state']} reason={result['trigger_reason']}")
        return result

    trigger_level = _safe_float(payload.get("trigger_level") or payload.get("trigger_price_reference"))
    invalidation_level = _safe_float(
        payload.get("invalidation_level")
        or payload.get("invalidation_price_reference")
        or payload.get("stop_level")
    )
    if trigger_level is None:
        result = {
            "trigger_type": "BREAKOUT_HIGH",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_trigger_level",
            "trigger_price_reference": None,
            "invalidation_price_reference": invalidation_level,
            "trigger_event_emitted": False,
            "execution_refinement_mode": "NONE",
            "trigger_quality_flags": ["BLOCKED", "MISSING_TRIGGER_REFERENCE"],
        }
        print(f"[TRIGGER] FLAT_TOP_BREAKOUT state={result['trigger_state']} reason={result['trigger_reason']}")
        return result

    if invalidation_level is None:
        result = {
            "trigger_type": "BREAKOUT_HIGH",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_invalidation_level",
            "trigger_price_reference": trigger_level,
            "invalidation_price_reference": None,
            "trigger_event_emitted": False,
            "execution_refinement_mode": "NONE",
            "trigger_quality_flags": ["BLOCKED", "MISSING_INVALIDATION_REFERENCE"],
        }
        print(f"[TRIGGER] FLAT_TOP_BREAKOUT state={result['trigger_state']} reason={result['trigger_reason']}")
        return result

    last = candles[-1]
    last_high = _safe_float(last.get("high") if isinstance(last, dict) else getattr(last, "high", None))
    last_close = _safe_float(last.get("close") if isinstance(last, dict) else getattr(last, "close", None))
    if last_high is None or last_close is None:
        result = {
            "trigger_type": "BREAKOUT_HIGH",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "malformed_price_payload",
            "trigger_price_reference": trigger_level,
            "invalidation_price_reference": invalidation_level,
            "trigger_event_emitted": False,
            "execution_refinement_mode": "NONE",
            "trigger_quality_flags": ["BLOCKED", "MISSING_LAST_CLOSE"],
        }
        print(f"[TRIGGER] FLAT_TOP_BREAKOUT state={result['trigger_state']} reason={result['trigger_reason']}")
        return result

    fired = last_high >= trigger_level and last_close > trigger_level
    result = {
        "trigger_type": "BREAKOUT_HIGH",
        "trigger_state": "FIRED" if fired else "ARMED",
        "trigger_ready_now": fired,
        "trigger_reason": "flat_top_break_confirmed" if fired else "flat_top_breakout_armed",
        "trigger_price_reference": trigger_level,
        "invalidation_price_reference": invalidation_level,
        "trigger_event_emitted": bool(fired),
        "execution_refinement_mode": "NONE",
        "trigger_quality_flags": [],
    }
    print(f"[TRIGGER] FLAT_TOP_BREAKOUT state={result['trigger_state']} reason={result['trigger_reason']}")
    return result
