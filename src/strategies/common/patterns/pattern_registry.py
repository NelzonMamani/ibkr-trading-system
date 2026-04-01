"""Shared pattern detector registry for canonical reusable detectors."""

from __future__ import annotations

from src.strategies.common.patterns.pattern_flat_top_breakout import detect_flat_top_breakout
from src.strategies.common.patterns.pattern_cup_handle import detect_cup_handle
from src.strategies.common.patterns.pattern_first_pullback import detect_first_pullback
from src.strategies.common.patterns.pattern_micro_pullback import detect_micro_pullback
from src.strategies.common.patterns.pattern_opening_drive import detect_opening_drive
from src.strategies.common.patterns.pattern_orb import detect_orb
from src.strategies.common.patterns.pattern_parabolic_exhaustion import detect_parabolic_exhaustion
from src.strategies.common.patterns.pattern_premarket_high_break import detect_premarket_high_break

PATTERN_DETECTORS = {
    "P_ORB": detect_orb,
    "P_OPENING_DRIVE": detect_opening_drive,
    "P_PREMARKET_HIGH_BREAK": detect_premarket_high_break,
    "P_FIRST_PULLBACK": detect_first_pullback,
    "P_MICRO_PULLBACK": detect_micro_pullback,
    "P_FLAT_TOP_BREAKOUT": detect_flat_top_breakout,
    "P_CUP_HANDLE": detect_cup_handle,
    "P_PARABOLIC_EXHAUSTION": detect_parabolic_exhaustion,
}

__all__ = ["PATTERN_DETECTORS", "detect_orb", "detect_opening_drive", "detect_premarket_high_break", "detect_first_pullback", "detect_micro_pullback", "detect_flat_top_breakout", "detect_cup_handle", "detect_parabolic_exhaustion"]
