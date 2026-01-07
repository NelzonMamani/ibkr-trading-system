"""Signal type definitions for deterministic teaching signals."""

from enum import Enum


class SignalType(str, Enum):
    MOMO_BREAKOUT = "MOMO_BREAKOUT"
    HOD_BREAK = "HOD_BREAK"
    ORB_BREAK = "ORB_BREAK"
    VWAP_RECLAIM = "VWAP_RECLAIM"
    FIRST_PULLBACK_LONG = "FIRST_PULLBACK_LONG"
    WEAKNESS = "WEAKNESS"
