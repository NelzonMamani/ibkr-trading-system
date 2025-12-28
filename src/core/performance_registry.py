from domain.performance_snapshot import PerformanceSnapshot
from domain.trade_outcome import TradeOutcome


class PerformanceRegistry:
    """
    In-memory registry that aggregates TradeOutcome records.

    This class is intentionally side-effect free and maintains an internal
    collection of trade outcomes as the single source of truth for performance
    metrics.
    """

    def __init__(self) -> None:
        self._outcomes: list[TradeOutcome] = []

    def record(self, outcomes: list[TradeOutcome]) -> None:
        if not outcomes:
            return
        self._outcomes.extend(outcomes)

    def snapshot(self) -> PerformanceSnapshot:
        total_trades = len(self._outcomes)
        wins = sum(1 for outcome in self._outcomes if outcome.outcome == "WIN")
        losses = sum(1 for outcome in self._outcomes if outcome.outcome == "LOSS")
        flats = sum(1 for outcome in self._outcomes if outcome.outcome == "FLAT")
        gross_pnl = sum(outcome.realised_pnl for outcome in self._outcomes)

        win_rate = wins / total_trades if total_trades else 0.0
        avg_pnl_per_trade = gross_pnl / total_trades if total_trades else 0.0

        by_strategy: dict[str, dict[str, float | int]] = {}
        by_trader_type: dict[str, dict[str, float | int]] = {}

        for outcome in self._outcomes:
            strategy_bucket = by_strategy.setdefault(
                outcome.strategy_name, self._create_empty_bucket()
            )
            trader_type_bucket = by_trader_type.setdefault(
                outcome.trader_type, self._create_empty_bucket()
            )

            self._update_bucket(strategy_bucket, outcome)
            self._update_bucket(trader_type_bucket, outcome)

        self._finalize_bucket_metrics(by_strategy)
        self._finalize_bucket_metrics(by_trader_type)

        return PerformanceSnapshot(
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            flats=flats,
            win_rate=win_rate,
            gross_pnl=gross_pnl,
            avg_pnl_per_trade=avg_pnl_per_trade,
            by_strategy=by_strategy,
            by_trader_type=by_trader_type,
        )

    @staticmethod
    def _create_empty_bucket() -> dict[str, float | int]:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "flats": 0,
            "win_rate": 0.0,
            "gross_pnl": 0.0,
            "avg_pnl_per_trade": 0.0,
        }

    @staticmethod
    def _update_bucket(bucket: dict[str, float | int], outcome: TradeOutcome) -> None:
        bucket["total_trades"] += 1
        bucket["gross_pnl"] += outcome.realised_pnl
        if outcome.outcome == "WIN":
            bucket["wins"] += 1
        elif outcome.outcome == "LOSS":
            bucket["losses"] += 1
        elif outcome.outcome == "FLAT":
            bucket["flats"] += 1

    @staticmethod
    def _finalize_bucket_metrics(buckets: dict[str, dict[str, float | int]]) -> None:
        for bucket in buckets.values():
            total_trades = bucket["total_trades"]
            wins = bucket["wins"]
            gross_pnl = bucket["gross_pnl"]
            bucket["win_rate"] = wins / total_trades if total_trades else 0.0
            bucket["avg_pnl_per_trade"] = (
                gross_pnl / total_trades if total_trades else 0.0
            )
