"""Shared pattern detector registry for canonical reusable detectors."""

from __future__ import annotations

from src.strategies.common.patterns.pattern_flat_top_breakout import detect_flat_top_breakout
from src.strategies.common.patterns.pattern_first_pullback import detect_first_pullback
from src.strategies.common.patterns.pattern_micro_pullback import detect_micro_pullback
from src.strategies.common.patterns.pattern_orb import detect_orb

PATTERN_DETECTORS = {
    "P_ORB": detect_orb,
    "P_FIRST_PULLBACK": detect_first_pullback,
    "P_MICRO_PULLBACK": detect_micro_pullback,
    "P_FLAT_TOP_BREAKOUT": detect_flat_top_breakout,
}

__all__ = [
    "PATTERN_DETECTORS",
    "detect_orb",
    "detect_first_pullback",
    "detect_micro_pullback",
    "detect_flat_top_breakout",
]
