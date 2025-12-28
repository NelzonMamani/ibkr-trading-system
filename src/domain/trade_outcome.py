from dataclasses import dataclass


@dataclass
class TradeOutcome:
    symbol: str
    trader_type: str
    strategy_name: str
    direction: str
    entry_price: float
    exit_price: float
    quantity: int
    realised_pnl: float
    duration_ticks: int
    outcome: str  # WIN | LOSS | FLAT

