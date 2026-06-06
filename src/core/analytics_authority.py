from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
import json
from typing import Any, Iterable
from uuid import uuid4


PNL_KEYS = (
    "net_realised_pnl",
    "net_realized_pnl",
    "realised_pnl",
    "realized_pnl",
    "pnl",
)


@dataclass(frozen=True)
class AnalyticsDataQualityIssue:
    issue_id: str
    code: str
    severity: str
    source: str
    trade_identity: str
    field_name: str
    detail: str
    timestamp: str

    def to_event_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AnalyticsTradeRecord:
    source: str
    trade_identity: str
    run_id: str
    trading_day: str
    run_mode: str
    strategy_key: str | None
    symbol: str | None
    setup_family: str | None
    exit_reason: str | None
    exit_category: str | None
    entry_price: float | None
    exit_price: float | None
    quantity: int | None
    realized_pnl: float | None
    unrealized_pnl: float = 0.0
    timestamp: str | None = None


@dataclass(frozen=True)
class AnalyticsSnapshot:
    run_id: str
    trading_day: str
    run_mode: str
    strategy_key: str
    symbol: str
    setup_family: str
    trade_count: int
    attempted_trade_count: int
    blocked_trade_count: int
    filled_trade_count: int
    win_count: int
    loss_count: int
    breakeven_count: int
    realized_pnl: float
    unrealized_pnl: float
    gross_profit: float
    gross_loss: float
    average_win: float
    average_loss: float
    profit_factor: float | None
    win_rate: float
    expectancy: float
    max_single_trade_loss: float
    max_single_trade_win: float
    max_drawdown: float
    daily_risk_lock_count: int
    recovery_lock_count: int
    stop_loss_exit_count: int
    target_exit_count: int
    trailing_exit_count: int
    manual_exit_count: int
    unknown_exit_count: int
    data_quality_issue_count: int
    execution_failure_count: int
    timestamp: str
    incomplete_data: bool = False
    source_counts: dict[str, int] = field(default_factory=dict)
    block_reason_counts: dict[str, int] = field(default_factory=dict)
    recovery_status_counts: dict[str, int] = field(default_factory=dict)
    breakdowns: dict[str, dict[str, dict[str, float | int | None]]] = field(default_factory=dict)
    data_quality_issues: tuple[AnalyticsDataQualityIssue, ...] = ()

    def to_event_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["data_quality_issues"] = [
            issue.to_event_payload() for issue in self.data_quality_issues
        ]
        return payload


