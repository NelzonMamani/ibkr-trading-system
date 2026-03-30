"""Shared Opening Range Breakout (ORB) pattern detection."""

from __future__ import annotations

from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.strategy_contracts import SessionContext


def _safe_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def detect_orb(inputs: PatternInputs) -> PatternResult:
    """Detect true long-side opening range breakout with full quality gates."""

    def reject(reason: str, *, quality_flags: list[str] | None = None) -> PatternResult:
        print(f"[PATTERN] ORB detected=False symbol={inputs.symbol}")
        print(f"[PATTERN][REJECT] reason={reason} symbol={inputs.symbol}")
        return PatternResult(
            setup_id="P_ORB",
            pattern_name="Opening Range Breakout",
            pattern_family=PatternFamily.BREAKOUT,
            detected=False,
            direction=Direction.LONG,
            confidence=0.0,
            setup_quality_tags=quality_flags or [],
            setup_family_id="OPENING_RANGE_BREAKOUT",
            entry_zone=None,
            stop_suggestion=None,
            rationale_text=f"Rejected: {reason}",
            rejection_reason=reason,
            risk_flags=[],
            data_quality_flags=list(inputs.data_quality_flags),
            trigger_type="XL_ORB_BREAK",
        )

    if len(inputs.candles) < 6:
        return reject("insufficient_1m_candles")

    session_label = str(inputs.session_context.value if hasattr(inputs.session_context, "value") else inputs.session_context).upper()
    session_phase = str((inputs.news_context or {}).get("session_phase") or "").upper()
    if session_label != SessionContext.REGULAR.value and session_phase not in {"RTH_OPEN", "MORNING"}:
        return reject("session_not_rth_open_or_morning")

    key_levels = inputs.levels.key_levels or {}
    provided_orh = _safe_float(inputs.levels.hod) or _safe_float(key_levels.get("OPENING_RANGE_HIGH"))
    provided_orl = _safe_float(inputs.levels.lod) or _safe_float(key_levels.get("OPENING_RANGE_LOW"))
    premarket_high = _safe_float(inputs.levels.premarket_high)
    premarket_low = _safe_float(inputs.levels.premarket_low)
    if premarket_high is None or premarket_low is None:
        return reject("missing_premarket_levels")

    vwap = _safe_float(inputs.indicators.vwap)
    ema9 = _safe_float(inputs.indicators.ema9)
    ema20 = _safe_float(inputs.indicators.ema20)
    if vwap is None or ema9 is None or ema20 is None:
        return reject("missing_required_indicators")

    macd = _safe_float((inputs.news_context or {}).get("macd"))
    if macd is None:
        macd = _safe_float((inputs.news_context or {}).get("macd_hist"))
    if macd is None:
        return reject("missing_macd")

    rvol = _safe_float(inputs.liquidity_context.rvol)
    spread_raw = _safe_float(inputs.liquidity_context.spread)
    if rvol is None or spread_raw is None:
        return reject("missing_liquidity_context")

    opening = inputs.candles[:5]
    last = inputs.candles[-1]
    orh = max(float(c.high) for c in opening)
    orl = min(float(c.low) for c in opening)

    if provided_orh is not None:
        orh = max(orh, provided_orh)
    if provided_orl is not None:
        orl = min(orl, provided_orl)

    if float(last.high) <= orh:
        return reject("no_break_above_orh")
    if float(last.close) <= orh:
        return reject("no_hold_above_orh")

    opening_avg_volume = sum(float(c.volume) for c in opening) / max(len(opening), 1)
    if float(last.volume) <= opening_avg_volume:
        return reject("breakout_volume_below_opening_average")

    if float(last.close) <= vwap:
        return reject("price_below_vwap")
    if macd <= 0:
        return reject("macd_not_positive")

    spread_pct = spread_raw if spread_raw < 1 else spread_raw / max(float(last.close), 1e-9)
    spread_threshold = 0.01
    if rvol < 1.5:
        return reject("rvol_below_threshold")
    if spread_pct > spread_threshold:
        return reject("spread_too_wide")

    pullback_low = _safe_float((inputs.news_context or {}).get("last_pullback_low"))
    stop_anchor = pullback_low if pullback_low is not None else orl
    if stop_anchor is None:
        return reject("missing_stop_anchor")

    risk_per_share = float(last.close) - float(stop_anchor)
    extension_too_large = risk_per_share <= 0 or (risk_per_share / max(float(last.close), 1e-9)) > 0.05
    if extension_too_large:
        return reject("extension_too_large")

    confidence = 0.70
    confidence += min(0.12, max(0.0, rvol - 1.5) * 0.04)
    confidence += 0.06 if float(last.close) > max(orh, premarket_high) else 0.0
    confidence += 0.05 if float(last.close) > ema9 > ema20 else 0.0
    confidence = min(0.95, confidence)

    print(f"[PATTERN] ORB detected=True symbol={inputs.symbol}")
    return PatternResult(
        setup_id="P_ORB",
        pattern_name="Opening Range Breakout",
        pattern_family=PatternFamily.BREAKOUT,
        detected=True,
        direction=Direction.LONG,
        confidence=confidence,
        setup_quality_tags=["break_above_orh", "hold_confirmed", "above_vwap", "macd_positive"],
        setup_family_id="OPENING_RANGE_BREAKOUT",
        entry_zone=f"break_above_orh:{orh:.4f}",
        stop_suggestion=f"orb_low:{stop_anchor:.4f}",
        rationale_text=(
            "ORB long confirmed with break+hold above ORH, strong breakout volume, VWAP support, "
            f"positive MACD, and liquidity pass. orh={orh:.4f} orl={orl:.4f} "
            f"close={float(last.close):.4f} rvol={rvol:.2f} spread_pct={spread_pct:.4f}."
        ),
        rejection_reason=None,
        risk_flags=[] if risk_per_share / max(float(last.close), 1e-9) <= 0.04 else ["WIDE_RISK_PER_SHARE"],
        data_quality_flags=list(inputs.data_quality_flags),
        trigger_type="XL_ORB_BREAK",
        trigger_level=orh,
        stop_level=stop_anchor,
        invalidation_level=stop_anchor,
    )
