"""Validation helpers for Epoch 5 contracts."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Iterable


def ensure_fields(payload: dict, required: Iterable[str]) -> list[str]:
    missing = [field for field in required if field not in payload]
    return missing


def asdict_safe(value):
    if is_dataclass(value):
        return asdict(value)
    return value