class AnalyticsAuthority:
    """Canonical P14 analytics authority.

    The authority reconstructs metrics from event, storage, lifecycle, and
    execution evidence. Missing values are flagged as data quality issues and
    are not substituted into performance calculations.
    """

    def __init__(
        self,
        *,
        event_collector: Any | None = None,
        storage_engine: Any | None = None,
        trade_lifecycle_engine: Any | None = None,
    ) -> None:
        self.event_collector = event_collector
        self.storage_engine = storage_engine
        self.trade_lifecycle_engine = trade_lifecycle_engine
        self.last_snapshot: AnalyticsSnapshot | None = None

    def evaluate(
        self,
        *,
        run_id: str | None = None,
        trading_day: str | None = None,
        run_mode: str = "SIM",
        strategy_key: str | None = None,
        symbol: str | None = None,
        setup_family: str | None = None,
        now: datetime | None = None,
        event_collector: Any | None = None,
        storage_engine: Any | None = None,
        trade_lifecycle_engine: Any | None = None,
        execution_results: Iterable[Any] | None = None,
        event_replay_complete: bool = True,
        emit_audit_event: bool = True,
    ) -> AnalyticsSnapshot:
        if event_collector is not None:
            self.event_collector = event_collector
        if storage_engine is not None:
            self.storage_engine = storage_engine
        if trade_lifecycle_engine is not None:
            self.trade_lifecycle_engine = trade_lifecycle_engine

        timestamp = self._timestamp(now)
        resolved_run_id = str(run_id or getattr(self.storage_engine, "run_id", None) or "UNKNOWN")
        resolved_day = str(trading_day or self._trading_day(now))
        resolved_mode = str(run_mode or "SIM").upper()
        issues: list[AnalyticsDataQualityIssue] = []

        if not event_replay_complete:
            issues.append(
                self._issue(
                    code="EVENT_REPLAY_INCOMPLETE",
                    source="event_replay",
                    trade_identity="SYSTEM",
                    field_name="event_replay_complete",
                    detail="Event replay did not complete before analytics evaluation.",
                    timestamp=timestamp,
                )
            )

        event_records, event_counters = self._records_from_events(
            run_id=resolved_run_id,
            trading_day=resolved_day,
            run_mode=resolved_mode,
            timestamp=timestamp,
            issues=issues,
        )
        storage_records, storage_counters = self._records_from_storage(
            run_id=resolved_run_id,
            trading_day=resolved_day,
            run_mode=resolved_mode,
            timestamp=timestamp,
            issues=issues,
        )
        lifecycle_records, lifecycle_unrealized = self._records_from_lifecycle(
            run_id=resolved_run_id,
            trading_day=resolved_day,
            run_mode=resolved_mode,
            timestamp=timestamp,
            issues=issues,
        )
        execution_counters = self._counters_from_execution_results(execution_results)

        records = self._dedupe_records([*storage_records, *event_records, *lifecycle_records])
        filtered = self._filter_records(
            records,
            strategy_key=strategy_key,
            symbol=symbol,
            setup_family=setup_family,
        )
        blocked_reason_counts = self._merge_counts(
            event_counters["block_reason_counts"],
            storage_counters["block_reason_counts"],
        )
        recovery_status_counts = self._merge_counts(
            event_counters["recovery_status_counts"],
            storage_counters["recovery_status_counts"],
        )
        attempted_trade_count = (
            len(filtered)
            + sum(blocked_reason_counts.values())
            + execution_counters["attempted_count"]
        )
        filled_trade_count = len(filtered)
        execution_failure_count = (
            event_counters["execution_failure_count"]
            + storage_counters["execution_failure_count"]
            + execution_counters["failure_count"]
        )

        snapshot = self._build_snapshot(
            records=filtered,
            all_records=records,
            run_id=resolved_run_id,
            trading_day=resolved_day,
            run_mode=resolved_mode,
            strategy_key=strategy_key,
            symbol=symbol,
            setup_family=setup_family,
            timestamp=timestamp,
            attempted_trade_count=attempted_trade_count,
            blocked_trade_count=sum(blocked_reason_counts.values()),
            filled_trade_count=filled_trade_count,
            daily_risk_lock_count=event_counters["daily_risk_lock_count"]
            + storage_counters["daily_risk_lock_count"],
            recovery_lock_count=event_counters["recovery_lock_count"]
            + storage_counters["recovery_lock_count"],
            execution_failure_count=execution_failure_count,
            unrealized_pnl=lifecycle_unrealized,
            source_counts={
                "events": event_counters["record_count"],
                "storage": storage_counters["record_count"],
                "lifecycle": len(lifecycle_records),
            },
            block_reason_counts=blocked_reason_counts,
            recovery_status_counts=recovery_status_counts,
            issues=tuple(issues),
        )
        if resolved_mode != "READ_ONLY":
            self.last_snapshot = snapshot
        if emit_audit_event:
            self._emit_snapshot(snapshot)
            self._emit_data_quality_issues(snapshot.data_quality_issues)
        return snapshot

    def _records_from_events(
        self,
        *,
        run_id: str,
        trading_day: str,
        run_mode: str,
        timestamp: str,
        issues: list[AnalyticsDataQualityIssue],
    ) -> tuple[list[AnalyticsTradeRecord], dict[str, Any]]:
        collector = self.event_collector
        counters = self._empty_counters()
        if collector is None or not hasattr(collector, "snapshot_all"):
            return [], counters
        try:
            events = list(collector.snapshot_all() or [])
        except Exception:
            issues.append(
                self._issue(
                    code="EVENT_HISTORY_READ_FAILED",
                    source="event_collector",
                    trade_identity="SYSTEM",
                    field_name="snapshot_all",
                    detail="Event collector history could not be read.",
                    timestamp=timestamp,
                )
            )
            return [], counters

        records: list[AnalyticsTradeRecord] = []
        for event in events:
            event_type = str(getattr(event, "event_type", "") or "")
            payload = dict(getattr(event, "payload", {}) or {})
            event_timestamp = getattr(event, "timestamp", None)
            if event_type == "TRADE_CLOSED":
                if self._trading_day(event_timestamp) != trading_day:
                    continue
                payload.setdefault("event_id", getattr(event, "event_id", None))
                payload.setdefault("timestamp", event_timestamp)
                record = self._record_from_payload(
                    payload,
                    source="event_history",
                    run_id=run_id,
                    trading_day=trading_day,
                    run_mode=run_mode,
                    timestamp=timestamp,
                    issues=issues,
                )
                records.append(record)
                continue
            if self._trading_day(event_timestamp) != trading_day:
                continue
            if event_type == "TRADE_BLOCKED":
                reason = self._block_reason(payload)
                counters["block_reason_counts"][reason] = counters["block_reason_counts"].get(reason, 0) + 1
                continue
            if event_type in {"ORDER_REJECTED", "ORDER_REJECTED_HARD", "ORDER_SUBMISSION_FAILED"}:
                counters["execution_failure_count"] += 1
                continue
            if event_type == "DAILY_RISK_DECISION" and bool(payload.get("blocks_new_entries")):
                counters["daily_risk_lock_count"] += 1
                continue
            if event_type == "AUTONOMOUS_RECOVERY_DECISION":
                status = str(payload.get("recovery_status") or "UNKNOWN")
                counters["recovery_status_counts"][status] = counters["recovery_status_counts"].get(status, 0) + 1
                if bool(payload.get("blocks_new_entries")):
                    counters["recovery_lock_count"] += 1
        counters["record_count"] = len(records)
        return records, counters

    def _records_from_storage(
        self,
        *,
        run_id: str,
        trading_day: str,
        run_mode: str,
        timestamp: str,
        issues: list[AnalyticsDataQualityIssue],
    ) -> tuple[list[AnalyticsTradeRecord], dict[str, Any]]:
        storage = self.storage_engine
        counters = self._empty_counters()
        if storage is None:
            return [], counters
        store = getattr(storage, "_store", storage)
        if store is None:
            issues.append(
                self._issue(
                    code="STORAGE_UNAVAILABLE",
                    source="storage",
                    trade_identity="SYSTEM",
                    field_name="_store",
                    detail="Storage engine was provided but no store is available.",
                    timestamp=timestamp,
                )
            )
            return [], counters

        records: list[AnalyticsTradeRecord] = []
        fetch_trade_outcomes = getattr(store, "fetch_trade_outcomes", None)
        if callable(fetch_trade_outcomes):
            try:
                rows = list(fetch_trade_outcomes(run_id) or [])
            except Exception:
                issues.append(
                    self._issue(
                        code="STORAGE_UNAVAILABLE",
                        source="storage.trade_outcomes",
                        trade_identity="SYSTEM",
                        field_name="fetch_trade_outcomes",
                        detail="Persisted trade outcomes could not be read.",
                        timestamp=timestamp,
                    )
                )
                rows = []
            for row in rows:
                payload = dict(row)
                payload.update(self._payload_from_json(row.get("payload_json")))
                closed_at = payload.get("closed_at") or payload.get("timestamp") or row.get("created_at")
                if closed_at and self._trading_day(self._parse_datetime(closed_at)) != trading_day:
                    continue
                payload.setdefault("timestamp", closed_at)
                payload.setdefault("trade_id", row.get("trade_id") or row.get("lifecycle_trade_id"))
                payload.setdefault("trade_outcome_id", row.get("trade_outcome_id"))
                records.append(
                    self._record_from_payload(
                        payload,
                        source="storage.trade_outcomes",
                        run_id=run_id,
                        trading_day=trading_day,
                        run_mode=run_mode,
                        timestamp=timestamp,
                        issues=issues,
                    )
                )

        fetch_events = getattr(store, "fetch_events", None)
        if callable(fetch_events):
            try:
                rows = list(fetch_events(run_id) or [])
            except Exception:
                issues.append(
                    self._issue(
                        code="STORAGE_UNAVAILABLE",
                        source="storage.events",
                        trade_identity="SYSTEM",
                        field_name="fetch_events",
                        detail="Persisted event history could not be read.",
                        timestamp=timestamp,
                    )
                )
                rows = []
            for row in rows:
                event_type = str(row.get("event_type") or "")
                row_timestamp = row.get("timestamp") or row.get("created_at")
                if row_timestamp and self._trading_day(self._parse_datetime(row_timestamp)) != trading_day:
                    continue
                payload = self._payload_from_json(row.get("payload_json"))
                if event_type == "TRADE_BLOCKED":
                    reason = self._block_reason(payload)
                    counters["block_reason_counts"][reason] = counters["block_reason_counts"].get(reason, 0) + 1
                elif event_type == "DAILY_RISK_DECISION" and bool(payload.get("blocks_new_entries")):
                    counters["daily_risk_lock_count"] += 1
                elif event_type == "AUTONOMOUS_RECOVERY_DECISION":
                    status = str(payload.get("recovery_status") or "UNKNOWN")
                    counters["recovery_status_counts"][status] = counters["recovery_status_counts"].get(status, 0) + 1
                    if bool(payload.get("blocks_new_entries")):
                        counters["recovery_lock_count"] += 1
                elif event_type in {"ORDER_REJECTED", "ORDER_REJECTED_HARD", "ORDER_SUBMISSION_FAILED"}:
                    counters["execution_failure_count"] += 1
        counters["record_count"] = len(records)
        return records, counters

    def _records_from_lifecycle(
        self,
        *,
        run_id: str,
        trading_day: str,
        run_mode: str,
        timestamp: str,
        issues: list[AnalyticsDataQualityIssue],
    ) -> tuple[list[AnalyticsTradeRecord], float]:
        engine = self.trade_lifecycle_engine
        if engine is None:
            return [], 0.0
        try:
            if hasattr(engine, "get_open_lifecycle_trades"):
                trades = list(engine.get_open_lifecycle_trades() or [])
            else:
                trades = []
        except Exception:
            issues.append(
                self._issue(
                    code="LIFECYCLE_READ_FAILED",
                    source="lifecycle",
                    trade_identity="SYSTEM",
                    field_name="get_open_lifecycle_trades",
                    detail="Lifecycle trades could not be read.",
                    timestamp=timestamp,
                )
            )
            return [], 0.0

        unrealized = 0.0
        for trade in trades:
            unrealized += self._float_attr(trade, "unrealized_pnl", 0.0)
            status = str(getattr(trade, "status", getattr(trade, "state", "")) or "")
            reconciled = getattr(trade, "reconciled", getattr(trade, "broker_reconciled", True))
            if status.upper().startswith("UNRECONCILED") or reconciled is False:
                issues.append(
                    self._issue(
                        code="UNRECONCILED_OPEN_POSITION",
                        source="lifecycle",
                        trade_identity=str(getattr(trade, "trade_id", "UNKNOWN")),
                        field_name="status",
                        detail="Open lifecycle position is not reconciled.",
                        timestamp=timestamp,
                    )
                )
        return [], round(unrealized, 2)

    def _record_from_payload(
        self,
        payload: dict[str, Any],
        *,
        source: str,
        run_id: str,
        trading_day: str,
        run_mode: str,
        timestamp: str,
        issues: list[AnalyticsDataQualityIssue],
    ) -> AnalyticsTradeRecord:
        trade_identity = self._trade_identity(payload, source)
        strategy_key = self._first_text(payload, "strategy_key", "strategy_name", "trader_type")
        symbol = self._first_text(payload, "symbol")
        setup_family = self._first_text(payload, "setup_family", "setup_family_id", "pattern_name")
        exit_reason = self._first_text(payload, "exit_reason", "reason")
        exit_category = self._first_text(payload, "exit_category", "exit_type")
        entry_price = self._optional_float(payload, "entry_price")
        exit_price = self._optional_float(payload, "exit_price", "close_price")
        quantity = self._optional_int(payload, "quantity", "filled_quantity")
        realized_pnl = self._pnl_from_payload(payload)

        required_fields = {
            "trade_id": self._first_text(payload, "trade_id", "trade_outcome_id", "event_id"),
            "strategy_key": strategy_key,
            "setup_family": setup_family,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "quantity": quantity,
            "realized_pnl": realized_pnl,
            "timestamp": payload.get("timestamp") or payload.get("closed_at"),
        }
        for field_name, value in required_fields.items():
            if value not in (None, ""):
                continue
            issues.append(
                self._issue(
                    code=f"MISSING_{field_name.upper()}",
                    source=source,
                    trade_identity=trade_identity,
                    field_name=field_name,
                    detail=f"Closed trade evidence is missing {field_name}.",
                    timestamp=timestamp,
                )
            )

        if self._has_mismatched_state(payload):
            issues.append(
                self._issue(
                    code="MISMATCHED_LIFECYCLE_EXECUTION_STATE",
                    source=source,
                    trade_identity=trade_identity,
                    field_name="lifecycle_state",
                    detail="Lifecycle state and execution state disagree.",
                    timestamp=timestamp,
                )
            )

        return AnalyticsTradeRecord(
            source=source,
            trade_identity=trade_identity,
            run_id=run_id,
            trading_day=trading_day,
            run_mode=run_mode,
            strategy_key=strategy_key,
            symbol=symbol,
            setup_family=setup_family,
            exit_reason=exit_reason,
            exit_category=exit_category,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=quantity,
            realized_pnl=realized_pnl,
            timestamp=self._timestamp(payload.get("timestamp") or payload.get("closed_at") or timestamp),
        )

    def _build_snapshot(
        self,
        *,
        records: list[AnalyticsTradeRecord],
        all_records: list[AnalyticsTradeRecord],
        run_id: str,
        trading_day: str,
        run_mode: str,
        strategy_key: str | None,
        symbol: str | None,
        setup_family: str | None,
        timestamp: str,
        attempted_trade_count: int,
        blocked_trade_count: int,
        filled_trade_count: int,
        daily_risk_lock_count: int,
        recovery_lock_count: int,
        execution_failure_count: int,
        unrealized_pnl: float,
        source_counts: dict[str, int],
        block_reason_counts: dict[str, int],
        recovery_status_counts: dict[str, int],
        issues: tuple[AnalyticsDataQualityIssue, ...],
    ) -> AnalyticsSnapshot:
        pnl_values = [float(record.realized_pnl) for record in records if record.realized_pnl is not None]
        wins = [value for value in pnl_values if value > 0]
        losses = [value for value in pnl_values if value < 0]
        breakeven = [value for value in pnl_values if value == 0]
        gross_profit = round(sum(wins), 2)
        gross_loss = round(sum(losses), 2)
        realized_pnl = round(sum(pnl_values), 2)
        trade_count = len(records)
        win_count = len(wins)
        loss_count = len(losses)
        breakeven_count = len(breakeven)
        average_win = round(gross_profit / win_count, 2) if win_count else 0.0
        average_loss = round(gross_loss / loss_count, 2) if loss_count else 0.0
        profit_factor = round(abs(gross_profit / gross_loss), 4) if gross_loss else None
        win_rate = round(win_count / trade_count, 4) if trade_count else 0.0
        expectancy = round(realized_pnl / trade_count, 2) if trade_count else 0.0
        max_single_trade_loss = round(min(pnl_values), 2) if pnl_values else 0.0
        max_single_trade_win = round(max(pnl_values), 2) if pnl_values else 0.0

        return AnalyticsSnapshot(
            run_id=run_id,
            trading_day=trading_day,
            run_mode=run_mode,
            strategy_key=strategy_key or "ALL",
            symbol=str(symbol).upper() if symbol else "ALL",
            setup_family=setup_family or "ALL",
            trade_count=trade_count,
            attempted_trade_count=attempted_trade_count,
            blocked_trade_count=blocked_trade_count,
            filled_trade_count=filled_trade_count,
            win_count=win_count,
            loss_count=loss_count,
            breakeven_count=breakeven_count,
            realized_pnl=realized_pnl,
            unrealized_pnl=round(float(unrealized_pnl or 0.0), 2),
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            average_win=average_win,
            average_loss=average_loss,
            profit_factor=profit_factor,
            win_rate=win_rate,
            expectancy=expectancy,
            max_single_trade_loss=max_single_trade_loss,
            max_single_trade_win=max_single_trade_win,
            max_drawdown=self._max_drawdown(pnl_values),
            daily_risk_lock_count=daily_risk_lock_count,
            recovery_lock_count=recovery_lock_count,
            stop_loss_exit_count=self._exit_count(records, "STOP"),
            target_exit_count=self._exit_count(records, "TARGET"),
            trailing_exit_count=self._exit_count(records, "TRAIL"),
            manual_exit_count=self._exit_count(records, "MANUAL"),
            unknown_exit_count=self._unknown_exit_count(records),
            data_quality_issue_count=len(issues),
            execution_failure_count=execution_failure_count,
            timestamp=timestamp,
            incomplete_data=bool(issues),
            source_counts=source_counts,
            block_reason_counts=dict(sorted(block_reason_counts.items())),
            recovery_status_counts=dict(sorted(recovery_status_counts.items())),
            breakdowns=self._breakdowns(all_records, block_reason_counts, recovery_status_counts),
            data_quality_issues=issues,
        )

    def _emit_snapshot(self, snapshot: AnalyticsSnapshot) -> None:
        collector = self.event_collector
        emit = getattr(collector, "emit", None)
        if not callable(emit):
            return
        try:
            emit(
                event_type="ANALYTICS_SNAPSHOT",
                source="AnalyticsAuthority",
                payload=snapshot.to_event_payload(),
            )
        except Exception as exc:
            print(f"[ANALYTICS][AUDIT][FAILED] reason={exc}")

    def _emit_data_quality_issues(self, issues: Iterable[AnalyticsDataQualityIssue]) -> None:
        collector = self.event_collector
        emit = getattr(collector, "emit", None)
        if not callable(emit):
            return
        for issue in issues:
            try:
                emit(
                    event_type="ANALYTICS_DATA_QUALITY_ISSUE",
                    source="AnalyticsAuthority",
                    payload=issue.to_event_payload(),
                )
            except Exception as exc:
                print(f"[ANALYTICS][DATA_QUALITY][AUDIT][FAILED] reason={exc}")

    @staticmethod
    def _filter_records(
        records: list[AnalyticsTradeRecord],
        *,
        strategy_key: str | None,
        symbol: str | None,
        setup_family: str | None,
    ) -> list[AnalyticsTradeRecord]:
        filtered = records
        if strategy_key:
            strategy_u = str(strategy_key).upper()
            filtered = [
                record for record in filtered
                if str(record.strategy_key or "").upper() == strategy_u
            ]
        if symbol:
            symbol_u = str(symbol).upper()
            filtered = [
                record for record in filtered
                if str(record.symbol or "").upper() == symbol_u
            ]
        if setup_family:
            setup_u = str(setup_family).upper()
            filtered = [
                record for record in filtered
                if str(record.setup_family or "").upper() == setup_u
            ]
        return filtered

    @staticmethod
    def _dedupe_records(records: list[AnalyticsTradeRecord]) -> list[AnalyticsTradeRecord]:
        deduped: list[AnalyticsTradeRecord] = []
        seen: set[str] = set()
        ordered = sorted(
            records,
            key=lambda record: (
                0 if str(record.source).startswith("storage.") else 1,
                record.timestamp or "",
                record.symbol or "",
                record.strategy_key or "",
                record.trade_identity,
            ),
        )
        for record in ordered:
            identities = {
                record.trade_identity,
                AnalyticsAuthority._canonical_close_identity(record),
            }
            if seen.intersection(identities):
                continue
            seen.update(identities)
            deduped.append(record)
        return sorted(
            deduped,
            key=lambda record: (
                record.timestamp or "",
                record.symbol or "",
                record.strategy_key or "",
                record.trade_identity,
            ),
        )

    def _breakdowns(
        self,
        records: list[AnalyticsTradeRecord],
        block_reason_counts: dict[str, int],
        recovery_status_counts: dict[str, int],
    ) -> dict[str, dict[str, dict[str, float | int | None]]]:
        dimensions = {
            "trading_day": lambda record: record.trading_day,
            "run_id": lambda record: record.run_id,
            "run_mode": lambda record: record.run_mode,
            "strategy_key": lambda record: record.strategy_key or "UNKNOWN",
            "symbol": lambda record: record.symbol or "UNKNOWN",
            "setup_family": lambda record: record.setup_family or "UNKNOWN",
            "exit_reason": lambda record: record.exit_reason or "UNKNOWN",
        }
        breakdowns = {
            name: self._record_breakdown(records, getter)
            for name, getter in dimensions.items()
        }
        breakdowns["block_reason"] = {
            reason: {"blocked_trade_count": count, "trade_count": 0, "realized_pnl": 0.0}
            for reason, count in sorted(block_reason_counts.items())
        }
        breakdowns["recovery_status"] = {
            status: {"recovery_lock_count": count, "trade_count": 0, "realized_pnl": 0.0}
            for status, count in sorted(recovery_status_counts.items())
        }
        return breakdowns

    @staticmethod
    def _record_breakdown(
        records: list[AnalyticsTradeRecord],
        getter: Any,
    ) -> dict[str, dict[str, float | int | None]]:
        buckets: dict[str, dict[str, float | int | None]] = {}
        for record in records:
            key = str(getter(record) or "UNKNOWN")
            bucket = buckets.setdefault(
                key,
                {
                    "trade_count": 0,
                    "win_count": 0,
                    "loss_count": 0,
                    "breakeven_count": 0,
                    "realized_pnl": 0.0,
                    "win_rate": 0.0,
                    "profit_factor": None,
                },
            )
            bucket["trade_count"] += 1
            pnl = record.realized_pnl
            if pnl is None:
                continue
            bucket["realized_pnl"] = round(float(bucket["realized_pnl"]) + pnl, 2)
            if pnl > 0:
                bucket["win_count"] += 1
            elif pnl < 0:
                bucket["loss_count"] += 1
            else:
                bucket["breakeven_count"] += 1
        for bucket_key, bucket in buckets.items():
            trade_count = int(bucket["trade_count"])
            wins = int(bucket["win_count"])
            losses = int(bucket["loss_count"])
            bucket["win_rate"] = round(wins / trade_count, 4) if trade_count else 0.0
            bucket_records = [
                record for record in records
                if str(getter(record) or "UNKNOWN") == bucket_key
                and record.realized_pnl is not None
            ]
            bucket_profit = sum(
                float(record.realized_pnl or 0.0)
                for record in bucket_records
                if float(record.realized_pnl or 0.0) > 0
            )
            bucket_loss = sum(
                float(record.realized_pnl or 0.0)
                for record in bucket_records
                if float(record.realized_pnl or 0.0) < 0
            )
            if bucket_loss:
                bucket["profit_factor"] = round(abs(bucket_profit / bucket_loss), 4)
        return dict(sorted(buckets.items()))

    @staticmethod
    def _canonical_close_identity(record: AnalyticsTradeRecord) -> str:
        timestamp_bucket = "NO_TIMESTAMP"
        if record.timestamp:
            parsed = AnalyticsAuthority._parse_datetime(record.timestamp)
            timestamp_bucket = parsed.replace(second=0, microsecond=0).isoformat()
        pnl = "NO_PNL" if record.realized_pnl is None else f"{float(record.realized_pnl):.2f}"
        entry = "NO_ENTRY" if record.entry_price is None else f"{float(record.entry_price):.4f}"
        exit_price = "NO_EXIT" if record.exit_price is None else f"{float(record.exit_price):.4f}"
        quantity = "NO_QTY" if record.quantity is None else str(int(record.quantity))
        return "|".join(
            [
                "closed_trade",
                str(record.symbol or "UNKNOWN").upper(),
                str(record.strategy_key or "UNKNOWN").upper(),
                str(record.setup_family or "UNKNOWN").upper(),
                timestamp_bucket,
                pnl,
                quantity,
                entry,
                exit_price,
                str(record.exit_reason or "UNKNOWN").upper(),
            ]
        )

    @staticmethod
    def _counters_from_execution_results(execution_results: Iterable[Any] | None) -> dict[str, int]:
        counters = {"attempted_count": 0, "failure_count": 0}
        for result in list(execution_results or []):
            if bool(getattr(result, "attempted", False)):
                counters["attempted_count"] += 1
            status = str(getattr(result, "status", "") or "").upper()
            if status in {"BLOCKED", "REJECTED", "FAILED", "CANCELLED"}:
                counters["failure_count"] += 1
        return counters

    @staticmethod
    def _empty_counters() -> dict[str, Any]:
        return {
            "record_count": 0,
            "block_reason_counts": {},
            "recovery_status_counts": {},
            "daily_risk_lock_count": 0,
            "recovery_lock_count": 0,
            "execution_failure_count": 0,
        }

    @staticmethod
    def _merge_counts(*counts: dict[str, int]) -> dict[str, int]:
        merged: dict[str, int] = {}
        for count_map in counts:
            for key, value in count_map.items():
                merged[key] = merged.get(key, 0) + int(value or 0)
        return dict(sorted(merged.items()))

    @staticmethod
    def _exit_count(records: list[AnalyticsTradeRecord], marker: str) -> int:
        marker_u = marker.upper()
        count = 0
        for record in records:
            text = str(record.exit_category or record.exit_reason or "").upper()
            if marker_u == "STOP" and "TRAIL" in text:
                continue
            if marker_u in text:
                count += 1
        return count

    @staticmethod
    def _unknown_exit_count(records: list[AnalyticsTradeRecord]) -> int:
        known = {"STOP", "TARGET", "TRAIL", "MANUAL"}
        count = 0
        for record in records:
            text = str(record.exit_category or record.exit_reason or "").upper()
            if not text or text == "UNKNOWN" or not any(marker in text for marker in known):
                count += 1
        return count

    @staticmethod
    def _max_drawdown(pnl_values: list[float]) -> float:
        peak = 0.0
        equity = 0.0
        max_drawdown = 0.0
        for pnl in pnl_values:
            equity += pnl
            peak = max(peak, equity)
            max_drawdown = min(max_drawdown, equity - peak)
        return round(max_drawdown, 2)

    @staticmethod
    def _block_reason(payload: dict[str, Any]) -> str:
        return str(
            payload.get("reason_code")
            or payload.get("reason")
            or payload.get("rationale")
            or "UNKNOWN"
        )

    @staticmethod
    def _has_mismatched_state(payload: dict[str, Any]) -> bool:
        lifecycle_state = str(payload.get("lifecycle_state") or "").upper()
        execution_state = str(payload.get("execution_state") or "").upper()
        if not lifecycle_state or not execution_state:
            return False
        return lifecycle_state == "OPEN" and execution_state in {"CLOSED", "FILLED_EXIT"}

    @staticmethod
    def _first_text(payload: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                return str(value)
        return None

    @staticmethod
    def _pnl_from_payload(payload: dict[str, Any]) -> float | None:
        for key in PNL_KEYS:
            if key not in payload:
                continue
            try:
                return round(float(payload.get(key)), 2)
            except (TypeError, ValueError):
                return None
        return None

    def _optional_float(self, payload: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            if key not in payload or payload.get(key) in (None, ""):
                continue
            try:
                return float(payload.get(key))
            except (TypeError, ValueError):
                return None
        return None

    @staticmethod
    def _optional_int(payload: dict[str, Any], *keys: str) -> int | None:
        for key in keys:
            if key not in payload or payload.get(key) in (None, ""):
                continue
            try:
                return int(payload.get(key))
            except (TypeError, ValueError):
                return None
        return None

    @staticmethod
    def _payload_from_json(payload_json: Any) -> dict[str, Any]:
        if isinstance(payload_json, dict):
            return dict(payload_json)
        if not payload_json:
            return {}
        try:
            decoded = json.loads(str(payload_json))
        except Exception:
            return {}
        return dict(decoded) if isinstance(decoded, dict) else {}

    def _trade_identity(self, payload: dict[str, Any], source: str) -> str:
        for key in (
            "trade_id",
            "trade_outcome_id",
            "event_id",
            "fill_id",
            "execution_id",
            "client_order_id",
            "lifecycle_trade_id",
        ):
            value = payload.get(key)
            if value not in (None, ""):
                return f"{key}:{value}"
        timestamp = self._timestamp(payload.get("timestamp") or payload.get("closed_at"))
        pnl = self._pnl_from_payload(payload)
        return ":".join(
            [
                "fallback",
                source,
                str(payload.get("symbol") or ""),
                timestamp,
                f"{pnl:.8f}" if pnl is not None else "NO_PNL",
            ]
        )

    @staticmethod
    def _float_attr(obj: Any, attr: str, default: float) -> float:
        try:
            return float(getattr(obj, attr, default) or default)
        except (TypeError, ValueError):
            return default

    def _issue(
        self,
        *,
        code: str,
        source: str,
        trade_identity: str,
        field_name: str,
        detail: str,
        timestamp: str,
        severity: str = "WARN",
    ) -> AnalyticsDataQualityIssue:
        return AnalyticsDataQualityIssue(
            issue_id=f"analytics-dq-{uuid4().hex[:12]}",
            code=code,
            severity=severity,
            source=source,
            trade_identity=trade_identity,
            field_name=field_name,
            detail=detail,
            timestamp=timestamp,
        )

    def _trading_day(self, value: Any) -> str:
        parsed = self._parse_datetime(value)
        return parsed.date().isoformat()

    def _timestamp(self, value: Any = None) -> str:
        return self._parse_datetime(value).isoformat()

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, date):
            parsed = datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
        elif value:
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                parsed = datetime.now(timezone.utc)
        else:
            parsed = datetime.now(timezone.utc)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)


__all__ = [
    "AnalyticsAuthority",
    "AnalyticsDataQualityIssue",
    "AnalyticsSnapshot",
    "AnalyticsTradeRecord",
]
