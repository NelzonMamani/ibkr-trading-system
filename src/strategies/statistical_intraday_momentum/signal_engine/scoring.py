"""Deterministic scoring logic for statistical intraday momentum."""

from __future__ import annotations

from dataclasses import dataclass

from .features import FeatureVector
from ..strategy_policy import SignalSpec


@dataclass(frozen=True)
class ScoreState:
    """Represents the computed score and thresholds for intent mapping."""

    score: float
    entry_threshold: float
    hold_threshold: float
    exit_threshold: float

    def is_entry(self) -> bool:
        return self.score >= self.entry_threshold

    def is_hold(self) -> bool:
        return self.score >= self.hold_threshold

    def is_exit(self) -> bool:
        return self.score <= self.exit_threshold


def compute_score(features: FeatureVector, signal: SignalSpec) -> ScoreState:
    score = (
        (0.4 * features.return_5m)
        + (0.3 * features.return_15m)
        + (0.2 * features.persistence)
        + (0.1 * features.volume_accel)
    )
    return ScoreState(
        score=score,
        entry_threshold=signal.entry_threshold,
        hold_threshold=signal.hold_threshold,
        exit_threshold=signal.exit_threshold,
    )
