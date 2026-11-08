"""Shared pullback and continuation setup family implementations."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from math import isclose

from src.strategies.ross_momentum.strategy_policy import (
    THREE_BAR_PULLBACK_DESCRIPTIVE_OBJECTIVE,
    SECOND_PULLBACK_DESCRIPTIVE_OBJECTIVE,
    RANGE_BREAK_DESCRIPTIVE_OBJECTIVE,
    CANONICAL_POLICY,
)

from src.strategies.common.triggers.trigger_abcd_continuation import abcd_candle_rejection
from src.strategies.ross_momentum.policy.pattern_input_policy import PatternInputPolicy

from src.strategies.common.triggers.trigger_pullback_variants import (
    evaluate_second_pullback_trigger,
    evaluate_three_bar_pullback_trigger,
)

from src.strategies.common.patterns.pattern_hod_break import detect_hod_break
from src.strategies.common.patterns.pattern_ema_pullback import detect_ema_pullback
from src.strategies.common.patterns.pattern_flat_top_breakout import detect_flat_top_breakout
from src.strategies.common.patterns.pattern_opening_drive import detect_opening_drive
from src.strategies.common.patterns.pattern_vwap_pullback import detect_vwap_pullback
from src.strategies.common.patterns.pattern_trend_continuation_stair_step import (
    detect_trend_continuation_stair_step,
)
from src.strategies.common.patterns.pullback_utils import validate_volume_contraction
from src.utils.time_utils import to_ny_time
from src.strategies.ross_momentum.patterns.pattern_base import PatternBase
from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs, _timeframe_provenance
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult, SetupSemantic


class _SimpleLongPattern(PatternBase):
    pattern_id = ""
    name = ""
    family = PatternFamily.BREAKOUT
    direction_bias = Direction.LONG

    def _check(self, inputs: PatternInputs) -> tuple[bool, str]:
        if len(inputs.candles) < 5:
            return False, "insufficient candles"
        return True, "ok"

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        ok, reason = self._check(inputs)
        if not ok:
            return self._rejected(reason, inputs)
        last = inputs.candles[-1]
        prev = inputs.candles[-2]
        if last.close <= prev.close:
            return self._rejected("no continuation close", inputs)
        return self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=0.58,
            rationale=f"{self.name} heuristic continuation trigger.",
            setup_quality_tags=[self.pattern_id.lower()],
        )


class RangeBreakoutPattern(_SimpleLongPattern):
    pattern_id = "P_RANGE_BREAKOUT"
    name = "Range / Rectangle Breakout"

    def __init__(self, measurement_policy=None):
        # Existing Ross registry uses its policy; other strategy callers can
        # supply their own compatible measurement policy without a second detector.
        self._measurement_policy = (measurement_policy if measurement_policy is not None
                                    else CANONICAL_POLICY.range_break)

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        def reject(reason):
            return replace(self._rejected(reason, inputs), setup_family_id="RANGE_BREAK")

        candles = list(inputs.candles or [])
        clock = inputs.observed_at_utc
        # A rectangle needs measured completed geometry. Timeless generic
        # continuation fixtures cannot assert that authority.
        if not isinstance(clock, datetime) or clock.tzinfo is None:
            return reject("range_missing_original_clock")
        rejection = abcd_candle_rejection(candles, observed_at_utc=clock, require_clock=True)
        if rejection:
            return reject(rejection)
        seconds = {"10s": 10, "1m": 60, "5m": 300}.get(inputs.primary_timeframe)
        if seconds is None:
            return reject("range_structure_timeframe_unsupported")
        completed = [c for c in candles if c.timestamp + timedelta(seconds=seconds) <= clock]
        spec = self._measurement_policy
        if len(completed) < spec.formation_bars:
            return reject("range_incomplete_geometry")
        formation = completed[-spec.formation_bars:]
        step = timedelta(seconds=seconds)
        if any(b.timestamp - a.timestamp != step for a, b in zip(formation, formation[1:])):
            return reject("range_gapped_geometry")
        if to_ny_time(formation[0].timestamp).date() != to_ny_time(formation[-1].timestamp).date():
            return reject("range_cross_day_geometry")
        if _timeframe_provenance(formation, inputs.primary_timeframe,
                PatternInputPolicy.from_policy_v2(), symbol=inputs.symbol, now_utc=clock) != "PRESENT":
            return reject("range_stale_geometry")
        high = max(c.high for c in formation)
        low = min(c.low for c in formation)
        height = high - low
        def inclusive_le(left, right):
            # Decimal quote arithmetic can straddle an inclusive geometric
            # boundary by a few ULPs. This never changes strict execution cross.
            return left <= right or isclose(left, right,
                rel_tol=spec.numeric_relative_tolerance, abs_tol=0)
        if not (inclusive_le(spec.minimum_height_fraction, height / high)
                and inclusive_le(height / high, spec.maximum_height_fraction)):
            return reject("range_height_outside_calibration")
        tolerance = height * spec.boundary_tolerance_fraction
        if not inclusive_le(high - min(c.high for c in formation), tolerance):
            return reject("range_upper_boundary_not_flat")
        if not inclusive_le(max(c.low for c in formation) - low, tolerance):
            return reject("range_lower_boundary_not_flat")
        confirmation_start = formation[-1].timestamp + step
        expiry = confirmation_start + step * spec.confirmation_window_bars
        if clock >= expiry:
            return reject("range_expired_geometry")
        # Forming bars never supply anchors, but can invalidate this occurrence.
        if any(c.low <= low for c in candles if c.timestamp >= confirmation_start):
            return reject("range_structural_invalidation_breached")
        return PatternResult(
            setup_id=self.pattern_id, pattern_name=self.name, pattern_family=self.family,
            detected=True, direction=Direction.LONG, confidence=0.58,
            setup_family_id="RANGE_BREAK", setup_quality_tags=["measured_rectangle"],
            rationale_text="Completed measured rectangle; own execution confirmation required.",
            target_suggestion=RANGE_BREAK_DESCRIPTIVE_OBJECTIVE,
            trigger_type="BREAKOUT_HIGH", trigger_level=high, stop_level=low,
            invalidation_level=low, setup_semantic=SetupSemantic.CONTINUATION.value,
            signal_class="ENTRY", trigger_mode="BREAKOUT_CONTINUATION",
            data_quality_flags=list(inputs.data_quality_flags),
            setup_metadata={
                "origin_timestamp": formation[0].timestamp,
                "formation_start_timestamp": formation[0].timestamp,
                "confirmation_start_timestamp": confirmation_start,
                "confirmation_expiry_timestamp": expiry,
                "structure_completed_timestamp": formation[-1].timestamp,
                "range_high": high, "range_low": low, "range_height": height,
                "formation_bar_count": len(formation),
                "boundary_tolerance": tolerance,
                "primary_timeframe": inputs.primary_timeframe,
                "execution_refinement_timeframe": inputs.execution_refinement_timeframe,
                "timeframe_provenance": dict(inputs.timeframe_provenance or {}),
            },
        )


class FlatTopBreakoutPattern(_SimpleLongPattern):
    pattern_id = "P_FLAT_TOP_BREAKOUT"
    name = "Flat Top Breakout"

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        return detect_flat_top_breakout(inputs)


class AscendingTriangleBreakoutPattern(_SimpleLongPattern):
    pattern_id = "P_ASCENDING_TRIANGLE_BREAKOUT"
    name = "Ascending Triangle Breakout"


class PennantBreakPattern(_SimpleLongPattern):
    pattern_id = "P_PENNANT_BREAK"
    name = "Pennant Break"


class EmaPullbackPattern(_SimpleLongPattern):
    pattern_id = "P_EMA_PULLBACK"
    name = "EMA Pullback"
    family = PatternFamily.PULLBACK

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        return detect_ema_pullback(inputs)


class VwapPullbackPattern(_SimpleLongPattern):
    pattern_id = "P_VWAP_PULLBACK"
    name = "VWAP Pullback"
    family = PatternFamily.PULLBACK

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        return detect_vwap_pullback(inputs)


def _safe_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _read(item: object, field: str) -> object:
    if isinstance(item, dict):
        return item.get(field)
    return getattr(item, field, None)


def _reject_pullback(
    *,
    inputs: PatternInputs,
    pattern_id: str,
    pattern_name: str,
    family: str,
    reason: str,
) -> PatternResult:
    print(f"[PATTERN][{family}] detected=False symbol={inputs.symbol} reason={reason}")
    return PatternResult(
        setup_id=pattern_id,
        pattern_name=pattern_name,
        pattern_family=PatternFamily.PULLBACK,
        detected=False,
        direction=Direction.LONG,
        confidence=0.0,
        setup_quality_tags=[],
        setup_family_id=family,
        setup_semantic=SetupSemantic.CONTINUATION.value,
        rationale_text=f"Rejected: {reason}",
        rejection_reason=reason,
        data_quality_flags=list(inputs.data_quality_flags),
        trigger_type="PULLBACK_HIGH_BREAK",
        signal_class="ENTRY",
        trigger_mode="NONE",
    )


def _volume(values: list[object]) -> list[float]:
    return [_safe_float(_read(item, "volume")) or 0.0 for item in values]


def _bar_values(candles: list[object]) -> tuple[list[float], list[float], list[float], list[float], list[float]] | None:
    opens = [_safe_float(_read(item, "open")) for item in candles]
    highs = [_safe_float(_read(item, "high")) for item in candles]
    lows = [_safe_float(_read(item, "low")) for item in candles]
    closes = [_safe_float(_read(item, "close")) for item in candles]
    volumes = [_safe_float(_read(item, "volume")) for item in candles]
    if any(value is None for value in [*opens, *highs, *lows, *closes, *volumes]):
        return None
    return (
        [float(value) for value in opens if value is not None],
        [float(value) for value in highs if value is not None],
        [float(value) for value in lows if value is not None],
        [float(value) for value in closes if value is not None],
        [float(value) for value in volumes if value is not None],
    )


def _detected_pullback(
    *,
    inputs: PatternInputs,
    pattern_id: str,
    pattern_name: str,
    family: str,
    confidence: float,
    pullback_candles: list[object],
    trigger_candle: object,
    rationale: str,
    setup_quality_tags: list[str],
    target_suggestion: str | None = None,
) -> PatternResult:
    pullback_high = max(float(_read(candle, "high")) for candle in pullback_candles)
    pullback_low = min(float(_read(candle, "low")) for candle in pullback_candles)
    trigger_low = float(_read(trigger_candle, "low"))
    trigger_high = float(_read(trigger_candle, "high"))
    trigger_close = float(_read(trigger_candle, "close"))
    pullback_volumes = _volume(pullback_candles)
    pullback_volume = sum(pullback_volumes) / max(len(pullback_volumes), 1)
    breakout_attempt = trigger_high >= pullback_high or trigger_close > pullback_high
    breakout_volume_confirmed = None
    if breakout_attempt:
        breakout_volume_confirmed = float(_read(trigger_candle, "volume")) > pullback_volume

    if trigger_low <= pullback_low:
        return _reject_pullback(
            inputs=inputs,
            pattern_id=pattern_id,
            pattern_name=pattern_name,
            family=family,
            reason="structural_invalidation_breached",
        )

    print(
        f"[PATTERN][{family}] detected=True symbol={inputs.symbol} "
        f"trigger={pullback_high:.4f} stop={pullback_low:.4f}"
    )
    return PatternResult(
        setup_id=pattern_id,
        pattern_name=pattern_name,
        pattern_family=PatternFamily.PULLBACK,
        detected=True,
        direction=Direction.LONG,
        confidence=confidence,
        setup_quality_tags=list(dict.fromkeys([*setup_quality_tags, "continuation"])),
        setup_family_id=family,
        setup_semantic=SetupSemantic.CONTINUATION.value,
        rationale_text=f"{rationale} trigger={pullback_high:.4f} stop={pullback_low:.4f}.",
        target_suggestion=target_suggestion,
        rejection_reason=None,
        data_quality_flags=list(inputs.data_quality_flags),
        trigger_type="PULLBACK_HIGH_BREAK",
        trigger_level=pullback_high,
        stop_level=pullback_low,
        invalidation_level=pullback_low,
        signal_class="ENTRY",
        trigger_mode="NONE",
        setup_metadata={
            "pullback_high": pullback_high,
            "pullback_low": pullback_low,
            "pullback_volume": pullback_volume,
            "breakout_attempt": breakout_attempt,
            "breakout_volume_confirmed": breakout_volume_confirmed,
            "primary_timeframe": inputs.primary_timeframe,
            "execution_refinement_timeframe": inputs.execution_refinement_timeframe,
            "context_timeframe": inputs.context_timeframe,
            "timeframe_provenance": dict(inputs.timeframe_provenance or {}),
        },
    )


def _evaluate_armed_pullback(pattern, inputs: PatternInputs) -> PatternResult:
    """Recover the newest originating structure within the supplied candle history.

    The registry retains authority over session and input freshness. Historical
    trigger checks consume only real bars and the existing registered contract.
    A newer structural origin supersedes older ones even if it has since ended.
    """
    candles = list(inputs.candles or [])
    if len(candles) < 5:
        return pattern._evaluate_window(inputs)
    latest_result = None
    for start in range(len(candles) - 5, -1, -1):
        origin = candles[start:start + 5]
        result = pattern._evaluate_window(replace(inputs, candles=origin))
        if latest_result is None:
            latest_result = result
        if not result.detected:
            if result.rejection_reason == "structural_invalidation_breached":
                return result
            continue

        evaluator = (
            evaluate_three_bar_pullback_trigger
            if result.setup_family_id == "THREE_BAR_PULLBACK"
            else evaluate_second_pullback_trigger
        )
        for index in range(start + 4, len(candles)):
            if _bar_values(candles[index - 1:index + 1]) is None:
                return _reject_pullback(
                    inputs=inputs, pattern_id=pattern.pattern_id,
                    pattern_name=pattern.name, family=result.setup_family_id,
                    reason="invalid_candle_fields",
                )
            if index > start + 4:
                result = pattern._evaluate_window(
                    replace(inputs, candles=[*origin[:4], candles[index]])
                )
                if not result.detected:
                    return result
            if index < len(candles) - 1 and inputs.execution_refinement_timeframe == inputs.primary_timeframe:
                trigger = evaluator(
                    {
                        "trigger_level": result.trigger_level,
                        "stop_level": result.stop_level,
                        "invalidation_level": result.invalidation_level,
                        "setup_metadata": result.setup_metadata,
                    },
                    {"candles": candles[index - 1:index + 1]},
                )
                if trigger["trigger_ready_now"]:
                    return _reject_pullback(
                        inputs=inputs, pattern_id=pattern.pattern_id,
                        pattern_name=pattern.name, family=result.setup_family_id,
                        reason="pullback_breakout_already_consumed",
                    )
        result.setup_metadata["pullback_start_timestamp"] = _read(
            origin[1 if result.setup_family_id == "THREE_BAR_PULLBACK" else 3], "timestamp"
        )
        result.setup_metadata["pullback_end_timestamp"] = _read(origin[4], "timestamp")
        result.setup_metadata["origin_timestamp"] = _read(origin[0], "timestamp")
        result.setup_metadata["structure_completed_timestamp"] = _read(origin[3], "timestamp")
        return result
    return latest_result


class ThreeBarPullbackPattern(_SimpleLongPattern):
    pattern_id = "P_THREE_BAR_PULLBACK"
    name = "Three-Bar Pullback"
    family = PatternFamily.PULLBACK

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        return _evaluate_armed_pullback(self, inputs)

    def _evaluate_window(self, inputs: PatternInputs) -> PatternResult:
        candles = list(inputs.candles or [])
        if len(candles) < 5:
            return _reject_pullback(
                inputs=inputs,
                pattern_id=self.pattern_id,
                pattern_name=self.name,
                family="THREE_BAR_PULLBACK",
                reason="insufficient_candles",
            )
        window = candles[-5:]
        values = _bar_values(window)
        if values is None:
            return _reject_pullback(
                inputs=inputs,
                pattern_id=self.pattern_id,
                pattern_name=self.name,
                family="THREE_BAR_PULLBACK",
                reason="invalid_candle_fields",
            )
        opens, highs, _lows, closes, volumes = values
        impulse_ok = closes[0] > opens[0] and highs[0] >= opens[0]
        pullback_closes_lower = closes[1] >= closes[2] >= closes[3]
        pullback_bars = [window[1], window[2], window[3]]
        pullback_orderly = all(closes[index] <= opens[index] for index in (1, 2, 3)) and pullback_closes_lower
        pullback_volume = sum(volumes[1:4]) / 3
        volume_dry_up = validate_volume_contraction(pullback_volume, volumes[0])
        if not impulse_ok:
            return _reject_pullback(
                inputs=inputs,
                pattern_id=self.pattern_id,
                pattern_name=self.name,
                family="THREE_BAR_PULLBACK",
                reason="missing_initial_impulse",
            )
        if not pullback_orderly:
            return _reject_pullback(
                inputs=inputs,
                pattern_id=self.pattern_id,
                pattern_name=self.name,
                family="THREE_BAR_PULLBACK",
                reason="three_bar_pullback_not_orderly",
            )
        if not volume_dry_up:
            return _reject_pullback(
                inputs=inputs,
                pattern_id=self.pattern_id,
                pattern_name=self.name,
                family="THREE_BAR_PULLBACK",
                reason="pullback_volume_not_dry",
            )
        return _detected_pullback(
            inputs=inputs,
            pattern_id=self.pattern_id,
            pattern_name=self.name,
            family="THREE_BAR_PULLBACK",
            confidence=0.58,
            pullback_candles=pullback_bars,
            trigger_candle=window[-1],
            rationale="Three-bar pullback continuation detected from canonical pullback structure.",
            setup_quality_tags=["three_bar_pullback", "pullback_volume_dry_up"],
            target_suggestion=THREE_BAR_PULLBACK_DESCRIPTIVE_OBJECTIVE,
        )


class TrendContinuationStairStepPattern(_SimpleLongPattern):
    pattern_id = "P_TREND_CONTINUATION_STAIR_STEP"
    name = "Trend Continuation (Stair-Step)"

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        return detect_trend_continuation_stair_step(inputs)


class SecondPullbackPattern(_SimpleLongPattern):
    pattern_id = "P_SECOND_PULLBACK"
    name = "Second Pullback"
    family = PatternFamily.PULLBACK

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        return _evaluate_armed_pullback(self, inputs)

    def _evaluate_window(self, inputs: PatternInputs) -> PatternResult:
        candles = list(inputs.candles or [])
        if len(candles) < 5:
            return _reject_pullback(
                inputs=inputs,
                pattern_id=self.pattern_id,
                pattern_name=self.name,
                family="SECOND_PULLBACK",
                reason="insufficient_candles",
            )
        window = candles[-5:]
        values = _bar_values(window)
        if values is None:
            return _reject_pullback(
                inputs=inputs,
                pattern_id=self.pattern_id,
                pattern_name=self.name,
                family="SECOND_PULLBACK",
                reason="invalid_candle_fields",
            )
        opens, highs, _lows, closes, volumes = values
        impulse_ok = closes[0] > opens[0] and highs[0] >= opens[0]
        first_pullback_ok = closes[1] <= opens[1]
        first_break_ok = closes[2] > highs[1]
        second_pullback_ok = closes[3] <= opens[3]
        volume_dry_up = validate_volume_contraction(volumes[3], volumes[2])
        if not impulse_ok:
            return _reject_pullback(
                inputs=inputs,
                pattern_id=self.pattern_id,
                pattern_name=self.name,
                family="SECOND_PULLBACK",
                reason="missing_initial_impulse",
            )
        if not (first_pullback_ok and first_break_ok):
            return _reject_pullback(
                inputs=inputs,
                pattern_id=self.pattern_id,
                pattern_name=self.name,
                family="SECOND_PULLBACK",
                reason="missing_first_pullback_break",
            )
        if not second_pullback_ok:
            return _reject_pullback(
                inputs=inputs,
                pattern_id=self.pattern_id,
                pattern_name=self.name,
                family="SECOND_PULLBACK",
                reason="second_pullback_not_orderly",
            )
        if not volume_dry_up:
            return _reject_pullback(
                inputs=inputs,
                pattern_id=self.pattern_id,
                pattern_name=self.name,
                family="SECOND_PULLBACK",
                reason="pullback_volume_not_dry",
            )
        return _detected_pullback(
            inputs=inputs,
            pattern_id=self.pattern_id,
            pattern_name=self.name,
            family="SECOND_PULLBACK",
            confidence=0.58,
            pullback_candles=[window[3]],
            trigger_candle=window[-1],
            rationale="Second pullback continuation detected after first pullback break.",
            setup_quality_tags=["second_pullback", "pullback_volume_dry_up"],
            target_suggestion=SECOND_PULLBACK_DESCRIPTIVE_OBJECTIVE,
        )


class LiquiditySweepReclaimPattern(_SimpleLongPattern):
    pattern_id = "P_LIQUIDITY_SWEEP_RECLAIM"
    name = "Liquidity Sweep Reclaim"


class HODBreakPattern(_SimpleLongPattern):
    pattern_id = "P_HOD_BREAK"
    name = "High of Day Break"

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        return detect_hod_break(inputs)


class OpeningDrivePattern(_SimpleLongPattern):
    pattern_id = "P_OPENING_DRIVE"
    name = "Opening Drive"

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        return detect_opening_drive(inputs)
