"""Canonical Ross setup family primitives for setup engine reuse."""

from __future__ import annotations

from dataclasses import replace
from statistics import mean

from src.strategies.ross_momentum.patterns.pattern_base import PatternBase
from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.strategy_contracts import SessionContext


def _avg_volume(candles, lookback: int = 8) -> float:
    if not candles:
        return 0.0
    sample = candles[-lookback:] if len(candles) >= lookback else candles
    return mean(c.volume for c in sample)


def _safe_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _safe_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on", "active"}:
        return True
    if text in {"0", "false", "no", "n", "off", "inactive"}:
        return False
    return None


class GapGoPattern(PatternBase):
    pattern_id = "P_GAP_GO"
    name = "Gap & Go"
    family = PatternFamily.GAP_OPEN
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        if inputs.session_context not in {SessionContext.PRE, SessionContext.REGULAR}:
            return self._rejected("SESSION_NOT_SUPPORTED", inputs)
        if len(inputs.candles) < 4:
            return self._rejected("MISSING_PRICE_MOMENTUM", inputs)

        key_levels = inputs.levels.key_levels or {}
        premarket_high = _safe_float(inputs.levels.premarket_high) or _safe_float(key_levels.get("PREMARKET_HIGH"))
        prior_close = _safe_float(inputs.levels.prior_close) or _safe_float(key_levels.get("PRIOR_CLOSE"))
        hod = _safe_float(inputs.levels.hod) or _safe_float(key_levels.get("HOD"))
        opening_range_high = (
            _safe_float(key_levels.get("OPENING_RANGE_HIGH"))
            or _safe_float(key_levels.get("ORB_HIGH"))
            or _safe_float(key_levels.get("BREAKOUT_RANGE_UPPER"))
        )
        if premarket_high is None and opening_range_high is None and hod is None and prior_close is None:
            return self._rejected("MISSING_KEY_LEVELS", inputs)

        last = inputs.candles[-1]
        prev = inputs.candles[-2]
        intraday_low = min(float(c.low) for c in inputs.candles)
        if last.close <= intraday_low:
            return self._rejected("MISSING_PRICE_MOMENTUM", inputs)

        if prior_close is None or prior_close <= 0:
            return self._rejected("INSUFFICIENT_GAP", inputs)
        gap_pct = (last.close - prior_close) / prior_close
        if gap_pct <= 0.0:
            return self._rejected("INSUFFICIENT_GAP", inputs)

        price = float(last.close)
        press_pmh = premarket_high is not None and price >= premarket_high
        press_orh = opening_range_high is not None and price >= opening_range_high
        press_hod = hod is not None and price >= hod
        continuation_above_prior_close = prior_close is not None and price > prior_close and price > float(prev.close)
        if not any([press_pmh, press_orh, press_hod, continuation_above_prior_close]):
            return self._rejected("NOT_AT_BREAKOUT_LEVEL", inputs)

        rvol = _safe_float(inputs.liquidity_context.rvol)
        if rvol is None:
            return self._rejected("MISSING_TRADABILITY_CONTEXT", inputs)
        if inputs.session_context == SessionContext.PRE:
            min_rvol = 0.3
        elif inputs.session_context == SessionContext.REGULAR:
            min_rvol = 1.0
        else:
            min_rvol = 0.5
        if rvol < min_rvol:
            return self._rejected("INSUFFICIENT_RVOL", inputs)

        structure_ctx = inputs.news_context or {}
        trend_up = _safe_bool(structure_ctx.get("trend_up"))
        impulse_active = _safe_bool(structure_ctx.get("impulse_active"))
        consolidation_active = _safe_bool(structure_ctx.get("consolidation_active"))
        compression_active = _safe_bool(structure_ctx.get("compression_active"))
        continuation_pressure = _safe_bool(structure_ctx.get("continuation_pressure"))
        structure_known = any(
            value is not None
            for value in (trend_up, impulse_active, consolidation_active, compression_active, continuation_pressure)
        )
        if structure_known:
            structure_ok = bool(trend_up) or bool(impulse_active) or (bool(continuation_pressure) and (bool(consolidation_active) or bool(compression_active)))
        else:
            # Conservative fallback: require continuation structure visible in candles and trend references.
            structure_ok = (
                float(last.close) > float(prev.close)
                and float(last.high) >= float(prev.high)
                and (inputs.indicators.ema9 is None or float(last.close) >= float(inputs.indicators.ema9))
                and (inputs.indicators.vwap is None or float(last.close) >= float(inputs.indicators.vwap))
            )
        if not structure_ok:
            return self._rejected("WEAK_STRUCTURE", inputs)

        spread = _safe_float(inputs.liquidity_context.spread)
        if spread is None:
            return self._rejected("MISSING_TRADABILITY_CONTEXT", inputs)
        spread_pct = spread if spread < 1 else spread / max(price, 1e-9)
        if spread_pct > 0.08:
            return self._rejected("WIDE_SPREAD", inputs)

        float_millions = _safe_float(inputs.liquidity_context.float_millions)
        risk_flags: list[str] = []
        if float_millions is None:
            risk_flags.append("FLOAT_CONTEXT_MISSING")
        elif float_millions <= 8.0:
            risk_flags.append("LOW_FLOAT")
        if not structure_known:
            risk_flags.append("STRUCTURE_CONTEXT_MISSING")

        volume_ok = float(last.volume) >= _avg_volume(inputs.candles)
        above_vwap = inputs.indicators.vwap is not None and price >= float(inputs.indicators.vwap)
        setup_tags = ["HIGH_RVOL", "LEVEL_PRESSURE", "OPENING_MOMENTUM"]
        if inputs.session_context == SessionContext.PRE:
            setup_tags.append("PREMARKET_STRENGTH")
        if above_vwap:
            setup_tags.append("ABOVE_VWAP")
        if float_millions is not None and float_millions <= 8.0:
            setup_tags.append("LOW_FLOAT")

        confidence = min(0.9, 0.62 + min(gap_pct, 0.25) * 0.8 + (0.08 if volume_ok else 0.0) + (0.06 if structure_known else 0.0))
        detected = self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=confidence,
            rationale=(
                "Gap-up continuation context is active with level pressure and session-aligned participation.\n"
                f"Gap%={gap_pct:.2%}, close={price:.2f}, PMH={premarket_high}, ORH={opening_range_high}, "
                f"HOD={hod}, RVOL={rvol:.2f}, spread={spread:.4f}."
            ),
            entry_zone="Break/hold continuation through PMH/ORH/HOD context",
            stop_suggestion="Under premarket high or opening pullback low",
            target_suggestion="Range expansion toward HOD extension",
            setup_quality_tags=setup_tags,
            risk_flags=risk_flags,
        )
        trigger_type = "BREAKOUT_HIGH"
        if press_pmh:
            trigger_type = "PMH_BREAK"
        elif press_hod:
            trigger_type = "HOD_BREAK"
        elif press_orh:
            trigger_type = "BREAK_AND_HOLD"
        return replace(detected, setup_family_id="GAP_GO", trigger_type=trigger_type)


