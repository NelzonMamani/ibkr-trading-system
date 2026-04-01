"""Shared PARABOLIC_EXHAUSTION pattern detection."""

from __future__ import annotations

from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult


def _safe_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def detect_parabolic_exhaustion(inputs: PatternInputs) -> PatternResult:
    def reject(reason: str) -> PatternResult:
        return PatternResult(
            setup_id="P_PARABOLIC_EXHAUSTION",
            pattern_name="Parabolic Exhaustion",
            pattern_family=PatternFamily.EXHAUSTION,
            detected=False,
            direction=Direction.LONG,
            confidence=0.0,
            setup_quality_tags=[],
            setup_family_id="PARABOLIC_EXHAUSTION",
            rejection_reason=reason,
            rationale_text=f"Rejected: {reason}",
            trigger_type="XL_PARABOLIC_EXHAUSTION",
            data_quality_flags=list(inputs.data_quality_flags),
            non_entry_signal=True,
        )

    candles = list(inputs.candles or [])
    if len(candles) < 5:
        return reject("insufficient_candles")

    recent = candles[-5:]
    closes = [_safe_float(getattr(c, "close", None)) for c in recent]
    highs = [_safe_float(getattr(c, "high", None)) for c in recent]
    lows = [_safe_float(getattr(c, "low", None)) for c in recent]
    volumes = [_safe_float(getattr(c, "volume", None)) for c in recent]
    if any(v is None for v in [*closes, *highs, *lows, *volumes]):
        return reject("missing_price_fields")

    prev_prev_move = closes[-3] - closes[-4]
    prev_move = closes[-2] - closes[-3]
    last_move = closes[-1] - closes[-2]
    acceleration_increasing = last_move > prev_move > prev_prev_move

    vwap = _safe_float(getattr(inputs.indicators, "vwap", None))
    if vwap is None or vwap <= 0:
        return reject("missing_vwap")
    extension_pct = (closes[-1] - vwap) / vwap
    extreme_extension = extension_pct >= 0.05

    ranges = [max(0.0, h - l) for h, l in zip(highs, lows)]
    last_range = ranges[-1]
    avg_range = sum(ranges[:-1]) / max(1, len(ranges) - 1)
    range_expansion = last_range > avg_range * 1.5 if avg_range > 0 else False

    last_volume = volumes[-1]
    avg_volume = sum(volumes[:-1]) / max(1, len(volumes) - 1)
    volume_spike = last_volume >= avg_volume * 2 if avg_volume > 0 else False

    last_high, last_low, last_close = highs[-1], lows[-1], closes[-1]
    wick_base = max(last_high - last_low, 1e-9)
    upper_wick_ratio = (last_high - last_close) / wick_base
    wick_rejection = upper_wick_ratio >= 0.4

    if not acceleration_increasing:
        return reject("acceleration_not_increasing")
    if not extreme_extension:
        return reject("no_extreme_extension")
    if not (volume_spike or wick_rejection):
        return reject("no_volume_or_rejection_confirmation")

    confidence = 0.65 + (0.1 if volume_spike else 0.0) + (0.08 if wick_rejection else 0.0) + (0.04 if range_expansion else 0.0)

    return PatternResult(
        setup_id="P_PARABOLIC_EXHAUSTION",
        pattern_name="Parabolic Exhaustion",
        pattern_family=PatternFamily.EXHAUSTION,
        detected=True,
        direction=Direction.LONG,
        confidence=min(0.9, confidence),
        setup_quality_tags=["parabolic", "exhaustion", "climax", "extension_extreme"],
        setup_family_id="PARABOLIC_EXHAUSTION",
        trigger_type="XL_PARABOLIC_EXHAUSTION",
        trigger_level=last_high,
        stop_level=None,
        invalidation_level=None,
        setup_metadata={
            "extension_pct": extension_pct,
            "velocity": last_move,
            "acceleration": last_move - prev_move,
            "volume_spike": volume_spike,
            "wick_ratio": upper_wick_ratio,
            "range_expansion": range_expansion,
        },
        rationale_text="Parabolic exhaustion detected: extreme extension with terminal momentum signatures.",
        non_entry_signal=True,
        risk_flags=["EXIT_SIGNAL", "RISK_OFF"],
    )
