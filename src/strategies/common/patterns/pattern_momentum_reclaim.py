"""Shared MOMENTUM_RECLAIM pattern detection."""

from __future__ import annotations

from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.strategy_contracts import SessionContext


_VALID_SESSIONS = {SessionContext.REGULAR, SessionContext.PRE}


def _safe_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def detect_momentum_reclaim(inputs: PatternInputs) -> PatternResult:
    """Detect reclaim of VWAP/EMA after shakeout followed by continuation."""

    def reject(reason: str, rationale: str | None = None) -> PatternResult:
        print(
            "[PATTERN_TRACE][RESULT] "
            f"symbol={inputs.symbol} pattern=Momentum Reclaim detected=False reason={reason}"
        )
        return PatternResult(
            setup_id="P_MOMENTUM_RECLAIM",
            pattern_name="Momentum Reclaim",
            pattern_family=PatternFamily.PULLBACK,
            detected=False,
            direction=Direction.LONG,
            confidence=0.0,
            setup_quality_tags=[],
            setup_family_id="MOMENTUM_RECLAIM",
            rationale_text=rationale or f"Rejected: {reason}",
            rejection_reason=reason,
            data_quality_flags=list(inputs.data_quality_flags),
            trigger_type="XL_MOMENTUM_RECLAIM",
        )

    print(f"[PATTERN_TRACE][CALL] symbol={inputs.symbol} pattern=Momentum Reclaim")
    if inputs.session_context not in _VALID_SESSIONS:
        return reject("invalid_session")

    candles = list(inputs.candles or [])
    if len(candles) < 3:
        return reject("missing_candles")

    level_type = None
    level = _safe_float(inputs.indicators.vwap)
    if level is not None:
        level_type = "VWAP"
    if level is None:
        level = _safe_float(inputs.indicators.ema9)
        if level is not None:
            level_type = "EMA9"
    if level is None:
        level = _safe_float(inputs.indicators.ema20)
        if level is not None:
            level_type = "EMA20"
    if level is None or level_type is None:
        return reject("missing_indicator_reference")

    print(f"[PATTERN_TRACE][INPUT] symbol={inputs.symbol} pattern=Momentum Reclaim level={level:.4f} type={level_type}")

    spread = _safe_float(inputs.liquidity_context.spread)
    if spread is None:
        return reject("low_liquidity")
    if spread > 0.08:
        return reject("wide_spread")
    rvol = _safe_float(inputs.liquidity_context.rvol)
    if rvol is not None and rvol < 0.7:
        return reject("low_liquidity")

    for candle in candles[-6:]:
        if any(_safe_float(getattr(candle, field, None)) is None for field in ("open", "high", "low", "close")):
            return reject("missing_price_fields")

    recent = candles[-6:]
    below_level_seen = any(float(c.low) < level for c in recent)
    if not below_level_seen:
        return reject("no_pullback_detected")

    last = candles[-1]
    prev = candles[-2]
    last_close = float(last.close)
    prev_close = float(prev.close)
    if not (prev_close <= level and last_close > level):
        return reject("no_reclaim")

    last_open = float(last.open)
    last_high = float(last.high)
    body = abs(last_close - last_open)
    upper_wick = max(0.0, last_high - max(last_open, last_close))
    if body > 0 and upper_wick > body * 1.6:
        return reject("weak_reclaim")

    recent_low = min(float(c.low) for c in recent)
    pullback_depth = (level - recent_low) / max(level, 1e-9)
    if pullback_depth > 0.04:
        return reject("excessive_pullback")

    avg_volume = sum(max(float(c.volume), 0.0) for c in recent[:-1]) / max(1, len(recent) - 1)
    last_volume = max(float(last.volume), 0.0)
    if not ((rvol is not None and rvol >= 1.2) or (avg_volume > 0 and last_volume >= avg_volume)):
        return reject("insufficient_volume_confirmation")

    reclaim_strength = (last_close - level) / max(level, 1e-9)
    level_quality_tag = "vwap_reclaim" if level_type == "VWAP" else "ema_reclaim"
    print(
        "[PATTERN_TRACE][RESULT] "
        f"symbol={inputs.symbol} pattern=Momentum Reclaim detected=True reason=detected type={level_type}"
    )
    return PatternResult(
        setup_id="P_MOMENTUM_RECLAIM",
        pattern_name="Momentum Reclaim",
        pattern_family=PatternFamily.PULLBACK,
        detected=True,
        direction=Direction.LONG,
        confidence=0.67,
        setup_quality_tags=["reclaim", "shakeout", "continuation", level_quality_tag],
        setup_family_id="MOMENTUM_RECLAIM",
        rationale_text=(
            "Price shook below dynamic support and reclaimed it with continuation confirmation. "
            f"reference={level_type} level={level:.4f} pullback_depth={pullback_depth:.2%}"
        ),
        rejection_reason=None,
        data_quality_flags=list(inputs.data_quality_flags),
        trigger_type="XL_MOMENTUM_RECLAIM",
        trigger_level=level,
        stop_level=recent_low,
        invalidation_level=level,
        setup_metadata={
            "reference_level_type": level_type,
            "reference_level": level_type,
            "pullback_depth": pullback_depth,
            "reclaim_strength": reclaim_strength,
            "structure_quality": "continuation_valid",
        },
    )

