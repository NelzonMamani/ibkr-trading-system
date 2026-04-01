"""Shared trigger evaluator for BULL_FLAG family."""

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


def evaluate_bull_flag_trigger(payload, values):
    data = payload if isinstance(payload, dict) else {}
    levels = values if isinstance(values, dict) else {}
    candles = list(levels.get("candles") or [])

    trigger_level = _safe_float(data.get("trigger_level"))
    stop_level = _safe_float(data.get("stop_level"))
    invalidation_level = _safe_float(data.get("invalidation_level"))
    base = {
        "trigger_type": "BULL_FLAG_BREAKOUT",
        "trigger_price_reference": trigger_level,
        "invalidation_price_reference": invalidation_level,
        "trigger_level": trigger_level,
        "stop_level": stop_level,
        "execution_refinement_mode": "BREAKOUT_CONTINUATION",
    }
    if len(candles) < 2 or None in {trigger_level, stop_level, invalidation_level}:
        out = {**base, "trigger_state": "BLOCKED", "trigger_ready_now": False, "trigger_reason": "missing_fields"}
        print(f"[TRIGGER][BULL_FLAG] fired=False reason={out['trigger_reason']}")
        return out

    prev = candles[-2]
    last = candles[-1]
    prev_close = _safe_float(_read(prev, "close"))
    last_close = _safe_float(_read(last, "close"))
    last_high = _safe_float(_read(last, "high"))
    last_low = _safe_float(_read(last, "low"))
    last_open = _safe_float(_read(last, "open"))
    last_volume = _safe_float(_read(last, "volume"))
    if None in {prev_close, last_close, last_high, last_low, last_open, last_volume}:
        out = {**base, "trigger_state": "BLOCKED", "trigger_ready_now": False, "trigger_reason": "missing_fields"}
        print(f"[TRIGGER][BULL_FLAG] fired=False reason={out['trigger_reason']}")
        return out

    if not (prev_close <= trigger_level and last_close > trigger_level and last_high >= trigger_level):
        out = {**base, "trigger_state": "ARMED", "trigger_ready_now": False, "trigger_reason": "awaiting_breakout"}
        print(f"[TRIGGER][BULL_FLAG] fired=False reason={out['trigger_reason']}")
        return out

    candle_range = max(last_high - last_low, 1e-9)
    body = abs(last_close - last_open)
    upper_wick = max(last_high - max(last_open, last_close), 0.0)
    wick_only_breakout = body / candle_range < 0.25 and upper_wick / candle_range > 0.55
    if wick_only_breakout:
        out = {**base, "trigger_state": "BLOCKED", "trigger_ready_now": False, "trigger_reason": "breakout_shape_invalid"}
        print(f"[TRIGGER][BULL_FLAG] fired=False reason={out['trigger_reason']}")
        return out

    spread = _safe_float(levels.get("spread"))
    max_spread = _safe_float(levels.get("max_spread")) or 0.05
    if spread is not None and spread > max_spread:
        out = {**base, "trigger_state": "BLOCKED", "trigger_ready_now": False, "trigger_reason": "spread_too_wide"}
        print(f"[TRIGGER][BULL_FLAG] fired=False reason={out['trigger_reason']}")
        return out

    rvol = _safe_float(levels.get("rvol"))
    avg_volume = _safe_float(levels.get("avg_volume"))
    if avg_volume is None:
        prior_vols = [_safe_float(_read(c, "volume")) or 0.0 for c in candles[:-1]]
        avg_volume = sum(prior_vols) / max(1, len(prior_vols))
    volume_ok = (rvol is not None and rvol >= 1.1) or (last_volume >= max(avg_volume or 0.0, 1.0))
    if not volume_ok:
        out = {**base, "trigger_state": "BLOCKED", "trigger_ready_now": False, "trigger_reason": "liquidity_confirmation_failed"}
        print(f"[TRIGGER][BULL_FLAG] fired=False reason={out['trigger_reason']}")
        return out

    out = {**base, "trigger_state": "FIRED", "trigger_ready_now": True, "trigger_reason": "bull_flag_breakout_confirmed"}
    print("[TRIGGER][BULL_FLAG] fired=True reason=bull_flag_breakout_confirmed")
    return out
