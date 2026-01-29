from dataclasses import dataclass
from typing import Optional

@dataclass
class TradeIntent:
    symbol: str
    target_pct: float
    max_price: Optional[float]
    rationale_id: str
    state: str  # READY, BLOCKED_CAPITAL, AWAITING_APPROVAL
