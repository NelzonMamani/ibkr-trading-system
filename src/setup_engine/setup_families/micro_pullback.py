"""Canonical Micro Pullback owner: confirmed continuation and legacy armed-readiness modes."""

from __future__ import annotations

from dataclasses import replace
from statistics import mean
from typing import List

from src.strategies.common.candles.candle_evidence import evidence_tags
from src.strategies.common.candles.multi_candle import detect_engulfing, detect_three_soldiers_crows
from src.strategies.common.candles.single_candle import detect_long_wick
from src.strategies.ross_momentum.patterns.pattern_base import PatternBase
from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult


def _avg_volume(candles: List, lookback: int = 5) -> float:
    if len(candles) < 1:
        return 0.0
    sample = candles[-lookback:] if len(candles) >= lookback else candles
    return mean(candle.volume for candle in sample)


def _safe_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None



class MicroPullbackPattern(PatternBase):
    pattern_id = "P_MICRO_PULLBACK"
    name = "Micro Pullback"
    family = PatternFamily.PULLBACK
    direction_bias = Direction.LONG

    def evaluate(self, inputs: PatternInputs) -> PatternResult:
        candles = inputs.candles
        if len(candles) < 5:
            return self._rejected("insufficient candles", inputs)
        ema9 = inputs.indicators.ema9
        if ema9 is None:
            return self._rejected("missing EMA9", inputs)
        trigger = candles[-1]
        if trigger.close < ema9:
            return self._rejected("price below EMA9", inputs)
        if trigger.close <= trigger.open:
            return self._rejected("no continuation close", inputs)

        pullback: list = []
        cursor = len(candles) - 2
        while cursor >= 0 and len(pullback) < 3:
            candle = candles[cursor]
            if candle.close <= candle.open:
                pullback.insert(0, candle)
                cursor -= 1
                continue
            break
        if not pullback:
            return self._rejected("no 1-3 bar pullback", inputs)
        impulse = candles[max(0, cursor - 2) : cursor + 1]
        if len(impulse) < 2:
            return self._rejected("missing initial impulse", inputs)
        impulse_gain = impulse[-1].close - impulse[0].open
        min_impulse = max(abs(impulse[0].open) * 0.003, 0.05)
        if impulse_gain <= min_impulse:
            return self._rejected("missing initial impulse", inputs)
        impulse_high = max(c.high for c in impulse)
        impulse_low = min(c.low for c in impulse)
        pullback_low = min(c.low for c in pullback)
        depth = (impulse_high - pullback_low) / max(impulse_high - impulse_low, 1e-9)
        if depth > 0.65:
            return self._rejected("pullback too deep", inputs)
        pullback_high = max(c.high for c in pullback)
        if trigger.close <= pullback_high:
            return self._rejected("no continuation close", inputs)

        volume_avg = _avg_volume(candles)
        volume_ok = trigger.volume >= volume_avg
        confidence = 0.65 if volume_ok else 0.55
        tags = ["volume_confirmed" if volume_ok else "volume_soft", "continuation_confirmed"]

        candle_evidence = [
            evidence
            for evidence in [
                detect_long_wick(trigger),
                detect_engulfing(candles),
                detect_three_soldiers_crows(candles),
            ]
            if evidence
        ]
        tags.extend(evidence_tags(candle_evidence))

        rationale = (
            "Impulse, controlled 1-3 bar pullback, and continuation close back through pullback highs.\n"
            f"Impulse gain={impulse_gain:.2f}, pullback depth={depth:.2%}, close={trigger.close:.2f}, EMA9={ema9:.2f}."
        )
        result = self._detected(
            inputs,
            direction=Direction.LONG,
            confidence=confidence,
            rationale=rationale,
            entry_zone="Break of pullback high",
            stop_suggestion="Below pullback low",
            target_suggestion="Prior high / HOD",
            setup_quality_tags=tags,
        )

        return replace(
            result, setup_family_id="MICRO_PULLBACK",
            trigger_level=float(pullback_high), stop_level=float(pullback_low),
            invalidation_level=float(pullback_low),
        )

    def evaluate_readiness(self, inputs: PatternInputs) -> PatternResult:
        """Detect structural readiness for micro pullback continuation after an impulse leg."""

        def reject(reason: str) -> PatternResult:
            print(f"[PATTERN] MICRO_PULLBACK detected=False symbol={inputs.symbol} reason={reason}")
            return PatternResult(
                setup_id="P_MICRO_PULLBACK",
                pattern_name="Micro Pullback",
                pattern_family=PatternFamily.PULLBACK,
                detected=False,
                direction=Direction.LONG,
                confidence=0.0,
                setup_quality_tags=[],
                setup_family_id="MICRO_PULLBACK",
                rationale_text=f"Rejected: {reason}",
                rejection_reason=reason,
                data_quality_flags=list(inputs.data_quality_flags),
                trigger_type="XL_MICRO_PULLBACK",
            )

        candles = list(inputs.candles or [])
        if len(candles) < 5:
            return reject("insufficient_candles")

        impulse_start = candles[-5]
        impulse_end = candles[-3]
        pullback_a = candles[-2]
        pullback_b = candles[-1]

        impulse_low = _safe_float(getattr(impulse_start, "low", None))
        impulse_high = _safe_float(getattr(impulse_end, "high", None))
        impulse_start_close = _safe_float(getattr(impulse_start, "close", None))
        impulse_end_close = _safe_float(getattr(impulse_end, "close", None))
        if None in {impulse_low, impulse_high, impulse_start_close, impulse_end_close}:
            return reject("missing_impulse_prices")

        impulse_range = float(impulse_high - impulse_low)
        if impulse_range <= 0:
            return reject("invalid_impulse_range")

        impulse_gain = float(impulse_end_close - impulse_start_close)
        if impulse_gain <= 0 or impulse_gain < (impulse_range * 0.35):
            return reject("missing_impulse_leg")

        pullback_high = max(
            _safe_float(getattr(pullback_a, "high", None)) or float("-inf"),
            _safe_float(getattr(pullback_b, "high", None)) or float("-inf"),
        )
        pullback_low = min(
            _safe_float(getattr(pullback_a, "low", None)) or float("inf"),
            _safe_float(getattr(pullback_b, "low", None)) or float("inf"),
        )
        if pullback_high in {float("-inf")} or pullback_low in {float("inf")}:
            return reject("missing_pullback_prices")

        shallow_pullback = (impulse_high - pullback_low) <= (impulse_range * 0.45)
        if not shallow_pullback:
            return reject("pullback_too_deep")

        pullback_brief = len(candles[-2:]) <= 2
        if not pullback_brief:
            return reject("pullback_not_brief")

        ema9 = _safe_float(inputs.indicators.ema9)
        continuation_support = ema9 if ema9 is not None else impulse_start_close
        if pullback_low <= float(continuation_support):
            return reject("pullback_lost_continuation_support")

        trigger_level = pullback_high
        stop_level = pullback_low
        if trigger_level <= stop_level:
            return reject("entry_stop_structure_invalid")

        print(
            "[PATTERN] MICRO_PULLBACK detected=True "
            f"symbol={inputs.symbol} trigger={trigger_level:.4f} stop={stop_level:.4f}"
        )
        return PatternResult(
            setup_id="P_MICRO_PULLBACK",
            pattern_name="Micro Pullback",
            pattern_family=PatternFamily.PULLBACK,
            detected=True,
            direction=Direction.LONG,
            confidence=0.66,
            setup_quality_tags=["impulse_leg", "shallow_pullback", "continuation_support_held"],
            setup_family_id="MICRO_PULLBACK",
            rationale_text=(
                "Micro pullback continuation structure detected with intact support and "
                f"defined trigger={trigger_level:.4f} invalidation={stop_level:.4f}."
            ),
            rejection_reason=None,
            data_quality_flags=list(inputs.data_quality_flags),
            trigger_type="XL_MICRO_PULLBACK",
            trigger_level=trigger_level,
            stop_level=stop_level,
            invalidation_level=stop_level,
        )
