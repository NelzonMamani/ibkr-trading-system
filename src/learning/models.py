from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class LearningTrade:
    strategy_name: str
    symbol: str
    entry_time: datetime | None
    exit_time: datetime | None
    entry_price: float | None
    exit_price: float | None
    pnl: float | None
    pnl_pct: float | None
    tags: list[str] = field(default_factory=list)
    gate_context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LearningDataset:
    trades: list[LearningTrade]

    def trade_count(self) -> int:
        return len(self.trades)

    def winning_trades(self) -> list[LearningTrade]:
        return [trade for trade in self.trades if (trade.pnl or 0.0) > 0]

    def losing_trades(self) -> list[LearningTrade]:
        return [trade for trade in self.trades if (trade.pnl or 0.0) < 0]
