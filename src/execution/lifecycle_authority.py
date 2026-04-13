from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import os
from typing import Any


NON_TERMINAL_STATES = {
    "ENTRY_INTENT_CREATED",
    "ENTRY_SUBMIT_PENDING",
    "ENTRY_ACK_PENDING",
    "ENTRY_WORKING",
    "ENTRY_PARTIAL",
    "POSITION_OPEN_CONFIRMED",
    "EXIT_INTENT_CREATED",
    "EXIT_SUBMIT_PENDING",
    "EXIT_ACK_PENDING",
    "EXIT_WORKING",
    "EXIT_PARTIAL",
    "RECOVERY_ATTACHED",
}

TERMINAL_STATES = {
    "ENTRY_REJECTED",
    "ENTRY_CANCELLED",
    "EXIT_REJECTED",
    "EXIT_CANCELLED",
    "POSITION_CLOSED_CONFIRMED",
    "TRADE_INVALIDATED",
}

CANONICAL_LIFECYCLE_STATES = NON_TERMINAL_STATES | TERMINAL_STATES


@dataclass
class LifecycleStateRecord:
    symbol: str
    trade_id: str | None
    broker_order_id: int | str | None
    lifecycle_state: str
    quantity: int
    filled_quantity: int
    side: str
    entry_exit_role: str
    first_seen_at: datetime
    last_updated_at: datetime
    terminal: bool
    rationale: str

    def to_log_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["first_seen_at"] = self.first_seen_at.isoformat()
        payload["last_updated_at"] = self.last_updated_at.isoformat()
        return payload


@dataclass
class LifecycleTransitionEvent:
    symbol: str
    trade_id: str | None
    from_state: str
    to_state: str
    trigger: str
    timestamp: datetime
    rationale: str

    def to_log_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat()
        return payload


@dataclass
class LifecycleAuthorityVerdict:
    healthy: bool
    active_count: int
    terminal_count: int
    stalled_count: int
    orphan_count: int
    invalid_count: int
    block_new_entries: bool
    block_exit_progression: bool
    rationale: str

    def to_log_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LifecycleAnomaly:
    symbol: str
    trade_id: str | None
    anomaly_type: str
    severity: str
    rationale: str

    def to_log_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any, *, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return fallback


def _entry_state_from_order_state(state: str) -> str:
    mapping = {
        "PENDING_SUBMISSION": "ENTRY_SUBMIT_PENDING",
        "SUBMITTED_PENDING_CONFIRMATION": "ENTRY_ACK_PENDING",
        "SUBMITTED": "ENTRY_ACK_PENDING",
        "ACKNOWLEDGED": "ENTRY_WORKING",
        "WORKING": "ENTRY_WORKING",
        "PARTIALLY_FILLED": "ENTRY_PARTIAL",
        "FILLED": "POSITION_OPEN_CONFIRMED",
        "REJECTED": "ENTRY_REJECTED",
        "CANCELLED": "ENTRY_CANCELLED",
        "EXPIRED": "ENTRY_CANCELLED",
        "INACTIVE": "ENTRY_CANCELLED",
    }
    return mapping.get(state, "ENTRY_INTENT_CREATED")


def _exit_state_from_order_state(state: str) -> str:
    mapping = {
        "PENDING_SUBMISSION": "EXIT_SUBMIT_PENDING",
        "SUBMITTED_PENDING_CONFIRMATION": "EXIT_ACK_PENDING",
        "SUBMITTED": "EXIT_ACK_PENDING",
        "ACKNOWLEDGED": "EXIT_WORKING",
        "WORKING": "EXIT_WORKING",
        "PARTIALLY_FILLED": "EXIT_PARTIAL",
        "FILLED": "POSITION_CLOSED_CONFIRMED",
        "REJECTED": "EXIT_REJECTED",
        "CANCELLED": "EXIT_CANCELLED",
        "EXPIRED": "EXIT_CANCELLED",
        "INACTIVE": "EXIT_CANCELLED",
    }
    return mapping.get(state, "EXIT_INTENT_CREATED")


def _is_terminal_state(state: str) -> bool:
    return state in TERMINAL_STATES


