"""Pattern validation stage for Ross Momentum setup families."""

from __future__ import annotations

from dataclasses import dataclass

from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.setup_engine import SetupEvaluation


@dataclass(frozen=True)
class PatternEvaluation:
    pattern_name: str
    detected: bool
    direction: str
    confidence: float
    rationale: str
    rejection_reason: str | None
    reference_highs_lows: dict[str, float]
    pullback_high: float | None
    pullback_low: float | None
    impulse_high: float | None
    impulse_low: float | None
    volume_assessment: str
    structure_assessment: str
    invalidation_ready: bool


class PatternEngine:
    def evaluate(self, setup: SetupEvaluation, pattern_input: PatternInputs) -> PatternEvaluation:
        candles = pattern_input.candles or []
        if not setup.detected:
            return PatternEvaluation(
                pattern_name="NONE",
                detected=False,
                direction="LONG",
                confidence=0.0,
                rationale="Pattern stage skipped because no setup family was active.",
                rejection_reason="NO_SETUP_FAMILY",
                reference_highs_lows={},
                pullback_high=None,
                pullback_low=None,
                impulse_high=None,
                impulse_low=None,
                volume_assessment="UNKNOWN",
                structure_assessment="NO_SETUP",
                invalidation_ready=False,
            )
        if len(candles) < 4:
            return PatternEvaluation(
                pattern_name=f"{setup.setup_family}_PATTERN",
                detected=False,
                direction="LONG",
                confidence=0.0,
                rationale="Insufficient structure for pattern validation.",
                rejection_reason="INSUFFICIENT_STRUCTURE",
                reference_highs_lows={},
                pullback_high=None,
                pullback_low=None,
                impulse_high=None,
                impulse_low=None,
                volume_assessment="UNKNOWN",
                structure_assessment="INSUFFICIENT_CANDLES",
                invalidation_ready=False,
            )

        impulse_leg = candles[:-2]
        pullback_candle = candles[-2]
        trigger_candle = candles[-1]
        impulse_high = max(c.high for c in impulse_leg)
        impulse_low = min(c.low for c in impulse_leg)
        impulse_volume = sum(c.volume for c in impulse_leg) / max(len(impulse_leg), 1)
        pullback_high = pullback_candle.high
        pullback_low = pullback_candle.low
        pullback_volume = pullback_candle.volume

        structure_ok = pullback_low > impulse_low and trigger_candle.low >= pullback_low
        volume_ok = pullback_volume <= impulse_volume * 0.9
        invalidation_ready = pullback_low > 0
        rejection: str | None = None
        detected = structure_ok and invalidation_ready

        if not structure_ok:
            rejection = "STRUCTURE_FAILURE"
        elif not invalidation_ready:
            rejection = "NO_INVALIDATION_ANCHOR"
        elif not volume_ok:
            rejection = "PULLBACK_VOLUME_TOO_HEAVY"
            detected = False

        return PatternEvaluation(
            pattern_name=f"{setup.setup_family}_CONTINUATION",
            detected=detected,
            direction="LONG",
            confidence=0.82 if detected else 0.25,
            rationale="Pattern aligns with setup structure." if detected else "Pattern rejected by Ross structure checks.",
            rejection_reason=rejection,
            reference_highs_lows={
                "impulse_high": impulse_high,
                "impulse_low": impulse_low,
                "pullback_high": pullback_high,
                "pullback_low": pullback_low,
            },
            pullback_high=pullback_high,
            pullback_low=pullback_low,
            impulse_high=impulse_high,
            impulse_low=impulse_low,
            volume_assessment="PULLBACK_LIGHT" if volume_ok else "PULLBACK_HEAVY",
            structure_assessment="VALID" if structure_ok else "FAILED",
            invalidation_ready=invalidation_ready,
        )
