"""Position ownership engine derived strictly from execution lineage."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def compute_positions_from_executions(
    executions: list[dict[str, Any]],
    broker_positions_by_symbol: dict[str, int] | None = None,
) -> dict[str, dict[str, int]]:
    """Compute system/external/broker quantities by symbol.

    System quantity is derived only from execution lineage rows tagged with
    order_ref prefix ``ROSS::``.
    """

    broker_positions = {str(k).upper(): int(v) for k, v in (broker_positions_by_symbol or {}).items()}
    system_qty_by_symbol: dict[str, int] = defaultdict(int)
    symbols: set[str] = set(broker_positions.keys())

    for row in executions:
        symbol = str(row.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        symbols.add(symbol)
        order_ref = str(row.get("order_ref") or "").strip()
        side = str(row.get("side") or "").upper().strip()
        qty = int(row.get("quantity") or 0)
        if not order_ref.startswith("ROSS::"):
            continue
        if side == "BUY":
            system_qty_by_symbol[symbol] += qty
        elif side == "SELL":
            system_qty_by_symbol[symbol] -= qty

    result: dict[str, dict[str, int]] = {}
    for symbol in sorted(symbols):
        broker_qty = int(broker_positions.get(symbol, 0))
        system_qty = int(system_qty_by_symbol.get(symbol, 0))
        result[symbol] = {
            "system_qty": system_qty,
            "external_qty": broker_qty - system_qty,
            "broker_qty": broker_qty,
        }
    return result
