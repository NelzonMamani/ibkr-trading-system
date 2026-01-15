"""Logging helpers for consistent console banners."""
from __future__ import annotations

from typing import Optional

from src.config.runtime_config import RunMode, get_run_mode
from src.config.system_config import get_current_market_session


_MODE_LABELS = {
    "SIM": "SIM",
    "READONLY": "READONLY",
    "LIVE_1SHARE": "LIVE_1SHARE",
    "LIVE_READ_ONLY": "READONLY",
    "LIVE_MICRO": "LIVE_1SHARE",
    "LIVE": "LIVE",
    "PAPER": "PAPER",
}


def normalize_mode_label(mode: str | RunMode | None) -> str:
    if mode is None:
        resolved = get_run_mode()
        mode_value = resolved.value
    elif isinstance(mode, RunMode):
        mode_value = mode.value
    else:
        mode_value = str(mode).strip().upper()
    return _MODE_LABELS.get(mode_value, mode_value)


def format_mode_banner(mode: str | RunMode | None = None, session: Optional[str] = None) -> str:
    label = normalize_mode_label(mode)
    session_label = session or get_current_market_session()
    return f"MODE={label} SESSION={session_label}"


def print_mode_banner(mode: str | RunMode | None = None, session: Optional[str] = None) -> None:
    print(f"[BOOT] {format_mode_banner(mode=mode, session=session)}")


def print_section(title: str) -> None:
    line = "=" * len(title)
    print(f"\n{line}\n{title}\n{line}")