class FirstPullbackPattern(PatternBase):
    pattern_id = "P_FIRST_PULLBACK"
    name = "First Pullback"
    family = PatternFamily.PULLBACK
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        candles = inputs.candles
        if len(candles) < 6:
            return self._rejected("insufficient candles", inputs)
        impulse = candles[-6:-3]
        pullback = candles[-3:-1]
        trigger = candles[-1]
        impulse_gain = impulse[-1].close - impulse[0].open
        if impulse_gain <= 0:
            return self._rejected("missing initial impulse", inputs)
        if not all(c.close <= c.open for c in pullback):
            return self._rejected("pullback bars not controlled", inputs)
        pullback_low = min(c.low for c in pullback)
        pullback_retrace = (impulse[-1].high - pullback_low) / max(impulse[-1].high - impulse[0].low, 1e-9)
        if pullback_retrace > 0.45:
            return self._rejected("pullback too deep", inputs)
        if trigger.close <= max(c.high for c in pullback):
            return self._rejected("no reclaim trigger", inputs)
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=0.74,
            rationale=(
                "Initial impulse followed by first controlled pullback and reclaim trigger.\n"
                f"Impulse_gain={impulse_gain:.2f}, retrace={pullback_retrace:.2%}."
            ),
            entry_zone="Break above pullback high",
            stop_suggestion="Below pullback low",
            target_suggestion="Retest impulse high then measured extension",
            setup_quality_tags=["first_pullback", "continuation_structure"],
        )


