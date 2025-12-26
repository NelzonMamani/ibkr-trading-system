from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional


@dataclass
class ActiveTrade:
    trade_id: str
    symbol: str
    strategy_name: str
    trader_type: str
    direction: str
    quantity: int
    entry_timestamp: datetime
    status: Literal["OPEN", "CLOSED"] = "OPEN"
    close_timestamp: Optional[datetime] = None
    close_reason: Optional[str] = None

    def __post_init__(self) -> None:
        print(
            "[TRADE:LIFECYCLE] CREATED trade_id="
            f"{self.trade_id} symbol={self.symbol} strategy={self.strategy_name} "
            f"status set to {self.status} (CREATED→OPEN)"
        )

    def close(self, reason: str) -> None:
        self.status = "CLOSED"
        self.close_reason = reason
        self.close_timestamp = datetime.utcnow()
        print(
            "[TRADE:LIFECYCLE] CLOSED trade_id="
            f"{self.trade_id} symbol={self.symbol} strategy={self.strategy_name} "
            f"reason={reason} status transitioned to CLOSED (OPEN→CLOSED)"
        )
