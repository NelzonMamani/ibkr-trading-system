"""Position query evidence; rows alone never establish broker availability."""
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class BrokerPositionResult:
    rows: tuple[Any, ...] = ()
    status: str = "UNAVAILABLE"
    account: str | None = None
    completed_at: datetime | None = None


class PositionRows(list):
    def __init__(self, rows=(), *, available=False):
        super().__init__(rows)
        self.available = available
