"""Shared HALT_RESUME pattern detection."""

from __future__ import annotations

from datetime import datetime

from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult

HALT_GAP_THRESHOLD_SECONDS = 120.0
MIN_STABILIZATION_CANDLES = 4
MAX_SPREAD_PCT = 0.08
MAX_STRUCTURE_WIDTH_PCT = 0.05
MAX_CHAOTIC_ALTERNATION_RATIO = 0.8


def _safe_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _seconds_between(left: datetime | None, right: datetime | None) -> float | None:
    if left is None or right is None:
        return None
    return (right - left).total_seconds()


def detect_halt_resume(inputs: PatternInputs) -> PatternResult:
    def reject(reason: str, rationale: str | None = None) -> PatternResult:
        print(f"[PATTERN_TRACE][RESULT] symbol={inputs.symbol} pattern=Halt Resume detected=False reason={reason}")
        return PatternResult(
            setup_id="P_HALT_RESUME",
            pattern_name="Halt Resume Continuation",
            pattern_family=PatternFamily.BREAKOUT,
            detected=False,
            direction=Direction.LONG,
            confidence=0.0,
            setup_quality_tags=[],
            setup_family_id="HALT_RESUME",
            rationale_text=rationale or f"Rejected: {reason}",
            rejection_reason=reason,
            data_quality_flags=list(inputs.data_quality_flags),
            trigger_type="XL_HALT_RESUME_BREAK",
        )

    candles = list(inputs.candles or [])
    if len(candles) < 3:
        return reject("insufficient_candles")

    halt_meta = inputs.halt_metadata or {}
    resume_index: int | None = None

    if halt_meta:
        resume_time = halt_meta.get("resume_time")
        if isinstance(resume_time, datetime):
            for idx, candle in enumerate(candles):
                ts = getattr(candle, "timestamp", None)
                if ts is not None and ts >= resume_time:
                    resume_index = idx
                    break

    if resume_index is None:
        gap_index: int | None = None
        for i in range(1, len(candles)):
            prev = candles[i - 1]
            curr = candles[i]
            gap_seconds = _seconds_between(getattr(prev, "timestamp", None), getattr(curr, "timestamp", None))
            zero_vol_gap = _safe_float(getattr(prev, "volume", None)) == 0.0 and _safe_float(getattr(curr, "volume", None)) == 0.0
            if (gap_seconds is not None and gap_seconds > HALT_GAP_THRESHOLD_SECONDS) or zero_vol_gap:
                gap_index = i
                break
        if gap_index is None:
            return reject("no_halt_detected")
        resume_index = gap_index

    if resume_index <= 0 or resume_index >= len(candles):
        return reject("invalid_resume_structure")

    post_resume = candles[resume_index + 1 :]
    if len(post_resume) < MIN_STABILIZATION_CANDLES:
        return reject("insufficient_stabilization")

    spread = _safe_float(getattr(inputs.liquidity_context, "spread", None))
    if spread is None:
        return reject("missing_liquidity")
    last_close = _safe_float(getattr(candles[-1], "close", None))
    if last_close is None or last_close <= 0:
        return reject("missing_price_fields")
    spread_pct = spread if spread < 1 else spread / last_close
    if spread_pct > MAX_SPREAD_PCT:
        return reject("wide_spread")

    resume_candle = candles[resume_index]
    resume_range = max((_safe_float(resume_candle.high) or 0.0) - (_safe_float(resume_candle.low) or 0.0), 1e-9)
    stabilization_slice = post_resume[:MIN_STABILIZATION_CANDLES]
    recent_ranges = [max((_safe_float(c.high) or 0.0) - (_safe_float(c.low) or 0.0), 0.0) for c in stabilization_slice]
    if not recent_ranges or max(recent_ranges) >= resume_range * 0.7:
        return reject("no_range_stabilization")

    consolidation_high = max(_safe_float(c.high) or float("-inf") for c in stabilization_slice)
    consolidation_low = min(_safe_float(c.low) or float("inf") for c in stabilization_slice)
    if consolidation_high in {float("-inf"), float("inf")} or consolidation_low in {float("-inf"), float("inf")}:
        return reject("missing_price_fields")
    structure_width_pct = (consolidation_high - consolidation_low) / max(last_close, 1e-9)
    if structure_width_pct > MAX_STRUCTURE_WIDTH_PCT:
        return reject("no_structure")

    rvol = _safe_float(getattr(inputs.liquidity_context, "rvol", None))
    if rvol is not None and rvol < 0.8:
        return reject("low_participation")

    resume_open = _safe_float(getattr(resume_candle, "open", None))
    resume_close = _safe_float(getattr(resume_candle, "close", None))
    if resume_open is None or resume_close is None:
        return reject("missing_price_fields")
    if resume_close <= resume_open:
        return reject("no_long_bias")

    body_signs = []
    upper_wick_dominance = 0
    for candle in stabilization_slice:
        op = _safe_float(getattr(candle, "open", None))
        cl = _safe_float(getattr(candle, "close", None))
        hi = _safe_float(getattr(candle, "high", None))
        lo = _safe_float(getattr(candle, "low", None))
        if None in {op, cl, hi, lo}:
            return reject("missing_price_fields")
        body = abs(cl - op)
        rng = max(hi - lo, 1e-9)
        sign = 1 if cl >= op else -1
        body_signs.append(sign)
        upper_wick = max(0.0, hi - max(op, cl))
        if upper_wick > body and upper_wick / rng > 0.4:
            upper_wick_dominance += 1
    alternations = sum(1 for i in range(1, len(body_signs)) if body_signs[i] != body_signs[i - 1])
    if alternations / max(len(body_signs) - 1, 1) > MAX_CHAOTIC_ALTERNATION_RATIO:
        return reject("chaotic_post_halt_tape")
    if upper_wick_dominance >= max(2, len(stabilization_slice) // 2):
        return reject("upper_wick_rejection")

    impulse_strength = (resume_close - resume_open) / max(resume_range, 1e-9)
    confidence = min(0.85, max(0.65, 0.68 + min(impulse_strength, 1.0) * 0.1 + (0.05 if (rvol or 0.0) >= 1.2 else 0.0)))
    return PatternResult(
        setup_id="P_HALT_RESUME",
        pattern_name="Halt Resume Continuation",
        setup_family_id="HALT_RESUME",
        pattern_family=PatternFamily.BREAKOUT,
        detected=True,
        direction=Direction.LONG,
        confidence=confidence,
        trigger_type="XL_HALT_RESUME_BREAK",
        trigger_level=consolidation_high,
        stop_level=consolidation_low,
        invalidation_level=consolidation_low,
        setup_quality_tags=["halt_resume", "post_halt_stabilization", "range_compression"],
        setup_metadata={
            "resume_index": resume_index,
            "stabilization_candles": MIN_STABILIZATION_CANDLES,
            "range_width": consolidation_high - consolidation_low,
            "resume_impulse_strength": impulse_strength,
            "spread_pct": spread_pct,
        },
        rationale_text=(
            "Post-halt continuation detected after strict stabilization/structure checks. "
            f"resume_index={resume_index} trigger={consolidation_high:.4f} stop={consolidation_low:.4f}"
        ),
    )
