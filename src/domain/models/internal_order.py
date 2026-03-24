from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class InternalOrder:
    """
    Canonical internal order model for broker translations.

    direction: "LONG", "SHORT", or "SELL" (close-long semantic)
    order_type: "MKT" or "LMT"
    """

    client_order_id: str
    symbol: str
    direction: str  # "LONG" | "SHORT" | "SELL"
    quantity: int
    order_type: str  # "MKT" | "LMT"
    limit_price: Optional[float] = None
    time_in_force: str = "DAY"
    strategy_name: str = "UNKNOWN"
    trader_type: str = "UNKNOWN"
