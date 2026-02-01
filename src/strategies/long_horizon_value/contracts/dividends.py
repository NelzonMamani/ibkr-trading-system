from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class DividendEvent:
    symbol: str
    amount: float
    currency: str
    date: str


@dataclass
class DividendReport:
    events: List[DividendEvent]
    reinvestment_enabled: bool
    notes: List[str]