def build_lifecycle_snapshot(orchestrator_or_dependencies: Any, as_of: datetime) -> list[LifecycleStateRecord]:
    print("[LIFECYCLE][SNAPSHOT][START]")
    records: list[LifecycleStateRecord] = []

    trade_registry = getattr(orchestrator_or_dependencies, "trade_registry", None)
    position_snapshot = getattr(orchestrator_or_dependencies, "_latest_position_truth_snapshot", None)
    active_broker_positions = set()
    if position_snapshot is not None and hasattr(position_snapshot, "broker_positions"):
        active_broker_positions = {
            symbol.upper()
            for symbol, row in dict(position_snapshot.broker_positions).items()
            if int(getattr(row, "quantity", 0) or 0) != 0
        }

    if trade_registry is not None and hasattr(trade_registry, "snapshot"):
        for trade in trade_registry.snapshot():
            symbol = str(getattr(trade, "symbol", "") or "").upper()
            if not symbol:
                continue
            trade_id = str(getattr(trade, "lifecycle_trade_id", "") or f"{symbol}:{getattr(trade, 'trader_type', 'unknown')}")
            qty = abs(int(getattr(trade, "quantity", 0) or 0))
            direction = str(getattr(trade, "direction", "") or "LONG").upper()
            side = "SELL" if direction in {"SHORT", "SELL"} else "BUY"
            recovery_tag = str(getattr(trade, "recovery_tag", "") or "")
            if recovery_tag == "broker_attached":
                state = "RECOVERY_ATTACHED"
                rationale = "recovery_attached_trade"
            elif symbol in active_broker_positions:
                state = "POSITION_OPEN_CONFIRMED"
                rationale = "position_truth_confirms_open"
            else:
                state = "ENTRY_WORKING"
                rationale = "active_trade_registry_open_without_broker_confirmation"
            records.append(
                LifecycleStateRecord(
                    symbol=symbol,
                    trade_id=trade_id,
                    broker_order_id=getattr(trade, "ibkr_order_id", None),
                    lifecycle_state=state,
                    quantity=qty,
                    filled_quantity=qty if state in {"POSITION_OPEN_CONFIRMED", "RECOVERY_ATTACHED"} else 0,
                    side=side,
                    entry_exit_role="ENTRY",
                    first_seen_at=as_of,
                    last_updated_at=as_of,
                    terminal=_is_terminal_state(state),
                    rationale=rationale,
                )
            )

    runtime_orders: list[dict[str, Any]] = []
    provider_orders = getattr(orchestrator_or_dependencies, "runtime_order_records", None)
    if callable(provider_orders):
        runtime_orders = list(provider_orders() or [])
    else:
        try:
            from src.execution.order_router import runtime_order_lifecycle_snapshot

            runtime_orders = list(runtime_order_lifecycle_snapshot() or [])
        except Exception:
            runtime_orders = []

    for row in runtime_orders:
        symbol = str(row.get("symbol", "") or "").upper()
        if not symbol:
            continue
        is_exit = bool(row.get("is_exit", False))
        role = "EXIT" if is_exit else "ENTRY"
        order_state = str(row.get("canonical_state", "") or "").upper()
        lifecycle_state = _exit_state_from_order_state(order_state) if is_exit else _entry_state_from_order_state(order_state)
        first_seen = _parse_dt(row.get("first_seen_at"), fallback=as_of)
        last_seen = _parse_dt(row.get("last_update_at"), fallback=as_of)
        quantity = abs(int(row.get("total_qty", 0) or 0))
        filled_qty = abs(int(row.get("filled_qty", 0) or 0))
        if is_exit and lifecycle_state == "POSITION_CLOSED_CONFIRMED":
            closure_evidence = bool(row.get("fill_seen", False)) or bool(row.get("terminal", False))
            if not closure_evidence:
                lifecycle_state = "EXIT_WORKING"
        records.append(
            LifecycleStateRecord(
                symbol=symbol,
                trade_id=str(row.get("intent_id", "") or row.get("order_ref", "") or None),
                broker_order_id=row.get("broker_order_id"),
                lifecycle_state=lifecycle_state,
                quantity=quantity,
                filled_quantity=filled_qty,
                side=str(row.get("side", "") or "UNKNOWN").upper(),
                entry_exit_role=role,
                first_seen_at=first_seen,
                last_updated_at=last_seen,
                terminal=bool(row.get("terminal", False)) or _is_terminal_state(lifecycle_state),
                rationale=f"order_router_state={order_state or 'UNKNOWN'}",
            )
        )

    active = sum(1 for row in records if not row.terminal)
    terminal = sum(1 for row in records if row.terminal)
    print(f"[LIFECYCLE][SNAPSHOT][RESULT] active={active} terminal={terminal}")
    return records


