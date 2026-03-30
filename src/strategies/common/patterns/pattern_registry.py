"""Shared pattern detector registry for canonical reusable detectors."""

from __future__ import annotations

from src.strategies.common.patterns.pattern_first_pullback import detect_first_pullback
from src.strategies.common.patterns.pattern_orb import detect_orb

PATTERN_DETECTORS = {
    "P_ORB": detect_orb,
    "P_FIRST_PULLBACK": detect_first_pullback,
}

__all__ = ["PATTERN_DETECTORS", "detect_orb", "detect_first_pullback"]
