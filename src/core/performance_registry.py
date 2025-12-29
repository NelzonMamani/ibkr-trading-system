from decimal import Decimal
from typing import Iterable

from core.events import SystemEvent
from domain.performance_snapshot import PerformanceSnapshot
from utils.price_math import q_money, to_decimal


class PerformanceRegistry:
    """
    In-memory registry that aggregates trade performance from authoritative events.

    TRADE_CLOSED events are treated as the single source of truth. Metrics are
    derived directly from recorded event payloads to guarantee alignment
    between replay, accounting, and runtime reporting.
    """

    def __init__(self) -> None:
        self._closed_trades: list[dict] = []

    def record(self, events: Iterable[SystemEvent]) -> None:
        if not events:
            return
        for event in events:
            self._record_event(event)

    def _record_event(self, event: SystemEvent) -> None:
        if getattr(event, "event_type", None) != "TRADE_CLOSED":
            return
        payload = event.payload or {}
        net_realised_pnl = q_money(self._extract_realised_pnl(payload))
        gross_realised_pnl = q_money(self._extract_gross_realised_pnl(payload))
        commission = q_money(self._extract_commission(payload))
        normalised_payload = {
            "symbol": payload.get("symbol", "UNKNOWN"),
            "trader_type": payload.get("trader_type", "UNKNOWN"),
            "strategy_name": payload.get("strategy_name", "UNKNOWN"),
            "realised_pnl": net_realised_pnl,
            "gross_realised_pnl": gross_realised_pnl,
            "commission": commission,
            "outcome": self._classify_outcome(net_realised_pnl),
        }
        self._closed_trades.append(normalised_payload)

    def snapshot(self) -> PerformanceSnapshot:
        total_trades = len(self._closed_trades)
        wins = sum(1 for trade in self._closed_trades if trade["outcome"] == "WIN")
        losses = sum(1 for trade in self._closed_trades if trade["outcome"] == "LOSS")
        flats = sum(1 for trade in self._closed_trades if trade["outcome"] == "FLAT")
        gross_pnl = q_money(
            sum(trade.get("gross_realised_pnl", trade["realised_pnl"]) for trade in self._closed_trades)
        )
        total_commissions = q_money(
            sum(trade.get("commission", Decimal("0")) for trade in self._closed_trades)
        )
        net_pnl = q_money(gross_pnl - total_commissions)

        win_rate = wins / total_trades if total_trades else 0.0
        avg_pnl_per_trade = float(net_pnl) / total_trades if total_trades else 0.0

        by_strategy = self._build_buckets(self._closed_trades, "strategy_name")
        by_trader_type = self._build_buckets(self._closed_trades, "trader_type")

        return PerformanceSnapshot(
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            flats=flats,
            win_rate=win_rate,
            gross_pnl=float(gross_pnl),
            total_commissions=float(total_commissions),
            net_pnl=float(net_pnl),
            avg_pnl_per_trade=avg_pnl_per_trade,
            by_strategy=by_strategy,
            by_trader_type=by_trader_type,
        )

    def _build_buckets(
        self,
        trades: list[dict],
        key: str,
    ) -> dict[str, dict[str, float | int]]:
        buckets: dict[str, dict[str, float | int]] = {}
        for trade in trades:
            bucket_key = trade.get(key, "UNKNOWN")
            bucket = buckets.setdefault(bucket_key, self._create_empty_bucket())
            self._update_bucket(bucket, trade)
        self._finalize_bucket_metrics(buckets)
        return buckets

    @staticmethod
    def _create_empty_bucket() -> dict[str, float | int]:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "flats": 0,
            "win_rate": 0.0,
            "gross_pnl": Decimal("0"),
            "total_commissions": Decimal("0"),
            "net_pnl": Decimal("0"),
            "avg_pnl_per_trade": 0.0,
        }

    @staticmethod
    def _update_bucket(bucket: dict[str, float | int], trade: dict) -> None:
        bucket["total_trades"] += 1
        bucket["gross_pnl"] += trade.get("gross_realised_pnl", trade["realised_pnl"])
        bucket["total_commissions"] += trade.get("commission", Decimal("0"))
        if trade["outcome"] == "WIN":
            bucket["wins"] += 1
        elif trade["outcome"] == "LOSS":
            bucket["losses"] += 1
        elif trade["outcome"] == "FLAT":
            bucket["flats"] += 1

    @staticmethod
    def _finalize_bucket_metrics(buckets: dict[str, dict[str, float | int]]) -> None:
        for bucket in buckets.values():
            total_trades = bucket["total_trades"]
            wins = bucket["wins"]
            gross_pnl = q_money(bucket["gross_pnl"])
            total_commissions = q_money(bucket.get("total_commissions", Decimal("0")))
            net_pnl = q_money(gross_pnl - total_commissions)
            bucket["win_rate"] = wins / total_trades if total_trades else 0.0
            bucket["net_pnl"] = float(net_pnl)
            bucket["gross_pnl"] = float(gross_pnl)
            bucket["total_commissions"] = float(total_commissions)
            bucket["avg_pnl_per_trade"] = (
                float(net_pnl) / total_trades if total_trades else 0.0
            )

    @staticmethod
    def _extract_realised_pnl(payload: dict) -> Decimal:
        if payload is None:
            return Decimal("0")
        return to_decimal(payload.get("net_realised_pnl", payload.get("realised_pnl", payload.get("pnl", 0.0))))

    @staticmethod
    def _extract_gross_realised_pnl(payload: dict) -> Decimal:
        if payload is None:
            return Decimal("0")
        if "gross_realised_pnl" in payload:
            return to_decimal(payload.get("gross_realised_pnl", 0.0))
        return to_decimal(payload.get("realised_pnl", payload.get("pnl", 0.0)))

    @staticmethod
    def _extract_commission(payload: dict) -> Decimal:
        if payload is None:
            return Decimal("0")
        return to_decimal(payload.get("commission", 0.0))

    @staticmethod
    def _classify_outcome(realised_pnl: Decimal) -> str:
        if realised_pnl > Decimal("0"):
            return "WIN"
        if realised_pnl < Decimal("0"):
            return "LOSS"
        return "FLAT"
