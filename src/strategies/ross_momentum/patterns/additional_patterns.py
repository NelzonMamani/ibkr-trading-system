"""Additional Ross Momentum pattern detectors for full coverage."""

from __future__ import annotations

from typing import List, Optional

from src.strategies.ross_momentum.patterns.pattern_base import PatternBase
from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily


def _is_green(candle) -> bool:
    return candle.close >= candle.open


def _is_red(candle) -> bool:
    return candle.close < candle.open


def _body(candle) -> float:
    return abs(candle.close - candle.open)


def _range(candle) -> float:
    return candle.high - candle.low


class GapAndGoPattern(PatternBase):
    name = "Gap & Go"
    family = PatternFamily.GAP_OPEN
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs):
        candles = inputs.candles
        prior_close = inputs.levels.prior_close
        if prior_close is None or len(candles) < 3:
            return self._rejected("missing prior close or candles", inputs)
        first = candles[0]
        gap_pct = ((first.open - prior_close) / prior_close) * 100.0
        if gap_pct < 4.0:
            return self._rejected("gap below threshold", inputs)
        if candles[-1].close <= max(c.high for c in candles[:2]):
            return self._rejected("no continuation above opening drive", inputs)
        rationale = (
            f"Gap & Go with opening drive continuation (gap={gap_pct:.1f}%)."
        )
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=0.72,
            rationale=rationale,
            entry_zone="Break above opening drive high",
            stop_suggestion="Below opening drive low",
            target_suggestion="Gap extension",
            setup_quality_tags=["gap_and_go"],
        )


class FirstPullbackPattern(PatternBase):
    name = "First Pullback"
    family = PatternFamily.PULLBACK
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs):
        candles = inputs.candles
        if len(candles) < 6:
            return self._rejected("insufficient candles", inputs)
        impulse = candles[:2]
        if not all(_is_green(c) for c in impulse):
            return self._rejected("no initial impulse", inputs)
        pullback = candles[2:-1]
        red_count = sum(1 for c in pullback if _is_red(c))
        if red_count < 1:
            return self._rejected("no pullback sequence", inputs)
        if candles[-1].close <= max(c.high for c in impulse):
            return self._rejected("no breakout above impulse high", inputs)
        rationale = "First pullback after opening impulse."
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=0.66,
            rationale=rationale,
            entry_zone="Break above impulse high",
            stop_suggestion="Below pullback low",
            target_suggestion="Continuation move",
            setup_quality_tags=["first_pullback"],
        )


class BreakOfKeyLevelPattern(PatternBase):
    name = "Break of Key Level"
    family = PatternFamily.BREAKOUT
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs):
        candles = inputs.candles
        if len(candles) < 2:
            return self._rejected("insufficient candles", inputs)
        last = candles[-1]
        prev = candles[-2]
        levels = list(inputs.levels.key_levels.values())
        if inputs.levels.premarket_high is not None:
            levels.append(inputs.levels.premarket_high)
        if inputs.levels.prior_close is not None:
            levels.append(inputs.levels.prior_close)
        if not levels:
            return self._rejected("no key levels", inputs)
        for level in levels:
            if prev.close <= level < last.close:
                rationale = f"Break of key level {level:.2f}."
                return self._detected(
                    inputs,
                    direction=Direction.LONG,
                    confidence=0.64,
                    rationale=rationale,
                    entry_zone="Break above key level",
                    stop_suggestion="Back below key level",
                    target_suggestion="Next key level",
                    setup_quality_tags=["key_level_break"],
                )
        return self._rejected("no key level break", inputs)


class ABCDContinuationPattern(PatternBase):
    name = "ABCD Continuation"
    family = PatternFamily.PULLBACK
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs):
        candles = inputs.candles
        if len(candles) < 4:
            return self._rejected("insufficient candles", inputs)
        a, b, c, d = candles[-4:]
        if b.close <= a.close or c.close >= b.close or d.close <= b.close:
            return self._rejected("no ABCD structure", inputs)
        rationale = "ABCD continuation with higher high."
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=0.63,
            rationale=rationale,
            entry_zone="Break above B high",
            stop_suggestion="Below C low",
            target_suggestion="Measured ABCD extension",
            setup_quality_tags=["abcd"],
        )


