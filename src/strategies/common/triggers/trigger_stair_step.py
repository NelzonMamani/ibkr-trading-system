"""Shared trigger evaluator for TREND_CONTINUATION_STAIR_STEP family."""

from __future__ import annotations


def _safe_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _read(item, field: str):
    if isinstance(item, dict):
        return item.get(field)
    return getattr(item, field, None)


def evaluate_stair_step_trigger(payload, values):
    levels = values if isinstance(values, dict) else {}
    candles = list(levels.get("candles") or [])
    data = payload if isinstance(payload, dict) else {}

    trigger_level = _safe_float(data.get("trigger_level"))
    stop_level = _safe_float(data.get("stop_level"))
    invalidation_level = _safe_float(data.get("invalidation_level"))

    if not candles or trigger_level is None or stop_level is None or invalidation_level is None:
        out = {
            "trigger_type": "XL_STAIR_STEP_BREAKOUT",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_fields",
            "trigger_price_reference": trigger_level,
            "invalidation_price_reference": invalidation_level,
            "execution_refinement_mode": "RECLAIM_BREAKOUT",
        }
        print(f"[TRIGGER][STAIR_STEP] fired=False reason={out['trigger_reason']}")
        return out

    last = candles[-1]
    prev = candles[-2] if len(candles) > 1 else None

    prev_close = _safe_float(_read(prev, "close"))
    last_close = _safe_float(_read(last, "close"))
    last_high = _safe_float(_read(last, "high"))
    last_low = _safe_float(_read(last, "low"))
    last_open = _safe_float(_read(last, "open"))
    last_volume = _safe_float(_read(last, "volume"))

    if None in {prev_close, last_close, last_high, last_low, last_open, last_volume}:
        out = {
            "trigger_type": "XL_STAIR_STEP_BREAKOUT",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_fields",
            "trigger_price_reference": trigger_level,
            "invalidation_price_reference": invalidation_level,
            "execution_refinement_mode": "RECLAIM_BREAKOUT",
        }
        print(f"[TRIGGER][STAIR_STEP] fired=False reason={out['trigger_reason']}")
        return out

    min_break_pct = max(0.0005, _safe_float(levels.get("min_break_pct")) or 0.001)
    breakout = prev_close <= trigger_level and last_close > trigger_level * (1 + min_break_pct) and last_high >= trigger_level

    if not breakout:
        out = {
            "trigger_type": "XL_STAIR_STEP_BREAKOUT",
            "trigger_state": "ARMED",
            "trigger_ready_now": False,
            "trigger_reason": "awaiting_breakout",
            "trigger_price_reference": trigger_level,
            "invalidation_price_reference": invalidation_level,
            "execution_refinement_mode": "RECLAIM_BREAKOUT",
        }
        print(f"[TRIGGER][STAIR_STEP] fired=False reason={out['trigger_reason']}")
        return out

    candle_range = max(last_high - last_low, 1e-9)
    candle_body = abs(last_close - last_open)
    upper_wick = last_high - max(last_close, last_open)
    wick_only = candle_body / candle_range < 0.25 and upper_wick / candle_range > 0.5
    exhaustion = candle_body / candle_range < 0.2 and (last_close - last_low) / candle_range > 0.85

    if wick_only or exhaustion:
        out = {
            "trigger_type": "XL_STAIR_STEP_BREAKOUT",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "breakout_shape_invalid",
            "trigger_price_reference": trigger_level,
            "invalidation_price_reference": invalidation_level,
            "execution_refinement_mode": "RECLAIM_BREAKOUT",
        }
        print(f"[TRIGGER][STAIR_STEP] fired=False reason={out['trigger_reason']}")
        return out

    rvol = _safe_float(levels.get("rvol"))
    avg_volume = _safe_float(levels.get("avg_volume"))
    if avg_volume is None:
        vols = [_safe_float(_read(c, "volume")) or 0.0 for c in candles[-5:]]
        avg_volume = sum(vols) / max(len(vols), 1)

    volume_ok = (rvol is not None and rvol >= 1.2) or (last_volume >= max(avg_volume or 0.0, 1.0))
    if not volume_ok:
        out = {
            "trigger_type": "XL_STAIR_STEP_BREAKOUT",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "liquidity_confirmation_failed",
            "trigger_price_reference": trigger_level,
            "invalidation_price_reference": invalidation_level,
            "execution_refinement_mode": "RECLAIM_BREAKOUT",
        }
        print(f"[TRIGGER][STAIR_STEP] fired=False reason={out['trigger_reason']}")
        return out

    out = {
        "trigger_type": "XL_STAIR_STEP_BREAKOUT",
        "trigger_state": "FIRED",
        "trigger_ready_now": True,
        "trigger_reason": "stair_step_breakout_confirmed",
        "trigger_price_reference": trigger_level,
        "invalidation_price_reference": invalidation_level,
        "execution_refinement_mode": "RECLAIM_BREAKOUT",
    }
    print(f"[TRIGGER][STAIR_STEP] fired=True reason={out['trigger_reason']}")
    return out
