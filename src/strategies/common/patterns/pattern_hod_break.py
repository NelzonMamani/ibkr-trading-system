"""Shared HOD_BREAK pattern detection."""

from __future__ import annotations

from math import isfinite

from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs, _timeframe_provenance
from src.strategies.ross_momentum.policy.pattern_input_policy import PatternInputPolicy
from src.strategies.common.triggers.trigger_abcd_continuation import abcd_candle_rejection
from src.strategies.ross_momentum.strategy_policy import HOD_DESCRIPTIVE_OBJECTIVE
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.strategy_contracts import SessionContext

_VALID_SESSIONS = {SessionContext.REGULAR}


def _safe_float(value: object) -> float | None:
    try:
        number = None if value is None or isinstance(value, bool) else float(value)
        return number if number is not None and isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _read(obj, field: str):
    if isinstance(obj, dict):
        return obj.get(field)
    return getattr(obj, field, None)


def detect_hod_break(inputs: PatternInputs) -> PatternResult:
    """Detect HOD continuation compression with breakout-ready structure."""

    def reject(reason: str, rationale: str | None = None) -> PatternResult:
        print(
            f"[PATTERN_TRACE][RESULT] symbol={inputs.symbol} pattern=HOD Break "
            f"detected=False rejection_reason={reason}"
        )
        return PatternResult(
            setup_id="P_HOD_BREAK",
            pattern_name="High of Day Break",
            pattern_family=PatternFamily.BREAKOUT,
            detected=False,
            direction=Direction.LONG,
            confidence=0.0,
            setup_quality_tags=[],
            setup_family_id="HOD_BREAK",
            rationale_text=rationale or f"Rejected: {reason}",
            rejection_reason=reason,
            data_quality_flags=list(inputs.data_quality_flags),
            trigger_type="XL_HOD_BREAK",
        )

    print(f"[PATTERN_TRACE][CALL] symbol={inputs.symbol} pattern=HOD Break")
    if inputs.session_context not in _VALID_SESSIONS:
        return reject("invalid_session", "HOD Break is valid only in regular/RTH session.")

    candles = list(inputs.candles or [])
    if len(candles) < 6:
        return reject("missing_candles")

    spread = _safe_float(getattr(inputs.liquidity_context, "spread", None))
    if spread is None:
        return reject("low_liquidity")
    if spread > 0.08:
        return reject("wide_spread")

    last = candles[-1]
    prev = candles[-2]

    hod = _safe_float(getattr(inputs.levels, "hod", None))
    hod_source = str(getattr(inputs.levels, "hod_source", None) or _read(getattr(inputs.levels, "key_levels", {}), "hod_source") or "").upper()
    # Runtime owns this measured reference separately from legacy contextual
    # HOD (which may include PRE/forming highs and is also consumed by Key).
    established_hod = getattr(inputs.levels, "established_rth_hod", None)
    if established_hod is not None:
        hod = _safe_float(established_hod)
        hod_source = "RTH"
    if hod_source != "RTH":
        return reject("invalid_hod_source", "HOD source must be explicitly RTH.")
    if hod is None:
        return reject("missing_hod")

    if hod <= 0:
        return reject("missing_hod")

    rejection = abcd_candle_rejection(candles, observed_at_utc=inputs.observed_at_utc,
                                      require_clock=bool(inputs.timeframe_provenance))
    if rejection:
        return reject(rejection)
    if inputs.observed_at_utc is not None:
        status = _timeframe_provenance(candles, inputs.timeframe,
            PatternInputPolicy.from_policy_v2(), symbol=inputs.symbol, now_utc=inputs.observed_at_utc)
        if status != "PRESENT":
            return reject("STALE_SOURCE")

    last_open = _safe_float(_read(last, "open"))
    last_high = _safe_float(_read(last, "high"))
    last_low = _safe_float(_read(last, "low"))
    last_close = _safe_float(_read(last, "close"))
    prev_close = _safe_float(_read(prev, "close"))
    if any(v is None for v in (last_open, last_high, last_low, last_close, prev_close)):
        return reject("missing_price_fields")

    distance_to_hod = (hod - float(last_close)) / hod
    if distance_to_hod > 0.004:
        return reject("no_hod_proximity", f"Distance to HOD too large: {distance_to_hod:.4%}")

    recent = candles[-4:]
    recent_high = max(_safe_float(_read(c, "high")) or float("-inf") for c in recent)
    recent_low = min(_safe_float(_read(c, "low")) or float("inf") for c in recent)
    if recent_high == float("-inf") or recent_low == float("inf"):
        return reject("missing_price_fields")

    range_compression = (recent_high - recent_low) / hod
    if range_compression > 0.018:
        return reject("no_compression", f"Recent range too wide: {range_compression:.4%}")

    ema9 = _safe_float(getattr(inputs.indicators, "ema9", None))
    ema20 = _safe_float(getattr(inputs.indicators, "ema20", None))
    vwap = _safe_float(getattr(inputs.indicators, "vwap", None))
    trend_context_ok = True
    if ema9 is not None and last_close < ema9:
        trend_context_ok = False
    if ema20 is not None and last_close < ema20:
        trend_context_ok = False
    if vwap is not None and last_close < vwap:
        trend_context_ok = False
    if not trend_context_ok:
        return reject("broken_trend_context")

    rvol = _safe_float(getattr(inputs.liquidity_context, "rvol", None))
    avg_volume = sum(max(0.0, _safe_float(_read(c, "volume")) or 0.0) for c in candles[-6:-1]) / 5
    last_volume = max(0.0, _safe_float(_read(last, "volume")) or 0.0)
    volume_ok = (rvol is not None and rvol >= 1.25) or (avg_volume > 0 and last_volume >= avg_volume)
    if not volume_ok:
        return reject("insufficient_volume_confirmation")

    body = abs(float(last_close) - float(last_open))
    full_range = max(float(last_high) - float(last_low), 1e-9)
    upper_wick = max(float(last_high) - max(float(last_close), float(last_open)), 0.0)
    if float(last_high) > hod and float(last_close) < hod:
        return reject("wick_through_only")
    if body > 0 and upper_wick > body * 1.8:
        return reject("exhaustion_break")
    if body / full_range < 0.2:
        return reject("chaotic_tape")

    consolidation_lows = [_safe_float(_read(c, "low")) for c in candles[-5:-1]]
    consolidation_lows = [float(v) for v in consolidation_lows if v is not None]
    recent_structure_low = min(consolidation_lows) if consolidation_lows else float(last_low)
    stop_level = recent_structure_low

    print(
        "[PATTERN_TRACE][INPUT] "
        f"symbol={inputs.symbol} hod={hod:.4f} level_source={hod_source} "
        f"distance_to_hod={distance_to_hod:.4%} range_compression={range_compression:.4%}"
    )
    print(
        f"[PATTERN_TRACE][RESULT] symbol={inputs.symbol} pattern=HOD Break "
        "detected=True rejection_reason=detected"
    )
    return PatternResult(
        setup_id="P_HOD_BREAK",
        pattern_name="High of Day Break",
        pattern_family=PatternFamily.BREAKOUT,
        detected=True,
        direction=Direction.LONG,
        confidence=0.71,
        setup_quality_tags=["hod", "continuation", "compression", "breakout_ready"],
        setup_family_id="HOD_BREAK",
        target_suggestion=HOD_DESCRIPTIVE_OBJECTIVE,
        rationale_text=(
            "Price is compressing beneath the active session HOD with constructive continuation context and "
            "sufficient participation for a breakout trigger."
        ),
        rejection_reason=None,
        data_quality_flags=list(inputs.data_quality_flags),
        trigger_type="XL_HOD_BREAK",
        trigger_level=hod,
        stop_level=stop_level,
        invalidation_level=stop_level,
        setup_metadata={
            "level_type": "HOD",
            "level_source": hod_source,
            "distance_to_hod": distance_to_hod,
            "range_compression": range_compression,
            "rvol": rvol,
            "recent_structure_low": recent_structure_low,
        },
    )
