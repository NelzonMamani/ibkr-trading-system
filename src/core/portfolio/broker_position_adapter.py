from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class BrokerPositionSnapshot:
    symbol: str
    quantity: int
    avg_entry_price: float
    timestamp: str


class BrokerPositionSnapshotAdapter:
    """Best-effort broker snapshot adapter. Never raises to callers."""

    def __init__(self, broker_client: Any | None = None) -> None:
        self._broker_client = broker_client

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def fetch_broker_positions(self) -> list[BrokerPositionSnapshot]:
        if self._broker_client is None:
            print("[LIFECYCLE][BROKER_SNAPSHOT][DEGRADED] reason=no_broker_client")
            return []

        # Use existing broker integration if present.
        if not hasattr(self._broker_client, "get_positions"):
            print("[LIFECYCLE][BROKER_SNAPSHOT][DEGRADED] reason=get_positions_unavailable")
            return []

        try:
            rows = self._broker_client.get_positions()
        except Exception as exc:
            print(f"[LIFECYCLE][BROKER_SNAPSHOT][DEGRADED] reason=fetch_failed error={exc}")
            return []

        snapshots: list[BrokerPositionSnapshot] = []
        for row in rows or []:
            try:
                symbol = str(getattr(row, "symbol", None) or row.get("symbol") or "").upper()
                quantity = int(getattr(row, "quantity", None) or row.get("quantity") or 0)
                avg_entry_price = float(
                    getattr(row, "avg_entry_price", None)
                    or getattr(row, "average_cost", None)
                    or row.get("avg_entry_price")
                    or row.get("average_cost")
                    or 0.0
                )
                if not symbol:
                    continue
                snapshots.append(
                    BrokerPositionSnapshot(
                        symbol=symbol,
                        quantity=quantity,
                        avg_entry_price=avg_entry_price,
                        timestamp=self._now_iso(),
                    )
                )
            except Exception as exc:
                print(f"[LIFECYCLE][BROKER_SNAPSHOT][WARN] reason=row_parse_failed error={exc}")
        return snapshots
