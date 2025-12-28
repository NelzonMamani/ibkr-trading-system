from dataclasses import dataclass
from typing import Dict, List


@dataclass
class StrategyPerformanceSnapshot:
    strategy_name: str
    total_trades: int
    wins: int
    losses: int
    flats: int
    gross_pnl: float

    @property
    def win_rate(self) -> float:
        return self.wins / self.total_trades if self.total_trades else 0.0


class StrategyPerformanceTracker:
    """
    In-memory tracker that aggregates closed trade events by strategy.

    This tracker is intentionally deterministic and side-effect free, relying
    only on the event payloads provided to `record_trade_close`.
    """

    def __init__(self) -> None:
        self._by_strategy: Dict[str, Dict[str, float | int]] = {}

    def record_trade_close(self, event_payload) -> None:
        if not isinstance(event_payload, dict):
            return

        strategy_name = str(event_payload.get("strategy_name") or "UNKNOWN")
        pnl = event_payload.get("pnl")
        if pnl is None:
            pnl = event_payload.get("realised_pnl", 0.0)

        try:
            pnl_value = float(pnl)
        except (TypeError, ValueError):
            pnl_value = 0.0
        pnl_value = round(pnl_value, 2)

        bucket = self._by_strategy.setdefault(
            strategy_name,
            {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "flats": 0,
                "gross_pnl": 0.0,
            },
        )

        bucket["total_trades"] += 1
        bucket["gross_pnl"] += pnl_value
        if pnl_value > 0:
            bucket["wins"] += 1
        elif pnl_value < 0:
            bucket["losses"] += 1
        else:
            bucket["flats"] += 1

    def snapshot(self) -> List[StrategyPerformanceSnapshot]:
        snapshots = [
            StrategyPerformanceSnapshot(
                strategy_name=strategy_name,
                total_trades=bucket["total_trades"],
                wins=bucket["wins"],
                losses=bucket["losses"],
                flats=bucket["flats"],
                gross_pnl=bucket["gross_pnl"],
            )
            for strategy_name, bucket in self._by_strategy.items()
        ]
        return sorted(snapshots, key=lambda snap: snap.strategy_name)
