"""Shared MICRO_PULLBACK pattern detection."""

from __future__ import annotations

from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult


def _safe_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def detect_micro_pullback(inputs: PatternInputs) -> PatternResult:
    """Detect structural readiness for micro pullback continuation after an impulse leg."""

    def reject(reason: str) -> PatternResult:
        print(f"[PATTERN] MICRO_PULLBACK detected=False symbol={inputs.symbol} reason={reason}")
        return PatternResult(
            setup_id="P_MICRO_PULLBACK",
            pattern_name="Micro Pullback",
            pattern_family=PatternFamily.PULLBACK,
            detected=False,
            direction=Direction.LONG,
            confidence=0.0,
            setup_quality_tags=[],
            setup_family_id="MICRO_PULLBACK",
            rationale_text=f"Rejected: {reason}",
            rejection_reason=reason,
            data_quality_flags=list(inputs.data_quality_flags),
            trigger_type="XL_MICRO_PULLBACK",
        )

    candles = list(inputs.candles or [])
    if len(candles) < 5:
        return reject("insufficient_candles")

    impulse_start = candles[-5]
    impulse_end = candles[-3]
    pullback_a = candles[-2]
    pullback_b = candles[-1]

    impulse_low = _safe_float(getattr(impulse_start, "low", None))
    impulse_high = _safe_float(getattr(impulse_end, "high", None))
    impulse_start_close = _safe_float(getattr(impulse_start, "close", None))
    impulse_end_close = _safe_float(getattr(impulse_end, "close", None))
    if None in {impulse_low, impulse_high, impulse_start_close, impulse_end_close}:
        return reject("missing_impulse_prices")

    impulse_range = float(impulse_high - impulse_low)
    if impulse_range <= 0:
        return reject("invalid_impulse_range")

    impulse_gain = float(impulse_end_close - impulse_start_close)
    if impulse_gain <= 0 or impulse_gain < (impulse_range * 0.35):
        return reject("missing_impulse_leg")

    pullback_high = max(
        _safe_float(getattr(pullback_a, "high", None)) or float("-inf"),
        _safe_float(getattr(pullback_b, "high", None)) or float("-inf"),
    )
    pullback_low = min(
        _safe_float(getattr(pullback_a, "low", None)) or float("inf"),
        _safe_float(getattr(pullback_b, "low", None)) or float("inf"),
    )
    if pullback_high in {float("-inf")} or pullback_low in {float("inf")}:
        return reject("missing_pullback_prices")

    shallow_pullback = (impulse_high - pullback_low) <= (impulse_range * 0.45)
    if not shallow_pullback:
        return reject("pullback_too_deep")

    pullback_brief = len(candles[-2:]) <= 2
    if not pullback_brief:
        return reject("pullback_not_brief")

    ema9 = _safe_float(inputs.indicators.ema9)
    continuation_support = ema9 if ema9 is not None else impulse_start_close
    if pullback_low <= float(continuation_support):
        return reject("pullback_lost_continuation_support")

    trigger_level = pullback_high
    stop_level = pullback_low
    if trigger_level <= stop_level:
        return reject("entry_stop_structure_invalid")

    print(
        "[PATTERN] MICRO_PULLBACK detected=True "
        f"symbol={inputs.symbol} trigger={trigger_level:.4f} stop={stop_level:.4f}"
    )
    return PatternResult(
        setup_id="P_MICRO_PULLBACK",
        pattern_name="Micro Pullback",
        pattern_family=PatternFamily.PULLBACK,
        detected=True,
        direction=Direction.LONG,
        confidence=0.66,
        setup_quality_tags=["impulse_leg", "shallow_pullback", "continuation_support_held"],
        setup_family_id="MICRO_PULLBACK",
        rationale_text=(
            "Micro pullback continuation structure detected with intact support and "
            f"defined trigger={trigger_level:.4f} invalidation={stop_level:.4f}."
        ),
        rejection_reason=None,
        data_quality_flags=list(inputs.data_quality_flags),
        trigger_type="XL_MICRO_PULLBACK",
        trigger_level=trigger_level,
        stop_level=stop_level,
        invalidation_level=stop_level,
    )
