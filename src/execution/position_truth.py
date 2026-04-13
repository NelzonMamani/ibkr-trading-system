from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from src.config.runtime_config import RunMode


CRITICAL_MISMATCH_TYPES = {"BROKER_ONLY_POSITION", "SYSTEM_ONLY_POSITION", "SIGN_MISMATCH", "UNKNOWN_STATE"}
WARNING_MISMATCH_TYPES = {"QUANTITY_MISMATCH"}


@dataclass
class NormalizedBrokerPosition:
    symbol: str
    quantity: int
    avg_cost: float | None
    market_price: float | None
    market_value: float | None
    source: str
    as_of: datetime

    def to_log_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["as_of"] = self.as_of.isoformat()
        return payload


@dataclass
class NormalizedSystemPosition:
    symbol: str
    quantity: int
    source: str
    as_of: datetime

    def to_log_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["as_of"] = self.as_of.isoformat()
        return payload


@dataclass
class PositionMismatch:
    symbol: str
    broker_quantity: int
    system_quantity: int
    mismatch_type: str
    severity: str
    rationale: str

    def to_log_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PositionTruthSnapshot:
    broker_positions: dict[str, NormalizedBrokerPosition]
    system_positions: dict[str, NormalizedSystemPosition]
    mismatches: list[PositionMismatch]
    matched_symbols: list[str]
    unknown_symbols: list[str]
    snapshot_status: str
    as_of: datetime

    def to_log_dict(self) -> dict[str, Any]:
        return {
            "broker_positions": {k: v.to_log_dict() for k, v in self.broker_positions.items()},
            "system_positions": {k: v.to_log_dict() for k, v in self.system_positions.items()},
            "mismatches": [m.to_log_dict() for m in self.mismatches],
            "matched_symbols": list(self.matched_symbols),
            "unknown_symbols": list(self.unknown_symbols),
            "snapshot_status": self.snapshot_status,
            "as_of": self.as_of.isoformat(),
        }


@dataclass
class PositionTruthVerdict:
    healthy: bool
    block_new_entries: bool
    block_exits: bool
    require_reconciliation: bool
    critical_mismatch_count: int
    warning_mismatch_count: int
    rationale: str

    def to_log_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PositionTruthConfig:
    broker_required: bool
    run_mode: RunMode | str


def _normalize_symbol(raw_symbol: Any) -> str:
    return str(raw_symbol or "").strip().upper()


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _read_value(row: Any, key: str, fallback: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, fallback)
    return getattr(row, key, fallback)


def _resolve_position_quantity(row: Any) -> int:
    raw = _read_value(row, "position", None)
    if raw is None:
        raw = _read_value(row, "quantity", 0)
    return int(raw or 0)


def collect_broker_position_snapshot(
    ibkr_client: Any,
    *,
    as_of: datetime,
    config: PositionTruthConfig,
) -> dict[str, NormalizedBrokerPosition]:
    print("[POSITION][BROKER_SNAPSHOT][START]")
    broker_positions: dict[str, NormalizedBrokerPosition] = {}
    mode_label = str(getattr(config.run_mode, "value", config.run_mode) or "UNKNOWN").upper()

    if ibkr_client is None:
        if config.broker_required:
            print(f"[POSITION][BROKER_SNAPSHOT][ERROR] mode={mode_label} reason=missing_client")
        print("[POSITION][BROKER_SNAPSHOT][RESULT] count=0")
        return broker_positions

    if not hasattr(ibkr_client, "positions"):
        if config.broker_required:
            print(f"[POSITION][BROKER_SNAPSHOT][ERROR] mode={mode_label} reason=positions_unavailable")
        print("[POSITION][BROKER_SNAPSHOT][RESULT] count=0")
        return broker_positions

    try:
        rows = ibkr_client.positions() or []
    except Exception as exc:
        print(f"[POSITION][BROKER_SNAPSHOT][ERROR] mode={mode_label} reason=positions_call_failed error={exc}")
        print("[POSITION][BROKER_SNAPSHOT][RESULT] count=0")
        return broker_positions

    for row in rows:
        symbol = _normalize_symbol(_read_value(row, "symbol", ""))
        if not symbol:
            continue
        quantity = _resolve_position_quantity(row)
        if quantity == 0:
            continue
        broker_positions[symbol] = NormalizedBrokerPosition(
            symbol=symbol,
            quantity=quantity,
            avg_cost=_optional_float(_read_value(row, "avgCost", _read_value(row, "avg_cost", _read_value(row, "average_cost")))),
            market_price=_optional_float(_read_value(row, "marketPrice", _read_value(row, "market_price"))),
            market_value=_optional_float(_read_value(row, "marketValue", _read_value(row, "market_value"))),
            source="ibkr.positions",
            as_of=as_of,
        )

    print(f"[POSITION][BROKER_SNAPSHOT][RESULT] count={len(broker_positions)}")
    return broker_positions


def collect_system_position_snapshot(active_trades: list[Any], *, as_of: datetime) -> dict[str, NormalizedSystemPosition]:
    print("[POSITION][SYSTEM_SNAPSHOT][START]")
    positions: dict[str, int] = {}
    for trade in active_trades:
        symbol = _normalize_symbol(getattr(trade, "symbol", ""))
        if not symbol:
            continue
        qty = int(getattr(trade, "quantity", 0) or 0)
        if qty == 0:
            continue
        direction = str(getattr(trade, "direction", "") or "").upper()
        signed_qty = -abs(qty) if direction in {"SHORT", "SELL"} else abs(qty)
        positions[symbol] = positions.get(symbol, 0) + signed_qty

    normalized = {
        symbol: NormalizedSystemPosition(
            symbol=symbol,
            quantity=qty,
            source="active_trade_registry",
            as_of=as_of,
        )
        for symbol, qty in positions.items()
        if qty != 0
    }
    print(f"[POSITION][SYSTEM_SNAPSHOT][RESULT] count={len(normalized)}")
    return normalized