def _stall_thresholds() -> tuple[int, int]:
    warn = int(os.getenv("LIFECYCLE_STALL_WARN_SECONDS", "90") or 90)
    critical = int(os.getenv("LIFECYCLE_STALL_CRITICAL_SECONDS", "180") or 180)
    return warn, max(critical, warn)


def detect_lifecycle_anomalies(
    records: list[LifecycleStateRecord],
    *,
    as_of: datetime,
) -> list[LifecycleAnomaly]:
    warn_seconds, critical_seconds = _stall_thresholds()
    anomalies: list[LifecycleAnomaly] = []

    by_symbol: dict[str, list[LifecycleStateRecord]] = {}
    for record in records:
        by_symbol.setdefault(record.symbol, []).append(record)
        if record.lifecycle_state not in CANONICAL_LIFECYCLE_STATES:
            anomalies.append(
                LifecycleAnomaly(
                    symbol=record.symbol,
                    trade_id=record.trade_id,
                    anomaly_type="INVALID_TRANSITION",
                    severity="CRITICAL",
                    rationale=f"unknown_canonical_state={record.lifecycle_state}",
                )
            )

        if record.entry_exit_role == "ENTRY" and record.lifecycle_state in {
            "ENTRY_SUBMIT_PENDING",
            "ENTRY_ACK_PENDING",
            "ENTRY_WORKING",
            "ENTRY_PARTIAL",
        }:
            age = (as_of - record.last_updated_at).total_seconds()
            if age >= warn_seconds:
                severity = "CRITICAL" if age >= critical_seconds else "WARNING"
                anomalies.append(
                    LifecycleAnomaly(
                        symbol=record.symbol,
                        trade_id=record.trade_id,
                        anomaly_type="STALLED_ENTRY",
                        severity=severity,
                        rationale=f"state={record.lifecycle_state} stalled_seconds={int(age)}",
                    )
                )

        if record.entry_exit_role == "EXIT" and record.lifecycle_state in {
            "EXIT_SUBMIT_PENDING",
            "EXIT_ACK_PENDING",
            "EXIT_WORKING",
            "EXIT_PARTIAL",
        }:
            age = (as_of - record.last_updated_at).total_seconds()
            if age >= warn_seconds:
                severity = "CRITICAL" if age >= critical_seconds else "WARNING"
                anomalies.append(
                    LifecycleAnomaly(
                        symbol=record.symbol,
                        trade_id=record.trade_id,
                        anomaly_type="STALLED_EXIT",
                        severity=severity,
                        rationale=f"state={record.lifecycle_state} stalled_seconds={int(age)}",
                    )
                )

    for symbol, symbol_records in by_symbol.items():
        has_entry = any(r.entry_exit_role == "ENTRY" for r in symbol_records)
        has_exit = any(r.entry_exit_role == "EXIT" for r in symbol_records)
        has_open = any(r.lifecycle_state in {"POSITION_OPEN_CONFIRMED", "RECOVERY_ATTACHED"} for r in symbol_records)
        has_closed_terminal = any(r.lifecycle_state == "POSITION_CLOSED_CONFIRMED" and r.terminal for r in symbol_records)
        working_exit = any(r.entry_exit_role == "EXIT" and not r.terminal for r in symbol_records)
        working_entry = any(r.entry_exit_role == "ENTRY" and not r.terminal for r in symbol_records)

        if working_entry and not has_open and not has_exit:
            anomalies.append(
                LifecycleAnomaly(
                    symbol=symbol,
                    trade_id=None,
                    anomaly_type="ORPHAN_WORKING_ORDER",
                    severity="CRITICAL",
                    rationale="entry_working_without_position_or_exit_attachment",
                )
            )
        if has_exit and not has_open and not has_closed_terminal:
            anomalies.append(
                LifecycleAnomaly(
                    symbol=symbol,
                    trade_id=None,
                    anomaly_type="EXIT_WITHOUT_POSITION",
                    severity="CRITICAL",
                    rationale="exit_lifecycle_present_but_no_position_truth",
                )
            )
        if has_open and not has_entry:
            anomalies.append(
                LifecycleAnomaly(
                    symbol=symbol,
                    trade_id=None,
                    anomaly_type="POSITION_WITHOUT_ENTRY_LIFECYCLE",
                    severity="WARNING",
                    rationale="position_open_without_entry_lifecycle_record",
                )
            )
        if working_exit and not any(r.entry_exit_role == "EXIT" and r.terminal for r in symbol_records):
            older_exit = [r for r in symbol_records if r.entry_exit_role == "EXIT"]
            if older_exit and all((as_of - r.first_seen_at).total_seconds() >= critical_seconds for r in older_exit):
                anomalies.append(
                    LifecycleAnomaly(
                        symbol=symbol,
                        trade_id=None,
                        anomaly_type="TERMINAL_STATE_MISSING",
                        severity="CRITICAL",
                        rationale="exit_lifecycle_missing_terminal_state",
                    )
                )

    for anomaly in anomalies:
        print(
            "[LIFECYCLE][ANOMALY] "
            f"symbol={anomaly.symbol} type={anomaly.anomaly_type} severity={anomaly.severity}"
        )
    return anomalies


