"""Shared Opening Range Breakout (ORB) pattern detection."""

from __future__ import annotations

from datetime import datetime, time, timezone

from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.strategy_contracts import SessionContext

_ORB_RANGE_LOCK: dict[tuple[str, str], tuple[float, float]] = {}


def _safe_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _session_key(symbol: str, candles: list) -> tuple[str, str] | None:
    dated = next((getattr(c, "timestamp", None) for c in candles if getattr(c, "timestamp", None) is not None), None)
    if not isinstance(dated, datetime):
        return None
    date_key = dated.astimezone(timezone.utc).date().isoformat() if dated.tzinfo else dated.date().isoformat()
    return symbol.upper(), date_key


def _is_opening_window_candle(candle) -> bool:
    ts = getattr(candle, "timestamp", None)
    if not isinstance(ts, datetime):
        return False
    ts_utc = ts.astimezone(timezone.utc) if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    return time(14, 30) <= ts_utc.time() <= time(14, 34)


def _resolve_orb_levels(inputs: PatternInputs) -> tuple[float | None, float | None, str | None]:
    key_levels = inputs.levels.key_levels or {}
    provided_orh = _safe_float(key_levels.get("OPENING_RANGE_HIGH"))
    provided_orl = _safe_float(key_levels.get("OPENING_RANGE_LOW"))
    session_key = _session_key(inputs.symbol, inputs.candles)
    if session_key and session_key in _ORB_RANGE_LOCK:
        return *_ORB_RANGE_LOCK[session_key], None
    if provided_orh is not None and provided_orl is not None:
        if session_key:
            _ORB_RANGE_LOCK[session_key] = (provided_orh, provided_orl)
        return provided_orh, provided_orl, None
    if len(inputs.candles) < 5:
        return None, None, "incomplete_opening_range_window"
    opening = [c for c in inputs.candles if _is_opening_window_candle(c)]
    if len(opening) < 5:
        return None, None, "missing_opening_range_timestamps"
    orh = max(float(c.high) for c in opening)
    orl = min(float(c.low) for c in opening)
    if session_key:
        _ORB_RANGE_LOCK[session_key] = (orh, orl)
    return orh, orl, None


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
    prev = inputs.candles[-2]
    orh, orl, range_error = _resolve_orb_levels(inputs)
    if range_error:
        return reject(range_error)
    if orh is None or orl is None:
        return reject("missing_orh_or_orl")

    if float(prev.high) < (orh * 0.999):
        return reject("price_not_near_orh")

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

    stop_anchor = orl
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
