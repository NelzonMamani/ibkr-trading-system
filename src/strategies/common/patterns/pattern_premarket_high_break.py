"""Shared PREMARKET_HIGH_BREAK pattern detection."""

from __future__ import annotations

from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.strategy_contracts import SessionContext


_VALID_SESSIONS = {SessionContext.PRE, SessionContext.REGULAR}


def _safe_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def detect_premarket_high_break(inputs: PatternInputs) -> PatternResult:
    """Detect PMH initial break or reclaim-and-hold with quality filters."""

    def reject(reason: str, rationale: str | None = None) -> PatternResult:
        print(
            f"[PATTERN_TRACE][RESULT] symbol={inputs.symbol} pattern=Premarket High Break "
            f"detected=False reason={reason}"
        )
        return PatternResult(
            setup_id="P_PREMARKET_HIGH_BREAK",
            pattern_name="Premarket High Break",
            pattern_family=PatternFamily.BREAKOUT,
            detected=False,
            direction=Direction.LONG,
            confidence=0.0,
            setup_quality_tags=[],
            setup_family_id="PREMARKET_HIGH_BREAK",
            rationale_text=rationale or f"Rejected: {reason}",
            rejection_reason=reason,
            data_quality_flags=list(inputs.data_quality_flags),
            trigger_type="XL_PREMARKET_HIGH_BREAK",
        )

    print(f"[PATTERN_TRACE][CALL] symbol={inputs.symbol} pattern=Premarket High Break")
    if inputs.session_context not in _VALID_SESSIONS:
        return reject("invalid_session")

    candles = list(inputs.candles or [])
    if len(candles) < 2:
        return reject("missing_candles")

    pmh = _safe_float(getattr(inputs.levels, "premarket_high", None))
    if pmh is None:
        return reject("missing_premarket_high")

    spread = _safe_float(getattr(inputs.liquidity_context, "spread", None))
    if spread is None:
        return reject("low_liquidity")
    if spread > 0.08:
        return reject("wide_spread")

    last = candles[-1]
    prev = candles[-2]
    vals = {
        "last_open": _safe_float(getattr(last, "open", None)),
        "last_high": _safe_float(getattr(last, "high", None)),
        "last_low": _safe_float(getattr(last, "low", None)),
        "last_close": _safe_float(getattr(last, "close", None)),
        "prev_close": _safe_float(getattr(prev, "close", None)),
    }
    if any(v is None for v in vals.values()):
        return reject("missing_price_fields")

    last_open = float(vals["last_open"])
    last_high = float(vals["last_high"])
    last_low = float(vals["last_low"])
    last_close = float(vals["last_close"])
    prev_close = float(vals["prev_close"])

    if last_high > pmh and last_close < pmh:
        return reject("wick_through_only")
    if last_close < pmh:
        return reject("failed_acceptance")

    recent = candles[-6:]
    saw_dip_below = any((_safe_float(getattr(c, "low", None)) or pmh) < pmh for c in recent)
    holding_above = last_close >= pmh

    initial_break = prev_close <= pmh and last_close >= pmh and holding_above
    reclaim_break = saw_dip_below and last_close >= pmh and holding_above
    post_break_hold = prev_close >= pmh and last_close >= pmh

    if not initial_break and not reclaim_break and not post_break_hold:
        return reject("failed_acceptance")

    avg_vol = sum(max(0.0, _safe_float(getattr(c, "volume", None)) or 0.0) for c in recent[:-1]) / max(1, len(recent) - 1)
    last_volume = max(0.0, _safe_float(getattr(last, "volume", None)) or 0.0)
    rvol = _safe_float(getattr(inputs.liquidity_context, "rvol", None))
    volume_ok = (rvol is not None and rvol >= 1.3) or (avg_vol > 0 and last_volume >= avg_vol)
    if not volume_ok:
        return reject("insufficient_volume_confirmation")

    body = max(abs(last_close - last_open), 1e-9)
    upper_wick = max(last_high - max(last_open, last_close), 0.0)
    if upper_wick > body * 1.6:
        return reject("pmh_break_exhaustion")

    if reclaim_break:
        path = "reclaim"
    elif initial_break:
        path = "initial_break"
    else:
        path = "post_break_hold"
    stop_buffer = max(0.01, pmh * 0.001)
    stop_level = pmh - stop_buffer
    confidence = 0.68 + (0.07 if path == "reclaim" else 0.03) + (0.05 if (rvol or 0.0) >= 2.0 else 0.0)

    print(
        "[PATTERN_TRACE][RESULT] "
        f"symbol={inputs.symbol} pattern=Premarket High Break detected=True reason=detected pmh={pmh:.4f} path={path}"
    )
    return PatternResult(
        setup_id="P_PREMARKET_HIGH_BREAK",
        pattern_name="Premarket High Break",
        pattern_family=PatternFamily.BREAKOUT,
        detected=True,
        direction=Direction.LONG,
        confidence=min(confidence, 0.9),
        setup_quality_tags=["pmh_break", path, "volume_confirmed"],
        setup_family_id="PREMARKET_HIGH_BREAK",
        rationale_text="Reclaim and hold above premarket high",
        rejection_reason=None,
        data_quality_flags=list(inputs.data_quality_flags),
        trigger_type="XL_PREMARKET_HIGH_BREAK",
        trigger_level=pmh,
        stop_level=stop_level,
        invalidation_level=pmh,
        setup_metadata={"pmh_path": path, "level_type": "PREMARKET_HIGH"},
    )
