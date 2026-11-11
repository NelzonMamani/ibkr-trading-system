from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from typing import Any
from uuid import uuid4

from src.core.portfolio.broker_position_adapter import BrokerPositionSnapshot
from src.core.portfolio.portfolio_state import PortfolioState
from src.core.portfolio.risk_signals import LifecycleRiskSignals

OPEN_STATUSES = {
    "OPEN",
    "PARTIALLY_CLOSED",
    "DRIFTED",
    "PARTIALLY_FILLED",
    "PROTECTION_PENDING",
    "PROTECTED",
    "TARGET_ACTIVE",
    "TRAILING_ELIGIBLE",
    "TRAILING_ACTIVE",
}
RECONCILIATION_CLASSIFICATIONS = {"MATCH", "MISMATCH", "ORPHAN", "EXTERNAL", "RECOVERED"}
TAKE_PROFIT_EVENT_TYPES = {
    "TAKE_PROFIT_CREATED",
    "TAKE_PROFIT_SUBMITTED",
    "TAKE_PROFIT_PARTIALLY_FILLED",
    "TAKE_PROFIT_FILLED",
    "TAKE_PROFIT_CANCELLED",
    "TAKE_PROFIT_SUPERSEDED",
    "TAKE_PROFIT_REJECTED",
}
TAKE_PROFIT_FILL_EVENT_TYPES = {"TAKE_PROFIT_PARTIALLY_FILLED", "TAKE_PROFIT_FILLED"}


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
    metadata: dict[str, Any] = field(default_factory=dict)


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
    target_price: float | None = None
    target_quantity: int = 0
    target_type: str | None = None
    gross_realized_pnl: float = 0.0
    realized_pnl_by_exit_reason: dict[str, float] = field(default_factory=dict)
    unrealized_pnl: float = 0.0
    last_mark_price: float | None = None
    source_order_ids: set[str] = field(default_factory=set)
    source_execution_ids: set[str] = field(default_factory=set)
    reconciliation_flags: set[str] = field(default_factory=set)
    drift_flags: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)
    take_profit_events: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class NativeValuationObservation:
    """A qualified external quote bound to one committed financial basis."""

    root_order_id: str
    account: str
    strategy: str
    symbol: str
    side: str
    con_id: int
    client_id: int
    connection_epoch: int
    quantity: int
    entry_avg_price: float
    basis_event_ids: tuple[str, ...]
    last_fill_timestamp: str
    price: float
    market_timestamp: str
    acquisition_completed_at: str
    request_id: int
    source: str
    timestamp_kind: str
    market_data_type: str
    completed: bool
    quality_flags: tuple[str, ...] = ()


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
        self._last_portfolio_state = PortfolioState()
        # Native feedback uses the existing canonical events/trades. These are
        # process-local completion fences, not another accounting ledger.
        self._native_feedback: dict[str, dict[str, Any]] = {}
        self._native_feedback_required = False
        self._native_feedback_fault: str | None = None
        self._native_committed_event_ids: set[str] = set()
        # Valuation permission is separate from factual fill completion. A
        # failed mark must neither poison fill intake nor authorize a retry.
        self._native_valuations: dict[str, dict[str, Any]] = {}
        self._native_valuation_unavailable: dict[str, str] = {}
        self._native_valuation_uncertain: dict[str, str] = {}

    def set_persistence_adapter(self, persistence_adapter: Any | None) -> None:
        self._persistence = persistence_adapter

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _trade_snapshot_payload(self, trade: LifecycleTrade) -> dict[str, Any]:
        return {
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
            "target_price": trade.target_price,
            "target_quantity": trade.target_quantity,
            "target_type": trade.target_type,
            "gross_realized_pnl": trade.gross_realized_pnl,
            "realized_pnl_by_exit_reason_json": json.dumps(trade.realized_pnl_by_exit_reason, sort_keys=True),
            "unrealized_pnl": trade.unrealized_pnl,
            "last_mark_price": trade.last_mark_price,
            "source_order_ids_json": str(sorted(trade.source_order_ids)),
            "source_execution_ids_json": str(sorted(trade.source_execution_ids)),
            "reconciliation_flags_json": str(sorted(trade.reconciliation_flags)),
            "drift_flags_json": str(sorted(trade.drift_flags)),
            "notes_json": str(trade.notes),
            "take_profit_events_json": json.dumps(trade.take_profit_events, sort_keys=True),
            "updated_at": self._now_iso(),
        }

    def _persist_trade_snapshot_best_effort(self, trade: LifecycleTrade) -> None:
        if self._persistence is None:
            return
        try:
            self._persistence.upsert_trade_lifecycle_trade(self._trade_snapshot_payload(trade))
        except Exception as exc:
            print(f"[LIFECYCLE][ERROR] stage=persist_trade_snapshot error={exc}")

    def _persist_event_best_effort(self, event: LifecycleEvent) -> None:
        if self._persistence is None:
            return
        try:
            self._persistence.insert_trade_lifecycle_event({
                **asdict(event), "timestamp": event.timestamp,
                "payload_json": json.dumps(event.metadata, sort_keys=True, allow_nan=False) if event.metadata else None,
            })
        except Exception as exc:
            print(f"[LIFECYCLE][ERROR] stage=persist_event event_id={event.event_id} error={exc}")

    def _persist_reconciliation_best_effort(self, payload: dict[str, Any]) -> None:
        if self._persistence is None:
            return
        try:
            self._persistence.insert_trade_lifecycle_reconciliation_event(payload)
        except Exception as exc:
            print(f"[LIFECYCLE][ERROR] stage=persist_reconcile error={exc}")

    @staticmethod
    def _exit_attribution(event_type: str, source: str | None = None) -> str:
        normalized = str(event_type or "").upper()
        source_u = str(source or "").upper()
        if normalized.startswith("TAKE_PROFIT"):
            return "TAKE_PROFIT"
        if "STOP" in normalized and "TRAIL" in normalized:
            return "TRAILING_STOP"
        if "STOP" in normalized:
            return "STOP_LOSS"
        if "MANUAL" in normalized or "FORCED" in normalized or "SYSTEM" in normalized:
            return "MANUAL_FORCED"
        if "BROKER" in normalized or "EXTERNAL" in normalized or "BROKER" in source_u or "EXTERNAL" in source_u:
            return "BROKER_EXTERNAL"
        return "UNKNOWN"

    def _apply_take_profit_audit_event(self, *, event: LifecycleEvent) -> LifecycleTrade | None:
        trade = self._trades.get(event.lifecycle_trade_id)
        if trade is None:
            print(f"[LIFECYCLE][WARN] take_profit_event_without_trade trade_id={event.lifecycle_trade_id}")
            return None
        payload = {
            "event_type": event.event_type,
            "quantity": int(event.quantity or 0),
            "price": float(event.price or 0.0),
            "timestamp": event.timestamp,
            "order_id": event.order_id,
            "execution_id": event.execution_id,
            "source": event.source,
        }
        if event.event_type == "TAKE_PROFIT_CREATED":
            trade.target_price = float(event.price or 0.0) or trade.target_price
            trade.target_quantity = int(event.quantity or 0) or trade.target_quantity
        if event.event_type == "TAKE_PROFIT_CANCELLED":
            trade.notes.append("take_profit_cancelled")
        if event.event_type == "TAKE_PROFIT_SUPERSEDED":
            trade.notes.append("take_profit_superseded")
        if event.event_type == "TAKE_PROFIT_REJECTED":
            trade.notes.append("take_profit_rejected")
        trade.take_profit_events.append(payload)
        print(
            "[LIFECYCLE][TAKE_PROFIT][AUDIT] "
            f"trade_id={trade.lifecycle_trade_id} symbol={trade.symbol} event={event.event_type}"
        )
        return trade

    @staticmethod
    def _classified_finding(
        *,
        lifecycle_trade_id: str | None,
        symbol: str,
        classification: str,
        finding_type: str,
        details: dict[str, Any],
        timestamp: str,
        source: str = "runtime_snapshot",
    ) -> dict[str, Any]:
        normalized = str(classification or "").upper()
        if normalized not in RECONCILIATION_CLASSIFICATIONS:
            normalized = "MISMATCH"
        severity = "INFO" if normalized in {"MATCH", "RECOVERED"} else ("WARNING" if normalized == "MISMATCH" else "CRITICAL")
        return {
            "reconciliation_id": str(uuid4()),
            "lifecycle_trade_id": lifecycle_trade_id,
            "symbol": symbol,
            "status": normalized,
            "classification": normalized,
            "severity": severity,
            "finding_type": finding_type,
            "details_json": str(details),
            "timestamp": timestamp,
            "source": source,
        }

    def recover_open_state(self) -> dict[str, Any]:
        print("[LIFECYCLE][RECOVERY][START]")
        if self._persistence is None:
            print("[LIFECYCLE][RECOVERY][DEGRADED] reason=no_persistence_adapter")
            return {"ok": False, "open_loaded": 0, "degraded": True}
        try:
            try:
                records = self._persistence.fetch_trade_lifecycle_trades(open_only=True)
            except TypeError:
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
                target_price=float(row["target_price"]) if row.get("target_price") is not None else None,
                target_quantity=int(row.get("target_quantity") or 0),
                target_type=row.get("target_type"),
                gross_realized_pnl=float(row.get("gross_realized_pnl") or 0.0),
                realized_pnl_by_exit_reason=json.loads(row.get("realized_pnl_by_exit_reason_json") or "{}"),
                unrealized_pnl=float(row.get("unrealized_pnl") or 0.0),
                last_mark_price=(
                    float(row["last_mark_price"]) if row.get("last_mark_price") is not None else None
                ),
                take_profit_events=json.loads(row.get("take_profit_events_json") or "[]"),
            )
            self._trades[trade.lifecycle_trade_id] = trade
            if trade.status in OPEN_STATUSES and trade.quantity_open > 0:
                self._symbol_to_open_trade_id[trade.symbol] = trade.lifecycle_trade_id
        loaded = len(self._symbol_to_open_trade_id)
        print(f"[LIFECYCLE][RECOVERY][LOADED] records={len(records)} open={loaded}")
        return {"ok": True, "open_loaded": loaded, "degraded": False}

    @staticmethod
    def _native_identity(identity: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(identity, dict):
            raise ValueError("NATIVE_LIFECYCLE_IDENTITY_REQUIRED")
        result = {key: identity.get(key) for key in (
            "root_order_id", "account", "symbol", "side", "client_id", "connection_epoch")}
        strategy = identity.get("strategy", identity.get("strategy_name"))
        if identity.get("strategy") is not None and identity.get("strategy_name") is not None and identity["strategy"] != identity["strategy_name"]:
            raise ValueError("NATIVE_LIFECYCLE_STRATEGY_CONFLICT")
        result["strategy"] = strategy
        for key in ("root_order_id", "account", "symbol", "side", "strategy"):
            value = result[key]
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError("NATIVE_LIFECYCLE_IDENTITY_INVALID")
        if result["side"] != "LONG" or result["symbol"] != result["symbol"].upper():
            raise ValueError("NATIVE_LIFECYCLE_IDENTITY_INVALID")
        for key in ("client_id", "connection_epoch"):
            if type(result[key]) is not int or result[key] < 0:
                raise ValueError("NATIVE_LIFECYCLE_IDENTITY_INVALID")
        native_id = identity.get("native_order_id")
        if isinstance(native_id, bool) or not isinstance(native_id, (str, int)):
            raise ValueError("NATIVE_LIFECYCLE_NATIVE_ID_INVALID")
        if not str(native_id).isdigit() or int(native_id) <= 0 or str(int(native_id)) != str(native_id):
            raise ValueError("NATIVE_LIFECYCLE_NATIVE_ID_INVALID")
        result["native_order_id"] = str(native_id)
        if identity.get("con_id") is not None:
            if type(identity["con_id"]) is not int or identity["con_id"] <= 0:
                raise ValueError("NATIVE_LIFECYCLE_SECURITY_INVALID")
            result["con_id"] = identity["con_id"]
        return result

    def require_native_feedback(self, feedback_id: str, identity: dict[str, Any] | None) -> None:
        self._native_feedback_required = True
        if not isinstance(feedback_id, str) or not feedback_id or feedback_id != feedback_id.strip():
            self._native_feedback_fault = "NATIVE_FEEDBACK_ID_INVALID"
            raise ValueError(self._native_feedback_fault)
        try:
            binding = self._native_identity(identity)
        except Exception as exc:
            self.mark_native_feedback_uncertain(feedback_id, str(exc))
            raise
        existing = self._native_feedback.get(feedback_id)
        if existing is not None:
            if existing.get("identity") != binding:
                old = existing.get("identity") or {}
                # An input-waiting frame may gain its first observed contract
                # identity. A committed/uncertain binding can never change.
                if (existing.get("state") == "PENDING" and existing.get("event_id") is None
                        and "con_id" not in old and "con_id" in binding
                        and old == {key: value for key, value in binding.items() if key != "con_id"}):
                    existing["identity"] = binding
                else:
                    self.mark_native_feedback_uncertain(feedback_id, "NATIVE_FEEDBACK_IDENTITY_CONFLICT")
                    raise ValueError("NATIVE_FEEDBACK_IDENTITY_CONFLICT")
            if existing["state"] == "UNCERTAIN":
                raise RuntimeError("NATIVE_FEEDBACK_UNCERTAIN")
            return
        self._native_feedback[feedback_id] = {"feedback_id": feedback_id, "identity": binding,
            "state": "PENDING", "event_id": None, "reason": None}

    def mark_native_feedback_uncertain(self, feedback_id: str, reason: str) -> None:
        self._native_feedback_required = True
        if not isinstance(feedback_id, str) or not feedback_id:
            self._native_feedback_fault = str(reason or "NATIVE_FEEDBACK_UNCERTAIN")
            return
        row = self._native_feedback.setdefault(feedback_id, {"feedback_id": feedback_id,
            "identity": None, "event_id": None})
        row.update(state="UNCERTAIN", reason=str(reason or "NATIVE_FEEDBACK_UNCERTAIN"))

    def complete_native_feedback(self, feedback_id: str) -> None:
        row = self._native_feedback.get(feedback_id)
        if (row is None or row.get("state") not in {"PENDING", "COMPLETE"}
                or row.get("event_id") not in self._native_committed_event_ids):
            raise RuntimeError("NATIVE_FEEDBACK_COMPLETION_UNCONFIRMED")
        row["state"] = "COMPLETE"

    def native_feedback_snapshot(self) -> dict[str, Any]:
        pending = [deepcopy(row) for row in self._native_feedback.values() if row["state"] == "PENDING"]
        uncertain = [deepcopy(row) for row in self._native_feedback.values() if row["state"] == "UNCERTAIN"]
        committed = [event for event in self._events if event.event_id in self._native_committed_event_ids]
        latest = {event.lifecycle_trade_id: event for event in committed}
        conflict = None
        for root, event in latest.items():
            trade = self._trades.get(root)
            metadata = event.metadata
            binding = metadata["native_identity"]
            if (trade is None or trade.symbol != binding["symbol"] or trade.side != "LONG"
                    or trade.strategy_name != binding["strategy"] or trade.target_price is not None
                    or trade.quantity_open != metadata["quantity_after"]
                    or trade.gross_realized_pnl != metadata["trade_pnl_after"]
                    or trade.entry_avg_price != metadata["entry_avg_price_after"]
                    or trade.stop_price != metadata["original_stop_price"]
                    or (metadata["terminal"] and (trade.status != "CLOSED" or trade.closed_at != metadata["terminal_timestamp"]))
                    or (not metadata["terminal"] and (trade.status not in OPEN_STATUSES or trade.closed_at is not None))):
                conflict = "NATIVE_LIFECYCLE_SNAPSHOT_CONFLICT"
                break
        native_marks_present = not self._native_valuation_uncertain
        for root in latest:
            trade = self._trades.get(root)
            if trade is None:
                native_marks_present = False
            elif trade.quantity_open > 0:
                try:
                    mark = trade.last_mark_price
                    if (mark is None or isinstance(mark, bool)
                            or not math.isfinite(float(mark)) or float(mark) <= 0
                            or root in self._native_valuation_unavailable
                            or not self._native_mark_matches_basis(root)):
                        native_marks_present = False
                except (TypeError, ValueError, OverflowError):
                    native_marks_present = False
        return {"required": self._native_feedback_required,
            "available": not pending and not uncertain and self._native_feedback_fault is None and conflict is None,
            "pending": pending, "uncertain": uncertain, "reason": self._native_feedback_fault or conflict,
            "events": [asdict(event) for event in committed],
            "trades": [asdict(trade) for trade in self._trades.values()],
            # Absence barrier only: price presence does not certify freshness.
            "native_unrealized_marks_present": native_marks_present,
            "unrealized_pnl": sum(float(trade.unrealized_pnl) for trade in self.open_trades())}

    def native_valuation_requirements(self) -> list[dict[str, Any]]:
        """Current same-process strict roots; restored rows confer no authority."""
        grouped: dict[str, list[LifecycleEvent]] = {}
        for event in self._events:
            if event.event_id in self._native_committed_event_ids:
                grouped.setdefault(event.lifecycle_trade_id, []).append(event)
        requirements = []
        for root, events in grouped.items():
            trade = self._trades.get(root)
            if trade is None or trade.quantity_open <= 0:
                continue
            entry = next((event for event in events if event.event_type == "ENTRY_FILL"), None)
            if entry is None:
                continue
            identity = entry.metadata["native_identity"]
            requirements.append({key: deepcopy(identity.get(key)) for key in (
                "root_order_id", "account", "strategy", "symbol", "side", "con_id",
                "client_id", "connection_epoch", "native_order_id")})
            requirements[-1].update(quantity=trade.quantity_open, entry_avg_price=trade.entry_avg_price,
                basis_event_ids=tuple(event.event_id for event in events),
                last_fill_timestamp=max(self._authoritative_time(event.timestamp) for event in events).isoformat())
        return requirements

    def _native_valuation_requirement(self, root: str) -> dict[str, Any] | None:
        return next((row for row in self.native_valuation_requirements() if row["root_order_id"] == root), None)

    def _native_mark_matches_basis(self, root: str) -> bool:
        saved = self._native_valuations.get(root)
        required = self._native_valuation_requirement(root)
        trade = self._trades.get(root)
        if saved is None or required is None or trade is None:
            return False
        observation = saved["observation"]
        return (all(getattr(observation, key) == value for key, value in required.items()
                    if key != "native_order_id")
                and trade.last_mark_price == observation.price
                and trade.unrealized_pnl == (observation.price - trade.entry_avg_price) * trade.quantity_open)

    @staticmethod
    def _native_valuation_client_matches(client: Any, observation: NativeValuationObservation) -> bool:
        if client is None:
            return False
        try:
            return (type(getattr(client, "client_id", None)) is int
                and client.client_id == observation.client_id
                and type(getattr(client, "_position_connection_epoch", None)) is int
                and client._position_connection_epoch == observation.connection_epoch
                and callable(getattr(client, "isConnected", None)) and client.isConnected() is True
                and not getattr(getattr(client, "_stop_event", None), "is_set", lambda: False)())
        except Exception:
            return False

    def mark_native_valuation_unavailable(self, root_order_id: str, reason: str) -> None:
        """Revoke a previous observation before a new external acquisition."""
        if self._native_valuation_requirement(root_order_id) is None:
            raise ValueError("NATIVE_VALUATION_OPEN_ROOT_REQUIRED")
        self._native_valuation_unavailable[root_order_id] = str(reason or "NATIVE_VALUATION_UNAVAILABLE")

    @staticmethod
    def _valuation_now(now: datetime, max_age_seconds: float) -> datetime:
        if (not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None
                or isinstance(max_age_seconds, bool) or not math.isfinite(float(max_age_seconds))
                or float(max_age_seconds) < 0):
            raise ValueError("NATIVE_VALUATION_CHECK_TIME_INVALID")
        return now.astimezone(timezone.utc)

    def native_valuation_snapshot(self, *, now: datetime, max_age_seconds: float,
                                  expected_source_client: Any | None = None) -> dict[str, Any]:
        """Admission-time freshness, without renewing any market timestamp."""
        checked = self._valuation_now(now, max_age_seconds)
        requirements = self.native_valuation_requirements()
        reason = next(iter(self._native_valuation_uncertain.values()), None)
        marks = []
        for required in requirements:
            root = required["root_order_id"]
            saved = self._native_valuations.get(root)
            if root in self._native_valuation_unavailable:
                reason = reason or self._native_valuation_unavailable[root]
            elif not self._native_mark_matches_basis(root):
                reason = reason or "NATIVE_VALUATION_MISSING_OR_BASIS_CHANGED"
            elif saved is not None:
                observed = saved["observation"]
                age = (checked - self._authoritative_time(observed.market_timestamp)).total_seconds()
                if (not self._native_valuation_client_matches(saved["source_client"], observed)
                        or (expected_source_client is not None and saved["source_client"] is not expected_source_client)):
                    reason = reason or "NATIVE_VALUATION_SOURCE_SCOPE_CHANGED"
                elif age < 0 or age > float(max_age_seconds):
                    reason = reason or "NATIVE_VALUATION_STALE_OR_FUTURE"
                else:
                    marks.append({"event_id": saved["event_id"], **asdict(observed)})
        if requirements and self.native_feedback_snapshot()["available"] is not True:
            reason = reason or "NATIVE_VALUATION_FINANCIAL_FEEDBACK_UNAVAILABLE"
        native_roots = {row["root_order_id"] for row in requirements}
        return {"available": reason is None, "reason": reason,
            "uncertain": deepcopy(self._native_valuation_uncertain), "marks": marks,
            "native_roots": sorted(native_roots), "checked_at": checked.isoformat(),
            "unrealized_pnl": sum(self._trades[root].unrealized_pnl for root in native_roots) if reason is None else None,
            "legacy_unrealized_pnl": sum(trade.unrealized_pnl for trade in self.open_trades()
                                         if trade.lifecycle_trade_id not in native_roots)}

    def apply_native_valuation(self, observation: NativeValuationObservation, *, now: datetime,
                               max_age_seconds: float, source_client: Any) -> LifecycleTrade:
        """Persist one audited mark before publishing it; never apply an EXIT."""
        root = getattr(observation, "root_order_id", None)
        try:
            checked = self._valuation_now(now, max_age_seconds)
            if type(observation) is not NativeValuationObservation:
                raise ValueError("NATIVE_VALUATION_OBSERVATION_REQUIRED")
            if root in self._native_valuation_uncertain:
                raise RuntimeError("NATIVE_VALUATION_UNCERTAIN")
            required = self._native_valuation_requirement(root)
            if required is None or self.native_feedback_snapshot()["available"] is not True:
                raise ValueError("NATIVE_VALUATION_COMMITTED_OPEN_ROOT_REQUIRED")
            if (any(getattr(observation, key) != value for key, value in required.items() if key != "native_order_id")
                    or any(type(getattr(observation, key)) is not int or getattr(observation, key) < minimum
                           for key, minimum in (("con_id", 1), ("client_id", 0), ("connection_epoch", 0),
                                                ("quantity", 1), ("request_id", 1)))
                    or type(observation.basis_event_ids) is not tuple
                    or isinstance(observation.price, bool) or not math.isfinite(float(observation.price))
                    or float(observation.price) <= 0 or isinstance(observation.entry_avg_price, bool)
                    or not math.isfinite(float(observation.entry_avg_price)) or observation.entry_avg_price <= 0
                    or observation.source != "IBKR" or observation.timestamp_kind != "LAST_TRADE"
                    or observation.market_data_type != "LIVE" or observation.completed is not True
                    or type(observation.quality_flags) is not tuple or observation.quality_flags
                    or not self._native_valuation_client_matches(source_client, observation)):
                raise ValueError("NATIVE_VALUATION_EVIDENCE_INVALID")
            market = self._authoritative_time(observation.market_timestamp)
            completed = self._authoritative_time(observation.acquisition_completed_at)
            latest_fill = self._authoritative_time(observation.last_fill_timestamp)
            if not latest_fill <= market <= completed <= checked:
                raise ValueError("NATIVE_VALUATION_TIME_BINDING_INVALID")
            if (checked - market).total_seconds() > float(max_age_seconds):
                raise ValueError("NATIVE_VALUATION_STALE")
            key = {name: getattr(observation, name) for name in (
                "root_order_id", "account", "client_id", "connection_epoch", "request_id", "market_timestamp", "basis_event_ids")}
            event_id = "native-mark:" + sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()
            prior = self._native_valuations.get(root)
            if prior is not None and prior["event_id"] == event_id:
                if (prior["observation"] != observation or prior["source_client"] is not source_client
                        or not self._native_mark_matches_basis(root)):
                    raise ValueError("NATIVE_VALUATION_OBSERVATION_CONFLICT")
                self._native_valuation_unavailable.pop(root, None)
                return self._trades[root]
            before = self._trades[root]
            candidate = deepcopy(before)
            candidate.last_mark_price = float(observation.price)
            candidate.unrealized_pnl = (candidate.last_mark_price - candidate.entry_avg_price) * candidate.quantity_open
            event = LifecycleEvent(event_id, root, observation.symbol, "LONG", "NATIVE_MARK", 0,
                candidate.last_mark_price, market.isoformat(), order_id=required["native_order_id"],
                source="native_valuation", metadata={"native_valuation": asdict(observation)})
            persist = getattr(self._persistence, "persist_native_lifecycle_feedback", None)
            try:
                if not callable(persist):
                    raise RuntimeError("NATIVE_VALUATION_STORAGE_REQUIRED")
                payload = {**asdict(event), "payload_json": json.dumps(event.metadata, sort_keys=True, allow_nan=False)}
                receipt = persist(self._trade_snapshot_payload(candidate), payload,
                    expected_trade=self._trade_snapshot_payload(before))
                if (not isinstance(receipt, dict) or receipt.get("completed") is not True
                        or receipt.get("event_id") != event_id):
                    raise RuntimeError("NATIVE_VALUATION_PERSISTENCE_UNCONFIRMED")
                if self._native_valuation_requirement(root) != required:
                    raise RuntimeError("NATIVE_VALUATION_BASIS_CHANGED_DURING_PERSISTENCE")
                if not self._native_valuation_client_matches(source_client, observation):
                    raise RuntimeError("NATIVE_VALUATION_SOURCE_CHANGED_DURING_PERSISTENCE")
            except BaseException as exc:
                self._native_valuation_uncertain[root] = str(exc or "NATIVE_VALUATION_UNCERTAIN")
                raise
            self._trades[root] = candidate
            self._events.append(event)
            self._event_ids_seen.add(event_id)
            self._native_valuations[root] = {"event_id": event_id, "observation": observation,
                "source_client": source_client}
            self._native_valuation_unavailable.pop(root, None)
            return candidate
        except BaseException as exc:
            if isinstance(root, str):
                self._native_valuation_unavailable[root] = str(exc or "NATIVE_VALUATION_UNAVAILABLE")
            raise

    @staticmethod
    def _authoritative_time(value: str) -> datetime:
        if not isinstance(value, str):
            raise ValueError("NATIVE_LIFECYCLE_TIME_REQUIRED")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            raise ValueError("NATIVE_LIFECYCLE_TIME_INVALID") from None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("NATIVE_LIFECYCLE_TIME_UNSCOPED")
        return parsed.astimezone(timezone.utc)

    def _apply_native_event(self, event: LifecycleEvent, *, strategy_name: str | None,
                            stop_price: float | None, native_identity: dict[str, Any] | None,
                            expected_quantity: int | None) -> LifecycleTrade:
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        feedback_id = metadata.get("feedback_id", event.event_id)
        try:
            self.require_native_feedback(feedback_id, native_identity)
            binding = self._native_feedback[feedback_id]["identity"]
            if not isinstance(event.metadata, dict):
                raise ValueError("NATIVE_LIFECYCLE_METADATA_INVALID")
            if (event.lifecycle_trade_id != binding["root_order_id"] or event.symbol != binding["symbol"]
                    or event.side != "LONG" or str(event.order_id) != binding["native_order_id"]
                    or (strategy_name is not None and strategy_name != binding["strategy"])):
                raise ValueError("NATIVE_LIFECYCLE_BINDING_CONFLICT")
            if (not isinstance(event.event_id, str) or not event.event_id or event.event_id != event.event_id.strip()
                    or not isinstance(event.execution_id, str) or not event.execution_id or event.execution_id != event.execution_id.strip()
                    or event.event_type not in {"ENTRY_FILL", "PARTIAL_EXIT", "STOP_EXIT", "EXIT_FILL"}
                    or type(event.quantity) is not int or event.quantity <= 0
                    or type(expected_quantity) is not int or expected_quantity < 0
                    or isinstance(event.price, bool) or not math.isfinite(float(event.price)) or float(event.price) <= 0):
                raise ValueError("NATIVE_LIFECYCLE_FILL_INVALID")
            timestamp = self._authoritative_time(event.timestamp).isoformat()
            reserved = {"native_identity", "realized_increment", "quantity_before", "quantity_after",
                "terminal", "terminal_timestamp", "trade_pnl_after", "native_feedback_committed",
                "entry_avg_price_after", "original_stop_price"}
            if "native_identity" in metadata and self._native_identity(metadata["native_identity"]) != binding:
                raise ValueError("NATIVE_LIFECYCLE_METADATA_CONFLICT")
            if reserved.intersection(metadata) - {"native_identity"}:
                raise ValueError("NATIVE_LIFECYCLE_COMPUTED_METADATA_RESERVED")
            supplied_metadata = {key: deepcopy(value) for key, value in metadata.items()
                                 if key not in {"native_identity", "feedback_id"}}
            json.dumps(supplied_metadata, sort_keys=True, allow_nan=False)
            owned = deepcopy(event)
            owned.timestamp = timestamp
            owned.price = float(event.price)
            owned.order_id = binding["native_order_id"]
            # Real execution identity, not another cumulative/status identity,
            # distinguishes a duplicate from a contradictory callback.
            for prior_event in self._events:
                if prior_event.event_id not in self._native_committed_event_ids:
                    continue
                old_binding = prior_event.metadata["native_identity"]
                same_execution = (old_binding["account"] == binding["account"]
                                  and prior_event.execution_id == owned.execution_id)
                if prior_event.event_id != owned.event_id and not same_execution:
                    continue
                old_metadata = {key: value for key, value in prior_event.metadata.items()
                                if key not in reserved | {"feedback_id"}}
                fields = ("lifecycle_trade_id", "symbol", "side", "event_type", "quantity", "price", "timestamp", "order_id", "execution_id", "source")
                if (old_binding != binding or any(getattr(prior_event, key) != getattr(owned, key) for key in fields)
                        or old_metadata != supplied_metadata):
                    raise ValueError("NATIVE_LIFECYCLE_EXECUTION_CONFLICT")
                self._native_feedback[feedback_id]["event_id"] = prior_event.event_id
                self._session_counts["duplicate_events_ignored"] += 1
                return self._trades[binding["root_order_id"]]
            if event.event_id in self._event_ids_seen:
                raise ValueError("NATIVE_LIFECYCLE_EVENT_CONFLICT")
            for other in self._native_feedback.values():
                if (other["state"] == "UNCERTAIN" and other.get("identity")
                        and other["identity"]["root_order_id"] == binding["root_order_id"]):
                    raise RuntimeError("NATIVE_LIFECYCLE_ROOT_UNCERTAIN")
            trade = self._trades.get(binding["root_order_id"])
            before = deepcopy(trade)
            if (trade.quantity_open if trade else 0) != expected_quantity:
                raise ValueError("NATIVE_LIFECYCLE_QUANTITY_CONFLICT")
            if trade is not None:
                entries = [row for row in self._events if row.event_id in self._native_committed_event_ids
                           and row.lifecycle_trade_id == trade.lifecycle_trade_id and row.event_type == "ENTRY_FILL"]
                if (not entries or trade.symbol != binding["symbol"] or trade.side != "LONG"
                        or trade.strategy_name != binding["strategy"] or trade.target_price is not None
                        or any(entries[0].metadata["native_identity"].get(key) != binding[key]
                               for key in binding if key != "native_order_id")):
                    raise ValueError("NATIVE_LIFECYCLE_TRADE_OWNERSHIP_CONFLICT")
                if event.event_type == "ENTRY_FILL" and entries[0].metadata["native_identity"]["native_order_id"] != binding["native_order_id"]:
                    raise ValueError("NATIVE_LIFECYCLE_ENTRY_ORDER_CONFLICT")
                if (event.event_type != "ENTRY_FILL"
                        and self._authoritative_time(timestamp) < min(self._authoritative_time(row.timestamp) for row in entries)):
                    raise ValueError("NATIVE_LIFECYCLE_EXIT_BEFORE_ENTRY")
                opposite = (entries if event.event_type != "ENTRY_FILL" else
                    [row for row in self._events if row.event_id in self._native_committed_event_ids
                     and row.lifecycle_trade_id == trade.lifecycle_trade_id and row.event_type != "ENTRY_FILL"])
                # Entry averages and realized exits cannot be rewound without
                # reconstructing an unknown historical basis. Same-type late
                # arrivals remain commutative; equal broker timestamps retain
                # the existing accounting order, not subsecond certification.
                if opposite and self._authoritative_time(timestamp) < max(self._authoritative_time(row.timestamp) for row in opposite):
                    raise ValueError("NATIVE_LIFECYCLE_CROSS_FILL_CHRONOLOGY_UNAVAILABLE")
                if stop_price is not None and float(stop_price) != trade.stop_price:
                    raise ValueError("NATIVE_LIFECYCLE_ORIGINAL_STOP_CONFLICT")
            elif event.event_type != "ENTRY_FILL" or self.find_open_trade_id_for_symbol(event.symbol) is not None:
                raise ValueError("NATIVE_LIFECYCLE_ENTRY_OWNERSHIP_REQUIRED")
            if event.event_type == "ENTRY_FILL":
                if (stop_price is None or isinstance(stop_price, bool)
                        or not math.isfinite(float(stop_price)) or float(stop_price) <= 0):
                    raise ValueError("NATIVE_LIFECYCLE_ORIGINAL_STOP_REQUIRED")
            elif event.quantity > expected_quantity:
                raise ValueError("NATIVE_LIFECYCLE_EXIT_EXCEEDS_OWNERSHIP")
            persist = getattr(self._persistence, "persist_native_lifecycle_feedback", None)
            if not callable(persist):
                raise RuntimeError("NATIVE_LIFECYCLE_STORAGE_REQUIRED")
            expected_snapshot = self._trade_snapshot_payload(before) if before else None
            self._event_ids_seen.add(owned.event_id)
            if event.event_type == "ENTRY_FILL":
                trade = self.apply_entry_fill(event=owned, strategy_name=binding["strategy"], stop_price=stop_price)
                trade.opened_at = min(self._authoritative_time(trade.opened_at), self._authoritative_time(timestamp)).isoformat()
                trade.closed_at = None
                realized = 0.0
                expected_after = expected_quantity + owned.quantity
                expected_entry_price = (((before.entry_avg_price if before else 0.0) * expected_quantity
                                         + owned.price * owned.quantity) / float(expected_after))
            else:
                trade = self.apply_exit_fill(event=owned)
                realized = (owned.price - before.entry_avg_price) * owned.quantity
                expected_after = expected_quantity - owned.quantity
                expected_entry_price = before.entry_avg_price
            expected_pnl = (before.gross_realized_pnl if before else 0.0) + realized
            if (trade is None or trade.quantity_open != expected_after
                    or trade.quantity_closed != (before.quantity_closed if before else 0) + (0 if event.event_type == "ENTRY_FILL" else owned.quantity)
                    or trade.gross_realized_pnl != expected_pnl or trade.entry_avg_price != expected_entry_price
                    or trade.target_price is not None or trade.stop_price != float(stop_price if stop_price is not None else before.stop_price)):
                raise RuntimeError("NATIVE_LIFECYCLE_PROJECTION_CONFLICT")
            terminal = event.event_type != "ENTRY_FILL" and trade.quantity_open == 0
            terminal_timestamp = None
            if terminal:
                exits = [self._authoritative_time(row.timestamp) for row in self._events
                         if row.event_id in self._native_committed_event_ids and row.lifecycle_trade_id == owned.lifecycle_trade_id
                         and row.event_type != "ENTRY_FILL"]
                terminal_timestamp = max(exits + [self._authoritative_time(timestamp)]).isoformat()
                trade.closed_at = terminal_timestamp
            owned.metadata = {**supplied_metadata, "feedback_id": feedback_id, "native_identity": binding,
                "realized_increment": realized, "quantity_before": expected_quantity, "quantity_after": expected_after,
                "terminal": terminal, "terminal_timestamp": terminal_timestamp,
                "trade_pnl_after": trade.gross_realized_pnl, "entry_avg_price_after": trade.entry_avg_price,
                "original_stop_price": trade.stop_price, "native_feedback_committed": True}
            # A financial DELTA supersedes the old quantity/basis observation.
            # Unknown mark outcomes remain latched separately and never impede
            # factual fill intake through a mark-only snapshot discrepancy.
            trade.last_mark_price = None
            trade.unrealized_pnl = 0.0
            self._native_valuations.pop(binding["root_order_id"], None)
            self._native_valuation_unavailable[binding["root_order_id"]] = "NATIVE_VALUATION_FINANCIAL_BASIS_CHANGED"
            event_payload = {**asdict(owned), "payload_json": json.dumps(owned.metadata, sort_keys=True, allow_nan=False)}
            receipt = persist(self._trade_snapshot_payload(trade), event_payload, expected_trade=expected_snapshot,
                financial_only=True)
            if not isinstance(receipt, dict) or receipt.get("completed") is not True or receipt.get("event_id") != owned.event_id:
                raise RuntimeError("NATIVE_LIFECYCLE_PERSISTENCE_UNCONFIRMED")
            self._events.append(owned)
            self._native_committed_event_ids.add(owned.event_id)
            self._native_feedback[feedback_id]["event_id"] = owned.event_id
            return trade
        except BaseException as exc:
            self.mark_native_feedback_uncertain(feedback_id, str(exc))
            raise

    def apply_event(self, event: LifecycleEvent, *, strategy_name: str | None = None, stop_price: float | None = None,
                    strict: bool = False, native_identity: dict[str, Any] | None = None,
                    expected_quantity: int | None = None) -> LifecycleTrade | None:
        if strict:
            return self._apply_native_event(event, strategy_name=strategy_name, stop_price=stop_price,
                native_identity=native_identity, expected_quantity=expected_quantity)
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

        event_type_u = str(event.event_type or "").upper()
        if event_type_u == "ENTRY_FILL":
            trade = self.apply_entry_fill(event=event, strategy_name=strategy_name, stop_price=stop_price)
        elif event_type_u in TAKE_PROFIT_EVENT_TYPES and event_type_u not in TAKE_PROFIT_FILL_EVENT_TYPES:
            trade = self._apply_take_profit_audit_event(event=event)
        else:
            trade = self.apply_exit_fill(event=event)
        self._persist_event_best_effort(event)
        if trade:
            self._persist_trade_snapshot_best_effort(trade)
        return trade

    def apply_entry_fill(self, *, event: LifecycleEvent, strategy_name: str | None = None, stop_price: float | None = None) -> LifecycleTrade:
        trade = self._trades.get(event.lifecycle_trade_id)
        if trade is None:
            existing_open_trade_id = self.find_open_trade_id_for_symbol(event.symbol)
            if existing_open_trade_id is not None:
                existing = self._trades[existing_open_trade_id]
                if strategy_name and existing.strategy_name and existing.strategy_name != strategy_name:
                    finding = self._classified_finding(
                        lifecycle_trade_id=existing.lifecycle_trade_id,
                        symbol=event.symbol,
                        classification="MISMATCH",
                        finding_type="entry_fill_ownership_conflict",
                        details={
                            "existing_strategy": existing.strategy_name,
                            "incoming_strategy": strategy_name,
                            "incoming_trade_id": event.lifecycle_trade_id,
                        },
                        timestamp=event.timestamp,
                    )
                    existing.drift_flags.add("ENTRY_OWNERSHIP_CONFLICT")
                    self._persist_trade_snapshot_best_effort(existing)
                    self._persist_reconciliation_best_effort(finding)
                    self._reconciliation_events.append(finding)
                    print(
                        "[LIFECYCLE][OWNERSHIP][CONFLICT] "
                        f"symbol={event.symbol} existing_strategy={existing.strategy_name} incoming_strategy={strategy_name}"
                    )
                    return existing
                existing.notes.append(f"merged_entry_fill_from_trade_id={event.lifecycle_trade_id}")
                trade = existing
            else:
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
        if trade.lifecycle_trade_id != event.lifecycle_trade_id:
            event.lifecycle_trade_id = trade.lifecycle_trade_id
        if trade.strategy_name is None and strategy_name is not None:
            trade.strategy_name = strategy_name
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
        realized_increment = (event.price - trade.entry_avg_price) * float(exit_qty) * sign
        trade.gross_realized_pnl += realized_increment
        attribution = self._exit_attribution(event.event_type, event.source)
        trade.realized_pnl_by_exit_reason[attribution] = (
            float(trade.realized_pnl_by_exit_reason.get(attribution, 0.0)) + float(realized_increment)
        )
        if str(event.event_type or "").upper() in TAKE_PROFIT_FILL_EVENT_TYPES:
            trade.take_profit_events.append(
                {
                    "event_type": event.event_type,
                    "quantity": int(exit_qty),
                    "price": float(event.price),
                    "timestamp": event.timestamp,
                    "order_id": event.order_id,
                    "execution_id": event.execution_id,
                    "source": event.source,
                    "realized_increment": float(realized_increment),
                }
            )
            trade.target_price = float(event.price)
            trade.target_quantity = max(int(trade.target_quantity or 0), int(event.quantity or 0))
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
            finding = self._classified_finding(
                lifecycle_trade_id=None,
                symbol=symbol,
                classification="EXTERNAL",
                finding_type="runtime_position_without_lifecycle_trade",
                details={"runtime_quantity": runtime_quantity, "runtime_avg_entry": runtime_avg_entry},
                timestamp=ts,
            )
            print(f"[LIFECYCLE][RECONCILE][EXTERNAL] symbol={symbol} runtime_qty={runtime_quantity}")
            self._session_counts["reconciliation_events_count"] += 1
            self._persist_reconciliation_best_effort(finding)
            self._reconciliation_events.append(finding)
            return finding
        if open_trade_id is None:
            finding = self._classified_finding(
                lifecycle_trade_id=None,
                symbol=symbol,
                classification="MATCH",
                finding_type="no_open_position",
                details={},
                timestamp=ts,
            )
            print(f"[LIFECYCLE][RECONCILE][MATCH] symbol={symbol} state=flat")
            self._persist_reconciliation_best_effort(finding)
            self._reconciliation_events.append(finding)
            return finding
        trade = self._trades[open_trade_id]
        if runtime_quantity <= 0:
            trade.status = "CLOSED"
            trade.reconciliation_flags.add("BROKER_FLAT_RECOVERED")
            trade.closed_at = ts
            trade.quantity_closed += trade.quantity_open
            trade.quantity_open = 0
            trade.unrealized_pnl = 0.0
            self._symbol_to_open_trade_id.pop(symbol, None)
            finding = self._classified_finding(
                lifecycle_trade_id=trade.lifecycle_trade_id,
                symbol=symbol,
                classification="RECOVERED",
                finding_type="lifecycle_open_without_runtime_position",
                details={"action": "broker_flat_closed_stale_lifecycle"},
                timestamp=ts,
            )
            print(f"[LIFECYCLE][RECONCILE][RECOVER] symbol={symbol} action=close_orphan trade_id={trade.lifecycle_trade_id}")
            self._persist_trade_snapshot_best_effort(trade)
        elif runtime_quantity != trade.quantity_open:
            trade.status = "DRIFTED"
            trade.drift_flags.add("QTY_MISMATCH")
            finding = self._classified_finding(
                lifecycle_trade_id=trade.lifecycle_trade_id,
                symbol=symbol,
                classification="MISMATCH",
                finding_type="quantity_mismatch",
                details={"runtime_quantity": runtime_quantity, "lifecycle_quantity": trade.quantity_open},
                timestamp=ts,
            )
            print(f"[LIFECYCLE][RECONCILE][DRIFT] symbol={symbol} runtime_qty={runtime_quantity} lifecycle_qty={trade.quantity_open}")
            self._persist_trade_snapshot_best_effort(trade)
        elif runtime_avg_entry is not None and abs(float(runtime_avg_entry) - float(trade.entry_avg_price)) > 1e-6:
            trade.status = "DRIFTED"
            trade.drift_flags.add("AVG_ENTRY_MISMATCH")
            finding = self._classified_finding(
                lifecycle_trade_id=trade.lifecycle_trade_id,
                symbol=symbol,
                classification="MISMATCH",
                finding_type="avg_entry_mismatch",
                details={"runtime_avg_entry": runtime_avg_entry, "lifecycle_avg_entry": trade.entry_avg_price},
                timestamp=ts,
            )
            print(f"[LIFECYCLE][RECONCILE][DRIFT] symbol={symbol} runtime_avg={runtime_avg_entry} lifecycle_avg={trade.entry_avg_price}")
            self._persist_trade_snapshot_best_effort(trade)
        else:
            finding = self._classified_finding(
                lifecycle_trade_id=trade.lifecycle_trade_id,
                symbol=symbol,
                classification="MATCH",
                finding_type="position_match",
                details={"runtime_quantity": runtime_quantity},
                timestamp=ts,
            )
            print(f"[LIFECYCLE][RECONCILE][MATCH] symbol={symbol} trade_id={trade.lifecycle_trade_id}")
        self._session_counts["reconciliation_events_count"] += 1
        self._persist_reconciliation_best_effort(finding)
        self._reconciliation_events.append(finding)
        return finding

    @staticmethod
    def _severity_for_status(status: str) -> str:
        normalized = str(status or "").upper()
        if normalized == "MATCH":
            return "INFO"
        if normalized == "DRIFTED":
            return "WARNING"
        return "CRITICAL"

    def reconcile_with_broker_snapshot(
        self,
        snapshot: list[BrokerPositionSnapshot],
    ) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        ts = self._now_iso()
        broker_by_symbol = {
            str(row.symbol).upper(): row for row in snapshot if str(getattr(row, "symbol", "")).strip()
        }
        lifecycle_open = self.open_trades()
        lifecycle_by_symbol: dict[str, list[LifecycleTrade]] = {}
        for trade in lifecycle_open:
            lifecycle_by_symbol.setdefault(str(trade.symbol).upper(), []).append(trade)

        all_symbols = sorted(set(lifecycle_by_symbol.keys()) | set(broker_by_symbol.keys()))
        for symbol in all_symbols:
            lifecycle_trades = lifecycle_by_symbol.get(symbol, [])
            broker_position = broker_by_symbol.get(symbol)
            broker_qty = int(getattr(broker_position, "quantity", 0) or 0) if broker_position else 0
            broker_avg = (
                float(getattr(broker_position, "avg_entry_price", 0.0) or 0.0) if broker_position else 0.0
            )
            runtime_qty = sum(int(t.quantity_open or 0) for t in lifecycle_trades)

            if len(lifecycle_trades) > 1 and broker_qty > 0:
                classification = "MISMATCH"
                finding_type = "structure_drift"
                details = {
                    "reason": "multiple_lifecycle_trades_single_broker_position",
                    "lifecycle_trade_ids": [t.lifecycle_trade_id for t in lifecycle_trades],
                    "broker_quantity": broker_qty,
                }
                for trade in lifecycle_trades:
                    trade.status = "DRIFTED"
                    trade.drift_flags.add("STRUCTURE_DRIFT")
                    self._persist_trade_snapshot_best_effort(trade)
            elif runtime_qty > 0 and broker_qty <= 0:
                classification = "ORPHAN"
                finding_type = "lifecycle_open_broker_flat"
                details = {
                    "runtime_quantity": runtime_qty,
                    "broker_quantity": broker_qty,
                    "action": "broker_flat_closed_stale_lifecycle",
                    "recovery_result": "RECOVERED",
                }
                for trade in lifecycle_trades:
                    trade.status = "CLOSED"
                    trade.closed_at = ts
                    trade.quantity_closed += int(trade.quantity_open or 0)
                    trade.quantity_open = 0
                    trade.unrealized_pnl = 0.0
                    trade.reconciliation_flags.add("BROKER_FLAT_RECOVERED")
                    if self._symbol_to_open_trade_id.get(trade.symbol) == trade.lifecycle_trade_id:
                        self._symbol_to_open_trade_id.pop(trade.symbol, None)
                    self._persist_trade_snapshot_best_effort(trade)
            elif runtime_qty <= 0 and broker_qty > 0:
                classification = "EXTERNAL"
                finding_type = "broker_open_lifecycle_missing"
                details = {"runtime_quantity": runtime_qty, "broker_quantity": broker_qty}
            elif runtime_qty != broker_qty:
                classification = "MISMATCH"
                finding_type = "qty_mismatch"
                details = {"runtime_quantity": runtime_qty, "broker_quantity": broker_qty}
                for trade in lifecycle_trades:
                    trade.status = "DRIFTED"
                    trade.drift_flags.add("BROKER_QTY_MISMATCH")
                    self._persist_trade_snapshot_best_effort(trade)
            else:
                lifecycle_avg = float(lifecycle_trades[0].entry_avg_price or 0.0) if lifecycle_trades else 0.0
                if abs(lifecycle_avg - broker_avg) > 1e-6:
                    classification = "MISMATCH"
                    finding_type = "avg_entry_mismatch"
                    details = {
                        "lifecycle_avg_entry": lifecycle_avg,
                        "broker_avg_entry": broker_avg,
                        "runtime_quantity": runtime_qty,
                    }
                    for trade in lifecycle_trades:
                        trade.status = "DRIFTED"
                        trade.drift_flags.add("BROKER_AVG_ENTRY_MISMATCH")
                        self._persist_trade_snapshot_best_effort(trade)
                else:
                    classification = "MATCH"
                    finding_type = "position_match"
                    details = {"runtime_quantity": runtime_qty, "broker_quantity": broker_qty}

            finding = self._classified_finding(
                lifecycle_trade_id=lifecycle_trades[0].lifecycle_trade_id if lifecycle_trades else None,
                symbol=symbol,
                classification=classification,
                finding_type=finding_type,
                details=details,
                timestamp=ts,
                source="broker_snapshot",
            )
            severity = str(finding["severity"])
            print(f"[LIFECYCLE][BROKER_RECONCILE][{severity}] symbol={symbol} reason={finding_type}")
            self._session_counts["reconciliation_events_count"] += 1
            self._persist_reconciliation_best_effort(finding)
            self._reconciliation_events.append(finding)
            findings.append(finding)
        return findings

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

    def validate_exit_authority(
        self,
        *,
        symbol: str,
        strategy_name: str,
        lifecycle_trade_id: str | None = None,
    ) -> dict[str, Any]:
        trade: LifecycleTrade | None = None
        if lifecycle_trade_id:
            candidate = self._trades.get(str(lifecycle_trade_id))
            if candidate is not None and candidate.status in OPEN_STATUSES:
                trade = candidate
        if trade is None:
            open_trade_id = self.find_open_trade_id_for_symbol(symbol)
            trade = self._trades.get(open_trade_id) if open_trade_id else None
        if trade is None:
            return {
                "allowed": False,
                "reason_code": "NO_OPEN_POSITION",
                "symbol": str(symbol or "").upper(),
                "requested_strategy": strategy_name,
                "owner_strategy": None,
            }
        requested = str(strategy_name or "").strip()
        owner = str(trade.strategy_name or "").strip()
        if owner and requested and owner != requested:
            return {
                "allowed": False,
                "reason_code": "OWNERSHIP_CONFLICT",
                "symbol": trade.symbol,
                "lifecycle_trade_id": trade.lifecycle_trade_id,
                "requested_strategy": requested,
                "owner_strategy": owner,
            }
        return {
            "allowed": True,
            "reason_code": "OWNER_MATCH",
            "symbol": trade.symbol,
            "lifecycle_trade_id": trade.lifecycle_trade_id,
            "requested_strategy": requested,
            "owner_strategy": owner or None,
        }

    def open_trades(self) -> list[LifecycleTrade]:
        return [trade for trade in self._trades.values() if trade.status in OPEN_STATUSES]

    def get_open_lifecycle_trades(self) -> list[LifecycleTrade]:
        return self.open_trades()

    def get_trade_accounting(self, lifecycle_trade_id: str) -> LifecycleTrade | None:
        return self._trades.get(lifecycle_trade_id)

    def get_symbol_accounting(self, symbol: str) -> list[LifecycleTrade]:
        return [trade for trade in self._trades.values() if trade.symbol == symbol]

    def get_drift_report(self) -> list[dict[str, Any]]:
        return [
            event
            for event in self._reconciliation_events
            if event.get("classification") in {"MISMATCH", "ORPHAN", "EXTERNAL", "RECOVERED"}
            or event.get("status") in {"DRIFTED", "ORPHANED"}
        ]

    def build_portfolio_state(self) -> PortfolioState:
        open_trades = self.open_trades()
        drifted_positions = sorted(
            {
                trade.symbol
                for trade in self._trades.values()
                if trade.status in {"DRIFTED", "ORPHANED"} or bool(trade.drift_flags)
            }
        )
        state = PortfolioState(
            total_open_positions=len(open_trades),
            total_exposure=sum(float(t.quantity_open) * float(t.entry_avg_price) for t in open_trades),
            total_realized_pnl=sum(float(t.gross_realized_pnl or 0.0) for t in self._trades.values()),
            total_unrealized_pnl=sum(float(t.unrealized_pnl or 0.0) for t in open_trades),
            symbols_open=sorted({t.symbol for t in open_trades if t.symbol}),
            drifted_positions=drifted_positions,
        )
        self._last_portfolio_state = state
        return state

    def compute_lifecycle_risk_signals(self) -> LifecycleRiskSignals:
        state = self.build_portfolio_state()
        max_drawdown_breached = state.total_realized_pnl <= -300.0
        pnl_drop_rate_exceeded = state.total_unrealized_pnl <= -250.0
        too_many_open_positions = state.total_open_positions > 5
        drift_detected = len(state.drifted_positions) > 0
        signals = LifecycleRiskSignals(
            max_drawdown_breached=max_drawdown_breached,
            pnl_drop_rate_exceeded=pnl_drop_rate_exceeded,
            too_many_open_positions=too_many_open_positions,
            drift_detected=drift_detected,
        )
        if max_drawdown_breached:
            print(f"[LIFECYCLE][RISK_SIGNAL] drawdown_exceeded value={state.total_realized_pnl:.2f}")
        if pnl_drop_rate_exceeded:
            print(f"[LIFECYCLE][RISK_SIGNAL] pnl_drop_rate_exceeded value={state.total_unrealized_pnl:.2f}")
        if too_many_open_positions:
            print(f"[LIFECYCLE][RISK_SIGNAL] too_many_open_positions value={state.total_open_positions}")
        if drift_detected:
            print(f"[LIFECYCLE][RISK_SIGNAL] drift_detected symbols={','.join(state.drifted_positions)}")
        return signals

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
            "portfolio_exposure": self._last_portfolio_state.total_exposure,
            "portfolio_realized_pnl": self._last_portfolio_state.total_realized_pnl,
            "portfolio_unrealized_pnl": self._last_portfolio_state.total_unrealized_pnl,
            "broker_mismatch_count": len(
                [
                    event
                    for event in self._reconciliation_events
                    if event.get("source") == "broker_snapshot" and event.get("status") != "MATCH"
                ]
            ),
            "drift_count": len([event for event in self._reconciliation_events if event.get("status") == "DRIFTED"]),
            "orphan_count": len([event for event in self._reconciliation_events if event.get("status") == "ORPHANED"]),
        }
        if self._persistence is not None:
            try:
                self._persistence.insert_trade_lifecycle_summary(summary)
            except Exception as exc:
                print(f"[LIFECYCLE][ERROR] stage=persist_summary error={exc}")
        return summary

    def get_session_lifecycle_summary(self) -> dict[str, Any]:
        return self.summarize_session_metrics()
