from datetime import datetime
from typing import Iterable

from config.runtime_config import get_live_micro_daily_max_loss
from config.system_config import get_current_market_session
from core.events import SystemEvent
from domain.performance_snapshot import PerformanceSnapshot

ALLOWED_EXIT_CATEGORIES = {
    "EXIT_STOP_LOSS",
    "EXIT_TARGET",
    "EXIT_TIME",
    "EXIT_FAILED_SETUP",
    "EXIT_STRATEGY",
}


class PerformanceRegistry:
    """
    In-memory registry that aggregates trade performance from authoritative events.

    TRADE_CLOSED events are treated as the single source of truth. Metrics are
    derived directly from recorded event payloads to guarantee alignment
    between replay, accounting, and runtime reporting. total_trades reflects
    closed trades; open trades are supplied by the caller for clarity.
    """

    def __init__(self) -> None:
        self._closed_trades: list[dict] = []
        self._circuit_breakers: list[SystemEvent] = []

    def record(self, events: Iterable[SystemEvent]) -> None:
        if not events:
            return
        for event in events:
            self._record_event(event)

    def _record_event(self, event: SystemEvent) -> None:
        event_type = getattr(event, "event_type", None)
        if event_type == "CIRCUIT_BREAKER_TRIGGERED":
            self._circuit_breakers.append(event)
            return
        if event_type != "TRADE_CLOSED":
            return
        payload = event.payload or {}
        net_realised_pnl = round(self._extract_realised_pnl(payload), 2)
        gross_realised_pnl = round(self._extract_gross_realised_pnl(payload), 2)
        commission = round(self._extract_commission(payload), 2)
        entry_price = self._extract_float(payload, "entry_price")
        exit_price = self._extract_float(payload, "exit_price")
        quantity = int(payload.get("quantity", 0) or 0)
        stop_loss_price = payload.get("stop_loss_price")
        direction = (payload.get("direction") or "UNKNOWN").upper()
        r_multiple = self._compute_r_multiple(
            net_realised_pnl,
            entry_price,
            stop_loss_price,
            quantity,
        )
        hold_duration_ticks = int(payload.get("hold_duration_ticks", 0) or 0)
        exit_category = payload.get("exit_category", "UNKNOWN")
        exit_reason = payload.get("exit_reason", "UNKNOWN")
        timestamp = event.timestamp or datetime.utcnow()
        session = get_current_market_session(timestamp)
        volatility_regime = payload.get("volatility_regime", "UNKNOWN")
        market_direction = payload.get("market_direction", "UNKNOWN")
        stop_breached, stop_near = self._assess_stop_adherence(
            direction,
            exit_price,
            stop_loss_price,
        )
        exit_discipline_ok = exit_category in ALLOWED_EXIT_CATEGORIES
        rule_flags = {
            "stop_loss_breached": stop_breached,
            "stop_loss_near_breach": stop_near,
            "exit_discipline_breached": not exit_discipline_ok,
        }
        normalised_payload = {
            "symbol": payload.get("symbol", "UNKNOWN"),
            "trader_type": payload.get("trader_type", "UNKNOWN"),
            "strategy_name": payload.get("strategy_name", "UNKNOWN"),
            "pattern_name": payload.get("pattern_name", "UNKNOWN"),
            "realised_pnl": net_realised_pnl,
            "gross_realised_pnl": gross_realised_pnl,
            "commission": commission,
            "outcome": self._classify_outcome(net_realised_pnl),
            "r_multiple": r_multiple,
            "hold_duration_ticks": hold_duration_ticks,
            "exit_reason": exit_reason,
            "exit_category": exit_category,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "direction": direction,
            "quantity": quantity,
            "stop_loss_price": stop_loss_price,
            "take_profit_price": payload.get("take_profit_price"),
            "timestamp": timestamp.isoformat(),
            "session": session,
            "volatility_regime": volatility_regime,
            "market_direction": market_direction,
            "rule_flags": rule_flags,
        }
        self._closed_trades.append(normalised_payload)

    def snapshot(self, open_trades: int | None = None) -> PerformanceSnapshot:
        summary = self._summarize_trades(self._closed_trades)
        total_trades = summary["total_trades"]
        closed_trades = total_trades
        open_trades_value = open_trades if open_trades is not None else 0
        wins = summary["wins"]
        losses = summary["losses"]
        flats = summary["flats"]
        gross_pnl = summary["gross_pnl"]
        total_commissions = summary["total_commissions"]
        net_pnl = summary["net_pnl"]
        win_rate = summary["win_rate"]
        avg_pnl_per_trade = summary["avg_pnl_per_trade"]

        by_strategy = self._build_buckets(self._closed_trades, "strategy_name")
        by_trader_type = self._build_buckets(self._closed_trades, "trader_type")
        by_pattern = self._build_buckets(
            self._closed_trades, "pattern_name", include_failures=True
        )
        by_session = self._build_buckets(self._closed_trades, "session")
        by_volatility = self._build_buckets(self._closed_trades, "volatility_regime")
        by_market_direction = self._build_buckets(self._closed_trades, "market_direction")
        rule_adherence = self._build_rule_adherence_summary(
            net_pnl=net_pnl,
            trades=self._closed_trades,
        )
        reports = self._build_reports(self._closed_trades)

        return PerformanceSnapshot(
            total_trades=total_trades,
            closed_trades=closed_trades,
            open_trades=open_trades_value,
            wins=wins,
            losses=losses,
            flats=flats,
            win_rate=win_rate,
            gross_pnl=gross_pnl,
            total_commissions=total_commissions,
            net_pnl=net_pnl,
            avg_pnl_per_trade=avg_pnl_per_trade,
            by_strategy=by_strategy,
            by_trader_type=by_trader_type,
            by_pattern=by_pattern,
            by_session=by_session,
            by_volatility_regime=by_volatility,
            by_market_direction=by_market_direction,
            trade_outcomes=list(self._closed_trades),
            rule_adherence=rule_adherence,
            reports=reports,
        )

    def _build_buckets(
        self,
        trades: list[dict],
        key: str,
        include_failures: bool = False,
    ) -> dict[str, dict[str, float | int | None | dict]]:
        buckets: dict[str, dict[str, float | int | None | dict]] = {}
        for trade in trades:
            bucket_key = trade.get(key, "UNKNOWN")
            bucket = buckets.setdefault(
                bucket_key,
                self._create_empty_bucket(include_failures=include_failures),
            )
            self._update_bucket(bucket, trade, include_failures=include_failures)
        self._finalize_bucket_metrics(buckets)
        return buckets

    @staticmethod
    def _create_empty_bucket(
        include_failures: bool = False,
    ) -> dict[str, float | int | None | dict]:
        bucket: dict[str, float | int | None | dict] = {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "flats": 0,
            "win_rate": 0.0,
            "gross_pnl": 0.0,
            "total_commissions": 0.0,
            "net_pnl": 0.0,
            "avg_pnl_per_trade": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "expectancy": 0.0,
            "profit_factor": None,
            "avg_r_multiple": 0.0,
            "avg_hold_duration_ticks": 0.0,
        }
        if include_failures:
            bucket["failure_modes"] = {}
        return bucket

    @staticmethod
    def _update_bucket(
        bucket: dict[str, float | int | None | dict],
        trade: dict,
        include_failures: bool = False,
    ) -> None:
        bucket["total_trades"] += 1
        bucket["gross_pnl"] += trade.get("gross_realised_pnl", trade["realised_pnl"])
        bucket["total_commissions"] += trade.get("commission", 0.0)
        bucket["avg_r_multiple"] += trade.get("r_multiple", 0.0) or 0.0
        bucket["avg_hold_duration_ticks"] += trade.get("hold_duration_ticks", 0) or 0
        if trade["outcome"] == "WIN":
            bucket["wins"] += 1
            bucket["avg_win"] += trade.get("realised_pnl", 0.0)
        elif trade["outcome"] == "LOSS":
            bucket["losses"] += 1
            bucket["avg_loss"] += trade.get("realised_pnl", 0.0)
            if include_failures:
                failure_modes = bucket.setdefault("failure_modes", {})
                reason = trade.get("exit_reason", "UNKNOWN")
                failure_modes[reason] = failure_modes.get(reason, 0) + 1
        elif trade["outcome"] == "FLAT":
            bucket["flats"] += 1

    @staticmethod
    def _finalize_bucket_metrics(
        buckets: dict[str, dict[str, float | int | None | dict]]
    ) -> None:
        for bucket in buckets.values():
            total_trades = bucket["total_trades"]
            wins = bucket["wins"]
            losses = bucket["losses"]
            gross_pnl = bucket["gross_pnl"]
            total_commissions = bucket.get("total_commissions", 0.0)
            net_pnl = gross_pnl - total_commissions
            bucket["win_rate"] = wins / total_trades if total_trades else 0.0
            bucket["net_pnl"] = net_pnl
            bucket["avg_pnl_per_trade"] = (
                net_pnl / total_trades if total_trades else 0.0
            )
            bucket["avg_win"] = (
                bucket["avg_win"] / wins if wins else 0.0
            )
            bucket["avg_loss"] = (
                bucket["avg_loss"] / losses if losses else 0.0
            )
            loss_total = bucket["avg_loss"] * losses
            win_total = bucket["avg_win"] * wins
            bucket["expectancy"] = (
                (bucket["avg_win"] * (wins / total_trades))
                + (bucket["avg_loss"] * (losses / total_trades))
                if total_trades
                else 0.0
            )
            bucket["profit_factor"] = (
                abs(win_total / loss_total)
                if loss_total
                else None
            )
            bucket["avg_r_multiple"] = (
                bucket["avg_r_multiple"] / total_trades if total_trades else 0.0
            )
            bucket["avg_hold_duration_ticks"] = (
                bucket["avg_hold_duration_ticks"] / total_trades if total_trades else 0.0
            )

    @staticmethod
    def _extract_realised_pnl(payload: dict) -> float:
        if payload is None:
            return 0.0
        return float(payload.get("net_realised_pnl", payload.get("realised_pnl", payload.get("pnl", 0.0))))

    @staticmethod
    def _extract_gross_realised_pnl(payload: dict) -> float:
        if payload is None:
            return 0.0
        if "gross_realised_pnl" in payload:
            return float(payload.get("gross_realised_pnl", 0.0))
        return float(payload.get("realised_pnl", payload.get("pnl", 0.0)))

    @staticmethod
    def _extract_commission(payload: dict) -> float:
        if payload is None:
            return 0.0
        return float(payload.get("commission", 0.0))

    @staticmethod
    def _extract_float(payload: dict, key: str) -> float:
        if payload is None:
            return 0.0
        value = payload.get(key, 0.0)
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _classify_outcome(realised_pnl: float) -> str:
        if realised_pnl > 0:
            return "WIN"
        if realised_pnl < 0:
            return "LOSS"
        return "FLAT"

    @staticmethod
    def _compute_r_multiple(
        realised_pnl: float,
        entry_price: float,
        stop_loss_price: float | None,
        quantity: int,
    ) -> float:
        if stop_loss_price in (None, 0.0):
            return 0.0
        risk_per_unit = abs(entry_price - float(stop_loss_price))
        total_risk = risk_per_unit * max(abs(quantity), 1)
        if total_risk <= 0:
            return 0.0
        return round(realised_pnl / total_risk, 4)

    @staticmethod
    def _assess_stop_adherence(
        direction: str,
        exit_price: float,
        stop_loss_price: float | None,
    ) -> tuple[bool, bool]:
        if stop_loss_price is None:
            return False, False
        stop_loss = float(stop_loss_price)
        if direction == "LONG":
            breached = exit_price < stop_loss
        elif direction == "SHORT":
            breached = exit_price > stop_loss
        else:
            return False, False
        threshold = abs(stop_loss) * 0.001
        near = (not breached) and abs(exit_price - stop_loss) <= threshold
        return breached, near

    def _summarize_trades(self, trades: list[dict]) -> dict[str, float | int]:
        total_trades = len(trades)
        wins = sum(1 for trade in trades if trade["outcome"] == "WIN")
        losses = sum(1 for trade in trades if trade["outcome"] == "LOSS")
        flats = sum(1 for trade in trades if trade["outcome"] == "FLAT")
        gross_pnl = round(
            sum(trade.get("gross_realised_pnl", trade["realised_pnl"]) for trade in trades), 2
        )
        total_commissions = round(
            sum(trade.get("commission", 0.0) for trade in trades), 2
        )
        net_pnl = round(gross_pnl - total_commissions, 2)
        win_rate = wins / total_trades if total_trades else 0.0
        avg_pnl_per_trade = net_pnl / total_trades if total_trades else 0.0
        return {
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "flats": flats,
            "win_rate": win_rate,
            "gross_pnl": gross_pnl,
            "total_commissions": total_commissions,
            "net_pnl": net_pnl,
            "avg_pnl_per_trade": avg_pnl_per_trade,
        }

    def _build_rule_adherence_summary(self, net_pnl: float, trades: list[dict]) -> dict:
        stop_violations = 0
        stop_near = 0
        exit_discipline_violations = 0
        for trade in trades:
            flags = trade.get("rule_flags", {})
            if flags.get("stop_loss_breached"):
                stop_violations += 1
            if flags.get("stop_loss_near_breach"):
                stop_near += 1
            if flags.get("exit_discipline_breached"):
                exit_discipline_violations += 1

        max_daily_loss = abs(get_live_micro_daily_max_loss())
        max_loss_breached = max_daily_loss > 0 and net_pnl <= -max_daily_loss
        near_max_loss = max_daily_loss > 0 and net_pnl <= -(0.8 * max_daily_loss)

        return {
            "stop_loss_violations": stop_violations,
            "stop_loss_near_violations": stop_near,
            "exit_discipline_violations": exit_discipline_violations,
            "max_loss_breached": max_loss_breached,
            "max_loss_near_breach": near_max_loss,
            "max_daily_loss_limit": max_daily_loss,
            "circuit_breaker_triggers": len(self._circuit_breakers),
        }

    def _build_reports(self, trades: list[dict]) -> dict[str, dict]:
        daily = self._grouped_report(trades, period="daily")
        weekly = self._grouped_report(trades, period="weekly")
        cumulative_summary = self._summarize_trades(trades)
        cumulative = {
            "summary": cumulative_summary,
            "summary_text": self._format_summary_text("CUMULATIVE", cumulative_summary),
        }
        return {
            "daily": daily,
            "weekly": weekly,
            "cumulative": cumulative,
        }

    def _grouped_report(self, trades: list[dict], period: str) -> dict[str, dict]:
        grouped: dict[str, list[dict]] = {}
        for trade in trades:
            timestamp = trade.get("timestamp")
            if not timestamp:
                continue
            try:
                trade_dt = datetime.fromisoformat(timestamp)
            except ValueError:
                continue
            if period == "daily":
                key = trade_dt.date().isoformat()
            else:
                iso_year, iso_week, _ = trade_dt.isocalendar()
                key = f"{iso_year}-W{iso_week:02d}"
            grouped.setdefault(key, []).append(trade)
        report: dict[str, dict] = {}
        for key, group_trades in sorted(grouped.items()):
            summary = self._summarize_trades(group_trades)
            report[key] = {
                "summary": summary,
                "summary_text": self._format_summary_text(key, summary),
            }
        return report

    @staticmethod
    def _format_summary_text(label: str, summary: dict[str, float | int]) -> str:
        return (
            f"{label} | total={summary['total_trades']} "
            f"wins={summary['wins']} losses={summary['losses']} "
            f"flats={summary['flats']} win_rate={summary['win_rate']:.2f} "
            f"net_pnl={summary['net_pnl']:.2f} avg_pnl={summary['avg_pnl_per_trade']:.2f}"
        )
