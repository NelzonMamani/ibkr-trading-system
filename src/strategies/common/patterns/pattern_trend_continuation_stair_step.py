"""Shared TREND_CONTINUATION_STAIR_STEP pattern detection."""

from __future__ import annotations

from statistics import mean

from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult

_MIN_LOOKBACK = 5
_MIN_RVOL = 1.2
_MAX_SPREAD_PCT = 0.08
_MIN_IMPULSE_RANGE = 0.15


def _safe_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _read(item: object, field: str) -> object:
    if isinstance(item, dict):
        return item.get(field)
    return getattr(item, field, None)


def detect_trend_continuation_stair_step(inputs: PatternInputs) -> PatternResult:
    """Detect stair-step continuation: impulse -> shallow pullback -> higher-low -> breakout trigger."""

    def reject(reason: str) -> PatternResult:
        print(f"[PATTERN][STAIR_STEP] detected=False symbol={inputs.symbol} reason={reason}")
        return PatternResult(
            setup_id="P_TREND_CONTINUATION_STAIR_STEP",
            pattern_name="Trend Continuation (Stair-Step)",
            pattern_family=PatternFamily.BREAKOUT,
            detected=False,
            direction=Direction.LONG,
            confidence=0.0,
            setup_quality_tags=[],
            setup_family_id="TREND_CONTINUATION_STAIR_STEP",
            rationale_text=f"Rejected: {reason}",
            rejection_reason=reason,
            data_quality_flags=list(inputs.data_quality_flags),
            trigger_type="XL_STAIR_STEP_BREAKOUT",
            signal_class="ENTRY",
            trigger_mode="BREAKOUT_CONTINUATION",
        )

    candles = list(inputs.candles or [])

    if len(candles) < _MIN_LOOKBACK:
        return reject("invalid_inputs")

    if any(_safe_float(_read(c, "volume")) is None for c in candles[-_MIN_LOOKBACK:]):
        return reject("invalid_inputs")

    for field in ("open", "high", "low", "close"):
        if any(_safe_float(_read(c, field)) is None for c in candles[-_MIN_LOOKBACK:]):
            return reject("invalid_inputs")

    rvol = _safe_float(inputs.liquidity_context.rvol)
    spread = _safe_float(inputs.liquidity_context.spread)
    last_close = _safe_float(_read(candles[-1], "close"))
    if rvol is None or rvol < _MIN_RVOL or spread is None or last_close is None:
        return reject("invalid_inputs")

    spread_pct = spread if spread < 1 else spread / max(last_close, 1e-9)
    if spread_pct > _MAX_SPREAD_PCT:
        return reject("invalid_inputs")

    structure_window = candles
    structure_highs = [_safe_float(_read(c, "high")) for c in structure_window]
    structure_lows = [_safe_float(_read(c, "low")) for c in structure_window]
    if any(v is None for v in structure_highs + structure_lows):
        return reject("no_uptrend_structure")
    higher_high_count = sum(
        1 for idx in range(1, len(structure_highs)) if structure_highs[idx] > structure_highs[idx - 1]
    )
    higher_low_count = sum(
        1 for idx in range(1, len(structure_lows)) if structure_lows[idx] > structure_lows[idx - 1]
    )
    if higher_high_count < 2 or higher_low_count < 2:
        return reject("no_uptrend_structure")

    highs = [_safe_float(_read(c, "high")) for c in candles]
    lows = [_safe_float(_read(c, "low")) for c in candles]
    impulse_window_highs = highs[:-2] or highs
    impulse_window_lows = lows[:-2] or lows
    impulse_low = min(v for v in impulse_window_lows if v is not None)
    impulse_high = max(v for v in impulse_window_highs if v is not None)
    impulse_range = float(impulse_high - impulse_low)
    if impulse_range < _MIN_IMPULSE_RANGE:
        return reject("weak_impulse")

    pullback_slice = candles[-2:]
    pullback_low = min(_safe_float(_read(c, "low")) for c in pullback_slice)
    pullback_high = max(_safe_float(_read(c, "high")) for c in pullback_slice)
    if pullback_low is None or pullback_high is None:
        return reject("invalid_inputs")

    pullback_depth = float((impulse_high - pullback_low) / max(impulse_range, 1e-9))
    if pullback_depth >= 0.5:
        return reject("pullback_too_deep")

    impulse_volumes = [_safe_float(_read(c, "volume")) or 0.0 for c in candles[-8:-2]]
    pullback_volumes = [_safe_float(_read(c, "volume")) or 0.0 for c in pullback_slice]
    impulse_volume = mean(impulse_volumes)
    pullback_volume = pullback_volumes[0] if pullback_volumes else 0.0
    volume_ratio = pullback_volume / max(impulse_volume, 1e-9)
    pullback_is_active = _safe_float(_read(candles[-2], "close")) < _safe_float(_read(candles[-3], "close"))
    if pullback_is_active and pullback_volume >= impulse_volume:
        return reject("volume_not_confirming")

    previous_pullback_low = min(_safe_float(_read(c, "low")) for c in candles[-4:-2])
    if previous_pullback_low is None or pullback_low <= previous_pullback_low:
        return reject("no_higher_low_sequence")

    vwap = _safe_float(inputs.indicators.vwap)
    ema9 = _safe_float(inputs.indicators.ema9)
    ema20 = _safe_float(inputs.indicators.ema20)
    macd = _safe_float((inputs.news_context or {}).get("macd"))

    trend_valid = True
    if vwap is not None and last_close <= vwap:
        trend_valid = False
    if ema9 is not None and ema20 is not None and ema9 <= ema20:
        trend_valid = False
    if macd is not None and macd <= 0:
        trend_valid = False
    if not trend_valid:
        return reject("trend_not_validated")

    trigger_level = max(v for v in structure_highs[-3:]) if structure_highs else pullback_high
    stop_level = pullback_low
    invalidation_level = min(previous_pullback_low, pullback_low)
    higher_low_sequence_count = 2 if pullback_low > previous_pullback_low else 1
    confidence = min(0.9, 0.6 + (0.15 * min(1.0, rvol / 2.0)) + (0.1 * (1.0 - pullback_depth)))

    print(
        "[PATTERN][STAIR_STEP] "
        f"detected=True symbol={inputs.symbol} reason=detected trigger={trigger_level:.4f} stop={stop_level:.4f}"
    )

    return PatternResult(
        setup_id="P_TREND_CONTINUATION_STAIR_STEP",
        pattern_name="Trend Continuation (Stair-Step)",
        pattern_family=PatternFamily.BREAKOUT,
        detected=True,
        direction=Direction.LONG,
        confidence=confidence,
        setup_quality_tags=["uptrend", "shallow_pullback", "higher_low_sequence"],
        setup_family_id="TREND_CONTINUATION_STAIR_STEP",
        rationale_text="Stair-step continuation detected with higher-low sequence and breakout trigger defined.",
        rejection_reason=None,
        data_quality_flags=list(inputs.data_quality_flags),
        trigger_type="XL_STAIR_STEP_BREAKOUT",
        trigger_level=trigger_level,
        stop_level=stop_level,
        invalidation_level=invalidation_level,
        signal_class="ENTRY",
        trigger_mode="BREAKOUT_CONTINUATION",
        setup_metadata={
            "impulse_range": impulse_range,
            "pullback_depth": pullback_depth,
            "higher_low_sequence_count": higher_low_sequence_count,
            "rvol": rvol,
            "volume_ratio": volume_ratio,
        },
    )
