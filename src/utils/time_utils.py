"""Time helpers for deterministic cycle identifiers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class CycleIdGenerator:
    """Deterministic, monotonically increasing cycle id generator."""

    counter: int = 0

    def next_id(self) -> int:
        self.counter += 1
        return self.counter


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
