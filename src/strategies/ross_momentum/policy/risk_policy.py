from dataclasses import dataclass


@dataclass(frozen=True)
class RiskPolicy:
    max_loss_per_trade: float = 0.20