def reconcile_position_truth(
    broker_positions: dict[str, NormalizedBrokerPosition],
    system_positions: dict[str, NormalizedSystemPosition],
    *,
    as_of: datetime,
    live_broker_mode: bool,
) -> tuple[PositionTruthSnapshot, PositionTruthVerdict]:
    print("[POSITION][RECONCILE][START]")
    all_symbols = sorted(set(broker_positions.keys()) | set(system_positions.keys()))
    mismatches: list[PositionMismatch] = []
    matched_symbols: list[str] = []
    unknown_symbols: list[str] = []

    for symbol in all_symbols:
        broker_qty = int(broker_positions.get(symbol).quantity) if symbol in broker_positions else 0
        system_qty = int(system_positions.get(symbol).quantity) if symbol in system_positions else 0

        mismatch: PositionMismatch | None = None
        if symbol in broker_positions and symbol not in system_positions:
            mismatch = PositionMismatch(
                symbol=symbol,
                broker_quantity=broker_qty,
                system_quantity=0,
                mismatch_type="BROKER_ONLY_POSITION",
                severity="CRITICAL",
                rationale="Broker reports an open position that runtime state does not track.",
            )
        elif symbol in system_positions and symbol not in broker_positions:
            mismatch = PositionMismatch(
                symbol=symbol,
                broker_quantity=0,
                system_quantity=system_qty,
                mismatch_type="SYSTEM_ONLY_POSITION" if live_broker_mode else "UNKNOWN_STATE",
                severity="CRITICAL" if live_broker_mode else "WARNING",
                rationale="Runtime tracks a position that broker snapshot does not confirm.",
            )
        elif broker_qty == 0 and system_qty == 0:
            continue
        elif broker_qty == system_qty:
            matched_symbols.append(symbol)
        elif broker_qty * system_qty < 0:
            mismatch = PositionMismatch(
                symbol=symbol,
                broker_quantity=broker_qty,
                system_quantity=system_qty,
                mismatch_type="SIGN_MISMATCH",
                severity="CRITICAL",
                rationale="Broker and runtime disagree on long/short side.",
            )
        elif broker_qty != system_qty:
            mismatch = PositionMismatch(
                symbol=symbol,
                broker_quantity=broker_qty,
                system_quantity=system_qty,
                mismatch_type="QUANTITY_MISMATCH",
                severity="WARNING",
                rationale="Broker and runtime quantities differ for same-side exposure.",
            )
        else:
            mismatch = PositionMismatch(
                symbol=symbol,
                broker_quantity=broker_qty,
                system_quantity=system_qty,
                mismatch_type="UNKNOWN_STATE",
                severity="CRITICAL",
                rationale="Position state could not be reconciled deterministically.",
            )

        if mismatch is not None:
            if mismatch.mismatch_type == "UNKNOWN_STATE":
                unknown_symbols.append(symbol)
            mismatches.append(mismatch)
            print(
                "[POSITION][MISMATCH] "
                f"symbol={mismatch.symbol} type={mismatch.mismatch_type} "
                f"broker_qty={mismatch.broker_quantity} system_qty={mismatch.system_quantity} severity={mismatch.severity}"
            )

    critical_count = sum(1 for mismatch in mismatches if mismatch.severity.upper() == "CRITICAL")
    warning_count = sum(1 for mismatch in mismatches if mismatch.severity.upper() == "WARNING")
    require_reconciliation = bool(mismatches)
    healthy = critical_count == 0 and warning_count == 0
    block_new_entries = critical_count > 0
    block_exits = any(m.mismatch_type in {"BROKER_ONLY_POSITION", "SIGN_MISMATCH", "UNKNOWN_STATE"} for m in mismatches)

    snapshot_status = "HEALTHY" if healthy else "MISMATCH"
    snapshot = PositionTruthSnapshot(
        broker_positions=broker_positions,
        system_positions=system_positions,
        mismatches=mismatches,
        matched_symbols=matched_symbols,
        unknown_symbols=unknown_symbols,
        snapshot_status=snapshot_status,
        as_of=as_of,
    )
    verdict = PositionTruthVerdict(
        healthy=healthy,
        block_new_entries=block_new_entries,
        block_exits=block_exits,
        require_reconciliation=require_reconciliation,
        critical_mismatch_count=critical_count,
        warning_mismatch_count=warning_count,
        rationale="position_truth_healthy" if healthy else "position_truth_mismatch_detected",
    )
    print(
        "[POSITION][RECONCILE][SUMMARY] "
        f"healthy={verdict.healthy} critical={critical_count} warning={warning_count} "
        f"block_new_entries={verdict.block_new_entries} block_exits={verdict.block_exits}"
    )
    return snapshot, verdict


def empty_position_truth_snapshot(*, as_of: datetime) -> PositionTruthSnapshot:
    return PositionTruthSnapshot(
        broker_positions={},
        system_positions={},
        mismatches=[],
        matched_symbols=[],
        unknown_symbols=[],
        snapshot_status="SKIPPED",
        as_of=as_of,
    )


def healthy_position_truth_verdict() -> PositionTruthVerdict:
    return PositionTruthVerdict(
        healthy=True,
        block_new_entries=False,
        block_exits=False,
        require_reconciliation=False,
        critical_mismatch_count=0,
        warning_mismatch_count=0,
        rationale="position_truth_not_required",
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
