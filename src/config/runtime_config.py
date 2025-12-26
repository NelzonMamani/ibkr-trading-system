"""
Define the runtime safety mode for the trading system.

Phase 4 — Step 4.1 introduces explicit runtime modes (SIM, PAPER, LIVE) to make
runtime intent obvious and to keep the system safe by default.
"""

from enum import Enum


class RunMode(str, Enum):
    """Enumerate supported runtime modes for the trading system."""

    SIM = "SIM"
    PAPER = "PAPER"
    LIVE = "LIVE"


DEFAULT_RUN_MODE: RunMode = RunMode.SIM


def get_run_mode() -> RunMode:
    """Return the current runtime mode.

    For now, this returns the safe default and does not inspect environment
    variables or command-line arguments.
    """

    return DEFAULT_RUN_MODE
