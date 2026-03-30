"""Shared FIRST_PULLBACK pattern detection."""

from __future__ import annotations

from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult


def _safe_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def detect_first_pullback(inputs: PatternInputs) -> PatternResult:
    """Detect structural readiness for a first pullback continuation setup."""

    def reject(reason: str) -> PatternResult:
        print(f"[PATTERN] FIRST_PULLBACK detected=False symbol={inputs.symbol}")
        return PatternResult(
            setup_id="P_FIRST_PULLBACK",
            pattern_name="First Pullback",
            pattern_family=PatternFamily.PULLBACK,
            detected=False,
            direction=Direction.LONG,
            confidence=0.0,
            setup_quality_tags=[],
            setup_family_id="FIRST_PULLBACK",
            rationale_text=f"Rejected: {reason}",
            rejection_reason=reason,
            data_quality_flags=list(inputs.data_quality_flags),
            trigger_type="PULLBACK_HIGH_BREAK",
        )

    candles = list(inputs.candles or [])
    if len(candles) < 5:
        return reject("insufficient_candles")

    ema9 = _safe_float(inputs.indicators.ema9)
    ema20 = _safe_float(inputs.indicators.ema20)
    if ema9 is None or ema20 is None:
        return reject("missing_required_indicators")

    impulse_a, impulse_b = candles[-5], candles[-4]
    pullback_segment = candles[-3:-1]

    impulse_ok = float(impulse_b.close) > float(impulse_a.close) and float(impulse_b.high) > float(impulse_a.high)
    if not impulse_ok:
        return reject("missing_initial_impulse")

    if len(pullback_segment) != 2:
        return reject("pullback_segment_invalid")

    pullback_high = max(float(c.high) for c in pullback_segment)
    pullback_low = min(float(c.low) for c in pullback_segment)
    pullback_controlled = (
        all(float(c.low) >= ema20 for c in pullback_segment)
        and all(float(c.close) >= ema20 for c in pullback_segment)
        and float(pullback_segment[-1].close) <= float(pullback_segment[0].close)
    )
    if not pullback_controlled:
        return reject("pullback_not_controlled")

    if pullback_high <= ema9:
        return reject("trigger_level_not_above_ema9")

    print(f"[PATTERN] FIRST_PULLBACK detected=True symbol={inputs.symbol}")
    return PatternResult(
        setup_id="P_FIRST_PULLBACK",
        pattern_name="First Pullback",
        pattern_family=PatternFamily.PULLBACK,
        detected=True,
        direction=Direction.LONG,
        confidence=0.68,
        setup_quality_tags=["initial_impulse", "controlled_pullback", "ema20_held"],
        setup_family_id="FIRST_PULLBACK",
        rationale_text=(
            "Structural first pullback detected after impulse with controlled pullback above ema20. "
            f"trigger={pullback_high:.4f} stop={pullback_low:.4f}"
        ),
        rejection_reason=None,
        data_quality_flags=list(inputs.data_quality_flags),
        trigger_type="PULLBACK_HIGH_BREAK",
        trigger_level=pullback_high,
        stop_level=pullback_low,
        invalidation_level=pullback_low,
    )
