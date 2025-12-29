"""
Define authoritative runtime settings for the trading system.

This module is the single source of truth for runtime modes and replay modes.
"""

from __future__ import annotations
import os
from dataclasses import dataclass
from enum import Enum

from config.trading_config import MAX_HOLD_TICKS, MIN_HOLD_TICKS


class RunMode(str, Enum):
    SIM = "SIM"
    PAPER = "PAPER"
    LIVE = "LIVE"


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


class EventReplayMode(str, Enum):
    OFF = "OFF"
    CYCLE = "CYCLE"
    RUN = "RUN"


DEFAULT_EVENT_REPLAY_MODE: EventReplayMode = EventReplayMode.CYCLE


def get_event_replay_mode(run_mode: RunMode) -> EventReplayMode:
    """
    Resolve EVENT_REPLAY_MODE using runtime-safe rules.

    Resolution order:
    1) LIVE always forces OFF
    2) ENV: EVENT_REPLAY_MODE
    3) DEFAULT_EVENT_REPLAY_MODE (CYCLE)
    """

    if run_mode == RunMode.LIVE:
        return EventReplayMode.OFF

    raw = (os.getenv("EVENT_REPLAY_MODE") or "").strip().upper()
    if not raw:
        return DEFAULT_EVENT_REPLAY_MODE

    try:
        return EventReplayMode(raw)
    except ValueError:
        print(
            f"[RUNTIME] Invalid EVENT_REPLAY_MODE='{raw}'. "
            f"Falling back to default {DEFAULT_EVENT_REPLAY_MODE}."
        )
        return DEFAULT_EVENT_REPLAY_MODE


@dataclass
class RuntimeConfig:
    """
    Minimal runtime configuration context for deterministic engine evaluation.

    This container intentionally mirrors the authoritative trading thresholds to
    make pure decision functions testable without importing global constants in
    multiple places.
    """

    min_hold_ticks: int = MIN_HOLD_TICKS
    max_hold_ticks: int = MAX_HOLD_TICKS
