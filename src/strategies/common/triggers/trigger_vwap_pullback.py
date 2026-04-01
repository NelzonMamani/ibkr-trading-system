"""Shared trigger evaluator for VWAP_PULLBACK family."""

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


def evaluate_vwap_pullback_trigger(payload, values):
    data = payload if isinstance(payload, dict) else {}
    levels = values if isinstance(values, dict) else {}
    candles = list(levels.get("candles") or [])

    trigger_level = _safe_float(data.get("trigger_level"))
    stop_level = _safe_float(data.get("stop_level"))
    invalidation_level = _safe_float(data.get("invalidation_level"))

    base = {
        "trigger_type": "XL_VWAP_PULLBACK_BREAKOUT",
        "trigger_price_reference": trigger_level,
        "invalidation_price_reference": invalidation_level,
        "trigger_level": trigger_level,
        "stop_level": stop_level,
        "execution_refinement_mode": "RECLAIM_BREAKOUT",
    }

    if len(candles) < 2 or trigger_level is None or stop_level is None or invalidation_level is None:
        out = {**base, "trigger_state": "BLOCKED", "trigger_ready_now": False, "trigger_reason": "missing_fields"}
        print(f"[TRIGGER][VWAP_PULLBACK] fired=False reason={out['trigger_reason']}")
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
        print(f"[TRIGGER][VWAP_PULLBACK] fired=False reason={out['trigger_reason']}")
        return out

    min_break_pct = max(0.0005, _safe_float(levels.get("min_break_pct")) or 0.001)
    breakout = prev_close <= trigger_level and last_close > trigger_level * (1 + min_break_pct) and last_high >= trigger_level
    if not breakout:
        out = {**base, "trigger_state": "ARMED", "trigger_ready_now": False, "trigger_reason": "awaiting_breakout"}
        print(f"[TRIGGER][VWAP_PULLBACK] fired=False reason={out['trigger_reason']}")
        return out

    candle_range = max(last_high - last_low, 1e-9)
    body = abs(last_close - last_open)
    upper_wick = max(last_high - max(last_close, last_open), 0.0)
    wick_only_breakout = body / candle_range < 0.25 and upper_wick / candle_range > 0.5
    exhaustion = body / candle_range < 0.2 or (body > 0 and upper_wick > body * 1.8)
    if wick_only_breakout or exhaustion:
        out = {**base, "trigger_state": "BLOCKED", "trigger_ready_now": False, "trigger_reason": "breakout_shape_invalid"}
        print(f"[TRIGGER][VWAP_PULLBACK] fired=False reason={out['trigger_reason']}")
        return out

    rvol = _safe_float(levels.get("rvol"))
    avg_volume = _safe_float(levels.get("avg_volume"))
    if avg_volume is None:
        prior_vols = [_safe_float(_read(c, "volume")) or 0.0 for c in candles[:-1]]
        avg_volume = sum(prior_vols) / max(len(prior_vols), 1)
    volume_ok = (rvol is not None and rvol >= 1.2) or (last_volume >= max(avg_volume or 0.0, 1.0))
    if not volume_ok:
        out = {**base, "trigger_state": "BLOCKED", "trigger_ready_now": False, "trigger_reason": "liquidity_confirmation_failed"}
        print(f"[TRIGGER][VWAP_PULLBACK] fired=False reason={out['trigger_reason']}")
        return out

    out = {**base, "trigger_state": "FIRED", "trigger_ready_now": True, "trigger_reason": "vwap_pullback_breakout_confirmed"}
    print(f"[TRIGGER][VWAP_PULLBACK] fired=True reason={out['trigger_reason']}")
    return out
