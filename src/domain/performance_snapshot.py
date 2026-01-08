from dataclasses import dataclass, field


@dataclass
class PerformanceSnapshot:
    total_trades: int
    closed_trades: int
    open_trades: int
    wins: int
    losses: int
    flats: int
    win_rate: float
    gross_pnl: float
    total_commissions: float
    net_pnl: float
    avg_pnl_per_trade: float
    by_strategy: dict[str, dict[str, float | int | None | dict]] = field(default_factory=dict)
    by_trader_type: dict[str, dict[str, float | int | None | dict]] = field(default_factory=dict)
    by_pattern: dict[str, dict[str, float | int | None | dict]] = field(default_factory=dict)
    by_session: dict[str, dict[str, float | int | None | dict]] = field(default_factory=dict)
    by_volatility_regime: dict[str, dict[str, float | int | None | dict]] = field(default_factory=dict)
    by_market_direction: dict[str, dict[str, float | int | None | dict]] = field(default_factory=dict)
    trade_outcomes: list[dict] = field(default_factory=list)
    rule_adherence: dict[str, object] = field(default_factory=dict)
    reports: dict[str, dict] = field(default_factory=dict)
