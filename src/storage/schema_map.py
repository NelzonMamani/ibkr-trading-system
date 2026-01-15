"""Schema mapping helpers for storage records."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


def to_serializable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {key: to_serializable(val) for key, val in value.items()}
    if isinstance(value, list):
        return [to_serializable(item) for item in value]
    return value
