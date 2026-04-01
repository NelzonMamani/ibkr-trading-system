"""Shared EMA_PULLBACK pattern detection."""

from __future__ import annotations

from statistics import mean

from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult

_MIN_HISTORY = 6
_MIN_RVOL = 1.2
_MAX_SPREAD = 0.08
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


def detect_ema_pullback(inputs: PatternInputs) -> PatternResult:
    """Detect canonical EMA9/EMA20 pullback reclaim continuation."""

    def reject(reason: str) -> PatternResult:
        print(f"[PATTERN][EMA_PULLBACK] detected=False symbol={inputs.symbol} reason={reason}")
        return PatternResult(
            setup_id="P_EMA_PULLBACK",
            pattern_name="EMA Pullback",
            pattern_family=PatternFamily.PULLBACK,
            detected=False,
            direction=Direction.LONG,
            confidence=0.0,
            setup_quality_tags=[],
            setup_family_id="EMA_PULLBACK",
            rationale_text=f"Rejected: {reason}",
            rejection_reason=reason,
            data_quality_flags=list(inputs.data_quality_flags),
            trigger_type="XL_EMA_PULLBACK_BREAKOUT",
            signal_class="ENTRY",
            trigger_mode="RECLAIM_BREAKOUT",
        )

    candles = list(inputs.candles or [])
    if len(candles) < _MIN_HISTORY:
        return reject("insufficient_history")

    ema9 = _safe_float(inputs.indicators.ema9)
    ema20 = _safe_float(inputs.indicators.ema20)
    if ema9 is None or ema20 is None:
        return reject("missing_ema")

    rvol = _safe_float(inputs.liquidity_context.rvol)
    spread = _safe_float(inputs.liquidity_context.spread)
    if rvol is None or rvol < _MIN_RVOL or spread is None or spread > _MAX_SPREAD:
        return reject("invalid_inputs")

    highs = [_safe_float(_read(c, "high")) for c in candles]
    lows = [_safe_float(_read(c, "low")) for c in candles]
    closes = [_safe_float(_read(c, "close")) for c in candles]
    opens = [_safe_float(_read(c, "open")) for c in candles]
    volumes = [_safe_float(_read(c, "volume")) for c in candles]
    if any(v is None for v in [*highs, *lows, *closes, *opens, *volumes]):
        return reject("invalid_inputs")

    last_close = float(closes[-1])
    prev_close = float(closes[-2])
    if not (ema9 > ema20 and last_close > ema9):
        return reject("no_trend_alignment")

    impulse_high = max(float(v) for v in highs[:-2] or highs)
    impulse_low = min(float(v) for v in lows[:-2] or lows)
    impulse_range = impulse_high - impulse_low
    impulse_range_pct = impulse_range / max(float(closes[0]), 1e-9)
    ema_sep_now = max(ema9 - ema20, 0.0)
    ema_sep_prev = max((_safe_float(closes[-3]) or last_close) - ema20, 0.0)
    if impulse_range_pct < _MIN_IMPULSE_RANGE_PCT or ema_sep_now < ema_sep_prev * 0.2:
        return reject("weak_impulse")

    ema_zone_low = min(ema9, ema20)
    ema_zone_high = max(ema9, ema20)
    last_low = float(lows[-1])
    prev_low = float(lows[-2])
    pullback_low = min(last_low, prev_low)
    if pullback_low > ema_zone_high:
        return reject("no_ema_test")

    pullback_depth = (impulse_high - pullback_low) / max(impulse_range, 1e-9)
    if pullback_depth > 0.68:
        return reject("pullback_too_deep")

    impulse_volume = mean(float(v) for v in volumes[-6:-2])
    pullback_volume = float(volumes[-2])
    if pullback_volume >= impulse_volume:
        return reject("selling_pressure_too_high")

    if not (prev_close <= ema_zone_high and last_close > ema9):
        return reject("no_ema_reclaim")

    vwap = _safe_float(inputs.indicators.vwap)
    macd = _safe_float((inputs.news_context or {}).get("macd"))
    trend_valid = last_close > ema9 and ema9 > ema20
    if vwap is not None and last_close <= vwap:
        trend_valid = False
    if macd is not None and macd <= 0:
        trend_valid = False
    if not trend_valid:
        return reject("trend_not_validated")

    trigger_level = max(float(v) for v in highs[-3:-1])
    stop_level = pullback_low
    invalidation_level = min(stop_level, ema20 * (1 - 0.001))
    ema_distance = (last_close - ema9) / max(ema9, 1e-9)
    volume_ratio = pullback_volume / max(impulse_volume, 1e-9)
    confidence = min(0.92, 0.58 + min(rvol, 2.5) * 0.08 + (1 - min(pullback_depth, 1.0)) * 0.1)

    print(
        "[PATTERN][EMA_PULLBACK] "
        f"detected=True symbol={inputs.symbol} reason=detected trigger={trigger_level:.4f} stop={stop_level:.4f}"
    )

    return PatternResult(
        setup_id="P_EMA_PULLBACK",
        pattern_name="EMA Pullback",
        pattern_family=PatternFamily.PULLBACK,
        detected=True,
        direction=Direction.LONG,
        confidence=confidence,
        setup_quality_tags=["ema_zone_test", "ema_reclaim", "continuation"],
        setup_family_id="EMA_PULLBACK",
        rationale_text="EMA9/EMA20 pullback reclaimed with continuation-ready breakout trigger.",
        rejection_reason=None,
        data_quality_flags=list(inputs.data_quality_flags),
        trigger_type="XL_EMA_PULLBACK_BREAKOUT",
        trigger_level=trigger_level,
        stop_level=stop_level,
        invalidation_level=invalidation_level,
        signal_class="ENTRY",
        trigger_mode="RECLAIM_BREAKOUT",
        setup_metadata={
            "ema_zone_range": [ema_zone_low, ema_zone_high],
            "pullback_depth": pullback_depth,
            "ema_distance": ema_distance,
            "volume_ratio": volume_ratio,
            "rvol": rvol,
        },
    )
