"""Shared FLAT_TOP_BREAKOUT pattern detection."""

from __future__ import annotations

from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult

_MIN_CANDLES = 5
_WINDOW_SIZE = 10
_TOLERANCE_PCT = 0.001
_MIN_TOUCHES = 2
_MIN_RVOL = 1.2
_MAX_SPREAD_PCT = 0.01


def _safe_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _spread_to_pct(spread: float, price_ref: float) -> float:
    if spread < 0:
        return 1.0
    if spread < 1.0:
        return spread
    return spread / max(price_ref, 1e-9)


def detect_flat_top_breakout(inputs: PatternInputs) -> PatternResult:
    """Detect structural readiness for a canonical Flat Top Breakout family."""

    def reject(reason: str, *, quality_tags: list[str] | None = None) -> PatternResult:
        print(f"[PATTERN] FLAT_TOP_BREAKOUT detected=False symbol={inputs.symbol} reason={reason}")
        return PatternResult(
            setup_id="P_FLAT_TOP_BREAKOUT",
            pattern_name="Flat Top Breakout",
            pattern_family=PatternFamily.BREAKOUT,
            detected=False,
            direction=Direction.LONG,
            confidence=0.0,
            setup_quality_tags=list(quality_tags or []),
            setup_family_id="FLAT_TOP_BREAKOUT",
            rationale_text=f"Rejected: {reason}",
            rejection_reason=reason,
            data_quality_flags=list(inputs.data_quality_flags),
            trigger_type="BREAKOUT_HIGH",
        )

    candles = list(inputs.candles or [])
    if len(candles) < _MIN_CANDLES:
        return reject("insufficient_candles")

    rvol = _safe_float(inputs.liquidity_context.rvol)
    spread = _safe_float(inputs.liquidity_context.spread)
    last_close = _safe_float(getattr(candles[-1], "close", None))
    if rvol is None or spread is None or last_close is None:
        return reject("missing_liquidity_context")
    if rvol < _MIN_RVOL:
        return reject("rvol_below_threshold")
    spread_pct = _spread_to_pct(spread, last_close)
    if spread_pct > _MAX_SPREAD_PCT:
        return reject("spread_too_wide")

    window = candles[-min(len(candles), _WINDOW_SIZE) :]
    highs = [_safe_float(getattr(candle, "high", None)) for candle in window]
    lows = [_safe_float(getattr(candle, "low", None)) for candle in window]
    closes = [_safe_float(getattr(candle, "close", None)) for candle in window]
    if any(v is None for v in highs + lows + closes):
        return reject("missing_price_fields")

    resistance = max(float(v) for v in highs if v is not None)
    tolerance_abs = max(resistance * _TOLERANCE_PCT, 1e-6)
    touches = [idx for idx, high in enumerate(highs) if high is not None and abs(high - resistance) <= tolerance_abs]
    if not touches:
        return reject("missing_flat_resistance")
    if len(touches) < _MIN_TOUCHES:
        return reject("insufficient_resistance_touches")

    touch_highs = [float(highs[idx]) for idx in touches]
    if max(touch_highs) - min(touch_highs) > tolerance_abs * 1.1:
        return reject("resistance_not_flat")

    if len(lows) < 4:
        return reject("insufficient_candles")
    first_half = lows[: len(lows) // 2]
    second_half = lows[len(lows) // 2 :]
    if not first_half or not second_half:
        return reject("no_supportive_pressure_under_resistance")
    early_low = min(float(v) for v in first_half if v is not None)
    late_low = min(float(v) for v in second_half if v is not None)
    lows_not_rising = late_low < (early_low - tolerance_abs * 0.75)
    if lows_not_rising:
        return reject("lows_not_rising")

    structure_low = min(float(v) for v in lows[-4:] if v is not None)
    range_span = max(float(v) for v in highs[-4:] if v is not None) - structure_low
    if range_span <= 0:
        return reject("no_supportive_pressure_under_resistance")
    if (resistance - structure_low) / max(resistance, 1e-9) > 0.06:
        return reject("pullback_too_loose")

    last_two_lows = [float(v) for v in lows[-2:] if v is not None]
    if len(last_two_lows) == 2 and last_two_lows[1] + tolerance_abs < last_two_lows[0]:
        return reject("no_supportive_pressure_under_resistance")

    trigger_level = resistance
    invalidation_level = min(last_two_lows) if len(last_two_lows) == 2 else structure_low
    if trigger_level <= 0:
        return reject("missing_trigger_level")
    if invalidation_level <= 0:
        return reject("missing_invalidation_level")
    if invalidation_level >= trigger_level:
        return reject("entry_stop_structure_invalid")

    near_resistance = closes[-1] >= resistance - tolerance_abs
    quality_tags = ["flat_resistance", "supportive_pressure", "liquidity_pass"]
    confidence = 0.62
    confidence += min(0.12, (len(touches) - _MIN_TOUCHES) * 0.05)
    if near_resistance:
        quality_tags.append("pressing_resistance")
        confidence += 0.06

    ema9 = _safe_float(inputs.indicators.ema9)
    ema20 = _safe_float(inputs.indicators.ema20)
    vwap = _safe_float(inputs.indicators.vwap)
    if vwap is not None and closes[-1] is not None and float(closes[-1]) >= vwap:
        quality_tags.append("above_vwap")
        confidence += 0.03
    if ema9 is not None and ema20 is not None and ema9 > ema20:
        quality_tags.append("ema9_above_ema20")
        confidence += 0.02

    confidence = min(0.95, round(confidence, 4))
    print(
        "[PATTERN] FLAT_TOP_BREAKOUT detected=True "
        f"symbol={inputs.symbol} resistance={trigger_level:.4f} touches={len(touches)}"
    )
    return PatternResult(
        setup_id="P_FLAT_TOP_BREAKOUT",
        pattern_name="Flat Top Breakout",
        pattern_family=PatternFamily.BREAKOUT,
        detected=True,
        direction=Direction.LONG,
        confidence=confidence,
        setup_quality_tags=quality_tags,
        setup_family_id="FLAT_TOP_BREAKOUT",
        rationale_text=(
            "Flat top structure ready with repeated resistance tests, supportive pressure beneath resistance, "
            f"and valid liquidity. resistance={trigger_level:.4f} touches={len(touches)} "
            f"invalidation={invalidation_level:.4f} rvol={rvol:.2f} spread_pct={spread_pct:.4f}."
        ),
        rejection_reason=None,
        data_quality_flags=list(inputs.data_quality_flags),
        trigger_type="BREAKOUT_HIGH",
        trigger_level=trigger_level,
        stop_level=invalidation_level,
        invalidation_level=invalidation_level,
    )
