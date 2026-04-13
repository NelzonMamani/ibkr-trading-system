from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from src.core_engine.state import RunMode


@dataclass
class ExecutionEvent:
    order_id: str | int
    symbol: str
    side: str
    filled_qty: int
    fill_price: float | None
    timestamp: datetime
    source: str

    def to_log_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat()
        return payload


@dataclass
class ExecutionRecord:
    order_id: str | int
    symbol: str
    total_qty: int
    filled_qty: int
    avg_fill_price: float | None
    status: str
    has_exec_details: bool
    first_seen: datetime
    last_update: datetime

    def to_log_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["first_seen"] = self.first_seen.isoformat()
        payload["last_update"] = self.last_update.isoformat()
        return payload


@dataclass
class ExecutionDelayClassification:
    order_id: str | int
    symbol: str
    state: str
    seconds_since_submit: float
    rationale: str

    def to_log_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FillAuthorityVerdict:
    healthy: bool
    missing_exec_count: int
    delayed_exec_count: int
    stalled_exec_count: int
    block_position_updates: bool
    block_new_entries: bool
    rationale: str

    def to_log_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_dt(value: Any, *, default: datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return default
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return default


def _runtime_rows(execution_engine_or_registry: Any) -> list[Any]:
    if execution_engine_or_registry is None:
        return []
    if hasattr(execution_engine_or_registry, "runtime_orders_snapshot"):
        snap = execution_engine_or_registry.runtime_orders_snapshot()
        if isinstance(snap, dict):
            return list(snap.values())
        return list(snap or [])
    if isinstance(execution_engine_or_registry, dict):
        return list(execution_engine_or_registry.values())
    return list(execution_engine_or_registry or [])


def build_execution_records(execution_engine_or_registry: Any, as_of: datetime) -> dict[str | int, ExecutionRecord]:
    print("[EXECUTION][RECORDS][START]")
    records: dict[str | int, ExecutionRecord] = {}
    for row in _runtime_rows(execution_engine_or_registry):
        order_id = getattr(row, "broker_order_id", None) if not isinstance(row, dict) else row.get("broker_order_id")
        if order_id is None:
            continue
        symbol = str((getattr(row, "symbol", "") if not isinstance(row, dict) else row.get("symbol", "")) or "").upper()
        if not symbol:
            symbol = "UNKNOWN"
        total_qty = int((getattr(row, "total_qty", 0) if not isinstance(row, dict) else row.get("total_qty", 0)) or 0)
        filled_qty = int((getattr(row, "filled_qty", 0) if not isinstance(row, dict) else row.get("filled_qty", 0)) or 0)
        avg_fill_price_raw = getattr(row, "avg_fill_price", None) if not isinstance(row, dict) else row.get("avg_fill_price")
        avg_fill_price = float(avg_fill_price_raw) if avg_fill_price_raw is not None else None
        status_raw = getattr(row, "canonical_state", "PRE_SUBMITTED") if not isinstance(row, dict) else row.get("canonical_state", "PRE_SUBMITTED")
        status = str(status_raw or "PRE_SUBMITTED").upper()
        first_seen = _parse_dt(
            getattr(row, "first_seen_at", None) if not isinstance(row, dict) else row.get("first_seen_at"),
            default=as_of,
        )
        last_update = _parse_dt(
            getattr(row, "last_update_at", None) if not isinstance(row, dict) else row.get("last_update_at"),
            default=as_of,
        )
        has_exec_details = filled_qty > 0 and avg_fill_price is not None
        records[order_id] = ExecutionRecord(
            order_id=order_id,
            symbol=symbol,
            total_qty=total_qty,
            filled_qty=filled_qty,
            avg_fill_price=avg_fill_price,
            status=status,
            has_exec_details=has_exec_details,
            first_seen=first_seen,
            last_update=last_update,
        )
    print(f"[EXECUTION][RECORDS][RESULT] count={len(records)}")
    return records


def _delay_threshold(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except ValueError:
        return float(default)


def classify_execution_delays(
    records: dict[str | int, ExecutionRecord],
    as_of: datetime,
    *,
    run_mode: RunMode | str | None = None,
) -> list[ExecutionDelayClassification]:
    mode = str(getattr(run_mode, "value", run_mode) or "").upper()
    if mode == "SIM":
        return []
    warn_seconds = _delay_threshold("EXEC_CALLBACK_DELAY_WARN_SECONDS", 5.0)
    stall_seconds = _delay_threshold("EXEC_CALLBACK_DELAY_STALL_SECONDS", 20.0)
    delays: list[ExecutionDelayClassification] = []
    for record in records.values():
        if record.total_qty > 0 and record.filled_qty >= record.total_qty:
            state = "COMPLETE"
            seconds = max(0.0, (as_of - record.first_seen).total_seconds())
            rationale = "execution_complete"
        elif record.has_exec_details:
            state = "PENDING_CALLBACK"
            seconds = max(0.0, (as_of - record.first_seen).total_seconds())
            rationale = "partial_execdetails_seen"
        else:
            seconds = max(0.0, (as_of - record.first_seen).total_seconds())
            if seconds >= stall_seconds:
                state = "STALLED"
                rationale = "execdetails_missing_stall_threshold"
            elif seconds >= warn_seconds:
                state = "DELAYED"
                rationale = "execdetails_missing_warn_threshold"
            else:
                state = "PENDING_CALLBACK"
                rationale = "awaiting_execdetails_callback"
        delay = ExecutionDelayClassification(
            order_id=record.order_id,
            symbol=record.symbol,
            state=state,
            seconds_since_submit=seconds,
            rationale=rationale,
        )
        print(
            f"[EXECUTION][DELAY] order_id={delay.order_id} symbol={delay.symbol} "
            f"state={delay.state} seconds={delay.seconds_since_submit:.2f}"
        )
        delays.append(delay)
    return delays


def evaluate_fill_authority(
    records: dict[str | int, ExecutionRecord],
    delays: list[ExecutionDelayClassification],
    *,
    run_mode: RunMode | str | None = None,
) -> FillAuthorityVerdict:
    mode = str(getattr(run_mode, "value", run_mode) or "").upper()
    if mode == "SIM":
        verdict = FillAuthorityVerdict(
            healthy=True,
            missing_exec_count=0,
            delayed_exec_count=0,
            stalled_exec_count=0,
            block_position_updates=False,
            block_new_entries=False,
            rationale="sim_mode_skip",
        )
        print("[EXECUTION][VERDICT] healthy=True missing=0 delayed=0 stalled=0")
        return verdict

    implied_fill_states = {"PARTIAL", "PARTIALLY_FILLED", "FILLED"}
    missing_exec_count = 0
    for record in records.values():
        if record.status in implied_fill_states and not record.has_exec_details:
            missing_exec_count += 1

    delayed_exec_count = sum(1 for delay in delays if delay.state == "DELAYED")
    stalled_exec_count = sum(1 for delay in delays if delay.state == "STALLED")

    healthy = missing_exec_count == 0 and stalled_exec_count == 0
    if stalled_exec_count > 0:
        rationale = "execution_stalled"
    elif missing_exec_count > 0:
        rationale = "missing_exec_details_detected"
    elif delayed_exec_count > 0:
        rationale = "execution_callbacks_delayed"
    else:
        rationale = "execution_truth_healthy"
    verdict = FillAuthorityVerdict(
        healthy=healthy,
        missing_exec_count=missing_exec_count,
        delayed_exec_count=delayed_exec_count,
        stalled_exec_count=stalled_exec_count,
        block_position_updates=missing_exec_count > 0 or stalled_exec_count > 0,
        block_new_entries=stalled_exec_count > 0,
        rationale=rationale,
    )
    print(
        "[EXECUTION][VERDICT] "
        f"healthy={verdict.healthy} missing={verdict.missing_exec_count} "
        f"delayed={verdict.delayed_exec_count} stalled={verdict.stalled_exec_count}"
    )
    return verdict