def evaluate_lifecycle_authority(
    records: list[LifecycleStateRecord],
    anomalies: list[LifecycleAnomaly],
) -> LifecycleAuthorityVerdict:
    active_count = sum(1 for record in records if not record.terminal)
    terminal_count = sum(1 for record in records if record.terminal)
    stalled_count = sum(1 for anomaly in anomalies if anomaly.anomaly_type in {"STALLED_ENTRY", "STALLED_EXIT"} and anomaly.severity == "CRITICAL")
    orphan_count = sum(1 for anomaly in anomalies if anomaly.anomaly_type == "ORPHAN_WORKING_ORDER")
    invalid_count = sum(1 for anomaly in anomalies if anomaly.anomaly_type in {"INVALID_TRANSITION", "TERMINAL_STATE_MISSING"})
    critical_exit_anomalies = any(
        anomaly.severity == "CRITICAL" and anomaly.anomaly_type in {"EXIT_WITHOUT_POSITION", "STALLED_EXIT", "TERMINAL_STATE_MISSING"}
        for anomaly in anomalies
    )
    critical = any(anomaly.severity == "CRITICAL" for anomaly in anomalies)

    healthy = not critical and stalled_count == 0 and orphan_count == 0 and invalid_count == 0
    block_new_entries = stalled_count > 0 or orphan_count > 0 or invalid_count > 0
    block_exit_progression = critical_exit_anomalies

    rationale = "lifecycle_healthy"
    if invalid_count > 0:
        rationale = "invalid_lifecycle_transition"
    elif orphan_count > 0:
        rationale = "orphan_orders_detected"
    elif stalled_count > 0:
        rationale = "lifecycle_stalled"
    elif block_exit_progression:
        rationale = "exit_lifecycle_untrusted"

    verdict = LifecycleAuthorityVerdict(
        healthy=healthy,
        active_count=active_count,
        terminal_count=terminal_count,
        stalled_count=stalled_count,
        orphan_count=orphan_count,
        invalid_count=invalid_count,
        block_new_entries=block_new_entries,
        block_exit_progression=block_exit_progression,
        rationale=rationale,
    )
    print(
        "[LIFECYCLE][VERDICT] "
        f"healthy={verdict.healthy} active={verdict.active_count} terminal={verdict.terminal_count} "
        f"stalled={verdict.stalled_count} orphan={verdict.orphan_count} invalid={verdict.invalid_count}"
    )
    return verdict


def build_and_evaluate_lifecycle_authority(orchestrator_or_dependencies: Any, *, as_of: datetime | None = None) -> tuple[list[LifecycleStateRecord], list[LifecycleAnomaly], LifecycleAuthorityVerdict]:
    evaluation_time = as_of or _utc_now()
    records = build_lifecycle_snapshot(orchestrator_or_dependencies, evaluation_time)
    anomalies = detect_lifecycle_anomalies(records, as_of=evaluation_time)
    verdict = evaluate_lifecycle_authority(records, anomalies)
    return records, anomalies, verdict
