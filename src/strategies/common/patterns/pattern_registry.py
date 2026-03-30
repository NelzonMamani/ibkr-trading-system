"""Shared pattern detector registry for canonical reusable detectors."""

from __future__ import annotations

from src.strategies.common.patterns.pattern_orb import detect_orb

PATTERN_DETECTORS = {
    "P_ORB": detect_orb,
}

__all__ = ["PATTERN_DETECTORS", "detect_orb"]
