from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import math
from typing import Any, Iterable
from uuid import uuid4


class StopAuthorityError(ValueError):
    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class StopAuditEventType(str, Enum):
    STOP_REQUIRED = "STOP_REQUIRED"
    STOP_SUBMITTED = "STOP_SUBMITTED"
    STOP_ACKNOWLEDGED = "STOP_ACKNOWLEDGED"
    STOP_REJECTED = "STOP_REJECTED"
    STOP_REPLACED = "STOP_REPLACED"
    STOP_TIGHTENED = "STOP_TIGHTENED"
    STOP_CANCELLED = "STOP_CANCELLED"
    STOP_TRIGGERED = "STOP_TRIGGERED"
    STOP_RECOVERY_RESULT = "STOP_RECOVERY_RESULT"


class StopRecoveryClassification(str, Enum):
    STOP_MATCH = "STOP_MATCH"
    STOP_MISSING = "STOP_MISSING"
    STOP_STALE = "STOP_STALE"
    STOP_ORPHAN = "STOP_ORPHAN"
    STOP_RECOVERED = "STOP_RECOVERED"
    STOP_UNSAFE = "STOP_UNSAFE"


class StopProtectionStatus(str, Enum):
    PROTECTED = "PROTECTED"
    PENDING = "PENDING"
    EXCEPTION = "EXCEPTION"
    UNSAFE = "UNSAFE"
    NOT_REQUIRED = "NOT_REQUIRED"


OPEN_POSITION_STATES = {"OPEN", "PARTIALLY_FILLED"}


@dataclass(frozen=True)
class StopAuthority:
    symbol: str
    strategy_owner: str
    lifecycle_trade_id: str | None = None
    position_id: str | None = None
    entry_order_id: str | None = None
    entry_intent_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", str(self.symbol or "").upper())
        object.__setattr__(self, "strategy_owner", str(self.strategy_owner or "UNKNOWN"))
        if not (self.lifecycle_trade_id or self.position_id):
            raise StopAuthorityError(
                "STOP_OWNER_ID_REQUIRED",
                "Stop authority requires lifecycle_trade_id or position_id.",
            )


@dataclass
class StopProtectionEvidence:
    symbol: str
    state: str
    active_stop_order_id: str | None = None
    pending_stop_order_intent: str | None = None
    emergency_stop_exception: str | None = None


@dataclass
class StopOrderRecord:
    authority: StopAuthority
    side: str
    quantity: int
    entry_price: float
    stop_price: float
    active_stop_order_id: str | None = None
    pending_stop_order_intent: str | None = None
    emergency_stop_exception: str | None = None
    status: str = "REGISTERED"
    current_price: float | None = None
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class StopAuditEvent:
    event_id: str
    timestamp: str
    event_type: StopAuditEventType
    authority: StopAuthority
    stop_price: float | None = None
    previous_stop_price: float | None = None
    active_stop_order_id: str | None = None
    pending_stop_order_intent: str | None = None
    quantity: int | None = None
    status: str | None = None
    reason: str | None = None
    recovery_classification: StopRecoveryClassification | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_storage_record(self, run_id: str | None = None) -> dict[str, Any]:
        payload_json = json.dumps(self.payload, sort_keys=True, default=str)
        return {
            "event_id": self.event_id,
            "run_id": run_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type.value,
            "symbol": self.authority.symbol,
            "lifecycle_trade_id": self.authority.lifecycle_trade_id,
            "position_id": self.authority.position_id,
            "strategy_owner": self.authority.strategy_owner,
            "entry_order_id": self.authority.entry_order_id,
            "entry_intent_id": self.authority.entry_intent_id,
            "active_stop_order_id": self.active_stop_order_id,
            "pending_stop_order_intent": self.pending_stop_order_intent,
            "stop_price": self.stop_price,
            "previous_stop_price": self.previous_stop_price,
            "quantity": self.quantity,
            "status": self.status,
            "reason": self.reason,
            "recovery_classification": (
                self.recovery_classification.value if self.recovery_classification else None
            ),
            "payload_json": payload_json,
            "created_at": self.timestamp,
        }

    @staticmethod
    def from_storage_record(record: dict[str, Any]) -> "StopAuditEvent":
        payload_raw = record.get("payload_json")
        try:
            payload = json.loads(payload_raw) if payload_raw else {}
        except json.JSONDecodeError:
            payload = {"raw_payload_json": payload_raw}
        return StopAuditEvent(
            event_id=str(record.get("event_id")),
            timestamp=str(record.get("timestamp") or record.get("created_at")),
            event_type=StopAuditEventType(str(record.get("event_type"))),
            authority=StopAuthority(
                symbol=str(record.get("symbol") or ""),
                lifecycle_trade_id=record.get("lifecycle_trade_id"),
                position_id=record.get("position_id"),
                strategy_owner=str(record.get("strategy_owner") or "UNKNOWN"),
                entry_order_id=record.get("entry_order_id"),
                entry_intent_id=record.get("entry_intent_id"),
            ),
            stop_price=_maybe_float(record.get("stop_price")),
            previous_stop_price=_maybe_float(record.get("previous_stop_price")),
            active_stop_order_id=record.get("active_stop_order_id"),
            pending_stop_order_intent=record.get("pending_stop_order_intent"),
            quantity=_maybe_int(record.get("quantity")),
            status=record.get("status"),
            reason=record.get("reason"),
            recovery_classification=(
                StopRecoveryClassification(str(record.get("recovery_classification")))
                if record.get("recovery_classification")
                else None
            ),
            payload=payload,
        )


