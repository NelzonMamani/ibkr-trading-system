from decimal import Decimal
from typing import Iterable, List, Dict

from domain.performance_snapshot import PerformanceSnapshot
from utils.price_math import D, quantize_money


class PerformanceRegistry:
    """
    Decimal-safe performance registry for deterministic replay.
    """

    def __init__(self) -> None:
        self._closed_trades: List[Dict] = []

    def record(self, events: Iterable) -> None:
        if not events:
            return
        for event in events:
            self._record_event(event)

    def _record_event(self, event) -> None:
        if getattr(event, "event_type", None) != "TRADE_CLOSED":
            return
        payload = event.payload or {}
        net_realised_pnl = quantize_money(D(self._extract_realised_pnl(payload)))
        gross_realised_pnl = quantize_money(D(self._extract_gross_realised_pnl(payload)))
        commission = quantize_money(D(self._extract_commission(payload)))
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
        gross_pnl = quantize_money(
            sum(D(trade.get("gross_realised_pnl", trade["realised_pnl"])) for trade in self._closed_trades)
        )
        total_commissions = quantize_money(
            sum(D(trade.get("commission", Decimal("0.00"))) for trade in self._closed_trades)
        )
        net_pnl = quantize_money(gross_pnl - total_commissions)

        win_rate = float(wins / total_trades) if total_trades else 0.0
        avg_pnl_per_trade = quantize_money(net_pnl / Decimal(total_trades)) if total_trades else Decimal("0.00")

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
            avg_pnl_per_trade=float(avg_pnl_per_trade),
            by_strategy=by_strategy,
            by_trader_type=by_trader_type,
        )

    def _build_buckets(
        self,
        trades: List[Dict],
        key: str,
    ) -> Dict[str, Dict[str, float | int]]:
        buckets: Dict[str, Dict[str, float | int]] = {}
        for trade in trades:
            bucket_key = trade.get(key, "UNKNOWN")
            bucket = buckets.setdefault(bucket_key, self._create_empty_bucket())
            self._update_bucket(bucket, trade)
        self._finalize_bucket_metrics(buckets)
        return buckets

    @staticmethod
    def _create_empty_bucket() -> Dict[str, float | int]:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "flats": 0,
            "win_rate": 0.0,
            "gross_pnl": 0.0,
            "total_commissions": 0.0,
            "net_pnl": 0.0,
            "avg_pnl_per_trade": 0.0,
        }

    @staticmethod
    def _update_bucket(bucket: Dict[str, float | int], trade: Dict) -> None:
        bucket["total_trades"] += 1
        bucket["gross_pnl"] += float(trade.get("gross_realised_pnl", trade["realised_pnl"]))
        bucket["total_commissions"] += float(trade.get("commission", 0.0))
        if trade["outcome"] == "WIN":
            bucket["wins"] += 1
        elif trade["outcome"] == "LOSS":
            bucket["losses"] += 1
        elif trade["outcome"] == "FLAT":
            bucket["flats"] += 1

    @staticmethod
    def _finalize_bucket_metrics(buckets: Dict[str, Dict[str, float | int]]) -> None:
        for bucket in buckets.values():
            total_trades = bucket["total_trades"]
            wins = bucket["wins"]
            gross_pnl = Decimal(str(bucket["gross_pnl"]))
            total_commissions = Decimal(str(bucket.get("total_commissions", 0.0)))
            net_pnl = gross_pnl - total_commissions
            bucket["win_rate"] = wins / total_trades if total_trades else 0.0
            bucket["net_pnl"] = float(net_pnl)
            bucket["avg_pnl_per_trade"] = float(
                net_pnl / Decimal(total_trades) if total_trades else Decimal("0.00")
            )

    @staticmethod
    def _extract_realised_pnl(payload: dict) -> Decimal:
        if payload is None:
            return Decimal("0.00")
        return D(payload.get("net_realised_pnl", payload.get("realised_pnl", payload.get("pnl", 0.0))))

    @staticmethod
    def _extract_gross_realised_pnl(payload: dict) -> Decimal:
        if payload is None:
            return Decimal("0.00")
        if "gross_realised_pnl" in payload:
            return D(payload.get("gross_realised_pnl", Decimal("0.00")))
        return D(payload.get("realised_pnl", payload.get("pnl", 0.0)))

    @staticmethod
    def _extract_commission(payload: dict) -> Decimal:
        if payload is None:
            return Decimal("0.00")
        return D(payload.get("commission", Decimal("0.00")))

    @staticmethod
    def _classify_outcome(realised_pnl: Decimal) -> str:
        if realised_pnl > 0:
            return "WIN"
        if realised_pnl < 0:
            return "LOSS"
        return "FLAT"
