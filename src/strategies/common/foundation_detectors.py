"""Foundation setup-family and structure detectors (E20)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.candles.functional import (
    average_range,
    breakout_failure,
    range_contraction,
    range_expansion,
)
from src.strategies.common.foundation import SETUP_FAMILIES


@dataclass(frozen=True)
class SetupContext:
    candles: Sequence[Candle]
    levels: dict[str, float] = field(default_factory=dict)
    zones: dict[str, tuple[float, float]] = field(default_factory=dict)
    indicators: dict[str, float] = field(default_factory=dict)
    flags: dict[str, bool] = field(default_factory=dict)

    def last_candle(self) -> Candle | None:
        return self.candles[-1] if self.candles else None

    def prior_candle(self) -> Candle | None:
        return self.candles[-2] if len(self.candles) >= 2 else None


@dataclass(frozen=True)
class DetectionResult:
    setup_family_id: str
    detected: bool
    confidence: float
    evidence: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class StructureDetectionResult:
    structure_id: str
    detected: bool
    metrics: dict[str, float] = field(default_factory=dict)


def _price_near_level(price: float, level: float, tolerance: float) -> bool:
    if level == 0:
        return False
    return abs(price - level) / level <= tolerance


def _trend_up(candles: Sequence[Candle]) -> bool:
    closes = [candle.close for candle in candles]
    return all(closes[i] >= closes[i - 1] for i in range(1, len(closes))) if closes else False


def _trend_down(candles: Sequence[Candle]) -> bool:
    closes = [candle.close for candle in candles]
    return all(closes[i] <= closes[i - 1] for i in range(1, len(closes))) if closes else False


def _trend_up_values(values: Sequence[float]) -> bool:
    return all(values[i] >= values[i - 1] for i in range(1, len(values))) if values else False


def _gap_direction(context: SetupContext, min_gap_pct: float = 0.01) -> str | None:
    if not context.candles:
        return None
    prior_close = context.levels.get("LVL_PRIOR_DAY_CLOSE")
    if prior_close is None:
        return None
    opening = context.candles[0].open
    gap_pct = (opening - prior_close) / prior_close if prior_close else 0.0
    if gap_pct >= min_gap_pct:
        return "up"
    if gap_pct <= -min_gap_pct:
        return "down"
    return None


def _opening_range(context: SetupContext) -> tuple[float | None, float | None]:
    return (
        context.indicators.get("opening_range_high"),
        context.indicators.get("opening_range_low"),
    )


def _avg_range(context: SetupContext) -> float:
    return context.indicators.get("avg_range", average_range(context.candles))


def detect_range_structure(candles: Sequence[Candle], max_multiplier: float = 1.2) -> bool:
    if len(candles) < 3:
        return False
    ranges = [candle.range for candle in candles]
    avg = sum(ranges) / len(ranges) if ranges else 0.0
    return max(ranges) <= avg * max_multiplier if avg else False


def detect_level_interaction(price: float, level: float, tolerance: float = 0.003) -> StructureDetectionResult:
    detected = _price_near_level(price, level, tolerance)
    return StructureDetectionResult(
        "LEVEL_INTERACTION",
        detected,
        {"price": price, "level": level, "tolerance": tolerance},
    )


def detect_zone_interaction(
    price: float, zone: tuple[float, float]
) -> StructureDetectionResult:
    upper, lower = zone
    detected = lower <= price <= upper if upper >= lower else upper <= price <= lower
    return StructureDetectionResult(
        "ZONE_INTERACTION",
        detected,
        {"price": price, "upper": upper, "lower": lower},
    )


def detect_compression_structure(candles: Sequence[Candle]) -> bool:
    return range_contraction(candles).detected


def _linear_slope(values: Sequence[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    x_vals = list(range(n))
    sum_x = sum(x_vals)
    sum_y = sum(values)
    sum_xy = sum(x * y for x, y in zip(x_vals, values))
    sum_xx = sum(x * x for x in x_vals)
    denom = n * sum_xx - sum_x * sum_x
    if denom == 0:
        return 0.0
    return (n * sum_xy - sum_x * sum_y) / denom


def detect_channel_structure(candles: Sequence[Candle]) -> bool:
    if len(candles) < 4:
        return False
    highs = [candle.high for candle in candles]
    lows = [candle.low for candle in candles]
    slope_high = _linear_slope(highs)
    slope_low = _linear_slope(lows)
    if slope_high == 0 or slope_low == 0:
        return False
    same_sign = slope_high * slope_low > 0
    slope_ratio = abs(slope_high - slope_low) / max(abs(slope_high), abs(slope_low))
    return same_sign and slope_ratio <= 0.35


def detect_wedge_structure(candles: Sequence[Candle]) -> bool:
    if len(candles) < 4:
        return False
    highs = [candle.high for candle in candles]
    lows = [candle.low for candle in candles]
    slope_high = _linear_slope(highs)
    slope_low = _linear_slope(lows)
    ranges = [candle.high - candle.low for candle in candles]
    return slope_high * slope_low > 0 and ranges[-1] < ranges[0]


def detect_vwap_structure(candles: Sequence[Candle], vwap: float | None) -> StructureDetectionResult:
    if not candles or vwap is None:
        return StructureDetectionResult("VWAP_STRUCTURE", False, {})
    last = candles[-1]
    above = last.close > vwap
    return StructureDetectionResult(
        "VWAP_STRUCTURE",
        True,
        {"vwap": vwap, "close": last.close, "above": 1.0 if above else 0.0},
    )


def _detect_gap_and_go(context: SetupContext) -> DetectionResult:
    gap_dir = _gap_direction(context)
    bullish = _trend_up(context.candles[-3:]) if len(context.candles) >= 3 else False
    detected = context.flags.get("gap_and_go", False) or (gap_dir == "up" and bullish)
    return DetectionResult("SF_GAP_AND_GO", detected, 0.7 if detected else 0.0)


def _detect_gap_fill(context: SetupContext) -> DetectionResult:
    gap_dir = _gap_direction(context)
    prior_close = context.levels.get("LVL_PRIOR_DAY_CLOSE")
    last = context.last_candle()
    tolerance = context.indicators.get("gap_fill_tolerance", 0.005)
    filled = (
        last is not None
        and prior_close is not None
        and _price_near_level(last.close, prior_close, tolerance)
    )
    detected = context.flags.get("gap_fill", False) or (gap_dir is not None and filled)
    return DetectionResult("SF_GAP_FILL", detected, 0.65 if detected else 0.0)


def _detect_gap_continuation(context: SetupContext) -> DetectionResult:
    gap_dir = _gap_direction(context)
    last = context.last_candle()
    first = context.candles[0] if context.candles else None
    detected = False
    if gap_dir == "up" and last and first:
        detected = last.close > first.close
    elif gap_dir == "down" and last and first:
        detected = last.close < first.close
    detected = detected or context.flags.get("gap_continuation", False)
    return DetectionResult("SF_GAP_CONTINUATION", detected, 0.6 if detected else 0.0)


def _detect_failed_gap_reversal(context: SetupContext) -> DetectionResult:
    gap_dir = _gap_direction(context)
    prior_close = context.levels.get("LVL_PRIOR_DAY_CLOSE")
    last = context.last_candle()
    detected = False
    if gap_dir == "up" and last and prior_close is not None:
        detected = last.close < prior_close
    elif gap_dir == "down" and last and prior_close is not None:
        detected = last.close > prior_close
    detected = detected or context.flags.get("failed_gap_reversal", False)
    return DetectionResult("SF_FAILED_GAP_REVERSAL", detected, 0.6 if detected else 0.0)


def _detect_opening_range_breakout(context: SetupContext) -> DetectionResult:
    high, _ = _opening_range(context)
    last = context.last_candle()
    detected = bool(last and high is not None and last.close > high)
    detected = detected or context.flags.get("opening_range_breakout", False)
    return DetectionResult("SF_OPENING_RANGE_BREAKOUT", detected, 0.65 if detected else 0.0)


def _detect_opening_range_breakdown(context: SetupContext) -> DetectionResult:
    _, low = _opening_range(context)
    last = context.last_candle()
    detected = bool(last and low is not None and last.close < low)
    detected = detected or context.flags.get("opening_range_breakdown", False)
    return DetectionResult("SF_OPENING_RANGE_BREAKDOWN", detected, 0.65 if detected else 0.0)


def _detect_opening_range_fakeout(context: SetupContext) -> DetectionResult:
    high, low = _opening_range(context)
    last = context.last_candle()
    previous = context.prior_candle()
    detected = False
    if high is not None and low is not None and last and previous:
        broke_high = previous.high > high and last.close <= high
        broke_low = previous.low < low and last.close >= low
        detected = broke_high or broke_low
    detected = detected or context.flags.get("opening_range_fakeout", False)
    return DetectionResult("SF_OPENING_RANGE_FAKEOUT", detected, 0.6 if detected else 0.0)


def _detect_premarket_high_break(context: SetupContext) -> DetectionResult:
    premarket_high = context.levels.get("LVL_PREMARKET_HIGH")
    last = context.last_candle()
    detected = bool(last and premarket_high is not None and last.close > premarket_high)
    detected = detected or context.flags.get("premarket_high_break", False)
    return DetectionResult("SF_PREMARKET_HIGH_BREAK", detected, 0.55 if detected else 0.0)


def _detect_premarket_low_break(context: SetupContext) -> DetectionResult:
    premarket_low = context.levels.get("LVL_PREMARKET_LOW")
    last = context.last_candle()
    detected = bool(last and premarket_low is not None and last.close < premarket_low)
    detected = detected or context.flags.get("premarket_low_break", False)
    return DetectionResult("SF_PREMARKET_LOW_BREAK", detected, 0.55 if detected else 0.0)


def _detect_first_pullback(context: SetupContext) -> DetectionResult:
    candles = list(context.candles)
    if len(candles) < 5:
        return DetectionResult("SF_FIRST_PULLBACK", False, 0.0)

    breakout_level_candidates = [
        context.levels.get("LVL_PREMARKET_HIGH"),
        context.levels.get("LVL_HIGH_OF_DAY"),
    ]
    breakout_level = next((float(level) for level in breakout_level_candidates if level is not None), None)
    if breakout_level is None:
        return DetectionResult("SF_FIRST_PULLBACK", False, 0.0)

    impulse_idx = None
    for idx in range(1, len(candles) - 2):
        prior = candles[idx - 1]
        current = candles[idx]
        broke_level = prior.close <= breakout_level < current.close
        strong_up = current.close > current.open and current.close >= prior.close
        if broke_level and strong_up:
            impulse_idx = idx

    if impulse_idx is None:
        return DetectionResult("SF_FIRST_PULLBACK", False, 0.0)

    impulse_candle = candles[impulse_idx]
    trigger_candle = candles[-1]
    pullback_candles = candles[impulse_idx + 1 : -1]
    if not (2 <= len(pullback_candles) <= 5):
        return DetectionResult("SF_FIRST_PULLBACK", False, 0.0)

    pullback_lows = [candle.low for candle in pullback_candles]
    pullback_high = max(candle.high for candle in pullback_candles)
    pullback_low = min(pullback_lows)
    pullback_is_retracing = (
        min(candle.close for candle in pullback_candles) < impulse_candle.close
        and any(candle.is_bearish for candle in pullback_candles)
        and all(candle.high <= impulse_candle.high for candle in pullback_candles)
    )
    holds_breakout = all(candle.low > breakout_level for candle in pullback_candles)
    higher_low_formed = pullback_lows[-1] > pullback_lows[0]
    trigger_fired = trigger_candle.high > pullback_high and trigger_candle.close > pullback_high

    detected = bool(
        context.flags.get("first_pullback", False)
        or (pullback_is_retracing and holds_breakout and higher_low_formed and trigger_fired)
    )
    pullback_depth_pct = ((pullback_high - pullback_low) / pullback_high * 100.0) if pullback_high else 0.0
    print(
        "[PATTERN] FIRST_PULLBACK "
        f"detected={detected} breakout_level={breakout_level:.4f} pullback_high={pullback_high:.4f}"
    )
    return DetectionResult(
        "SF_FIRST_PULLBACK",
        detected,
        0.68 if detected else 0.0,
        evidence={
            "breakout_level": breakout_level,
            "pullback_high": pullback_high,
            "pullback_depth_pct": pullback_depth_pct,
        },
    )


def _detect_second_pullback(context: SetupContext) -> DetectionResult:
    if len(context.candles) < 5:
        return DetectionResult("SF_SECOND_PULLBACK", False, 0.0)
    trend = _trend_up(context.candles[:-2])
    last_two = context.candles[-2:]
    pullbacks = all(candle.is_bearish for candle in last_two)
    detected = context.flags.get("second_pullback", False) or (trend and pullbacks)
    return DetectionResult("SF_SECOND_PULLBACK", detected, 0.55 if detected else 0.0)


def _detect_micro_pullback(context: SetupContext) -> DetectionResult:
    if len(context.candles) < 2:
        return DetectionResult("SF_MICRO_PULLBACK", False, 0.0)
    last, prev = context.candles[-1], context.candles[-2]
    inside = last.high <= prev.high and last.low >= prev.low
    detected = context.flags.get("micro_pullback", False) or inside
    return DetectionResult("SF_MICRO_PULLBACK", detected, 0.55 if detected else 0.0)


def _detect_bull_flag(context: SetupContext) -> DetectionResult:
    if len(context.candles) < 5:
        return DetectionResult("SF_BULL_FLAG", False, 0.0)
    trend = _trend_up(context.candles[:3])
    compression = detect_compression_structure(context.candles[-3:])
    detected = context.flags.get("bull_flag", False) or (trend and compression)
    return DetectionResult("SF_BULL_FLAG", detected, 0.6 if detected else 0.0)


def _detect_tight_flag(context: SetupContext) -> DetectionResult:
    if len(context.candles) < 5:
        return DetectionResult("SF_TIGHT_FLAG", False, 0.0)
    avg = _avg_range(context)
    tight = avg and all(candle.range <= avg * 0.8 for candle in context.candles[-3:])
    detected = context.flags.get("tight_flag", False) or bool(tight)
    return DetectionResult("SF_TIGHT_FLAG", detected, 0.55 if detected else 0.0)


def _detect_flat_top_breakout(context: SetupContext) -> DetectionResult:
    level = context.indicators.get("flat_top_level")
    last = context.last_candle()
    detected = bool(level and last and last.close > level)
    detected = detected or context.flags.get("flat_top_breakout", False)
    return DetectionResult("SF_FLAT_TOP_BREAKOUT", detected, 0.6 if detected else 0.0)


def _detect_ascending_triangle(context: SetupContext) -> DetectionResult:
    if len(context.candles) < 4:
        return DetectionResult("SF_ASCENDING_TRIANGLE", False, 0.0)
    highs = [candle.high for candle in context.candles[-4:]]
    lows = [candle.low for candle in context.candles[-4:]]
    flat_top = max(highs) - min(highs) <= _avg_range(context) * 0.3
    rising_lows = _trend_up_values(lows)
    detected = context.flags.get("ascending_triangle", False) or (flat_top and rising_lows)
    return DetectionResult("SF_ASCENDING_TRIANGLE", detected, 0.55 if detected else 0.0)


def _detect_momentum_staircase(context: SetupContext) -> DetectionResult:
    if len(context.candles) < 4:
        return DetectionResult("SF_MOMENTUM_STAIRCASE", False, 0.0)
    higher_highs = all(
        context.candles[i].high >= context.candles[i - 1].high
        for i in range(1, len(context.candles))
    )
    higher_lows = all(
        context.candles[i].low >= context.candles[i - 1].low
        for i in range(1, len(context.candles))
    )
    detected = context.flags.get("momentum_staircase", False) or (
        higher_highs and higher_lows
    )
    return DetectionResult("SF_MOMENTUM_STAIRCASE", detected, 0.6 if detected else 0.0)


def _detect_parabolic_continuation(context: SetupContext) -> DetectionResult:
    if len(context.candles) < 3:
        return DetectionResult("SF_PARABOLIC_CONTINUATION", False, 0.0)
    avg = _avg_range(context)
    expanding = avg and all(candle.range >= avg for candle in context.candles[-3:])
    detected = context.flags.get("parabolic_continuation", False) or bool(expanding)
    return DetectionResult("SF_PARABOLIC_CONTINUATION", detected, 0.6 if detected else 0.0)


def _detect_key_level_break(context: SetupContext) -> DetectionResult:
    key_level = context.indicators.get("key_level")
    last = context.last_candle()
    detected = bool(key_level and last and last.close > key_level)
    detected = detected or context.flags.get("key_level_break", False)
    return DetectionResult("SF_KEY_LEVEL_BREAK", detected, 0.55 if detected else 0.0)


def _detect_key_level_reclaim(context: SetupContext) -> DetectionResult:
    key_level = context.indicators.get("key_level")
    last = context.last_candle()
    prev = context.prior_candle()
    detected = bool(key_level and last and prev and prev.close < key_level < last.close)
    detected = detected or context.flags.get("key_level_reclaim", False)
    return DetectionResult("SF_KEY_LEVEL_RECLAIM", detected, 0.55 if detected else 0.0)


def _detect_high_of_day_break(context: SetupContext) -> DetectionResult:
    hod = context.levels.get("LVL_HIGH_OF_DAY")
    last = context.last_candle()
    detected = bool(last and hod is not None and last.close >= hod)
    detected = detected or context.flags.get("high_of_day_break", False)
    return DetectionResult("SF_HIGH_OF_DAY_BREAK", detected, 0.55 if detected else 0.0)


def _detect_low_of_day_break(context: SetupContext) -> DetectionResult:
    lod = context.levels.get("LVL_LOW_OF_DAY")
    last = context.last_candle()
    detected = bool(last and lod is not None and last.close <= lod)
    detected = detected or context.flags.get("low_of_day_break", False)
    return DetectionResult("SF_LOW_OF_DAY_BREAK", detected, 0.55 if detected else 0.0)


def _detect_prior_day_high_break(context: SetupContext) -> DetectionResult:
    level = context.levels.get("LVL_PRIOR_DAY_HIGH")
    last = context.last_candle()
    detected = bool(last and level is not None and last.close > level)
    detected = detected or context.flags.get("prior_day_high_break", False)
    return DetectionResult("SF_PRIOR_DAY_HIGH_BREAK", detected, 0.55 if detected else 0.0)


def _detect_prior_day_low_break(context: SetupContext) -> DetectionResult:
    level = context.levels.get("LVL_PRIOR_DAY_LOW")
    last = context.last_candle()
    detected = bool(last and level is not None and last.close < level)
    detected = detected or context.flags.get("prior_day_low_break", False)
    return DetectionResult("SF_PRIOR_DAY_LOW_BREAK", detected, 0.55 if detected else 0.0)


def _detect_prior_day_close_reclaim(context: SetupContext) -> DetectionResult:
    level = context.levels.get("LVL_PRIOR_DAY_CLOSE")
    last = context.last_candle()
    prev = context.prior_candle()
    detected = bool(level and last and prev and prev.close < level < last.close)
    detected = detected or context.flags.get("prior_day_close_reclaim", False)
    return DetectionResult("SF_PRIOR_DAY_CLOSE_RECLAIM", detected, 0.55 if detected else 0.0)


def _detect_weekly_level_interaction(context: SetupContext) -> DetectionResult:
    level_high = context.levels.get("LVL_WEEKLY_HIGH")
    level_low = context.levels.get("LVL_WEEKLY_LOW")
    last = context.last_candle()
    tolerance = context.indicators.get("weekly_tolerance", 0.005)
    detected = False
    if last and level_high:
        detected = detected or _price_near_level(last.close, level_high, tolerance)
    if last and level_low:
        detected = detected or _price_near_level(last.close, level_low, tolerance)
    detected = detected or context.flags.get("weekly_level_interaction", False)
    return DetectionResult("SF_WEEKLY_LEVEL_INTERACTION", detected, 0.5 if detected else 0.0)


def _detect_vwap_trend_day(context: SetupContext) -> DetectionResult:
    vwap = context.indicators.get("vwap")
    if vwap is None or len(context.candles) < 3:
        return DetectionResult("SF_VWAP_TREND_DAY", False, 0.0)
    closes = [candle.close for candle in context.candles[-3:]]
    detected = all(close >= vwap for close in closes)
    detected = detected or context.flags.get("vwap_trend_day", False)
    return DetectionResult("SF_VWAP_TREND_DAY", detected, 0.6 if detected else 0.0)


def _detect_vwap_reclaim(context: SetupContext) -> DetectionResult:
    vwap = context.indicators.get("vwap")
    last = context.last_candle()
    prev = context.prior_candle()
    detected = bool(vwap and last and prev and prev.close < vwap < last.close)
    detected = detected or context.flags.get("vwap_reclaim", False)
    return DetectionResult("SF_VWAP_RECLAIM", detected, 0.6 if detected else 0.0)


def _detect_vwap_fade(context: SetupContext) -> DetectionResult:
    vwap = context.indicators.get("vwap")
    last = context.last_candle()
    extension = context.indicators.get("vwap_extension", 0.01)
    detected = bool(
        vwap
        and last
        and (last.close - vwap) / vwap >= extension
        and last.is_bearish
    )
    detected = detected or context.flags.get("vwap_fade", False)
    return DetectionResult("SF_VWAP_FADE", detected, 0.55 if detected else 0.0)


def _detect_mean_reversion_extension(context: SetupContext) -> DetectionResult:
    mean = context.indicators.get("mean_price")
    extension = context.indicators.get("mean_extension", 0.02)
    last = context.last_candle()
    detected = bool(mean and last and abs(last.close - mean) / mean >= extension)
    detected = detected or context.flags.get("mean_reversion_extension", False)
    return DetectionResult("SF_MEAN_REVERSION_EXTENSION", detected, 0.55 if detected else 0.0)


def _detect_mean_reversion_bounce(context: SetupContext) -> DetectionResult:
    mean = context.indicators.get("mean_price")
    last = context.last_candle()
    prev = context.prior_candle()
    detected = bool(mean and last and prev and prev.close < mean < last.close)
    detected = detected or context.flags.get("mean_reversion_bounce", False)
    return DetectionResult("SF_MEAN_REVERSION_BOUNCE", detected, 0.55 if detected else 0.0)


def _detect_mean_reversion_failure(context: SetupContext) -> DetectionResult:
    mean = context.indicators.get("mean_price")
    last = context.last_candle()
    prev = context.prior_candle()
    detected = bool(mean and last and prev and prev.close > mean > last.close)
    detected = detected or context.flags.get("mean_reversion_failure", False)
    return DetectionResult("SF_MEAN_REVERSION_FAILURE", detected, 0.55 if detected else 0.0)


def _detect_abcd_continuation(context: SetupContext) -> DetectionResult:
    if len(context.candles) < 4:
        return DetectionResult("SF_ABCD_CONTINUATION", False, 0.0)
    closes = [candle.close for candle in context.candles[-4:]]
    leg1 = closes[1] - closes[0]
    leg2 = closes[3] - closes[2]
    detected = leg1 > 0 and leg2 > 0 and abs(leg1 - leg2) / max(abs(leg1), 1e-6) < 0.3
    detected = detected or context.flags.get("abcd_continuation", False)
    return DetectionResult("SF_ABCD_CONTINUATION", detected, 0.55 if detected else 0.0)


def _detect_abcd_reversal(context: SetupContext) -> DetectionResult:
    if len(context.candles) < 4:
        return DetectionResult("SF_ABCD_REVERSAL", False, 0.0)
    closes = [candle.close for candle in context.candles[-4:]]
    leg1 = closes[1] - closes[0]
    leg2 = closes[3] - closes[2]
    detected = leg1 < 0 and leg2 > 0
    detected = detected or context.flags.get("abcd_reversal", False)
    return DetectionResult("SF_ABCD_REVERSAL", detected, 0.5 if detected else 0.0)


def _detect_cup_and_handle(context: SetupContext) -> DetectionResult:
    if len(context.candles) < 5:
        return DetectionResult("SF_CUP_AND_HANDLE_INTRADAY", False, 0.0)
    closes = [candle.close for candle in context.candles[-5:]]
    mid_low = min(closes[1:4])
    detected = closes[-1] >= closes[0] and mid_low == min(closes)
    detected = detected or context.flags.get("cup_and_handle", False)
    return DetectionResult("SF_CUP_AND_HANDLE_INTRADAY", detected, 0.55 if detected else 0.0)


def _detect_head_and_shoulders(context: SetupContext) -> DetectionResult:
    if len(context.candles) < 5:
        return DetectionResult("SF_HEAD_AND_SHOULDERS", False, 0.0)
    highs = [candle.high for candle in context.candles[-5:]]
    detected = highs[2] == max(highs) and highs[0] < highs[2] and highs[4] < highs[2]
    detected = detected or context.flags.get("head_and_shoulders", False)
    return DetectionResult("SF_HEAD_AND_SHOULDERS", detected, 0.55 if detected else 0.0)


def _detect_inverse_head_and_shoulders(context: SetupContext) -> DetectionResult:
    if len(context.candles) < 5:
        return DetectionResult("SF_INVERSE_HEAD_AND_SHOULDERS", False, 0.0)
    lows = [candle.low for candle in context.candles[-5:]]
    detected = lows[2] == min(lows) and lows[0] > lows[2] and lows[4] > lows[2]
    detected = detected or context.flags.get("inverse_head_and_shoulders", False)
    return DetectionResult("SF_INVERSE_HEAD_AND_SHOULDERS", detected, 0.55 if detected else 0.0)


def _detect_rounded_bottom(context: SetupContext) -> DetectionResult:
    if len(context.candles) < 5:
        return DetectionResult("SF_ROUNDED_BOTTOM", False, 0.0)
    closes = [candle.close for candle in context.candles[-5:]]
    detected = closes[2] == min(closes) and closes[0] > closes[2] < closes[-1]
    detected = detected or context.flags.get("rounded_bottom", False)
    return DetectionResult("SF_ROUNDED_BOTTOM", detected, 0.5 if detected else 0.0)


def _detect_rounded_top(context: SetupContext) -> DetectionResult:
    if len(context.candles) < 5:
        return DetectionResult("SF_ROUNDED_TOP", False, 0.0)
    closes = [candle.close for candle in context.candles[-5:]]
    detected = closes[2] == max(closes) and closes[0] < closes[2] > closes[-1]
    detected = detected or context.flags.get("rounded_top", False)
    return DetectionResult("SF_ROUNDED_TOP", detected, 0.5 if detected else 0.0)


def _detect_box_range(context: SetupContext) -> DetectionResult:
    detected = detect_range_structure(context.candles)
    detected = detected or context.flags.get("box_range", False)
    return DetectionResult("SF_BOX_RANGE", detected, 0.55 if detected else 0.0)


def _detect_range_expansion(context: SetupContext) -> DetectionResult:
    avg = _avg_range(context)
    last = context.last_candle()
    detected = bool(last and avg and range_expansion(last, avg, 1.5).detected)
    detected = detected or context.flags.get("range_expansion", False)
    return DetectionResult("SF_RANGE_EXPANSION", detected, 0.6 if detected else 0.0)


def _detect_range_failure(context: SetupContext) -> DetectionResult:
    detected = breakout_failure(context.candles).detected
    detected = detected or context.flags.get("range_failure", False)
    return DetectionResult("SF_RANGE_FAILURE", detected, 0.55 if detected else 0.0)


def _detect_volatility_squeeze(context: SetupContext) -> DetectionResult:
    detected = detect_compression_structure(context.candles)
    detected = detected or context.flags.get("volatility_squeeze", False)
    return DetectionResult("SF_VOLATILITY_SQUEEZE", detected, 0.55 if detected else 0.0)


def _detect_compression_coil(context: SetupContext) -> DetectionResult:
    detected = detect_compression_structure(context.candles) and detect_range_structure(
        context.candles, 1.0
    )
    detected = detected or context.flags.get("compression_coil", False)
    return DetectionResult("SF_COMPRESSION_COIL", detected, 0.5 if detected else 0.0)


def _detect_inside_day(context: SetupContext) -> DetectionResult:
    if len(context.candles) < 2:
        return DetectionResult("SF_INSIDE_DAY", False, 0.0)
    last, prev = context.candles[-1], context.candles[-2]
    detected = last.high <= prev.high and last.low >= prev.low
    detected = detected or context.flags.get("inside_day", False)
    return DetectionResult("SF_INSIDE_DAY", detected, 0.5 if detected else 0.0)


def _detect_outside_day(context: SetupContext) -> DetectionResult:
    if len(context.candles) < 2:
        return DetectionResult("SF_OUTSIDE_DAY", False, 0.0)
    last, prev = context.candles[-1], context.candles[-2]
    detected = last.high >= prev.high and last.low <= prev.low
    detected = detected or context.flags.get("outside_day", False)
    return DetectionResult("SF_OUTSIDE_DAY", detected, 0.5 if detected else 0.0)


def _detect_failed_breakout(context: SetupContext) -> DetectionResult:
    detected = breakout_failure(context.candles).detected
    detected = detected or context.flags.get("failed_breakout", False)
    return DetectionResult("SF_FAILED_BREAKOUT", detected, 0.55 if detected else 0.0)


def _detect_failed_breakdown(context: SetupContext) -> DetectionResult:
    if len(context.candles) < 2:
        return DetectionResult("SF_FAILED_BREAKDOWN", False, 0.0)
    probe, failure = context.candles[-2], context.candles[-1]
    detected = probe.low < failure.low and failure.close > probe.close
    detected = detected or context.flags.get("failed_breakdown", False)
    return DetectionResult("SF_FAILED_BREAKDOWN", detected, 0.55 if detected else 0.0)


def _detect_bull_trap(context: SetupContext) -> DetectionResult:
    level = context.indicators.get("trap_level")
    last = context.last_candle()
    prev = context.prior_candle()
    detected = bool(level and last and prev and prev.high > level > last.close)
    detected = detected or context.flags.get("bull_trap", False)
    return DetectionResult("SF_BULL_TRAP", detected, 0.5 if detected else 0.0)


def _detect_bear_trap(context: SetupContext) -> DetectionResult:
    level = context.indicators.get("trap_level")
    last = context.last_candle()
    prev = context.prior_candle()
    detected = bool(level and last and prev and prev.low < level < last.close)
    detected = detected or context.flags.get("bear_trap", False)
    return DetectionResult("SF_BEAR_TRAP", detected, 0.5 if detected else 0.0)


def _detect_liquidity_sweep(context: SetupContext) -> DetectionResult:
    level = context.indicators.get("liquidity_level")
    last = context.last_candle()
    detected = False
    if level and last:
        detected = last.high > level and last.close < level
    detected = detected or context.flags.get("liquidity_sweep", False)
    return DetectionResult("SF_LIQUIDITY_SWEEP", detected, 0.55 if detected else 0.0)


def _detect_stop_run_reversal(context: SetupContext) -> DetectionResult:
    last = context.last_candle()
    avg = _avg_range(context)
    detected = bool(last and avg and last.range >= avg * 1.5 and last.upper_wick > last.body)
    detected = detected or context.flags.get("stop_run_reversal", False)
    return DetectionResult("SF_STOP_RUN_REVERSAL", detected, 0.55 if detected else 0.0)


def _detect_halt_resume(context: SetupContext) -> DetectionResult:
    detected = context.flags.get("halt_resume", False)
    return DetectionResult("SF_HALT_RESUME", detected, 0.7 if detected else 0.0)


def _detect_news_spike(context: SetupContext) -> DetectionResult:
    detected = context.flags.get("news_spike", False)
    return DetectionResult("SF_NEWS_SPIKE", detected, 0.7 if detected else 0.0)


def _detect_earnings_reaction(context: SetupContext) -> DetectionResult:
    detected = context.flags.get("earnings_reaction", False)
    return DetectionResult("SF_EARNINGS_REACTION", detected, 0.7 if detected else 0.0)


def _detect_event_continuation(context: SetupContext) -> DetectionResult:
    detected = context.flags.get("event_continuation", False)
    return DetectionResult("SF_EVENT_CONTINUATION", detected, 0.7 if detected else 0.0)


def _detect_event_reversal(context: SetupContext) -> DetectionResult:
    detected = context.flags.get("event_reversal", False)
    return DetectionResult("SF_EVENT_REVERSAL", detected, 0.7 if detected else 0.0)


def _detect_opening_drive(context: SetupContext) -> DetectionResult:
    detected = context.flags.get("opening_drive", False)
    if not detected and len(context.candles) >= 3:
        detected = _trend_up(context.candles[:3]) and range_expansion(
            context.candles[-1], _avg_range(context), 1.3
        ).detected
    return DetectionResult("SF_OPENING_DRIVE", detected, 0.6 if detected else 0.0)


def _detect_midday_compression(context: SetupContext) -> DetectionResult:
    detected = context.flags.get("midday_compression", False) or detect_compression_structure(
        context.candles[-3:]
    )
    return DetectionResult("SF_MIDDAY_COMPRESSION", detected, 0.5 if detected else 0.0)


def _detect_power_hour_expansion(context: SetupContext) -> DetectionResult:
    detected = context.flags.get("power_hour_expansion", False)
    if not detected:
        detected = _detect_range_expansion(context).detected
    return DetectionResult("SF_POWER_HOUR_EXPANSION", detected, 0.55 if detected else 0.0)


def _detect_late_day_breakdown(context: SetupContext) -> DetectionResult:
    detected = context.flags.get("late_day_breakdown", False)
    if not detected and len(context.candles) >= 2:
        detected = _trend_down(context.candles[-2:])
    return DetectionResult("SF_LATE_DAY_BREAKDOWN", detected, 0.5 if detected else 0.0)


def _detect_end_of_day_reversion(context: SetupContext) -> DetectionResult:
    detected = context.flags.get("end_of_day_reversion", False)
    mean = context.indicators.get("mean_price")
    last = context.last_candle()
    if not detected and mean and last:
        detected = _price_near_level(last.close, mean, 0.003)
    return DetectionResult("SF_END_OF_DAY_REVERSION", detected, 0.5 if detected else 0.0)


def _detect_relative_strength_leader(context: SetupContext) -> DetectionResult:
    strength = context.indicators.get("relative_strength")
    detected = bool(strength and strength >= 1.0)
    detected = detected or context.flags.get("relative_strength_leader", False)
    return DetectionResult("SF_RELATIVE_STRENGTH_LEADER", detected, 0.6 if detected else 0.0)


def _detect_relative_weakness_leader(context: SetupContext) -> DetectionResult:
    strength = context.indicators.get("relative_strength")
    weakness = context.indicators.get("relative_weakness")
    detected = bool((strength is not None and strength <= -1.0) or (weakness and weakness >= 1.0))
    detected = detected or context.flags.get("relative_weakness_leader", False)
    return DetectionResult("SF_RELATIVE_WEAKNESS_LEADER", detected, 0.6 if detected else 0.0)


def _detect_pair_divergence(context: SetupContext) -> DetectionResult:
    divergence = context.indicators.get("pair_divergence")
    detected = bool(divergence and abs(divergence) >= 1.0)
    detected = detected or context.flags.get("pair_divergence", False)
    return DetectionResult("SF_PAIR_DIVERGENCE", detected, 0.55 if detected else 0.0)


def _detect_spread_expansion(context: SetupContext) -> DetectionResult:
    spread = context.indicators.get("spread_change")
    detected = bool(spread and abs(spread) >= 1.0)
    detected = detected or context.flags.get("spread_expansion", False)
    return DetectionResult("SF_SPREAD_EXPANSION", detected, 0.5 if detected else 0.0)


def _detect_spread_reversion(context: SetupContext) -> DetectionResult:
    reversion = context.indicators.get("spread_reversion")
    detected = bool(reversion)
    detected = detected or context.flags.get("spread_reversion", False)
    return DetectionResult("SF_SPREAD_REVERSION", detected, 0.5 if detected else 0.0)


def _detect_zscore_extreme(context: SetupContext) -> DetectionResult:
    zscore = context.indicators.get("zscore")
    detected = bool(zscore and abs(zscore) >= 2.0)
    detected = detected or context.flags.get("zscore_extreme", False)
    return DetectionResult("SF_ZSCORE_EXTREME", detected, 0.5 if detected else 0.0)


def _detect_volatility_expansion(context: SetupContext) -> DetectionResult:
    regime = context.indicators.get("volatility_state")
    detected = regime == "expansion" or _detect_range_expansion(context).detected
    detected = detected or context.flags.get("volatility_expansion", False)
    return DetectionResult("SF_VOLATILITY_EXPANSION", detected, 0.55 if detected else 0.0)


def _detect_volatility_contraction(context: SetupContext) -> DetectionResult:
    regime = context.indicators.get("volatility_state")
    detected = regime == "contraction" or detect_compression_structure(context.candles)
    detected = detected or context.flags.get("volatility_contraction", False)
    return DetectionResult("SF_VOLATILITY_CONTRACTION", detected, 0.55 if detected else 0.0)


def _detect_high_volatility_regime(context: SetupContext) -> DetectionResult:
    detected = context.indicators.get("volatility_regime") == "high"
    detected = detected or context.flags.get("high_volatility_regime", False)
    return DetectionResult("SF_HIGH_VOLATILITY_REGIME", detected, 0.5 if detected else 0.0)


def _detect_low_volatility_regime(context: SetupContext) -> DetectionResult:
    detected = context.indicators.get("volatility_regime") == "low"
    detected = detected or context.flags.get("low_volatility_regime", False)
    return DetectionResult("SF_LOW_VOLATILITY_REGIME", detected, 0.5 if detected else 0.0)


def _detect_daily_trend_pullback(context: SetupContext) -> DetectionResult:
    detected = context.flags.get("daily_trend_pullback", False)
    if not detected and len(context.candles) >= 3:
        detected = _trend_up(context.candles[:-1]) and context.candles[-1].is_bearish
    return DetectionResult("SF_DAILY_TREND_PULLBACK", detected, 0.55 if detected else 0.0)


def _detect_weekly_base_breakout(context: SetupContext) -> DetectionResult:
    level = context.levels.get("LVL_WEEKLY_HIGH")
    last = context.last_candle()
    detected = bool(level and last and last.close > level)
    detected = detected or context.flags.get("weekly_base_breakout", False)
    return DetectionResult("SF_WEEKLY_BASE_BREAKOUT", detected, 0.55 if detected else 0.0)


def _detect_long_term_accumulation(context: SetupContext) -> DetectionResult:
    detected = context.flags.get("long_term_accumulation", False)
    return DetectionResult("SF_LONG_TERM_ACCUMULATION", detected, 0.6 if detected else 0.0)


def _detect_long_term_distribution(context: SetupContext) -> DetectionResult:
    detected = context.flags.get("long_term_distribution", False)
    return DetectionResult("SF_LONG_TERM_DISTRIBUTION", detected, 0.6 if detected else 0.0)


def _detect_macro_regime_shift(context: SetupContext) -> DetectionResult:
    detected = context.flags.get("macro_regime_shift", False)
    return DetectionResult("SF_MACRO_REGIME_SHIFT", detected, 0.6 if detected else 0.0)


SETUP_DETECTORS: Mapping[str, Callable[[SetupContext], DetectionResult]] = {
    "SF_GAP_AND_GO": _detect_gap_and_go,
    "SF_GAP_FILL": _detect_gap_fill,
    "SF_GAP_CONTINUATION": _detect_gap_continuation,
    "SF_FAILED_GAP_REVERSAL": _detect_failed_gap_reversal,
    "SF_OPENING_RANGE_BREAKOUT": _detect_opening_range_breakout,
    "SF_OPENING_RANGE_BREAKDOWN": _detect_opening_range_breakdown,
    "SF_OPENING_RANGE_FAKEOUT": _detect_opening_range_fakeout,
    "SF_PREMARKET_HIGH_BREAK": _detect_premarket_high_break,
    "SF_PREMARKET_LOW_BREAK": _detect_premarket_low_break,
    "SF_FIRST_PULLBACK": _detect_first_pullback,
    "SF_SECOND_PULLBACK": _detect_second_pullback,
    "SF_MICRO_PULLBACK": _detect_micro_pullback,
    "SF_BULL_FLAG": _detect_bull_flag,
    "SF_TIGHT_FLAG": _detect_tight_flag,
    "SF_FLAT_TOP_BREAKOUT": _detect_flat_top_breakout,
    "SF_ASCENDING_TRIANGLE": _detect_ascending_triangle,
    "SF_MOMENTUM_STAIRCASE": _detect_momentum_staircase,
    "SF_PARABOLIC_CONTINUATION": _detect_parabolic_continuation,
    "SF_KEY_LEVEL_BREAK": _detect_key_level_break,
    "SF_KEY_LEVEL_RECLAIM": _detect_key_level_reclaim,
    "SF_HIGH_OF_DAY_BREAK": _detect_high_of_day_break,
    "SF_LOW_OF_DAY_BREAK": _detect_low_of_day_break,
    "SF_PRIOR_DAY_HIGH_BREAK": _detect_prior_day_high_break,
    "SF_PRIOR_DAY_LOW_BREAK": _detect_prior_day_low_break,
    "SF_PRIOR_DAY_CLOSE_RECLAIM": _detect_prior_day_close_reclaim,
    "SF_WEEKLY_LEVEL_INTERACTION": _detect_weekly_level_interaction,
    "SF_VWAP_TREND_DAY": _detect_vwap_trend_day,
    "SF_VWAP_RECLAIM": _detect_vwap_reclaim,
    "SF_VWAP_FADE": _detect_vwap_fade,
    "SF_MEAN_REVERSION_EXTENSION": _detect_mean_reversion_extension,
    "SF_MEAN_REVERSION_BOUNCE": _detect_mean_reversion_bounce,
    "SF_MEAN_REVERSION_FAILURE": _detect_mean_reversion_failure,
    "SF_ABCD_CONTINUATION": _detect_abcd_continuation,
    "SF_ABCD_REVERSAL": _detect_abcd_reversal,
    "SF_CUP_AND_HANDLE_INTRADAY": _detect_cup_and_handle,
    "SF_HEAD_AND_SHOULDERS": _detect_head_and_shoulders,
    "SF_INVERSE_HEAD_AND_SHOULDERS": _detect_inverse_head_and_shoulders,
    "SF_ROUNDED_BOTTOM": _detect_rounded_bottom,
    "SF_ROUNDED_TOP": _detect_rounded_top,
    "SF_BOX_RANGE": _detect_box_range,
    "SF_RANGE_EXPANSION": _detect_range_expansion,
    "SF_RANGE_FAILURE": _detect_range_failure,
    "SF_VOLATILITY_SQUEEZE": _detect_volatility_squeeze,
    "SF_COMPRESSION_COIL": _detect_compression_coil,
    "SF_INSIDE_DAY": _detect_inside_day,
    "SF_OUTSIDE_DAY": _detect_outside_day,
    "SF_FAILED_BREAKOUT": _detect_failed_breakout,
    "SF_FAILED_BREAKDOWN": _detect_failed_breakdown,
    "SF_BULL_TRAP": _detect_bull_trap,
    "SF_BEAR_TRAP": _detect_bear_trap,
    "SF_LIQUIDITY_SWEEP": _detect_liquidity_sweep,
    "SF_STOP_RUN_REVERSAL": _detect_stop_run_reversal,
    "SF_HALT_RESUME": _detect_halt_resume,
    "SF_NEWS_SPIKE": _detect_news_spike,
    "SF_EARNINGS_REACTION": _detect_earnings_reaction,
    "SF_EVENT_CONTINUATION": _detect_event_continuation,
    "SF_EVENT_REVERSAL": _detect_event_reversal,
    "SF_OPENING_DRIVE": _detect_opening_drive,
    "SF_MIDDAY_COMPRESSION": _detect_midday_compression,
    "SF_POWER_HOUR_EXPANSION": _detect_power_hour_expansion,
    "SF_LATE_DAY_BREAKDOWN": _detect_late_day_breakdown,
    "SF_END_OF_DAY_REVERSION": _detect_end_of_day_reversion,
    "SF_RELATIVE_STRENGTH_LEADER": _detect_relative_strength_leader,
    "SF_RELATIVE_WEAKNESS_LEADER": _detect_relative_weakness_leader,
    "SF_PAIR_DIVERGENCE": _detect_pair_divergence,
    "SF_SPREAD_EXPANSION": _detect_spread_expansion,
    "SF_SPREAD_REVERSION": _detect_spread_reversion,
    "SF_ZSCORE_EXTREME": _detect_zscore_extreme,
    "SF_VOLATILITY_EXPANSION": _detect_volatility_expansion,
    "SF_VOLATILITY_CONTRACTION": _detect_volatility_contraction,
    "SF_HIGH_VOLATILITY_REGIME": _detect_high_volatility_regime,
    "SF_LOW_VOLATILITY_REGIME": _detect_low_volatility_regime,
    "SF_DAILY_TREND_PULLBACK": _detect_daily_trend_pullback,
    "SF_WEEKLY_BASE_BREAKOUT": _detect_weekly_base_breakout,
    "SF_LONG_TERM_ACCUMULATION": _detect_long_term_accumulation,
    "SF_LONG_TERM_DISTRIBUTION": _detect_long_term_distribution,
    "SF_MACRO_REGIME_SHIFT": _detect_macro_regime_shift,
}


def detect_setup_family(setup_family_id: str, context: SetupContext) -> DetectionResult:
    detector = SETUP_DETECTORS.get(setup_family_id)
    if detector is None:
        return DetectionResult(setup_family_id, False, 0.0, {"error": 1.0})
    return detector(context)


def detect_all_setups(context: SetupContext) -> list[DetectionResult]:
    return [detect_setup_family(setup_id, context) for setup_id in SETUP_FAMILIES]
