"""Canonical Ross setup family primitives for setup engine reuse."""

from __future__ import annotations

from dataclasses import replace
from statistics import mean

from src.setup_engine.setup_families.key_level_helpers import (
    level_candidates_for_inputs,
    nearest_relevant_key_level,
)
from src.strategies.common.patterns.pattern_cup_handle import detect_cup_handle
from src.strategies.common.patterns.pattern_momentum_reclaim import detect_momentum_reclaim
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
        return detect_momentum_reclaim(inputs)


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
    SWING_WINDOW = 1
    MIN_RETRACE = 0.30
    MAX_RETRACE = 0.70
    MAX_LOOKBACK_BARS = 60
    TRIGGER_ID = "XL_ABCD_CONTINUATION"
    MIN_AB_MOVE_PCT = 0.01
    MIN_AVG_PULLBACK_VOLUME = 100.0

    @staticmethod
    def _reject(symbol: str, reason: str, **fields: float | int | str) -> None:
        extras = " ".join(f"{k}={v}" for k, v in fields.items())
        suffix = f" {extras}" if extras else ""
        print(f"[SETUP][ABCD][REJECT_REASON] symbol={symbol} reason={reason}{suffix}")

    @staticmethod
    def _swing_high(candles, idx: int, window: int) -> bool:
        if idx - window < 0 or idx + window >= len(candles):
            return False
        current_high = float(candles[idx].high)
        for j in range(idx - window, idx + window + 1):
            if j == idx:
                continue
            if current_high <= float(candles[j].high):
                return False
        return True

    @staticmethod
    def _swing_low(candles, idx: int, window: int) -> bool:
        if idx - window < 0 or idx + window >= len(candles):
            return False
        current_low = float(candles[idx].low)
        for j in range(idx - window, idx + window + 1):
            if j == idx:
                continue
            if current_low >= float(candles[j].low):
                return False
        return True

    @classmethod
    def _find_latest_swing_triplet(cls, candles):
        highs = [idx for idx in range(len(candles)) if cls._swing_high(candles, idx, cls.SWING_WINDOW)]
        lows = [idx for idx in range(len(candles)) if cls._swing_low(candles, idx, cls.SWING_WINDOW)]
        for c_idx in reversed(lows):
            b_candidates = [idx for idx in highs if idx < c_idx]
            if not b_candidates:
                continue
            b_idx = b_candidates[-1]
            a_candidates = [idx for idx in lows if idx < b_idx]
            if not a_candidates:
                continue
            a_idx = a_candidates[-1]
            return a_idx, b_idx, c_idx
        return None

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        symbol = str(inputs.symbol or "UNKNOWN").upper()
        candles = inputs.candles[-self.MAX_LOOKBACK_BARS :] if len(inputs.candles) > self.MAX_LOOKBACK_BARS else inputs.candles
        print(f"[SETUP][ABCD][START] symbol={symbol} candles={len(candles)}")
        if len(candles) < 7:
            self._reject(symbol, "INSUFFICIENT_CANDLE_HISTORY")
            return self._rejected("INSUFFICIENT_CANDLE_HISTORY", inputs)

        swing_triplet = self._find_latest_swing_triplet(candles)
        if swing_triplet is None:
            self._reject(symbol, "NO_SWING_SEQUENCE")
            return self._rejected("NO_SWING_SEQUENCE", inputs)
        a_idx, b_idx, c_idx = swing_triplet
        if not (a_idx < b_idx < c_idx):
            self._reject(symbol, "INVALID_ORDERING", a_idx=a_idx, b_idx=b_idx, c_idx=c_idx)
            return self._rejected("INVALID_ORDERING", inputs)

        sequence = candles[a_idx : c_idx + 1]
        invalid_candle_found = any(
            float(getattr(c, "high", 0.0)) < float(getattr(c, "low", 0.0))
            or float(getattr(c, "low", 0.0)) <= 0.0
            or float(getattr(c, "high", 0.0)) <= 0.0
            for c in sequence
        )
        if invalid_candle_found:
            self._reject(symbol, "INVALID_CANDLE_DATA")
            return self._rejected("INVALID_CANDLE_DATA", inputs)

        a_price = float(candles[a_idx].low)
        b_price = float(candles[b_idx].high)
        c_price = float(candles[c_idx].low)
        ab_length = b_price - a_price
        if ab_length <= 0 or b_price <= a_price:
            self._reject(symbol, "NO_VALID_IMPULSE", a=a_price, b=b_price, c=c_price)
            return self._rejected("NO_VALID_IMPULSE", inputs)
        if (ab_length / max(a_price, 1e-9)) < self.MIN_AB_MOVE_PCT:
            self._reject(
                symbol,
                "AB_LENGTH_TOO_SMALL",
                a=f"{a_price:.4f}",
                b=f"{b_price:.4f}",
                ab_pct=f"{(ab_length / max(a_price, 1e-9)):.4f}",
            )
            return self._rejected("AB_LENGTH_TOO_SMALL", inputs)
        if c_price <= a_price:
            self._reject(symbol, "STRUCTURE_BROKEN_BELOW_A", a=f"{a_price:.4f}", c=f"{c_price:.4f}")
            return self._rejected("STRUCTURE_BROKEN_BELOW_A", inputs)

        retrace = (b_price - c_price) / ab_length
        if retrace < self.MIN_RETRACE:
            self._reject(symbol, "RETRACEMENT_TOO_SHALLOW", retracement=f"{retrace:.4f}")
            return self._rejected("RETRACEMENT_TOO_SHALLOW", inputs)
        if retrace > self.MAX_RETRACE:
            self._reject(symbol, "RETRACEMENT_TOO_DEEP", retracement=f"{retrace:.4f}")
            return self._rejected("RETRACEMENT_TOO_DEEP", inputs)

        pullback_window = candles[b_idx : c_idx + 1]
        pullback_volumes = [float(getattr(c, "volume", 0.0) or 0.0) for c in pullback_window]
        avg_pullback_volume = sum(pullback_volumes) / max(len(pullback_volumes), 1)
        if avg_pullback_volume < self.MIN_AVG_PULLBACK_VOLUME:
            self._reject(
                symbol,
                "LOW_VOLUME_ENVIRONMENT",
                avg_volume=f"{avg_pullback_volume:.2f}",
                min_volume=f"{self.MIN_AVG_PULLBACK_VOLUME:.2f}",
            )
            return self._rejected("LOW_VOLUME_ENVIRONMENT", inputs)
        trigger_level = max((float(c.high) for c in pullback_window), default=None)
        if trigger_level is None:
            self._reject(symbol, "NO_TRIGGER_LEVEL")
            return self._rejected("NO_TRIGGER_LEVEL", inputs)
        d_projection = c_price + ab_length

        quality_tags = ["valid_retracement", "measured_move_ready"]
        if retrace <= 0.45:
            quality_tags.append("shallow_pullback")
        else:
            quality_tags.append("deep_pullback")
        if ab_length / max(a_price, 1e-9) >= 0.03:
            quality_tags.append("clean_impulse")

        print(
            "[SETUP][ABCD][DETECTED] "
            f"symbol={symbol} A={a_price:.4f} B={b_price:.4f} C={c_price:.4f} "
            f"retracement={retrace:.4f} trigger={trigger_level:.4f} target={d_projection:.4f}"
        )
        return PatternResult(
            setup_id=self.pattern_id or self.name,
            setup_family_id="ABCD",
            pattern_name=self.name,
            pattern_family=self.family,
            detected=True,
            direction=Direction.LONG,
            confidence=0.72,
            setup_quality_tags=quality_tags,
            tags=quality_tags,
            entry_zone="Break above pullback high",
            stop_suggestion="Below C swing low",
            target_suggestion="AB measured move projection from C",
            rationale_text=(
                "ABCD continuation structure detected with valid retracement and measured-move projection.\n"
                f"A={a_price:.4f}, B={b_price:.4f}, C={c_price:.4f}, retracement={retrace:.2%}, "
                f"trigger={trigger_level:.4f}, D={d_projection:.4f}."
            ),
            risk_flags=[],
            data_quality_flags=inputs.data_quality_flags,
            session_valid=inputs.session_context.value in {"PRE", "REGULAR", "AFTER"},
            trigger_type=self.TRIGGER_ID,
            trigger_level=trigger_level,
            stop_level=c_price,
            invalidation_level=c_price,
            anchor_a_price=a_price,
            anchor_b_price=b_price,
            anchor_c_price=c_price,
            anchor_a_index=a_idx,
            anchor_b_index=b_idx,
            anchor_c_index=c_idx,
            ab_length=ab_length,
            retracement_pct=retrace,
            d_projection=d_projection,
            risk_reference_level=c_price,
            setup_metadata={
                "swing_window": self.SWING_WINDOW,
                "max_lookback_bars": self.MAX_LOOKBACK_BARS,
            },
        )


