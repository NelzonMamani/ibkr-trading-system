"""Shared Opening Range Breakout (ORB) pattern detection."""

from __future__ import annotations

from datetime import time
from zoneinfo import ZoneInfo

from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.strategy_contracts import SessionContext

_US_EASTERN = ZoneInfo("US/Eastern")
_ORB_OPEN_START = time(9, 30, 0)
_ORB_OPEN_END = time(9, 34, 59)


def _safe_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def detect_orb(inputs: PatternInputs) -> PatternResult:
    """Detect canonical ORB setup structure only (confirmation/trigger are downstream)."""

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

    if len(inputs.candles) < 2:
        return reject("insufficient_1m_candles")

    session_label = str(inputs.session_context.value if hasattr(inputs.session_context, "value") else inputs.session_context).upper()
    session_phase = str((inputs.news_context or {}).get("session_phase") or "").upper()
    if session_label != SessionContext.REGULAR.value and session_phase not in {"RTH_OPEN", "MORNING"}:
        return reject("session_not_rth_open_or_morning")

    key_levels = inputs.levels.key_levels or {}
    provided_orh = _safe_float(inputs.levels.hod) or _safe_float(key_levels.get("OPENING_RANGE_HIGH"))
    provided_orl = _safe_float(inputs.levels.lod) or _safe_float(key_levels.get("OPENING_RANGE_LOW"))
    rvol = _safe_float(inputs.liquidity_context.rvol)
    spread_raw = _safe_float(inputs.liquidity_context.spread)
    if rvol is None or spread_raw is None:
        return reject("missing_liquidity_context")

    if any(getattr(candle, "timestamp", None) is None for candle in inputs.candles):
        return reject("missing_opening_range_timestamps")
    opening = []
    for candle in inputs.candles:
        candle_ts = candle.timestamp
        assert candle_ts is not None
        if candle_ts.tzinfo is None:
            candle_et = candle_ts.replace(tzinfo=_US_EASTERN)
        else:
            candle_et = candle_ts.astimezone(_US_EASTERN)
        if _ORB_OPEN_START <= candle_et.time() <= _ORB_OPEN_END:
            opening.append(candle)
    if len(opening) < 5:
        return reject("insufficient_opening_range_candles")
    last = inputs.candles[-1]
    orh = max(float(c.high) for c in opening)
    orl = min(float(c.low) for c in opening)
    if orh <= orl:
        return reject("opening_range_not_defined")

    if provided_orh is not None:
        orh = max(orh, provided_orh)
    if provided_orl is not None:
        orl = min(orl, provided_orl)

    if float(last.high) < (orh * 0.998):
        return reject("price_not_near_orh")

    opening_avg_volume = sum(float(c.volume) for c in opening) / max(len(opening), 1)
    if float(last.volume) < (opening_avg_volume * 0.5):
        return reject("breakout_volume_below_opening_average")

    spread_pct = spread_raw if spread_raw < 1 else spread_raw / max(float(last.close), 1e-9)
    spread_threshold = 0.01
    if rvol < 1.2:
        return reject("rvol_below_threshold")
    if spread_pct > spread_threshold:
        return reject("spread_too_wide")

    stop_anchor = orl
    if stop_anchor is None:
        return reject("missing_stop_anchor")

    risk_per_share = float(last.close) - float(stop_anchor)
    extension_too_large = risk_per_share <= 0 or (risk_per_share / max(float(last.close), 1e-9)) > 0.05
    if extension_too_large:
        return reject("extension_too_large")

    confidence = 0.66
    confidence += min(0.14, max(0.0, rvol - 1.2) * 0.05)
    confidence += 0.05 if float(last.close) >= orh else 0.0
    confidence = min(0.95, confidence)

    print(f"[PATTERN] ORB detected=True symbol={inputs.symbol}")
    return PatternResult(
        setup_id="P_ORB",
        pattern_name="Opening Range Breakout",
        pattern_family=PatternFamily.BREAKOUT,
        detected=True,
        direction=Direction.LONG,
        confidence=confidence,
        setup_quality_tags=["orh_available", "volume_sane", "liquidity_sane", "stop_anchor_orl"],
        setup_family_id="OPENING_RANGE_BREAKOUT",
        entry_zone=f"break_above_orh:{orh:.4f}",
        stop_suggestion=f"orb_low:{stop_anchor:.4f}",
        rationale_text=(
            "ORB setup structure detected and eligible for confirmation/trigger evaluation. "
            f"orh={orh:.4f} orl={orl:.4f} close={float(last.close):.4f} "
            f"rvol={rvol:.2f} spread_pct={spread_pct:.4f} "
            f"vwap={_safe_float(inputs.indicators.vwap)} ema9={_safe_float(inputs.indicators.ema9)} "
            f"ema20={_safe_float(inputs.indicators.ema20)} macd={_safe_float((inputs.news_context or {}).get('macd'))}."
        ),
        rejection_reason=None,
        risk_flags=[] if risk_per_share / max(float(last.close), 1e-9) <= 0.04 else ["WIDE_RISK_PER_SHARE"],
        data_quality_flags=list(inputs.data_quality_flags),
        trigger_type="XL_ORB_BREAK",
        trigger_level=orh,
        stop_level=stop_anchor,
        invalidation_level=stop_anchor,
    )
