"""Shared trigger evaluator for ABCD continuation family."""

from __future__ import annotations

from datetime import datetime
from math import isfinite
from numbers import Real


def abcd_candle_rejection(candles, *, observed_at_utc=None, require_clock=False):
    """Bounded source/execution validity, reused by existing ABCD and GAP_GO owners."""
    if isinstance(observed_at_utc, str):
        try:
            observed_at_utc = datetime.fromisoformat(observed_at_utc)
        except ValueError:
            return "INVALID_CANDLE_TIMESTAMPS"
    if observed_at_utc is not None and (not isinstance(observed_at_utc, datetime)
                                       or observed_at_utc.tzinfo is None):
        return "INVALID_CANDLE_TIMESTAMPS"
    if require_clock and observed_at_utc is None:
        return "INVALID_CANDLE_TIMESTAMPS"
    previous = None
    for candle in candles:
        read = candle.get if isinstance(candle, dict) else lambda key: getattr(candle, key, None)
        values = [read(key) for key in ("open", "high", "low", "close", "volume")]
        if any(isinstance(v, bool) or not isinstance(v, Real) or not isfinite(v) for v in values):
            return "INVALID_CANDLE_DATA"
        opening, high, low, close, volume = values
        if min(opening, high, low, close) <= 0 or volume < 0 or low > min(opening, close) or high < max(opening, close):
            return "INVALID_CANDLE_DATA"
        if observed_at_utc is not None:
            timestamp = read("timestamp")
            if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
                return "INVALID_CANDLE_TIMESTAMPS"
            if timestamp > observed_at_utc:
                return "FUTURE_CANDLE_DATA"
            if previous is not None and timestamp <= previous:
                return "INVALID_CANDLE_TIMESTAMPS"
            previous = timestamp
    return None


def _safe_float(value):
    try:
        parsed = None if value is None else float(value)
        return parsed if parsed is not None and isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def evaluate_abcd_continuation_trigger(pattern_result, inputs):
    levels = inputs if isinstance(inputs, dict) else {}
    candles = list(levels.get("candles") or [])
    if not candles:
        payload = {
            "trigger_type": "XL_ABCD_CONTINUATION",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_candles",
        }
        print(
            "[TRIGGER][ABCD][STATE] "
            f"state={payload['trigger_state']} reason={payload['trigger_reason']}"
        )
        return payload

    result_payload = pattern_result if isinstance(pattern_result, dict) else {}
    stream = result_payload.get("execution_stream")
    if isinstance(stream, dict):
        rejection = abcd_candle_rejection(candles, observed_at_utc=stream.get("observed_at_utc"), require_clock=True)
        if rejection:
            return {"trigger_type": "XL_ABCD_CONTINUATION", "trigger_state": "BLOCKED",
                    "trigger_ready_now": False, "trigger_reason": "abcd_" + rejection.lower()}
    trigger_level = _safe_float(result_payload.get("trigger_level"))
    if trigger_level is None:
        payload = {
            "trigger_type": "XL_ABCD_CONTINUATION",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_trigger_level",
        }
        print(
            "[TRIGGER][ABCD][STATE] "
            f"state={payload['trigger_state']} reason={payload['trigger_reason']}"
        )
        return payload

    last = candles[-1]
    last_close = _safe_float(last.get("close") if isinstance(last, dict) else getattr(last, "close", None))
    last_high = _safe_float(last.get("high") if isinstance(last, dict) else getattr(last, "high", None))
    if last_close is None and last_high is None:
        payload = {
            "trigger_type": "XL_ABCD_CONTINUATION",
            "trigger_state": "BLOCKED",
            "trigger_ready_now": False,
            "trigger_reason": "missing_price_fields",
        }
        print(
            "[TRIGGER][ABCD][STATE] "
            f"state={payload['trigger_state']} reason={payload['trigger_reason']}"
        )
        return payload

    fired = bool(last_close is not None and last_high is not None and last_close > trigger_level and last_high >= trigger_level)
    a_price = _safe_float(result_payload.get("anchor_a_price"))
    b_price = _safe_float(result_payload.get("anchor_b_price"))
    c_price = _safe_float(result_payload.get("anchor_c_price"))
    retracement_pct = _safe_float(result_payload.get("retracement_pct"))
    d_projection = _safe_float(result_payload.get("d_projection"))
    payload = {
        "trigger_type": "XL_ABCD_CONTINUATION",
        "trigger_state": "FIRED" if fired else "ARMED",
        "trigger_ready_now": fired,
        "trigger_reason": "abcd_continuation_break_fired" if fired else "awaiting_abcd_continuation_break",
    }
    print(
        "[TRIGGER][ABCD][STATE] "
        f"state={payload['trigger_state']} reason={payload['trigger_reason']} "
        f"A={a_price} B={b_price} C={c_price} retracement={retracement_pct} "
        f"trigger={trigger_level} projection={d_projection}"
    )
    return payload
