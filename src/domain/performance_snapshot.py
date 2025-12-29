from dataclasses import dataclass, field


@dataclass
class PerformanceSnapshot:
    total_trades: int
    wins: int
    losses: int
    flats: int
    win_rate: float
    gross_pnl: float
    total_commissions: float
    net_pnl: float
    avg_pnl_per_trade: float
    by_strategy: dict[str, dict[str, float | int]] = field(default_factory=dict)
    by_trader_type: dict[str, dict[str, float | int]] = field(default_factory=dict)
