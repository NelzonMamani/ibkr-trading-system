from dataclasses import dataclass


@dataclass
class ExitSignal:
    symbol: str
    trader_type: str
    strategy_name: str
    reason: str
