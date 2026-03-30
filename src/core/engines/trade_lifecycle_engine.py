from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


OPEN_STATUSES = {"OPEN", "PARTIALLY_CLOSED"}


@dataclass
class LifecycleEvent:
    event_id: str
    lifecycle_trade_id: str
    symbol: str
    side: str
    event_type: str
    quantity: int
    price: float
    timestamp: str
    order_id: str | None = None
    execution_id: str | None = None
    source: str = "execution_engine"


@dataclass
class LifecycleTrade:
    lifecycle_trade_id: str
    symbol: str
    side: str
    strategy_name: str | None
    status: str
    opened_at: str
    closed_at: str | None = None
    quantity_open: int = 0
    quantity_closed: int = 0
    entry_avg_price: float = 0.0
    exit_avg_price: float | None = None
    stop_price: float | None = None
    gross_realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    last_mark_price: float | None = None
    source_order_ids: set[str] = field(default_factory=set)
    source_execution_ids: set[str] = field(default_factory=set)
    reconciliation_flags: set[str] = field(default_factory=set)
    drift_flags: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)


class TradeLifecycleEngine:
    """Canonical observer-only lifecycle authority with durable accounting."""

    def __init__(self, persistence_adapter: Any | None = None) -> None:
        self._trades: dict[str, LifecycleTrade] = {}
        self._symbol_to_open_trade_id: dict[str, str] = {}
        self._event_ids_seen: set[str] = set()
        self._order_execution_keys_seen: set[str] = set()
        self._events: list[LifecycleEvent] = []
        self._reconciliation_events: list[dict[str, Any]] = []
        self._persistence = persistence_adapter
        self._session_counts = {
            "total_lifecycle_trades_seen": 0,
            "reconciliation_events_count": 0,
            "duplicate_events_ignored": 0,
        }

    def set_persistence_adapter(self, persistence_adapter: Any | None) -> None:
        self._persistence = persistence_adapter

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _persist_trade_snapshot_best_effort(self, trade: LifecycleTrade) -> None:
        if self._persistence is None:
            return
        payload = {
            "lifecycle_trade_id": trade.lifecycle_trade_id,
            "symbol": trade.symbol,
            "side": trade.side,
            "strategy_name": trade.strategy_name,
            "status": trade.status,
            "opened_at": trade.opened_at,
            "closed_at": trade.closed_at,
            "quantity_open": trade.quantity_open,
            "quantity_closed": trade.quantity_closed,
            "entry_avg_price": trade.entry_avg_price,
            "exit_avg_price": trade.exit_avg_price,
            "stop_price": trade.stop_price,
            "gross_realized_pnl": trade.gross_realized_pnl,
            "unrealized_pnl": trade.unrealized_pnl,
            "last_mark_price": trade.last_mark_price,
            "source_order_ids_json": str(sorted(trade.source_order_ids)),
            "source_execution_ids_json": str(sorted(trade.source_execution_ids)),
            "reconciliation_flags_json": str(sorted(trade.reconciliation_flags)),
            "drift_flags_json": str(sorted(trade.drift_flags)),
            "notes_json": str(trade.notes),
            "updated_at": self._now_iso(),
        }
        try:
            self._persistence.upsert_trade_lifecycle_trade(payload)
        except Exception as exc:
            print(f"[LIFECYCLE][ERROR] stage=persist_trade_snapshot error={exc}")

    def _persist_event_best_effort(self, event: LifecycleEvent) -> None:
        if self._persistence is None:
            return
        try:
            self._persistence.insert_trade_lifecycle_event({**asdict(event), "timestamp": event.timestamp})
        except Exception as exc:
            print(f"[LIFECYCLE][ERROR] stage=persist_event event_id={event.event_id} error={exc}")

    def _persist_reconciliation_best_effort(self, payload: dict[str, Any]) -> None:
        if self._persistence is None:
            return
        try:
            self._persistence.insert_trade_lifecycle_reconciliation_event(payload)
        except Exception as exc:
            print(f"[LIFECYCLE][ERROR] stage=persist_reconcile error={exc}")

    def recover_open_state(self) -> dict[str, Any]:
        print("[LIFECYCLE][RECOVERY][START]")
        if self._persistence is None:
            print("[LIFECYCLE][RECOVERY][DEGRADED] reason=no_persistence_adapter")
            return {"ok": False, "open_loaded": 0, "degraded": True}
        try:
            records = self._persistence.fetch_trade_lifecycle_trades()
        except Exception as exc:
            print(f"[LIFECYCLE][RECOVERY][DEGRADED] reason=load_failed error={exc}")
            return {"ok": False, "open_loaded": 0, "degraded": True}
        if not records:
            print("[LIFECYCLE][RECOVERY][EMPTY]")
            return {"ok": True, "open_loaded": 0, "degraded": False}
        for row in records:
            trade = LifecycleTrade(
                lifecycle_trade_id=str(row["lifecycle_trade_id"]),
                symbol=str(row.get("symbol") or ""),
                side=str(row.get("side") or "LONG").upper(),
                strategy_name=row.get("strategy_name"),
                status=str(row.get("status") or "OPEN"),
                opened_at=str(row.get("opened_at") or self._now_iso()),
                closed_at=row.get("closed_at"),
                quantity_open=int(row.get("quantity_open") or 0),
                quantity_closed=int(row.get("quantity_closed") or 0),
                entry_avg_price=float(row.get("entry_avg_price") or 0.0),
                exit_avg_price=(
                    float(row["exit_avg_price"]) if row.get("exit_avg_price") is not None else None
                ),
                stop_price=float(row["stop_price"]) if row.get("stop_price") is not None else None,
                gross_realized_pnl=float(row.get("gross_realized_pnl") or 0.0),
                unrealized_pnl=float(row.get("unrealized_pnl") or 0.0),
                last_mark_price=(
                    float(row["last_mark_price"]) if row.get("last_mark_price") is not None else None
                ),
            )
            self._trades[trade.lifecycle_trade_id] = trade
            if trade.status in OPEN_STATUSES and trade.quantity_open > 0:
                self._symbol_to_open_trade_id[trade.symbol] = trade.lifecycle_trade_id
        loaded = len(self._symbol_to_open_trade_id)
        print(f"[LIFECYCLE][RECOVERY][LOADED] records={len(records)} open={loaded}")
        return {"ok": True, "open_loaded": loaded, "degraded": False}

    def apply_event(self, event: LifecycleEvent, *, strategy_name: str | None = None, stop_price: float | None = None) -> LifecycleTrade | None:
        if event.event_id in self._event_ids_seen:
            self._session_counts["duplicate_events_ignored"] += 1
            print(f"[LIFECYCLE][EVENT][DUPLICATE] event_id={event.event_id}")
            return self._trades.get(event.lifecycle_trade_id)
        dedupe_key = f"{event.order_id or ''}:{event.execution_id or ''}:{event.event_type}:{event.quantity}:{event.price}"
        if dedupe_key != ":::0:0.0" and dedupe_key in self._order_execution_keys_seen:
            self._session_counts["duplicate_events_ignored"] += 1
            print(f"[LIFECYCLE][EVENT][DUPLICATE] dedupe_key={dedupe_key}")
            return self._trades.get(event.lifecycle_trade_id)

        self._event_ids_seen.add(event.event_id)
        self._order_execution_keys_seen.add(dedupe_key)
        self._events.append(event)
        self._persist_event_best_effort(event)

        if event.event_type == "ENTRY_FILL":
            trade = self.apply_entry_fill(event=event, strategy_name=strategy_name, stop_price=stop_price)
        else:
            trade = self.apply_exit_fill(event=event)
        if trade:
            self._persist_trade_snapshot_best_effort(trade)
        return trade

    def apply_entry_fill(self, *, event: LifecycleEvent, strategy_name: str | None = None, stop_price: float | None = None) -> LifecycleTrade:
        trade = self._trades.get(event.lifecycle_trade_id)
        if trade is None:
            trade = LifecycleTrade(
                lifecycle_trade_id=event.lifecycle_trade_id,
                symbol=event.symbol,
                side=event.side,
                strategy_name=strategy_name,
                status="OPEN",
                opened_at=event.timestamp,
            )
            self._trades[trade.lifecycle_trade_id] = trade
            self._session_counts["total_lifecycle_trades_seen"] += 1
        prior_open = max(trade.quantity_open, 0)
        trade.quantity_open = prior_open + int(event.quantity)
        if trade.quantity_open > 0:
            trade.entry_avg_price = (
                ((trade.entry_avg_price * prior_open) + (event.price * event.quantity))
                / float(trade.quantity_open)
            )
        if stop_price is not None:
            trade.stop_price = float(stop_price)
        trade.status = "OPEN" if trade.quantity_closed == 0 else "PARTIALLY_CLOSED"
        if event.order_id:
            trade.source_order_ids.add(str(event.order_id))
        if event.execution_id:
            trade.source_execution_ids.add(str(event.execution_id))
        self._symbol_to_open_trade_id[trade.symbol] = trade.lifecycle_trade_id
        return trade

    def apply_exit_fill(self, *, event: LifecycleEvent) -> LifecycleTrade | None:
        trade = self._trades.get(event.lifecycle_trade_id)
        if trade is None:
            print(f"[LIFECYCLE][WARN] exit_without_trade trade_id={event.lifecycle_trade_id}")
            return None
        exit_qty = min(int(event.quantity), max(trade.quantity_open, 0))
        if exit_qty <= 0:
            return trade
        trade.quantity_open -= exit_qty
        trade.quantity_closed += exit_qty
        sign = 1.0 if trade.side == "LONG" else -1.0
        trade.gross_realized_pnl += (event.price - trade.entry_avg_price) * float(exit_qty) * sign
        total_closed = max(trade.quantity_closed, 1)
        prior_closed = total_closed - exit_qty
        if trade.exit_avg_price is None:
            trade.exit_avg_price = event.price
        else:
            trade.exit_avg_price = ((trade.exit_avg_price * prior_closed) + (event.price * exit_qty)) / float(total_closed)
        if event.order_id:
            trade.source_order_ids.add(str(event.order_id))
        if event.execution_id:
            trade.source_execution_ids.add(str(event.execution_id))
        if trade.quantity_open == 0:
            trade.status = "CLOSED"
            trade.closed_at = event.timestamp
            trade.unrealized_pnl = 0.0
            if self._symbol_to_open_trade_id.get(trade.symbol) == trade.lifecycle_trade_id:
                self._symbol_to_open_trade_id.pop(trade.symbol, None)
        else:
            trade.status = "PARTIALLY_CLOSED"
        return trade

    def apply_mark_price(self, *, trade_id: str, price: float) -> LifecycleTrade | None:
        trade = self._trades.get(trade_id)
        if trade is None:
            return None
        current_price = float(price)
        trade.last_mark_price = current_price
        if trade.status in OPEN_STATUSES and trade.quantity_open > 0:
            sign = 1.0 if trade.side == "LONG" else -1.0
            trade.unrealized_pnl = (current_price - trade.entry_avg_price) * float(trade.quantity_open) * sign
        else:
            trade.unrealized_pnl = 0.0
        self._persist_trade_snapshot_best_effort(trade)
        return trade

    def mark_to_market(self, *, trade_id: str, price: float) -> LifecycleTrade | None:
        return self.apply_mark_price(trade_id=trade_id, price=price)

    def reconcile_position(self, *, trade_id: str, closed: bool) -> LifecycleTrade | None:
        trade = self._trades.get(trade_id)
        if trade is None:
            return None
        if closed:
            self.apply_reconciliation_snapshot(
                symbol=trade.symbol,
                runtime_quantity=0,
                runtime_avg_entry=trade.entry_avg_price,
            )
        return self._trades.get(trade_id)

    def apply_reconciliation_snapshot(
        self,
        *,
        symbol: str,
        runtime_quantity: int,
        runtime_avg_entry: float | None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        ts = timestamp or self._now_iso()
        open_trade_id = self.find_open_trade_id_for_symbol(symbol)
        finding: dict[str, Any]
        if open_trade_id is None and runtime_quantity > 0:
            finding = {
                "reconciliation_id": str(uuid4()),
                "lifecycle_trade_id": None,
                "symbol": symbol,
                "status": "ORPHANED",
                "finding_type": "runtime_position_without_lifecycle_trade",
                "details_json": str({"runtime_quantity": runtime_quantity, "runtime_avg_entry": runtime_avg_entry}),
                "timestamp": ts,
            }
            print(f"[LIFECYCLE][RECONCILE][ORPHAN] symbol={symbol} runtime_qty={runtime_quantity}")
            self._session_counts["reconciliation_events_count"] += 1
            self._persist_reconciliation_best_effort(finding)
            self._reconciliation_events.append(finding)
            return finding
        if open_trade_id is None:
            finding = {
                "reconciliation_id": str(uuid4()),
                "lifecycle_trade_id": None,
                "symbol": symbol,
                "status": "MATCH",
                "finding_type": "no_open_position",
                "details_json": "{}",
                "timestamp": ts,
            }
            print(f"[LIFECYCLE][RECONCILE][MATCH] symbol={symbol} state=flat")
            self._persist_reconciliation_best_effort(finding)
            self._reconciliation_events.append(finding)
            return finding
        trade = self._trades[open_trade_id]
        if runtime_quantity <= 0:
            trade.status = "ORPHANED"
            trade.reconciliation_flags.add("RECONCILE_CLOSE_APPLIED")
            trade.closed_at = ts
            trade.quantity_closed += trade.quantity_open
            trade.quantity_open = 0
            trade.unrealized_pnl = 0.0
            self._symbol_to_open_trade_id.pop(symbol, None)
            finding = {
                "reconciliation_id": str(uuid4()),
                "lifecycle_trade_id": trade.lifecycle_trade_id,
                "symbol": symbol,
                "status": "ORPHANED",
                "finding_type": "lifecycle_open_without_runtime_position",
                "details_json": str({"action": "safe_reconcile_close"}),
                "timestamp": ts,
            }
            print(f"[LIFECYCLE][RECONCILE][RECOVER] symbol={symbol} action=close_orphan trade_id={trade.lifecycle_trade_id}")
            self._persist_trade_snapshot_best_effort(trade)
        elif runtime_quantity != trade.quantity_open:
            trade.status = "DRIFTED"
            trade.drift_flags.add("QTY_MISMATCH")
            finding = {
                "reconciliation_id": str(uuid4()),
                "lifecycle_trade_id": trade.lifecycle_trade_id,
                "symbol": symbol,
                "status": "DRIFTED",
                "finding_type": "quantity_mismatch",
                "details_json": str({"runtime_quantity": runtime_quantity, "lifecycle_quantity": trade.quantity_open}),
                "timestamp": ts,
            }
            print(f"[LIFECYCLE][RECONCILE][DRIFT] symbol={symbol} runtime_qty={runtime_quantity} lifecycle_qty={trade.quantity_open}")
            self._persist_trade_snapshot_best_effort(trade)
        elif runtime_avg_entry is not None and abs(float(runtime_avg_entry) - float(trade.entry_avg_price)) > 1e-6:
            trade.status = "DRIFTED"
            trade.drift_flags.add("AVG_ENTRY_MISMATCH")
            finding = {
                "reconciliation_id": str(uuid4()),
                "lifecycle_trade_id": trade.lifecycle_trade_id,
                "symbol": symbol,
                "status": "DRIFTED",
                "finding_type": "avg_entry_mismatch",
                "details_json": str({"runtime_avg_entry": runtime_avg_entry, "lifecycle_avg_entry": trade.entry_avg_price}),
                "timestamp": ts,
            }
            print(f"[LIFECYCLE][RECONCILE][DRIFT] symbol={symbol} runtime_avg={runtime_avg_entry} lifecycle_avg={trade.entry_avg_price}")
            self._persist_trade_snapshot_best_effort(trade)
        else:
            finding = {
                "reconciliation_id": str(uuid4()),
                "lifecycle_trade_id": trade.lifecycle_trade_id,
                "symbol": symbol,
                "status": "MATCH",
                "finding_type": "position_match",
                "details_json": str({"runtime_quantity": runtime_quantity}),
                "timestamp": ts,
            }
            print(f"[LIFECYCLE][RECONCILE][MATCH] symbol={symbol} trade_id={trade.lifecycle_trade_id}")
        self._session_counts["reconciliation_events_count"] += 1
        self._persist_reconciliation_best_effort(finding)
        self._reconciliation_events.append(finding)
        return finding

    def get_trade(self, trade_id: str) -> LifecycleTrade | None:
        return self._trades.get(trade_id)

    def find_open_trade_id_for_symbol(self, symbol: str) -> str | None:
        trade_id = self._symbol_to_open_trade_id.get(symbol)
        if not trade_id:
            return None
        trade = self._trades.get(trade_id)
        if trade is None or trade.status not in OPEN_STATUSES:
            return None
        return trade_id

    def open_trades(self) -> list[LifecycleTrade]:
        return [trade for trade in self._trades.values() if trade.status in OPEN_STATUSES]

    def get_open_lifecycle_trades(self) -> list[LifecycleTrade]:
        return self.open_trades()

    def get_trade_accounting(self, lifecycle_trade_id: str) -> LifecycleTrade | None:
        return self._trades.get(lifecycle_trade_id)

    def get_symbol_accounting(self, symbol: str) -> list[LifecycleTrade]:
        return [trade for trade in self._trades.values() if trade.symbol == symbol]

    def get_drift_report(self) -> list[dict[str, Any]]:
        return [event for event in self._reconciliation_events if event.get("status") in {"DRIFTED", "ORPHANED"}]

    def summarize_session_metrics(self) -> dict[str, Any]:
        open_trades = self.open_trades()
        partially_closed = [t for t in self._trades.values() if t.status == "PARTIALLY_CLOSED"]
        closed_trades = [t for t in self._trades.values() if t.status == "CLOSED"]
        drifted = [t for t in self._trades.values() if t.status == "DRIFTED"]
        orphaned = [t for t in self._trades.values() if t.status == "ORPHANED"]
        summary = {
            "total_lifecycle_trades_seen": max(self._session_counts["total_lifecycle_trades_seen"], len(self._trades)),
            "open_lifecycle_trades": len(open_trades),
            "partially_closed_trades": len(partially_closed),
            "closed_trades": len(closed_trades),
            "gross_realized_pnl": sum(float(t.gross_realized_pnl or 0.0) for t in self._trades.values()),
            "open_unrealized_pnl": sum(float(t.unrealized_pnl or 0.0) for t in open_trades),
            "drifted_trades_count": len(drifted),
            "orphaned_trades_count": len(orphaned),
            "reconciliation_events_count": self._session_counts["reconciliation_events_count"],
            "duplicate_events_ignored": self._session_counts["duplicate_events_ignored"],
        }
        if self._persistence is not None:
            try:
                self._persistence.insert_trade_lifecycle_summary(summary)
            except Exception as exc:
                print(f"[LIFECYCLE][ERROR] stage=persist_summary error={exc}")
        return summary

    def get_session_lifecycle_summary(self) -> dict[str, Any]:
        return self.summarize_session_metrics()