class CupAndHandlePattern(PatternBase):
    name = "Cup & Handle"
    family = PatternFamily.RANGE
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs):
        candles = inputs.candles
        if len(candles) < 8:
            return self._rejected("insufficient candles", inputs)
        left = candles[-8]
        mid = candles[-5]
        right = candles[-2]
        handle = candles[-2:]
        if mid.low >= min(left.low, right.low):
            return self._rejected("no cup depth", inputs)
        if abs(left.high - right.high) > left.high * 0.02:
            return self._rejected("rim mismatch", inputs)
        if handle[-1].close <= handle[0].open:
            return self._rejected("handle not constructive", inputs)
        rationale = "Intraday cup and handle structure."
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=0.6,
            rationale=rationale,
            entry_zone="Break above cup rim",
            stop_suggestion="Below handle low",
            target_suggestion="Measured cup extension",
            setup_quality_tags=["cup_handle"],
        )


class MomentumReclaimPattern(PatternBase):
    name = "Momentum Reclaim"
    family = PatternFamily.PULLBACK
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs):
        candles = inputs.candles
        if len(candles) < 2:
            return self._rejected("insufficient candles", inputs)
        vwap = inputs.indicators.vwap
        ema20 = inputs.indicators.ema20
        last = candles[-1]
        prev = candles[-2]
        reclaim_level = vwap or ema20
        if reclaim_level is None:
            return self._rejected("missing reclaim level", inputs)
        if prev.close >= reclaim_level or last.close <= reclaim_level:
            return self._rejected("no reclaim cross", inputs)
        rationale = f"Reclaim above {reclaim_level:.2f}."
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=0.62,
            rationale=rationale,
            entry_zone="Reclaim above VWAP/EMA",
            stop_suggestion="Back below reclaim level",
            target_suggestion="Prior high",
            setup_quality_tags=["momentum_reclaim"],
        )


class FlatTopBreakoutPattern(PatternBase):
    name = "Flat-Top / Ascending Breakout"
    family = PatternFamily.BREAKOUT
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs):
        candles = inputs.candles
        if len(candles) < 6:
            return self._rejected("insufficient candles", inputs)
        highs = [c.high for c in candles[-6:-1]]
        flat_top = max(highs) - min(highs) <= max(highs) * 0.003
        higher_lows = all(
            candles[i].low <= candles[i + 1].low for i in range(-6, -2)
        )
        last = candles[-1]
        if not flat_top or not higher_lows:
            return self._rejected("no flat-top structure", inputs)
        if last.close <= max(highs):
            return self._rejected("no breakout", inputs)
        rationale = "Flat-top breakout with ascending lows."
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=0.64,
            rationale=rationale,
            entry_zone="Break above flat top",
            stop_suggestion="Below rising lows",
            target_suggestion="Range expansion",
            setup_quality_tags=["flat_top"],
        )


class RedToGreenPattern(PatternBase):
    name = "Red-to-Green"
    family = PatternFamily.REVERSAL
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs):
        prior_close = inputs.levels.prior_close
        candles = inputs.candles
        if prior_close is None or len(candles) < 2:
            return self._rejected("missing prior close", inputs)
        if candles[-2].close >= prior_close:
            return self._rejected("no red-to-green setup", inputs)
        if candles[-1].close <= prior_close:
            return self._rejected("no reclaim above prior close", inputs)
        rationale = "Red-to-green reversal reclaim."
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=0.6,
            rationale=rationale,
            entry_zone="Break above prior close",
            stop_suggestion="Back below prior close",
            target_suggestion="Continuation",
            setup_quality_tags=["red_to_green"],
        )


class GreenToRedPattern(PatternBase):
    name = "Green-to-Red"
    family = PatternFamily.REVERSAL
    direction_bias = Direction.SHORT

    def evaluate(self, inputs: PatternInputs):
        prior_close = inputs.levels.prior_close
        candles = inputs.candles
        if prior_close is None or len(candles) < 2:
            return self._rejected("missing prior close", inputs)
        if candles[-2].close <= prior_close:
            return self._rejected("no green-to-red setup", inputs)
        if candles[-1].close >= prior_close:
            return self._rejected("no fail below prior close", inputs)
        rationale = "Green-to-red reversal failure."
        return self._detected(
            inputs,
            direction=Direction.SHORT,
            confidence=0.6,
            rationale=rationale,
            entry_zone="Break below prior close",
            stop_suggestion="Back above prior close",
            target_suggestion="Downside extension",
            setup_quality_tags=["green_to_red"],
        )


