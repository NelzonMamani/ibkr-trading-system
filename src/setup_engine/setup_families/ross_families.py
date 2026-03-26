"""Canonical Ross setup family primitives for setup engine reuse."""

from __future__ import annotations

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


class GapGoPattern(PatternBase):
    pattern_id = "P_GAP_GO"
    name = "Gap & Go"
    family = PatternFamily.GAP_OPEN
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        if len(inputs.candles) < 3:
            return self._rejected("insufficient candles", inputs)
        level = inputs.levels.premarket_high
        prior_close = inputs.levels.prior_close
        if level is None or prior_close is None:
            return self._rejected("missing premarket_high/prior_close", inputs)
        if level <= prior_close:
            return self._rejected("no upward opening gap", inputs)
        last = inputs.candles[-1]
        gap_pct = (level - prior_close) / prior_close
        volume_ok = last.volume >= _avg_volume(inputs.candles)
        rvol = inputs.liquidity_context.rvol or 0.0
        if last.close <= level:
            return self._rejected("gap not holding above premarket high", inputs)
        if rvol < 1.3:
            return self._rejected("insufficient relative volume", inputs)
        confidence = min(0.87, 0.62 + gap_pct * 3 + (0.08 if volume_ok else 0.0))
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=confidence,
            rationale=(
                "Gap-up open is holding and extending above premarket high with RVOL support.\n"
                f"Gap%={gap_pct:.2%}, PMH={level:.2f}, close={last.close:.2f}, RVOL={rvol:.2f}."
            ),
            entry_zone="Break/hold above premarket high continuation",
            stop_suggestion="Under premarket high or opening pullback low",
            target_suggestion="Range expansion toward HOD extension",
            setup_quality_tags=["gap_up", "rvol_confirmed", "go_not_fill"],
            trigger_type="break_above_level",
            trigger_level=level,
            entry_reference=f"break>{level:.4f}",
            stop_reference=f"below_premarket_high<{level:.4f}",
            invalidation_reference=f"close_below<{level:.4f}",
            required_confirmations=["rvol_min_1_3", "spread_ok", "volume_ok"],
            structural_notes=[f"gap_pct={gap_pct:.4f}", f"prior_close={prior_close:.4f}"],
        )


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
            trigger_type="break_of_pullback_high",
            trigger_level=max(c.high for c in pullback),
            entry_reference=f"break>{max(c.high for c in pullback):.4f}",
            stop_reference=f"below_pullback_low<{pullback_low:.4f}",
            invalidation_reference=f"close_below<{pullback_low:.4f}",
            required_confirmations=["controlled_pullback", "volume_context_ok", "spread_ok"],
            structural_notes=[f"retrace={pullback_retrace:.4f}"],
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
            trigger_type="reclaim_and_hold",
            trigger_level=reclaim_level,
            entry_reference=f"reclaim>{reclaim_level:.4f}",
            stop_reference=f"below_reclaim<{reclaim_level:.4f}",
            invalidation_reference=f"close_below<{reclaim_level:.4f}",
            required_confirmations=["reclaim_close", "spread_ok"],
            structural_notes=[f"reclaim={reclaim_level:.4f}"],
        )


class FailedOrbFakeoutPattern(PatternBase):
    pattern_id = "P_FAILED_ORB_FAKEOUT"
    name = "Failed ORB Fakeout"
    family = PatternFamily.REVERSAL
    direction_bias = Direction.SHORT

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        candles = inputs.candles
        if inputs.session_context != SessionContext.REGULAR:
            return self._rejected("not regular session", inputs, session_valid=False)
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
            trigger_type="break_below_failed_orb_level",
            trigger_level=range_high,
            entry_reference=f"fail_back_below<{range_high:.4f}",
            stop_reference=f"above_probe_high>{probe.high:.4f}",
            invalidation_reference=f"close_above>{probe.high:.4f}",
            required_confirmations=["opening_range_defined", "rejection_confirmed"],
            structural_notes=[f"or_low={range_low:.4f}"],
            non_entry_classification="AVOID",
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
            trigger_type="gap_fill_reversal_reclaim",
            trigger_level=prev.high,
            entry_reference=f"break>{prev.high:.4f}",
            stop_reference=f"below_fill_test_low<{min(c.low for c in recent):.4f}",
            invalidation_reference=f"close_below<{min(c.low for c in recent):.4f}",
            required_confirmations=["fill_touch", "reversal_close"],
            structural_notes=[f"prior_close={prior_close:.4f}"],
            non_entry_classification="CAUTION",
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
            trigger_type="measured_move_trigger",
            trigger_level=d.high,
            entry_reference=f"break>{d.high:.4f}",
            stop_reference=f"below_c_low<{c.low:.4f}",
            invalidation_reference=f"close_below<{c.low:.4f}",
            required_confirmations=["bc_retrace_valid", "cd_extension_valid"],
            structural_notes=[f"bc_ab={retrace:.4f}", f"cd_ab={extension:.4f}"],
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
            trigger_type="break_of_pattern_resistance",
            trigger_level=rim,
            entry_reference=f"break>{rim:.4f}",
            stop_reference=f"below_handle_low<{handle_low:.4f}",
            invalidation_reference=f"close_below<{handle_low:.4f}",
            required_confirmations=["handle_tight", "rim_break"],
            structural_notes=[f"cup_depth={cup_depth:.4f}", f"handle_depth={handle_depth:.4f}"],
        )


