"""
Define the runtime safety mode for the trading system.
Single source of truth for SIM / PAPER / LIVE.
"""

from __future__ import annotations
import os
from enum import Enum


class RunMode(str, Enum):
    SIM = "SIM"
    PAPER = "PAPER"
    LIVE = "LIVE"


# DEFAULT_RUN_MODE: RunMode = RunMode.SIM
DEFAULT_RUN_MODE: RunMode = RunMode.SIM


def get_run_mode() -> RunMode:
    """
    Authoritative runtime mode resolver.

    Resolution order:
    1) ENV: RUN_MODE
    2) DEFAULT_RUN_MODE (SIM)
    """
    raw = (os.getenv("RUN_MODE") or "").strip().upper()
    if not raw:
        return DEFAULT_RUN_MODE

    try:
        return RunMode(raw)
    except ValueError:
        print(f"[RUNTIME] Invalid RUN_MODE='{raw}'. Falling back to SAFE default SIM.")
        return RunMode.SIM
