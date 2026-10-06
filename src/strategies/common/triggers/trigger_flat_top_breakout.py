"""Shared trigger evaluator for FLAT_TOP_BREAKOUT family."""

from __future__ import annotations


def _safe_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def evaluate_flat_top_breakout_trigger(pattern_result, inputs):
    levels = inputs if isinstance(inputs, dict) else {}
    candles = list(levels.get("candles") or [])
    if not candles:
        return {
            "trigger_type": "BREAKOUT_HIGH",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_candles",
            "trigger_price_reference": None,
            "invalidation_price_reference": None,
            "trigger_quality_flags": ["BLOCKED", "MISSING_CANDLES"],
        }

    payload = pattern_result if isinstance(pattern_result, dict) else {}
    trigger_level = _safe_float(payload.get("trigger_level"))
    invalidation_level = _safe_float(payload.get("invalidation_level") or payload.get("stop_level"))
    if trigger_level is None:
        return {
            "trigger_type": "BREAKOUT_HIGH",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_trigger_level",
            "trigger_price_reference": None,
            "invalidation_price_reference": invalidation_level,
            "trigger_quality_flags": ["BLOCKED", "MISSING_TRIGGER_REFERENCE"],
        }

    last = candles[-1]
    last_close = _safe_float(last.get("close") if isinstance(last, dict) else getattr(last, "close", None))
    last_high = _safe_float(last.get("high") if isinstance(last, dict) else getattr(last, "high", None))
    if last_close is None and last_high is None:
        return {
            "trigger_type": "BREAKOUT_HIGH",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "malformed_price_payload",
            "trigger_price_reference": trigger_level,
            "invalidation_price_reference": invalidation_level,
            "trigger_quality_flags": ["BLOCKED", "MALFORMED_PRICE_PAYLOAD"],
        }

    fired = (
        last_close is not None
        and last_high is not None
        and last_close >= trigger_level
        and last_high >= trigger_level
    )
    flags = []
    if invalidation_level is None:
        flags.append("MISSING_INVALIDATION_REFERENCE")
    if (
        invalidation_level is not None
        and last_close is not None
        and last_close <= invalidation_level
    ):
        flags.append("NEAR_INVALIDATION")

    return {
        "trigger_type": "BREAKOUT_HIGH",
        "trigger_state": "FIRED" if fired else "ARMED",
        "trigger_ready_now": fired,
        "trigger_reason": "breakout_already_through_level" if fired else "breakout_not_cleared",
        "trigger_price_reference": trigger_level,
        "invalidation_price_reference": invalidation_level,
        "trigger_quality_flags": flags,
    }


def evaluate_consolidation_breakout_trigger(pattern_result, inputs):
    """Existing range break plus same-stream volume confirmation; no RVOL substitute."""
    out = evaluate_flat_top_breakout_trigger(pattern_result, inputs)
    if not out.get("trigger_ready_now"):
        return out
    candles = list((inputs or {}).get("candles") or [])
    def volume(candle):
        return _safe_float(candle.get("volume") if isinstance(candle, dict) else getattr(candle, "volume", None))
    values = [volume(candle) for candle in candles[-5:]]
    # The detector's last-volume >= mean(last five) law is equivalent to
    # last-volume >= mean(previous four); keep evidence in the execution stream.
    confirmed = len(values) == 5 and all(v is not None and v > 0 for v in values)
    if confirmed:
        confirmed = values[-1] >= sum(values[:-1]) / 4
    if not confirmed:
        return {**out, "trigger_state": "BLOCKED", "trigger_ready_now": False,
                "trigger_reason": "breakout_volume_unconfirmed",
                "trigger_quality_flags": ["BLOCKED", "BREAKOUT_VOLUME_UNCONFIRMED"]}
    return {**out, "trigger_reason": "consolidation_breakout_confirmed"}
