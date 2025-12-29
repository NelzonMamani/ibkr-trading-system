from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    bid: Optional[float]
    ask: Optional[float]
    last: Optional[float]
    asof_utc: datetime
    source: str = "IBKR"