class HalfDollarBreakPattern(PatternBase):
    name = "Half-Dollar Break"
    family = PatternFamily.BREAKOUT
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs):
        candles = inputs.candles
        if len(candles) < 2:
            return self._rejected("insufficient candles", inputs)
        last = candles[-1]
        prev = candles[-2]
        level = (int(prev.close * 2) / 2) + 0.5
        if prev.close <= level < last.close:
            rationale = f"Half-dollar break above {level:.2f}."
            return self._detected(
                inputs,
                direction=Direction.LONG,
                confidence=0.6,
                rationale=rationale,
                entry_zone="Break above half-dollar",
                stop_suggestion="Below half-dollar",
                target_suggestion="Next level",
                setup_quality_tags=["half_dollar"],
            )
        return self._rejected("no half-dollar break", inputs)


class WholeDollarBreakPattern(PatternBase):
    name = "Whole-Dollar Break"
    family = PatternFamily.BREAKOUT
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs):
        candles = inputs.candles
        if len(candles) < 2:
            return self._rejected("insufficient candles", inputs)
        last = candles[-1]
        prev = candles[-2]
        level = float(int(prev.close) + 1)
        if prev.close <= level < last.close:
            rationale = f"Whole-dollar break above {level:.2f}."
            return self._detected(
                inputs,
                direction=Direction.LONG,
                confidence=0.6,
                rationale=rationale,
                entry_zone="Break above whole-dollar",
                stop_suggestion="Below whole-dollar",
                target_suggestion="Next whole-dollar",
                setup_quality_tags=["whole_dollar"],
            )
        return self._rejected("no whole-dollar break", inputs)


class HaltResumeContinuationPattern(PatternBase):
    name = "Halt Resume Continuation"
    family = PatternFamily.VOL_EVENT
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs):
        if not inputs.data_quality_flags:
            return self._rejected("no halt flags", inputs)
        if not any("HALT" in flag for flag in inputs.data_quality_flags):
            return self._rejected("no halt flag present", inputs)
        candles = inputs.candles
        if len(candles) < 2:
            return self._rejected("insufficient candles", inputs)
        if candles[-1].close <= candles[-2].high:
            return self._rejected("no continuation after resume", inputs)
        rationale = "Halt resume continuation breakout."
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=0.65,
            rationale=rationale,
            entry_zone="Break above post-halt high",
            stop_suggestion="Below post-halt low",
            target_suggestion="Continuation",
            setup_quality_tags=["halt_resume"],
        )


class ParabolicExhaustionPattern(PatternBase):
    name = "Parabolic Exhaustion"
    family = PatternFamily.REVERSAL
    direction_bias = Direction.NEUTRAL

    def evaluate(self, inputs: PatternInputs):
        candles = inputs.candles
        if len(candles) < 4:
            return self._rejected("insufficient candles", inputs, direction=Direction.NEUTRAL)
        last_three = candles[-3:]
        if not all(_is_green(c) for c in last_three):
            return self._rejected("no parabolic advance", inputs, direction=Direction.NEUTRAL)
        avg_range = sum(_range(c) for c in candles[:-1]) / (len(candles) - 1)
        if _range(candles[-1]) < avg_range * 2.5:
            return self._rejected("range not extended", inputs, direction=Direction.NEUTRAL)
        rationale = "Parabolic exhaustion risk detected; avoid new entries."
        return self._detected(
            inputs,
            direction=Direction.NEUTRAL,
            confidence=0.9,
            rationale=rationale,
            entry_zone="Avoid new entries",
            stop_suggestion="Protect profits",
            target_suggestion="None",
            setup_quality_tags=["parabolic_exhaustion"],
            risk_flags=["VETO_PARABOLIC"],
        )