class MomentumReclaimPattern(PatternBase):
    pattern_id = "P_MOMENTUM_RECLAIM"
    name = "Momentum Reclaim"
    family = PatternFamily.PULLBACK
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        candles = inputs.candles
        if len(candles) < 4:
            return self._rejected("insufficient candles", inputs)
        last = candles[-1]
        ema9 = inputs.indicators.ema9
        vwap = inputs.indicators.vwap
        if ema9 is None and vwap is None:
            return self._rejected("missing reclaim reference (ema9/vwap)", inputs)
        refs = [v for v in [ema9, vwap] if v is not None]
        reclaim_level = max(refs)
        prior_lost = any(c.close < reclaim_level for c in candles[-4:-1])
        if not prior_lost:
            return self._rejected("no prior shakeout under reclaim level", inputs)
        if last.close <= reclaim_level:
            return self._rejected("reclaim not confirmed", inputs)
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=0.71,
            rationale=(
                "Price lost momentum reference and reclaimed it with close confirmation.\n"
                f"Reclaim level={reclaim_level:.2f}, close={last.close:.2f}."
            ),
            entry_zone="Close/retest above VWAP-EMA reclaim level",
            stop_suggestion="Back below reclaim level",
            target_suggestion="Prior swing high",
            setup_quality_tags=["reclaim", "shakeout_absorbed"],
        )


class FailedOrbFakeoutPattern(PatternBase):
    pattern_id = "P_FAILED_ORB_FAKEOUT"
    name = "Failed ORB Fakeout"
    family = PatternFamily.REVERSAL
    direction_bias = Direction.SHORT

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        candles = inputs.candles
        if inputs.session_context != SessionContext.REGULAR:
            return self._rejected("not regular session", inputs)
        if len(candles) < 7:
            return self._rejected("insufficient candles", inputs)
        opening = candles[:5]
        range_high = max(c.high for c in opening)
        range_low = min(c.low for c in opening)
        probe = candles[-2]
        last = candles[-1]
        if probe.high <= range_high:
            return self._rejected("no fakeout probe above opening range", inputs)
        if last.close >= range_high:
            return self._rejected("orb breakout still holding", inputs)
        confidence = 0.69 if last.close > range_low else 0.64
        return self._detected(
            inputs,
            direction=Direction.SHORT,
            confidence=confidence,
            rationale=(
                "Opening-range breakout attempt failed and price reclaimed back inside range.\n"
                f"Range high={range_high:.2f}, probe_high={probe.high:.2f}, close={last.close:.2f}."
            ),
            entry_zone="Failure back under OR high",
            stop_suggestion="Above fakeout wick high",
            target_suggestion="Opening range midpoint/low",
            setup_quality_tags=["orb_failure", "trap_move"],
            risk_flags=["FAKEOUT_VOLATILITY"],
        )


