"""Shared OPENING_DRIVE pattern detection."""

from __future__ import annotations

from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.strategy_contracts import SessionContext


def _safe_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def detect_opening_drive(inputs: PatternInputs) -> PatternResult:
    """Detect aggressive early-session opening drive continuation context."""

    def reject(reason: str, rationale: str | None = None) -> PatternResult:
        print(f"[PATTERN_TRACE][RESULT] symbol={inputs.symbol} pattern=Opening Drive detected=False reason={reason}")
        return PatternResult(
            setup_id="P_OPENING_DRIVE",
            pattern_name="Opening Drive",
            pattern_family=PatternFamily.BREAKOUT,
            detected=False,
            direction=Direction.LONG,
            confidence=0.0,
            setup_quality_tags=[],
            setup_family_id="OPENING_DRIVE",
            rationale_text=rationale or f"Rejected: {reason}",
            rejection_reason=reason,
            data_quality_flags=list(inputs.data_quality_flags),
            trigger_type="XL_OPENING_DRIVE_BREAK",
        )

    print(f"[PATTERN_TRACE][CALL] symbol={inputs.symbol} pattern=Opening Drive")
    session = inputs.session_context
    phase = getattr(inputs, "session_phase", None)

    if session != SessionContext.REGULAR:
        return reject("invalid_session", "Opening Drive is valid only during RTH_OPEN/regular open session.")
    if phase is not None and str(phase).upper() != "RTH_OPEN":
        return reject("invalid_phase", "Opening Drive requires the RTH_OPEN phase when phase context is available.")

    candles = list(inputs.candles or [])
    if len(candles) < 5:
        return reject("insufficient_candles")

    if not getattr(inputs, "levels", None):
        return reject("missing_levels")

    spread = _safe_float(getattr(inputs.liquidity_context, "spread", None))
    if spread is None:
        return reject("low_liquidity", "Missing spread context; tradability cannot be validated.")
    if spread > 0.08:
        return reject("wide_spread")

    rvol = _safe_float(getattr(inputs.liquidity_context, "rvol", None))
    total_volume = sum(max(0.0, _safe_float(getattr(c, "volume", 0.0)) or 0.0) for c in candles[-5:])
    if (rvol is None or rvol < 1.8) and total_volume < 4000:
        return reject("insufficient_volume_confirmation")

    open_price = _safe_float(getattr(candles[0], "open", None))
    first_high = max(_safe_float(getattr(c, "high", None)) or float("-inf") for c in candles[:3])
    if open_price is None or first_high == float("-inf"):
        return reject("missing_price_fields")

    last = candles[-1]
    last_close = _safe_float(getattr(last, "close", None))
    last_high = _safe_float(getattr(last, "high", None))
    last_low = _safe_float(getattr(last, "low", None))
    if None in {last_close, last_high, last_low}:
        return reject("missing_price_fields")

    impulse_gain = last_close - open_price
    impulse_range = max(1e-9, first_high - open_price)
    if impulse_gain <= 0 or impulse_gain < (impulse_range * 0.6):
        return reject("weak_open_impulse")

    session_peak = max(_safe_float(getattr(c, "high", None)) or float("-inf") for c in candles[-5:])
    if session_peak == float("-inf"):
        return reject("missing_price_fields")
    retrace_from_peak = (session_peak - last_low) / max(1e-9, session_peak - open_price)
    if retrace_from_peak > 0.45:
        return reject("excessive_pullback")

    body = abs(last_close - (_safe_float(getattr(last, "open", None)) or last_close))
    upper_wick = max(0.0, last_high - max(last_close, _safe_float(getattr(last, "open", None)) or last_close))
    if body > 0 and upper_wick > body * 1.2:
        return reject("opening_drive_exhaustion")

    trigger_level = last_high
    stop_level = last_low
    print(f"[PATTERN_TRACE][RESULT] symbol={inputs.symbol} pattern=Opening Drive detected=True")
    return PatternResult(
        setup_id="P_OPENING_DRIVE",
        pattern_name="Opening Drive",
        pattern_family=PatternFamily.BREAKOUT,
        detected=True,
        direction=Direction.LONG,
        confidence=0.74,
        setup_quality_tags=["early_session_impulse", "volume_confirmed", "limited_pullback"],
        setup_family_id="OPENING_DRIVE",
        rationale_text=(
            "Opening drive continuation structure detected with strong early directional impulse and participation. "
            f"trigger={trigger_level:.4f} stop={stop_level:.4f} rvol={rvol if rvol is not None else 0.0:.2f}"
        ),
        rejection_reason=None,
        data_quality_flags=list(inputs.data_quality_flags),
        trigger_type="XL_OPENING_DRIVE_BREAK",
        trigger_level=trigger_level,
        stop_level=stop_level,
        invalidation_level=stop_level,
    )
