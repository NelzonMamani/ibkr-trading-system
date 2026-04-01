"""Shared VWAP_PULLBACK pattern detection."""

from __future__ import annotations

from statistics import mean

from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult

_MIN_HISTORY = 6
_MIN_RVOL = 1.2
_MAX_SPREAD = 0.08
_VWAP_TOLERANCE_PCT = 0.0025
_MIN_IMPULSE_RANGE_PCT = 0.008


def _safe_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _read(item: object, field: str) -> object:
    if isinstance(item, dict):
        return item.get(field)
    return getattr(item, field, None)


def detect_vwap_pullback(inputs: PatternInputs) -> PatternResult:
    """Detect canonical VWAP pullback: impulse -> VWAP test -> reclaim -> breakout-ready continuation."""

    def reject(reason: str) -> PatternResult:
        print(f"[PATTERN][VWAP_PULLBACK] detected=False symbol={inputs.symbol} reason={reason}")
        return PatternResult(
            setup_id="P_VWAP_PULLBACK",
            pattern_name="VWAP Pullback",
            pattern_family=PatternFamily.PULLBACK,
            detected=False,
            direction=Direction.LONG,
            confidence=0.0,
            setup_quality_tags=[],
            setup_family_id="VWAP_PULLBACK",
            rationale_text=f"Rejected: {reason}",
            rejection_reason=reason,
            data_quality_flags=list(inputs.data_quality_flags),
            trigger_type="XL_VWAP_PULLBACK_BREAKOUT",
            signal_class="ENTRY",
            trigger_mode="RECLAIM_BREAKOUT",
        )

    candles = list(inputs.candles or [])
    if not candles:
        return reject("insufficient_history")
    if len(candles) < _MIN_HISTORY:
        return reject("insufficient_history")

    vwap = _safe_float(inputs.indicators.vwap)
    if vwap is None:
        return reject("missing_vwap")

    rvol = _safe_float(inputs.liquidity_context.rvol)
    spread = _safe_float(inputs.liquidity_context.spread)
    if rvol is None or rvol < _MIN_RVOL:
        return reject("invalid_inputs")
    if spread is None or spread > _MAX_SPREAD:
        return reject("invalid_inputs")

    highs = [_safe_float(_read(c, "high")) for c in candles]
    lows = [_safe_float(_read(c, "low")) for c in candles]
    closes = [_safe_float(_read(c, "close")) for c in candles]
    opens = [_safe_float(_read(c, "open")) for c in candles]
    volumes = [_safe_float(_read(c, "volume")) for c in candles]
    if any(v is None for v in [*highs, *lows, *closes, *opens, *volumes]):
        return reject("insufficient_history")

    first_close = float(closes[0])
    recent_high = max(float(v) for v in highs[:-2] or highs)
    recent_low = min(float(v) for v in lows[:-2] or lows)
    last_close = float(closes[-1])
    prev_close = float(closes[-2])

    trend_ok = (recent_high > first_close and sum(1 for i in range(1, len(highs)) if highs[i] > highs[i - 1]) >= 2)
    prior_above_vwap = any(float(c) > vwap for c in closes[:-2])
    if not trend_ok or not prior_above_vwap:
        return reject("no_trend_context")

    impulse_range = recent_high - recent_low
    impulse_range_pct = impulse_range / max(first_close, 1e-9)
    impulse_volume = mean(float(v) for v in volumes[-6:-2])
    pullback_volume = float(volumes[-2])
    if impulse_range_pct < _MIN_IMPULSE_RANGE_PCT or impulse_volume <= 0:
        return reject("weak_impulse")

    pullback_test_close = float(closes[-2])
    pullback_test_low = min(float(v) for v in lows[-2:])
    vwap_test = (
        abs(pullback_test_close - vwap) / max(vwap, 1e-9) <= _VWAP_TOLERANCE_PCT
        or pullback_test_low <= vwap * (1 + _VWAP_TOLERANCE_PCT)
    )
    if not vwap_test:
        return reject("no_vwap_test")

    pullback_low = min(float(v) for v in lows[-2:])
    pullback_depth = (recent_high - pullback_low) / max(impulse_range, 1e-9)
    if pullback_depth > 0.65:
        return reject("pullback_too_deep")
    if pullback_volume >= impulse_volume:
        return reject("selling_pressure_too_high")

    reclaim = prev_close <= vwap and last_close > vwap
    if not reclaim:
        return reject("no_vwap_reclaim")

    ema9 = _safe_float(inputs.indicators.ema9)
    ema20 = _safe_float(inputs.indicators.ema20)
    macd = _safe_float((inputs.news_context or {}).get("macd"))
    trend_valid = last_close > vwap
    if ema9 is not None and ema20 is not None and ema9 < ema20:
        trend_valid = False
    if macd is not None and macd <= 0:
        trend_valid = False
    if not trend_valid:
        return reject("trend_not_validated")

    trigger_level = max(float(v) for v in highs[-3:-1])
    stop_level = pullback_low
    invalidation_level = min(vwap * (1 - 0.001), pullback_low)
    vwap_distance = (last_close - vwap) / max(vwap, 1e-9)
    volume_ratio = pullback_volume / max(impulse_volume, 1e-9)
    reclaim_strength = (last_close - vwap) / max(impulse_range, 1e-9)
    confidence = min(0.9, 0.58 + min(rvol, 2.5) * 0.08 + (1 - min(pullback_depth, 1.0)) * 0.1)

    print(
        "[PATTERN][VWAP_PULLBACK] "
        f"detected=True symbol={inputs.symbol} reason=detected trigger={trigger_level:.4f} stop={stop_level:.4f}"
    )

    return PatternResult(
        setup_id="P_VWAP_PULLBACK",
        pattern_name="VWAP Pullback",
        pattern_family=PatternFamily.PULLBACK,
        detected=True,
        direction=Direction.LONG,
        confidence=confidence,
        setup_quality_tags=["vwap_test", "vwap_reclaim", "continuation"],
        setup_family_id="VWAP_PULLBACK",
        rationale_text="VWAP pullback reclaimed with continuation-ready micro-structure and breakout trigger.",
        rejection_reason=None,
        data_quality_flags=list(inputs.data_quality_flags),
        trigger_type="XL_VWAP_PULLBACK_BREAKOUT",
        trigger_level=trigger_level,
        stop_level=stop_level,
        invalidation_level=invalidation_level,
        signal_class="ENTRY",
        trigger_mode="RECLAIM_BREAKOUT",
        setup_metadata={
            "vwap_distance": vwap_distance,
            "pullback_depth": pullback_depth,
            "volume_ratio": volume_ratio,
            "reclaim_strength": reclaim_strength,
            "rvol": rvol,
        },
    )