class GapFillReversalPattern(PatternBase):
    pattern_id = "P_GAP_FILL_REVERSAL"
    name = "Gap Fill Reversal"
    family = PatternFamily.REVERSAL
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        prior_close = inputs.levels.prior_close
        if prior_close is None or len(inputs.candles) < 5:
            return self._rejected("missing prior close or candles", inputs)
        recent = inputs.candles[-5:]
        fill_touch = any(c.low <= prior_close <= c.high for c in recent)
        if not fill_touch:
            return self._rejected("gap fill level not tested", inputs)
        last = recent[-1]
        prev = recent[-2]
        if not (last.close > last.open and last.close > prev.high):
            return self._rejected("no reversal confirmation after fill", inputs)
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=0.67,
            rationale=(
                "Price tested prior close gap-fill level and reversed with confirmation close.\n"
                f"Prior close={prior_close:.2f}, last close={last.close:.2f}."
            ),
            entry_zone="Break above reversal confirmation candle",
            stop_suggestion="Below gap fill test low",
            target_suggestion="VWAP / opening range reclaim",
            setup_quality_tags=["gap_fill", "reversal_confirmation"],
            risk_flags=["COUNTERTREND_IF_WEAK"],
        )


class ABCDPattern(PatternBase):
    pattern_id = "P_ABCD"
    name = "ABCD Continuation"
    family = PatternFamily.PULLBACK
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        candles = inputs.candles
        if len(candles) < 8:
            return self._rejected("insufficient candles", inputs)
        a = candles[-8]
        b = candles[-5]
        c = candles[-3]
        d = candles[-1]
        ab = b.high - a.low
        bc = b.high - c.low
        cd = d.close - c.low
        if ab <= 0 or bc <= 0 or cd <= 0:
            return self._rejected("invalid AB/BC/CD leg geometry", inputs)
        retrace = bc / ab
        extension = cd / ab
        if not 0.25 <= retrace <= 0.7:
            return self._rejected("BC retracement out of range", inputs)
        if extension < 0.8:
            return self._rejected("CD extension too weak", inputs)
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=0.72,
            rationale=(
                "ABCD continuation measured move confirmed by BC retrace and CD extension.\n"
                f"BC/AB={retrace:.2f}, CD/AB={extension:.2f}."
            ),
            entry_zone="D-break continuation above C-to-D thrust",
            stop_suggestion="Below C swing low",
            target_suggestion="1.0-1.27 AB projection",
            setup_quality_tags=["ab_cd", "measured_move"],
        )


class CupHandlePattern(PatternBase):
    pattern_id = "P_CUP_HANDLE"
    name = "Cup and Handle"
    family = PatternFamily.RANGE
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        candles = inputs.candles
        if len(candles) < 12:
            return self._rejected("insufficient candles", inputs)
        window = candles[-12:]
        left_high = max(c.high for c in window[:4])
        cup_low = min(c.low for c in window[4:8])
        right_high = max(c.high for c in window[8:10])
        handle = window[10:]
        handle_low = min(c.low for c in handle)
        last = window[-1]
        if right_high < left_high * 0.985:
            return self._rejected("right side failed to recover cup rim", inputs)
        cup_depth = (left_high - cup_low) / max(left_high, 1e-9)
        handle_depth = (right_high - handle_low) / max(right_high, 1e-9)
        if cup_depth > 0.2 or handle_depth > 0.07:
            return self._rejected("cup/handle depth too large", inputs)
        rim = max(left_high, right_high)
        if last.close <= rim:
            return self._rejected("no breakout above cup rim", inputs)
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=0.7,
            rationale=(
                "Rounded cup recovery plus shallow handle resolved with rim breakout.\n"
                f"Cup depth={cup_depth:.2%}, handle depth={handle_depth:.2%}."
            ),
            entry_zone="Break and hold above cup rim",
            stop_suggestion="Below handle low",
            target_suggestion="Cup depth measured move",
            setup_quality_tags=["cup_handle", "base_breakout"],
        )


class HaltResumePattern(PatternBase):
    pattern_id = "P_HALT_RESUME"
    name = "Halt Resume"
    family = PatternFamily.VOL_EVENT
    direction_bias = Direction.NEUTRAL

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        return self._rejected(
            "disabled_no_halt_tape_in_pattern_inputs",
            inputs,
            direction=Direction.NEUTRAL,
        )