class HaltResumePattern(PatternBase):
    pattern_id = "P_HALT_RESUME"
    name = "Halt Resume"
    family = PatternFamily.VOL_EVENT
    direction_bias = Direction.NEUTRAL

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        if len(inputs.candles) < 4:
            return self._rejected("insufficient candles", inputs, direction=Direction.NEUTRAL)
        halt_ref = inputs.levels.key_levels.get("HALT_RESUME_LEVEL")
        stabilization_bars = inputs.candles[-3:-1]
        trigger = inputs.candles[-1]
        if halt_ref is None:
            halt_ref = max(c.high for c in stabilization_bars)
        stable = all((c.high - c.low) / max(c.close, 1e-9) < 0.04 for c in stabilization_bars)
        vol_ok = trigger.volume >= _avg_volume(inputs.candles, lookback=4) * 1.1
        if not stable:
            return self._rejected("post_halt_not_stabilized", inputs, direction=Direction.NEUTRAL)
        if trigger.close <= halt_ref:
            return self._rejected("halt_resume_level_not_broken", inputs, direction=Direction.NEUTRAL)
        if not vol_ok:
            return self._rejected("post_halt_volume_not_confirmed", inputs, direction=Direction.NEUTRAL)
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=0.66,
            rationale="Post-halt stabilization with resume break confirmed.",
            entry_zone="Break above post-halt stabilization range",
            stop_suggestion="Below stabilization low",
            target_suggestion="Halt continuation extension",
            setup_quality_tags=["halt_resume", "stabilized", "volume_confirmed"],
            trigger_type="post_halt_resume_break",
            trigger_level=halt_ref,
            entry_reference=f"break>{halt_ref:.4f}",
            stop_reference=f"below_stabilization_low<{min(c.low for c in stabilization_bars):.4f}",
            invalidation_reference=f"close_below<{min(c.low for c in stabilization_bars):.4f}",
            required_confirmations=["stabilization", "volume_expansion"],
            structural_notes=[f"halt_ref={halt_ref:.4f}"],
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
            trigger_type="exhaustion_warning",
            trigger_level=last.low,
            entry_reference=f"avoid_long_above<{last.high:.4f}",
            stop_reference=f"n/a_non_entry_{last.high:.4f}",
            invalidation_reference=f"resume_only_if_hold>{last.high:.4f}",
            required_confirmations=["climax_volume", "upper_wick_rejection"],
            structural_notes=[f"acceleration={acceleration:.4f}", f"wick_ratio={wick_ratio:.4f}"],
            non_entry_classification="EXIT",
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
            trigger_type="break_above_level",
            trigger_level=max(levels[name] for name in broken),
            entry_reference=f"break>{max(levels[name] for name in broken):.4f}",
            stop_reference=f"below_broken_level<{max(levels[name] for name in broken):.4f}",
            invalidation_reference=f"close_below<{max(levels[name] for name in broken):.4f}",
            required_confirmations=["break_close_confirmed", "spread_ok"],
            structural_notes=[f"broken={','.join(sorted(broken))}"],
        )


class OpeningFakeoutPattern(PatternBase):
    pattern_id = "P_OPENING_FAKEOUT"
    name = "Opening Fakeout"
    family = PatternFamily.REVERSAL
    direction_bias = Direction.SHORT

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        candles = inputs.candles
        if inputs.session_context != SessionContext.REGULAR:
            return self._rejected("not regular session", inputs, session_valid=False)
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
            trigger_type="opening_fakeout_warning",
            trigger_level=range_high,
            entry_reference=f"avoid_long_while_below<{range_high:.4f}",
            stop_reference=f"n/a_non_entry_{last.high:.4f}",
            invalidation_reference=f"close_above>{last.high:.4f}",
            required_confirmations=["opening_rejection", "wick_dominant"],
            structural_notes=[f"or_low={range_low:.4f}"],
            non_entry_classification="AVOID",
        )
