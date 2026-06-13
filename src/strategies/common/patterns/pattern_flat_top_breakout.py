"""Shared FLAT_TOP_BREAKOUT pattern detection."""

from __future__ import annotations

from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult


def _safe_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def detect_flat_top_breakout(inputs: PatternInputs) -> PatternResult:
    def reject(reason: str) -> PatternResult:
        return PatternResult(
            setup_id="P_FLAT_TOP_BREAKOUT",
            pattern_name="Flat Top Breakout",
            pattern_family=PatternFamily.BREAKOUT,
            detected=False,
            direction=Direction.LONG,
            confidence=0.0,
            setup_quality_tags=[],
            setup_family_id="FLAT_TOP_BREAKOUT",
            rationale_text=f"Rejected: {reason}",
            rejection_reason=reason,
            data_quality_flags=list(inputs.data_quality_flags),
            trigger_type="BREAKOUT_HIGH",
        )

    candles = list(inputs.candles or [])
    if len(candles) < 5:
        return reject("insufficient_candles")

    spread = _safe_float(inputs.liquidity_context.spread)
    if spread is None or spread > 0.05:
        return reject("liquidity_spread_too_wide")
    rvol = _safe_float(inputs.liquidity_context.rvol)
    if rvol is None or rvol < 1.1:
        return reject("liquidity_rvol_too_low")

    context = candles[-5:]
    pre_breakout = context[:-1]
    breakout = context[-1]
    pre_highs = [_safe_float(c.high) for c in pre_breakout]
    pre_lows = [_safe_float(c.low) for c in pre_breakout]
    breakout_close = _safe_float(breakout.close)
    breakout_high = _safe_float(breakout.high)
    if (
        any(value is None for value in pre_highs)
        or any(value is None for value in pre_lows)
        or breakout_close is None
        or breakout_high is None
    ):
        return reject("missing_price_fields")

    resistance = max(float(v) for v in pre_highs if v is not None)
    tolerance = max(0.02, resistance * 0.003)
    min_high = min(float(v) for v in pre_highs if v is not None)
    if resistance - min_high > tolerance * 1.8:
        return reject("resistance_not_flat")
    touches = sum(1 for high in pre_highs if high is not None and abs(high - resistance) <= tolerance)
    if touches < 3:
        return reject("insufficient_touches")

    avg_low = sum(float(v) for v in pre_lows if v is not None) / len(pre_lows)
    if avg_low <= (resistance - tolerance * 6.0):
        return reject("weak_structure_under_resistance")

    if breakout_close < (resistance + tolerance * 0.25) or breakout_high < resistance:
        return reject("breakout_not_confirmed")
    avg_pre_breakout_volume = sum(float(getattr(c, "volume", 0.0) or 0.0) for c in pre_breakout) / max(len(pre_breakout), 1)
    breakout_volume = float(getattr(breakout, "volume", 0.0) or 0.0)
    if avg_pre_breakout_volume > 0 and breakout_volume <= avg_pre_breakout_volume:
        return reject("breakout_volume_below_average")

    invalidation = min(float(v) for v in pre_lows if v is not None)
    if invalidation >= resistance:
        return reject("invalid_invalidation_structure")

    return PatternResult(
        setup_id="P_FLAT_TOP_BREAKOUT",
        pattern_name="Flat Top Breakout",
        pattern_family=PatternFamily.BREAKOUT,
        detected=True,
        direction=Direction.LONG,
        confidence=0.68,
        setup_quality_tags=["flat_resistance", "multi_touch", "confirmed_breakout"],
        setup_family_id="FLAT_TOP_BREAKOUT",
        rationale_text=(
            f"Flat-top resistance held for {touches} touches and price closed above "
            f"trigger={resistance:.4f}."
        ),
        rejection_reason=None,
        data_quality_flags=list(inputs.data_quality_flags),
        trigger_type="BREAKOUT_HIGH",
        trigger_level=resistance,
        invalidation_level=invalidation,
        stop_level=invalidation,
    )
