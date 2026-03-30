from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PortfolioState:
    total_open_positions: int = 0
    total_exposure: float = 0.0
    total_realized_pnl: float = 0.0
    total_unrealized_pnl: float = 0.0
    symbols_open: list[str] = field(default_factory=list)
    drifted_positions: list[str] = field(default_factory=list)
