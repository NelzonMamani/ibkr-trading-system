from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


class ExecutionIntegrityError(RuntimeError):
    """Raised when a fill violates execution truth invariants."""


@dataclass(frozen=True)
class ExecutionRecord:
    exec_id: str
    order_id: int
    symbol: str
    side: str
    qty: int
    price: float
    timestamp: str
    source: str = "execDetails"


class ExecutionLedger:
    """Append-only, execDetails-authoritative execution ledger."""

    def __init__(self) -> None:
        self._records: list[ExecutionRecord] = []
        self._index_by_exec_id: dict[str, ExecutionRecord] = {}

    def append_from_exec_details(
        self,
        *,
        exec_id: str | None,
        order_id: int,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        timestamp: str,
    ) -> ExecutionRecord:
        normalized_exec_id = str(exec_id or "").strip()
        if not normalized_exec_id:
            raise ExecutionIntegrityError("Missing exec_id from execDetails")
        if normalized_exec_id.upper().startswith("BACKFILL"):
            raise ExecutionIntegrityError("Synthetic exec_id forbidden")
        if normalized_exec_id in self._index_by_exec_id:
            raise ExecutionIntegrityError(f"Duplicate exec_id forbidden: {normalized_exec_id}")

        normalized_symbol = str(symbol or "").upper().strip()
        normalized_side = str(side or "").upper().strip()
        normalized_qty = int(qty)
        normalized_price = float(price)
        if normalized_qty <= 0:
            raise ExecutionIntegrityError("Zero or negative fill detected")
        if normalized_price <= 0:
            raise ExecutionIntegrityError("Non-positive fill price detected")

        record = ExecutionRecord(
            exec_id=normalized_exec_id,
            order_id=int(order_id),
            symbol=normalized_symbol,
            side=normalized_side,
            qty=normalized_qty,
            price=normalized_price,
            timestamp=str(timestamp),
        )
        self._records.append(record)
        self._index_by_exec_id[normalized_exec_id] = record
        print(
            "[EXECUTION][LEDGER_APPEND] "
            f"exec_id={record.exec_id} symbol={record.symbol} qty={record.qty} price={record.price}"
        )
        return record

    def has_exec_id(self, exec_id: str | None) -> bool:
        normalized_exec_id = str(exec_id or "").strip()
        return bool(normalized_exec_id) and normalized_exec_id in self._index_by_exec_id

    def records(self) -> tuple[ExecutionRecord, ...]:
        return tuple(self._records)

    def iter_symbol(self, symbol: str) -> Iterable[ExecutionRecord]:
        normalized = str(symbol or "").upper().strip()
        for record in self._records:
            if record.symbol == normalized:
                yield record

    def derive_positions(self) -> dict[str, dict[str, float]]:
        aggregates: dict[str, dict[str, float]] = {}
        for record in self._records:
            signed_qty = record.qty if record.side == "BUY" else -record.qty
            row = aggregates.setdefault(record.symbol, {"signed_qty": 0.0, "signed_notional": 0.0})
            row["signed_qty"] += float(signed_qty)
            row["signed_notional"] += float(signed_qty) * float(record.price)
        derived: dict[str, dict[str, float]] = {}
        for symbol, row in aggregates.items():
            qty = int(row["signed_qty"])
            avg = 0.0
            if qty != 0:
                avg = float(row["signed_notional"]) / float(qty)
            derived[symbol] = {"qty": qty, "avg_price": avg}
        return derived

    def analytics(self) -> dict[str, int]:
        unique_order_ids = {record.order_id for record in self._records}
        positions_opened = 0
        per_symbol_net: dict[str, int] = {}
        for record in self._records:
            prior = per_symbol_net.get(record.symbol, 0)
            delta = record.qty if record.side == "BUY" else -record.qty
            nxt = prior + delta
            if prior <= 0 < nxt:
                positions_opened += 1
            per_symbol_net[record.symbol] = nxt
        return {
            "filled_orders": len(unique_order_ids),
            "total_fills": len(self._records),
            "positions_opened": positions_opened,
        }

    def clear(self) -> None:
        self._records.clear()
        self._index_by_exec_id.clear()


EXECUTION_LEDGER = ExecutionLedger()