class ParabolicExhaustionPattern(PatternBase):
    pattern_id = "P_PARABOLIC_EXHAUSTION"
    name = "Parabolic Exhaustion"
    family = PatternFamily.REVERSAL
    direction_bias = Direction.SHORT

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        candles = inputs.candles
        if len(candles) < 6:
            return self._rejected("insufficient candles", inputs)
        recent = candles[-6:]
        gains = [c.close - c.open for c in recent[:-1]]
        if not all(g > 0 for g in gains):
            return self._rejected("not a sustained parabolic leg", inputs)
        acceleration = gains[-1] / max(gains[0], 1e-9)
        last = recent[-1]
        wick_ratio = (last.high - max(last.open, last.close)) / max(last.high - last.low, 1e-9)
        vol_spike = last.volume >= _avg_volume(candles, lookback=6) * 1.6
        if acceleration < 1.8 or wick_ratio < 0.45 or not vol_spike:
            return self._rejected("missing exhaustion signatures", inputs)
        return self._detected(
            inputs,
            direction=Direction.SHORT,
            confidence=0.73,
            rationale=(
                "Parabolic run shows climactic volume and upper-wick rejection at extension.\n"
                f"Acceleration={acceleration:.2f}, wick_ratio={wick_ratio:.2f}."
            ),
            entry_zone="Break below exhaustion candle low",
            stop_suggestion="Above exhaustion high",
            target_suggestion="VWAP/EMA mean reversion",
            setup_quality_tags=["parabolic", "volume_climax", "rejection_wick"],
            risk_flags=["EXHAUSTION_REVERSAL"],
        )


class KeyLevelBreakPattern(PatternBase):
    pattern_id = "P_KEY_LEVEL_BREAK"
    name = "Key Level Break"
    family = PatternFamily.BREAKOUT
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        if not inputs.candles:
            return self._rejected("no candles", inputs)
        levels = {
            "premarket_high": inputs.levels.premarket_high,
            "hod": inputs.levels.hod,
            **inputs.levels.key_levels,
        }
        levels = {k: v for k, v in levels.items() if v is not None}
        if not levels:
            return self._rejected("missing key levels", inputs)
        last = inputs.candles[-1]
        broken = [name for name, price in levels.items() if last.close > price and last.open <= price]
        if not broken:
            return self._rejected("no key level break", inputs)
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=0.68,
            rationale=(
                "Price closed through tracked key level(s) with breakout body confirmation.\n"
                f"Broken levels={', '.join(sorted(broken))}, close={last.close:.2f}."
            ),
            entry_zone="Close above broken key level with continuation",
            stop_suggestion="Back below broken level",
            target_suggestion="Next overhead key level",
            setup_quality_tags=["key_level_break", *sorted(broken)[:2]],
        )


class OpeningFakeoutPattern(PatternBase):
    pattern_id = "P_OPENING_FAKEOUT"
    name = "Opening Fakeout"
    family = PatternFamily.REVERSAL
    direction_bias = Direction.SHORT

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        candles = inputs.candles
        if inputs.session_context != SessionContext.REGULAR:
            return self._rejected("not regular session", inputs)
        if len(candles) < 6:
            return self._rejected("insufficient candles", inputs)
        opening = candles[:5]
        range_high = max(c.high for c in opening)
        range_low = min(c.low for c in opening)
        last = candles[-1]
        if last.high <= range_high or last.close >= range_high:
            return self._rejected("no rejection above opening high", inputs)
        if (last.high - last.close) < (last.close - last.low):
            return self._rejected("rejection wick not dominant", inputs)
        return self._detected(
            inputs,
            direction=Direction.SHORT,
            confidence=0.66,
            rationale=(
                "Early-session break attempt rejected with dominant upper wick back into opening range.\n"
                f"OR high={range_high:.2f}, OR low={range_low:.2f}, close={last.close:.2f}."
            ),
            entry_zone="Back below opening range high after wick rejection",
            stop_suggestion="Above rejection wick high",
            target_suggestion="Opening range midpoint/low",
            setup_quality_tags=["opening_fakeout", "rejection"],
            risk_flags=["OPENING_VOLATILITY"],
        )