class CupHandlePattern(PatternBase):
    pattern_id = "P_CUP_HANDLE"
    name = "Cup and Handle"
    family = PatternFamily.RANGE
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        return detect_cup_handle(inputs)


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
        if inputs.session_context not in {SessionContext.PRE, SessionContext.REGULAR}:
            return self._rejected("invalid_session", inputs)
        candles = list(inputs.candles or [])
        if len(candles) < 2:
            return self._rejected("missing_candles", inputs)

        spread = _safe_float(inputs.liquidity_context.spread)
        if spread is None:
            return self._rejected("missing_price_fields", inputs)
        last = candles[-1]
        prev = candles[-2]
        if any(_safe_float(getattr(last, field, None)) is None for field in ("open", "high", "low", "close")):
            return self._rejected("missing_price_fields", inputs)
        last_open = float(last.open)
        last_high = float(last.high)
        last_low = float(last.low)
        last_close = float(last.close)
        prev_close = float(prev.close)

        candidates = level_candidates_for_inputs(inputs)
        if not candidates:
            return self._rejected("no_relevant_key_level", inputs)
        selected = nearest_relevant_key_level(inputs=inputs, reference_price=prev_close, direction="LONG")
        if selected is None:
            return self._rejected("no_relevant_key_level", inputs)

        level_price = selected.level_price
        if last_close <= level_price and last_high > level_price:
            return self._rejected("wick_through_only", inputs)
        broke_level = last_high >= level_price and last_open <= level_price and last_close > level_price
        if not broke_level:
            return self._rejected("no_relevant_key_level", inputs)

        body_size = max(abs(last_close - last_open), 1e-9)
        upper_wick = max(last_high - max(last_open, last_close), 0.0)
        if upper_wick > body_size * 1.8:
            return self._rejected("failed_acceptance", inputs)
        if prev_close > level_price and last_close < prev_close:
            return self._rejected("key_level_break_exhaustion", inputs)

        rvol = _safe_float(inputs.liquidity_context.rvol)
        avg_vol = _avg_volume(candles, lookback=8)
        volume_confirmed = bool(last.volume >= avg_vol and (rvol is None or rvol >= 1.2))
        if not volume_confirmed:
            return self._rejected("insufficient_volume_confirmation", inputs)

        spread_pct = spread if spread < 1 else spread / max(last_close, 1e-9)
        if spread_pct > 0.08:
            return self._rejected("excessive_spread", inputs)
        float_millions = _safe_float(inputs.liquidity_context.float_millions)
        if float_millions is not None and float_millions < 2.0:
            return self._rejected("low_liquidity", inputs)

        confidence = 0.66 + (0.07 if (rvol or 0.0) >= 2.0 else 0.0) + (0.05 if selected.level_type in {"PREMARKET_HIGH", "HOD", "PRIOR_DAY_HIGH", "MULTI_DAY_HIGH"} else 0.0)
        detected = self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=min(confidence, 0.89),
            rationale=(
                "Decisive break and hold through key level with acceptance/participation confirmation.\n"
                f"level_type={selected.level_type}, level={level_price:.2f}, close={last_close:.2f}, rvol={rvol}, spread={spread:.4f}."
            ),
            entry_zone=f"Continuation above {selected.level_type} {level_price:.2f}",
            stop_suggestion=f"Back below {level_price:.2f}",
            target_suggestion="Expansion to next overhead key level",
            setup_quality_tags=["key_level_break", selected.level_type.lower(), "volume_confirmed"],
        )
        stop_level = min(last_low, level_price - 0.01)
        invalidation_level = level_price
        print(
            "[PATTERN_TRACE][INPUT] "
            f"symbol={inputs.symbol} pattern_id={self.pattern_id} selected_level={level_price:.4f} level_type={selected.level_type}"
        )
        return replace(
            detected,
            setup_family_id="KEY_LEVEL_BREAK",
            trigger_type="XL_KEY_LEVEL_BREAK",
            trigger_level=level_price,
            stop_level=stop_level,
            invalidation_level=invalidation_level,
            setup_metadata={
                **dict(detected.setup_metadata or {}),
                "level_type": selected.level_type,
                "selected_level_source": selected.source,
            },
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
