"""Trigger evaluation for Ross Momentum profitability layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.pattern_engine import PatternEvaluation


@dataclass(frozen=True)
class TriggerEvaluation:
    trigger_name: str
    triggered: bool
    trigger_level: float | None
    trigger_time: str | None
    rationale: str
    rejection_reason: str | None
    stop_anchor: float | None
    invalidation_level: float | None
    entry_style: str
    post_trigger_warnings: list[str] = field(default_factory=list)


class TriggerEngine:
    """Evaluates first-new-high trigger after pullback."""

    def evaluate(self, pattern: PatternEvaluation, current_candle: Candle) -> TriggerEvaluation:
        if not pattern.detected:
            return TriggerEvaluation(
                trigger_name="FIRST_NEW_HIGH_AFTER_PULLBACK",
                triggered=False,
                trigger_level=pattern.pullback_high,
                trigger_time=None,
                rationale="Trigger gated: pattern was not valid.",
                rejection_reason=pattern.rejection_reason or "PATTERN_NOT_VALID",
                stop_anchor=pattern.pullback_low,
                invalidation_level=pattern.pullback_low,
                entry_style="BREAKOUT",
            )

        pullback_high = pattern.pullback_high
        pullback_low = pattern.pullback_low
        if pullback_high is None or pullback_low is None:
            return TriggerEvaluation(
                trigger_name="FIRST_NEW_HIGH_AFTER_PULLBACK",
                triggered=False,
                trigger_level=pullback_high,
                trigger_time=None,
                rationale="Trigger rejected: missing pullback reference levels.",
                rejection_reason="MISSING_PULLBACK_LEVELS",
                stop_anchor=None,
                invalidation_level=None,
                entry_style="BREAKOUT",
            )

        if current_candle.low < pullback_low:
            return TriggerEvaluation(
                trigger_name="FIRST_NEW_HIGH_AFTER_PULLBACK",
                triggered=False,
                trigger_level=pullback_high,
                trigger_time=None,
                rationale="Trigger invalidated: pullback low broke before breakout.",
                rejection_reason="INVALIDATION_BROKEN",
                stop_anchor=pullback_low,
                invalidation_level=pullback_low,
                entry_style="BREAKOUT",
            )

        fired = current_candle.high > pullback_high
        if not fired:
            return TriggerEvaluation(
                trigger_name="FIRST_NEW_HIGH_AFTER_PULLBACK",
                triggered=False,
                trigger_level=pullback_high,
                trigger_time=None,
                rationale="No fire: current high did not exceed prior pullback high.",
                rejection_reason="HIGH_NOT_ABOVE_PULLBACK_HIGH",
                stop_anchor=pullback_low,
                invalidation_level=pullback_low,
                entry_style="BREAKOUT",
            )

        warnings: list[str] = []
        if current_candle.close <= pullback_high:
            warnings.append("BREAKOUT_NOT_CLOSING_ABOVE_LEVEL")
        return TriggerEvaluation(
            trigger_name="FIRST_NEW_HIGH_AFTER_PULLBACK",
            triggered=True,
            trigger_level=pullback_high,
            trigger_time=(current_candle.timestamp or datetime.now(timezone.utc)).isoformat(),
            rationale="Ross trigger fired: first candle made new high after pullback.",
            rejection_reason=None,
            stop_anchor=pullback_low,
            invalidation_level=pullback_low,
            entry_style="STOP_THROUGH_LEVEL",
            post_trigger_warnings=warnings,
        )