class StopAuditTrail:
    def __init__(self, *, storage_engine: Any | None = None) -> None:
        self.storage_engine = storage_engine
        self._events: list[StopAuditEvent] = []

    def record(
        self,
        event_type: StopAuditEventType | str,
        authority: StopAuthority,
        *,
        stop_price: float | None = None,
        previous_stop_price: float | None = None,
        active_stop_order_id: str | None = None,
        pending_stop_order_intent: str | None = None,
        quantity: int | None = None,
        status: str | None = None,
        reason: str | None = None,
        recovery_classification: StopRecoveryClassification | str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> StopAuditEvent:
        classification = (
            recovery_classification
            if isinstance(recovery_classification, StopRecoveryClassification)
            else StopRecoveryClassification(str(recovery_classification))
            if recovery_classification is not None
            else None
        )
        event = StopAuditEvent(
            event_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type if isinstance(event_type, StopAuditEventType) else StopAuditEventType(str(event_type)),
            authority=authority,
            stop_price=stop_price,
            previous_stop_price=previous_stop_price,
            active_stop_order_id=active_stop_order_id,
            pending_stop_order_intent=pending_stop_order_intent,
            quantity=quantity,
            status=status,
            reason=reason,
            recovery_classification=classification,
            payload=dict(payload or {}),
        )
        self._events.append(event)
        if self.storage_engine is not None and hasattr(self.storage_engine, "insert_stop_authority_event"):
            self.storage_engine.insert_stop_authority_event(event.to_storage_record())
        return event

    def events_for(self, lifecycle_trade_id: str | None = None, symbol: str | None = None) -> list[StopAuditEvent]:
        symbol_u = str(symbol or "").upper()
        return [
            event
            for event in self._events
            if (lifecycle_trade_id is None or event.authority.lifecycle_trade_id == lifecycle_trade_id)
            and (not symbol_u or event.authority.symbol == symbol_u)
        ]

    def reconstruct(
        self,
        *,
        lifecycle_trade_id: str | None = None,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            {
                **asdict(event),
                "event_type": event.event_type.value,
                "authority": asdict(event.authority),
                "recovery_classification": (
                    event.recovery_classification.value if event.recovery_classification else None
                ),
            }
            for event in sorted(
                self.events_for(lifecycle_trade_id=lifecycle_trade_id, symbol=symbol),
                key=lambda item: item.timestamp,
            )
        ]

    @staticmethod
    def reconstruct_from_storage(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        trail = StopAuditTrail()
        trail._events = [StopAuditEvent.from_storage_record(record) for record in records]
        return trail.reconstruct()


def assess_stop_protection(evidence: StopProtectionEvidence) -> dict[str, Any]:
    state = str(evidence.state or "").upper()
    if state not in OPEN_POSITION_STATES:
        return {
            "status": StopProtectionStatus.NOT_REQUIRED.value,
            "protected": True,
            "reason_code": "POSITION_NOT_OPEN",
        }
    if evidence.active_stop_order_id:
        return {
            "status": StopProtectionStatus.PROTECTED.value,
            "protected": True,
            "reason_code": "ACTIVE_STOP_ORDER",
        }
    if evidence.pending_stop_order_intent:
        return {
            "status": StopProtectionStatus.PENDING.value,
            "protected": True,
            "reason_code": "PENDING_STOP_ORDER_INTENT",
        }
    if evidence.emergency_stop_exception:
        return {
            "status": StopProtectionStatus.EXCEPTION.value,
            "protected": True,
            "reason_code": "DOCUMENTED_EMERGENCY_EXCEPTION",
        }
    return {
        "status": StopProtectionStatus.UNSAFE.value,
        "protected": False,
        "reason_code": "UNPROTECTED_OPEN_POSITION",
    }


def require_stop_protection(evidence: StopProtectionEvidence) -> None:
    assessment = assess_stop_protection(evidence)
    if not assessment["protected"]:
        raise StopAuthorityError(
            str(assessment["reason_code"]),
            f"{evidence.symbol} {evidence.state} has no active, pending, or documented stop protection.",
        )


def validate_stop_price(
    *,
    side: str,
    stop_price: float,
    entry_price: float | None = None,
    current_price: float | None = None,
    documented_exception: str | None = None,
) -> None:
    stop = _finite_positive("stop_price", stop_price)
    reference = _first_finite_positive(current_price, entry_price)
    side_u = str(side or "").upper()
    if side_u in {"LONG", "BUY"}:
        if reference is not None and stop >= reference and not documented_exception:
            raise StopAuthorityError(
                "INVALID_LONG_STOP_PRICE",
                f"LONG stop {stop} must be below reference price {reference}.",
            )
        return
    if side_u in {"SHORT", "SELL"}:
        if reference is not None and stop <= reference and not documented_exception:
            raise StopAuthorityError(
                "INVALID_SHORT_STOP_PRICE",
                f"SHORT stop {stop} must be above reference price {reference}.",
            )
        return
    raise StopAuthorityError("INVALID_SIDE", f"Unsupported stop side: {side}")


def is_stop_tightening(*, side: str, current_stop_price: float, candidate_stop_price: float) -> bool:
    current = _finite_positive("current_stop_price", current_stop_price)
    candidate = _finite_positive("candidate_stop_price", candidate_stop_price)
    side_u = str(side or "").upper()
    if side_u in {"LONG", "BUY"}:
        return candidate >= current
    if side_u in {"SHORT", "SELL"}:
        return candidate <= current
    raise StopAuthorityError("INVALID_SIDE", f"Unsupported stop side: {side}")


def validate_stop_update(
    *,
    authority: StopAuthority,
    requested_by_strategy: str,
    side: str,
    current_stop_price: float,
    candidate_stop_price: float,
    entry_price: float | None = None,
    current_price: float | None = None,
    risk_authorized_override: bool = False,
    override_reason: str | None = None,
) -> dict[str, Any]:
    requested = str(requested_by_strategy or "")
    if requested != authority.strategy_owner:
        raise StopAuthorityError(
            "STOP_OWNERSHIP_CONFLICT",
            f"Stop owned by {authority.strategy_owner}; requested by {requested or 'UNKNOWN'}.",
        )
    tightening = is_stop_tightening(
        side=side,
        current_stop_price=current_stop_price,
        candidate_stop_price=candidate_stop_price,
    )
    breakeven_exception = (
        tightening
        and entry_price is not None
        and abs(float(candidate_stop_price) - float(entry_price)) <= 1e-6
    )
    validate_stop_price(
        side=side,
        stop_price=candidate_stop_price,
        entry_price=entry_price,
        current_price=current_price,
        documented_exception="breakeven_stop" if breakeven_exception else None,
    )
    if not tightening and not risk_authorized_override:
        raise StopAuthorityError(
            "STOP_LOOSENING_REJECTED",
            "Protective stop cannot be loosened without explicit risk authority.",
        )
    if not tightening and risk_authorized_override and not str(override_reason or "").strip():
        raise StopAuthorityError(
            "RISK_OVERRIDE_REASON_REQUIRED",
            "Risk-authorized stop loosening requires a documented reason.",
        )
    return {
        "allowed": True,
        "tightening": tightening,
        "risk_authorized_override": bool(risk_authorized_override),
        "reason_code": "STOP_TIGHTENING_ALLOWED" if tightening else "RISK_AUTHORIZED_STOP_LOOSENING",
    }


def classify_stop_recovery(
    *,
    lifecycle_stop_order_id: str | None,
    lifecycle_stop_price: float | None,
    broker_stop_orders: Iterable[Any],
    symbol: str,
    broker_position_quantity: int,
    recovered: bool = False,
    unsafe: bool = False,
) -> dict[str, Any]:
    symbol_u = str(symbol or "").upper()
    open_orders = [_normalize_broker_stop_order(order) for order in broker_stop_orders]
    symbol_orders = [order for order in open_orders if not order["symbol"] or order["symbol"] == symbol_u]
    if unsafe:
        return _classification(StopRecoveryClassification.STOP_UNSAFE, symbol_u, "unsafe_stop_recovery")
    if recovered:
        return _classification(StopRecoveryClassification.STOP_RECOVERED, symbol_u, "stop_recovered")
    if int(broker_position_quantity or 0) == 0:
        if symbol_orders:
            return _classification(
                StopRecoveryClassification.STOP_ORPHAN,
                symbol_u,
                "open_stop_without_broker_position",
                broker_order_id=symbol_orders[0].get("order_id"),
            )
        return _classification(StopRecoveryClassification.STOP_MATCH, symbol_u, "flat_no_stop_required")
    if not lifecycle_stop_order_id:
        return _classification(StopRecoveryClassification.STOP_MISSING, symbol_u, "lifecycle_stop_order_missing")

    matched = next(
        (order for order in symbol_orders if str(order.get("order_id")) == str(lifecycle_stop_order_id)),
        None,
    )
    if matched is None:
        return _classification(
            StopRecoveryClassification.STOP_MISSING,
            symbol_u,
            "broker_open_stop_missing",
            broker_order_id=lifecycle_stop_order_id,
        )
    broker_stop_price = matched.get("stop_price")
    if (
        lifecycle_stop_price is not None
        and broker_stop_price is not None
        and abs(float(lifecycle_stop_price) - float(broker_stop_price)) > 1e-6
    ):
        return _classification(
            StopRecoveryClassification.STOP_STALE,
            symbol_u,
            "broker_stop_price_stale",
            broker_order_id=lifecycle_stop_order_id,
            broker_stop_price=broker_stop_price,
            lifecycle_stop_price=float(lifecycle_stop_price),
        )
    return _classification(
        StopRecoveryClassification.STOP_MATCH,
        symbol_u,
        "broker_stop_matches_lifecycle",
        broker_order_id=lifecycle_stop_order_id,
    )


def _classification(
    classification: StopRecoveryClassification,
    symbol: str,
    reason_code: str,
    **details: Any,
) -> dict[str, Any]:
    return {
        "classification": classification.value,
        "symbol": symbol,
        "reason_code": reason_code,
        **details,
    }


def _normalize_broker_stop_order(order: Any) -> dict[str, Any]:
    if isinstance(order, dict):
        metadata = order.get("metadata") or {}
        order_id = order.get("order_id") or order.get("orderId")
        symbol = order.get("symbol") or metadata.get("symbol")
        order_type = order.get("order_type") or order.get("orderType")
        stop_price = (
            order.get("stop_price")
            or order.get("auxPrice")
            or metadata.get("stop_price")
            or metadata.get("auxPrice")
        )
    else:
        metadata = getattr(order, "metadata", {}) or {}
        order_obj = getattr(order, "order", None)
        contract = getattr(order, "contract", None)
        order_id = getattr(order, "order_id", None) or getattr(order, "orderId", None)
        symbol = getattr(order, "symbol", None) or getattr(contract, "symbol", None) or metadata.get("symbol")
        order_type = (
            getattr(order, "order_type", None)
            or getattr(order_obj, "orderType", None)
            or metadata.get("order_type")
        )
        stop_price = (
            getattr(order, "stop_price", None)
            or getattr(order_obj, "auxPrice", None)
            or metadata.get("stop_price")
            or metadata.get("auxPrice")
        )
    return {
        "order_id": str(order_id) if order_id is not None else "",
        "symbol": str(symbol or "").upper(),
        "order_type": str(order_type or "").upper(),
        "stop_price": _maybe_float(stop_price),
    }


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _finite_positive(name: str, value: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise StopAuthorityError("INVALID_STOP_PRICE", f"{name} must be numeric.") from exc
    if not math.isfinite(number) or number <= 0.0:
        raise StopAuthorityError("INVALID_STOP_PRICE", f"{name} must be positive and finite.")
    return number


def _first_finite_positive(*values: float | None) -> float | None:
    for value in values:
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number) and number > 0.0:
            return number
    return None
