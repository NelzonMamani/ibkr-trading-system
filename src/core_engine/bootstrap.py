"""Bootstrap helpers for Epoch 5."""

from __future__ import annotations

from src.config.config_resolver import get_config
from src.core_engine.state import RunMode


def resolve_mode(value: str | None = None) -> RunMode:
    mode_value = value or str(get_config("RUN_MODE_EFFECTIVE") or "READONLY")
    return RunMode.from_value(mode_value)
