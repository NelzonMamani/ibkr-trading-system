"""Shared CUP_HANDLE pattern detection."""

from __future__ import annotations

from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.strategy_contracts import SessionContext


def _safe_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def detect_cup_handle(inputs: PatternInputs) -> PatternResult:
    """Detect conservative cup-and-handle continuation structure."""

    def reject(reason: str, rationale: str | None = None) -> PatternResult:
        print(f"[PATTERN_TRACE][RESULT] symbol={inputs.symbol} pattern=Cup & Handle detected=False rejection_reason={reason}")
        return PatternResult(
            setup_id="P_CUP_HANDLE",
            pattern_name="Cup & Handle",
            pattern_family=PatternFamily.BREAKOUT,
            detected=False,
            direction=Direction.LONG,
            confidence=0.0,
            setup_quality_tags=[],
            setup_family_id="CUP_HANDLE",
            rationale_text=rationale or f"Rejected: {reason}",
            rejection_reason=reason,
            data_quality_flags=list(inputs.data_quality_flags),
            trigger_type="XL_CUP_HANDLE_BREAK",
        )

    print(f"[PATTERN_TRACE][CALL] symbol={inputs.symbol} pattern=Cup & Handle")
    if inputs.session_context != SessionContext.REGULAR:
        return reject("invalid_session", "Cup & Handle is valid only during regular/RTH session.")

    candles = list(inputs.candles or [])
    if len(candles) < 14:
        return reject("missing_candles", "Need at least 14 candles for cup + handle structure.")

    if any(
        _safe_float(getattr(candle, field, None)) is None
        for candle in candles
        for field in ("open", "high", "low", "close")
    ):
        return reject("missing_price_fields")

    spread = _safe_float(inputs.liquidity_context.spread)
    if spread is None or spread > 0.08:
        return reject("wide_spread" if spread is not None else "low_liquidity")
    rvol = _safe_float(inputs.liquidity_context.rvol)
    if rvol is not None and rvol < 0.8:
        return reject("low_liquidity")

    window = candles[-14:]
    left, base, right, handle = window[:4], window[4:9], window[9:12], window[12:]

    left_high = max(float(c.high) for c in left)
    left_low = min(float(c.low) for c in left)
    cup_low = min(float(c.low) for c in base)
    right_high = max(float(c.high) for c in right)
    resistance = max(left_high, right_high)
    cup_range = max(resistance - cup_low, 1e-9)

    cup_depth = (resistance - cup_low) / max(resistance, 1e-9)
    if cup_depth < 0.03:
        return reject("insufficient_base")
    if cup_depth > 0.35:
        return reject("excessive_drawdown")

    # reject abrupt V recoveries; right side should rebuild with progression.
    if float(base[-1].close) >= resistance * 0.98:
        return reject("v_shape_rejection")
    if (float(base[-1].close) - cup_low) / cup_range > 0.78:
        return reject("v_shape_rejection")
    right_closes = [float(c.close) for c in right]
    if not (right_closes[0] <= right_closes[1] <= right_closes[2]):
        return reject("insufficient_structure")
    if right_high < left_high * 0.985:
        return reject("insufficient_structure")

    handle_high = max(float(c.high) for c in handle)
    handle_low = min(float(c.low) for c in handle)
    handle_depth = (resistance - handle_low) / max(resistance, 1e-9)
    handle_range = max(float(c.high) - float(c.low) for c in handle)
    if handle_high > resistance * 1.001:
        return reject("handle_not_formed")
    if handle_depth > min(0.12, cup_depth * 0.65):
        return reject("handle_too_deep")
    if handle_range > cup_range * 0.45:
        return reject("handle_too_volatile")

    handle_volumes = [max(float(c.volume), 0.0) for c in handle]
    base_volumes = [max(float(c.volume), 0.0) for c in base]
    breakout_bar = window[-1]
    breakout_volume = max(float(breakout_bar.volume), 0.0)
    avg_handle_volume = sum(handle_volumes) / max(len(handle_volumes), 1)
    avg_base_volume = sum(base_volumes) / max(len(base_volumes), 1)
    if avg_handle_volume > avg_base_volume * 1.35:
        return reject("insufficient_volume_pattern")
    if breakout_volume < avg_handle_volume * 0.9:
        return reject("insufficient_volume_pattern")

    trigger_level = resistance
    stop_level = handle_low
    print(
        f"[PATTERN_TRACE][INPUT] symbol={inputs.symbol} pattern=Cup & Handle resistance={trigger_level:.4f} handle_low={stop_level:.4f}"
    )
    print("[PATTERN_TRACE][RESULT] symbol=%s pattern=Cup & Handle detected=True rejection_reason=None" % inputs.symbol)
    return PatternResult(
        setup_id="P_CUP_HANDLE",
        pattern_name="Cup & Handle",
        pattern_family=PatternFamily.BREAKOUT,
        detected=True,
        direction=Direction.LONG,
        confidence=0.7,
        setup_quality_tags=["rounded_base", "controlled_handle", "breakout_ready"],
        setup_family_id="CUP_HANDLE",
        rationale_text=(
            "Rounded cup base recovered into resistance, followed by controlled handle compression; "
            f"breakout trigger armed at {trigger_level:.4f} with handle_low={stop_level:.4f}."
        ),
        rejection_reason=None,
        data_quality_flags=list(inputs.data_quality_flags),
        trigger_type="XL_CUP_HANDLE_BREAK",
        trigger_level=trigger_level,
        stop_level=stop_level,
        invalidation_level=stop_level,
        setup_metadata={
            "cup_high": resistance,
            "cup_low": cup_low,
            "cup_depth": cup_depth,
            "handle_high": handle_high,
            "handle_low": handle_low,
            "handle_depth": handle_depth,
            "structure_quality": "conservative_valid",
            "volume_profile": "handle_contraction_breakout_participation",
        },
    )
