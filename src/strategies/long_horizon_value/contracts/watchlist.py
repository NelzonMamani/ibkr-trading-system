from dataclasses import dataclass
from typing import Optional

@dataclass
class WatchlistEntry:
    symbol: str
    state: str  # NEW, UNDER_REVIEW, VALUED, WAITING_FOR_PRICE, FOCUS
    priority: Optional[int] = None
    notes: Optional[str] = None
