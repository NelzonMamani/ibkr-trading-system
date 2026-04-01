"""Shared utilities for continuation pullback validations."""

from __future__ import annotations


def compute_pullback_depth(impulse_high: float, pullback_low: float, impulse_range: float) -> float:
    return (impulse_high - pullback_low) / max(impulse_range, 1e-9)


def validate_pullback_depth(depth: float, max_depth: float = 0.65) -> bool:
    return depth < max_depth


def validate_volume_contraction(pullback_volume: float, impulse_volume: float) -> bool:
    return pullback_volume < impulse_volume


def compute_impulse_range(highs: list[float], lows: list[float]) -> float:
    return max(highs) - min(lows)


def is_shallow_pullback(depth: float) -> bool:
    return depth < 0.5


def is_moderate_pullback(depth: float) -> bool:
    return depth < 0.65


def reclaim_confirmed(prev_close: float, last_close: float, level: float) -> bool:
    return prev_close <= level and last_close > level
