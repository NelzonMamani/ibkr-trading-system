from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Iterable
from uuid import uuid4

from src.config.runtime_config import RunMode
from src.storage.storage_engine import StorageEngine


class PositionState(str, Enum):
    FLAT = "FLAT"
    OPEN = "OPEN"
    SCALING_IN = "SCALING_IN"
    REDUCING = "REDUCING"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"


class LifecycleIntent(str, Enum):
    OPEN = "OPEN"
    ADD = "ADD"
    SCALE_OUT = "SCALE_OUT"
    ADD_TO_WINNER = "ADD_TO_WINNER"
    PARTIAL_PROFIT = "PARTIAL_PROFIT"
    TRAILING_STOP_UPDATE = "TRAILING_STOP_UPDATE"
    FULL_EXIT = "FULL_EXIT"
    STOP_EXIT = "STOP_EXIT"
    TIME_EXIT = "TIME_EXIT"
    RISK_EXIT = "RISK_EXIT"
    SYSTEM_EXIT = "SYSTEM_EXIT"


ALLOWED_TRANSITIONS = {
    (PositionState.FLAT, PositionState.OPEN),
    (PositionState.OPEN, PositionState.SCALING_IN),
    (PositionState.OPEN, PositionState.REDUCING),
    (PositionState.SCALING_IN, PositionState.OPEN),
    (PositionState.REDUCING, PositionState.OPEN),
    (PositionState.OPEN, PositionState.OPEN),
    (PositionState.OPEN, PositionState.CLOSING),
    (PositionState.CLOSING, PositionState.CLOSED),
}


class LifecycleTransitionError(ValueError):
    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def normalize_state(value: PositionState | str) -> PositionState:
    if isinstance(value, PositionState):
        return value
    if isinstance(value, Enum):
        return PositionState(str(value.value).upper())
    return PositionState(str(value).upper())


def is_transition_allowed(from_state: PositionState, to_state: PositionState) -> bool:
    return (from_state, to_state) in ALLOWED_TRANSITIONS


@dataclass
class PositionLifecycle:
    symbol: str
    trader_type: str
    quantity: int = 0
    state: PositionState = PositionState.FLAT
    stop_loss_price: float | None = None
    stop_order_id: str | None = None
    trailing_stop_price: float | None = None
    partial_profit_taken: bool = False
    state_history: list[dict] = field(default_factory=list)


@dataclass
class LifecycleTransition:
    transition_id: str
    symbol: str
    trader_type: str
    from_state: PositionState
    to_state: PositionState
    intent: LifecycleIntent
    reason_code: str
    reason: str
    mode: str
    requested_quantity: int
    filled_quantity: int
    quantity_before: int
    quantity_after: int
    fill_status: str
    execution_blocked: bool
    fill_latency_ms: int | None
    transition_seq: int
    timestamp: datetime

    def to_storage_record(self, run_id: str) -> dict:
        return {
            "transition_id": self.transition_id,
            "run_id": run_id,
            "symbol": self.symbol,
            "trader_type": self.trader_type,
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "intent": self.intent.value,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "mode": self.mode,
            "requested_quantity": self.requested_quantity,
            "filled_quantity": self.filled_quantity,
            "quantity_before": self.quantity_before,
            "quantity_after": self.quantity_after,
            "fill_status": self.fill_status,
            "execution_blocked": int(self.execution_blocked),
            "fill_latency_ms": self.fill_latency_ms,
            "transition_seq": self.transition_seq,
            "timestamp": self.timestamp.isoformat(),
            "created_at": self.timestamp.isoformat(),
        }


@dataclass
class LifecycleResult:
    accepted: bool
    transitions: list[LifecycleTransition]
    rejection_reason_code: str | None = None
    rejection_reason: str | None = None


class PositionLifecycleEngine:
    def __init__(
        self,
        *,
        event_collector=None,
        storage_engine: StorageEngine | None = None,
        now_fn: Callable[[], datetime] | None = None,
        trailing_stop_sync_fn: Callable[[str, str, float], None] | None = None,
    ) -> None:
        self.event_collector = event_collector
        self.storage_engine = storage_engine
        self._seq = 0
        self._now = now_fn or (lambda: datetime.now(timezone.utc))
        self._trailing_stop_sync_fn = trailing_stop_sync_fn

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _emit_event(self, event_type: str, payload: dict) -> None:
        if not self.event_collector:
            return
        self.event_collector.emit(
            event_type=event_type,
            source="PositionLifecycleEngine",
            payload=payload,
        )

    def _persist_transitions(self, transitions: Iterable[LifecycleTransition]) -> None:
        if not self.storage_engine:
            return
        for transition in transitions:
            self.storage_engine.store_lifecycle_transition(
                transition.to_storage_record(self.storage_engine.run_id)
            )

    def _reject(
        self,
        *,
        position: PositionLifecycle,
        intent: LifecycleIntent,
        run_mode: RunMode,
        reason_code: str,
        reason: str,
    ) -> LifecycleResult:
        payload = {
            "symbol": position.symbol,
            "trader_type": position.trader_type,
            "from_state": position.state.value,
            "intent": intent.value,
            "reason_code": reason_code,
            "reason": reason,
            "mode": run_mode.value,
        }
        self._emit_event("LIFECYCLE_TRANSITION_REJECTED", payload)
        return LifecycleResult(
            accepted=False,
            transitions=[],
            rejection_reason_code=reason_code,
            rejection_reason=reason,
        )

    def _simulate_fill(self, requested_quantity: int, run_mode: RunMode) -> tuple[int, str, int | None]:
        if requested_quantity <= 0:
            return 0, "NONE", None
        if run_mode == RunMode.SIM:
            filled = requested_quantity if requested_quantity <= 1 else max(1, requested_quantity // 2)
            status = "FULL" if filled == requested_quantity else "PARTIAL"
            return filled, status, None
        if run_mode == RunMode.PAPER:
            return requested_quantity, "FULL", 750
        if run_mode == RunMode.READ_ONLY:
            return 0, "BLOCKED", None
        return 0, "PENDING", None

    def _apply_transition(
        self,
        *,
        position: PositionLifecycle,
        to_state: PositionState,
        intent: LifecycleIntent,
        run_mode: RunMode,
        requested_quantity: int,
        filled_quantity: int,
        fill_status: str,
        execution_blocked: bool,
        fill_latency_ms: int | None,
        reason_code: str,
        reason: str,
    ) -> LifecycleTransition:
        from_state = position.state
        if from_state == PositionState.CLOSED:
            raise LifecycleTransitionError("STATE_IMMUTABLE", "Closed positions are immutable.")
        if not is_transition_allowed(from_state, to_state):
            raise LifecycleTransitionError(
                "INVALID_TRANSITION",
                f"Invalid transition {from_state.value} -> {to_state.value}",
            )
        quantity_before = position.quantity
        position.state = to_state
        transition = LifecycleTransition(
            transition_id=str(uuid4()),
            symbol=position.symbol,
            trader_type=position.trader_type,
            from_state=from_state,
            to_state=to_state,
            intent=intent,
            reason_code=reason_code,
            reason=reason,
            mode=run_mode.value,
            requested_quantity=requested_quantity,
            filled_quantity=filled_quantity,
            quantity_before=quantity_before,
            quantity_after=position.quantity,
            fill_status=fill_status,
            execution_blocked=execution_blocked,
            fill_latency_ms=fill_latency_ms,
            transition_seq=self._next_seq(),
            timestamp=self._now(),
        )
        position.state_history.append(
            {
                "from": from_state.value,
                "to": to_state.value,
                "tick": None,
                "reason": reason,
                "reason_code": reason_code,
            }
        )
        self._emit_event(
            "LIFECYCLE_TRANSITION",
            {
                "symbol": position.symbol,
                "trader_type": position.trader_type,
                "from_state": from_state.value,
                "to_state": to_state.value,
                "intent": intent.value,
                "reason_code": reason_code,
                "reason": reason,
                "mode": run_mode.value,
                "requested_quantity": requested_quantity,
                "filled_quantity": filled_quantity,
                "quantity_before": quantity_before,
                "quantity_after": position.quantity,
                "fill_status": fill_status,
                "execution_blocked": execution_blocked,
                "fill_latency_ms": fill_latency_ms,
                "transition_seq": transition.transition_seq,
            },
        )
        return transition

    def apply_intent(
        self,
        position: PositionLifecycle,
        intent: LifecycleIntent,
        *,
        requested_quantity: int,
        run_mode: RunMode,
        reason: str,
        risk_approved: bool | None = None,
        filled_quantity_override: int | None = None,
        fill_status_override: str | None = None,
        fill_latency_ms_override: int | None = None,
    ) -> LifecycleResult:
        self._emit_event(
            "LIFECYCLE_INTENT",
            {
                "symbol": position.symbol,
                "trader_type": position.trader_type,
                "intent": intent.value,
                "requested_quantity": requested_quantity,
                "mode": run_mode.value,
                "reason": reason,
            },
        )
        if requested_quantity <= 0:
            return self._reject(
                position=position,
                intent=intent,
                run_mode=run_mode,
                reason_code="INVALID_QUANTITY",
                reason="Requested quantity must be positive.",
            )
        if run_mode == RunMode.LIVE and not risk_approved:
            return self._reject(
                position=position,
                intent=intent,
                run_mode=run_mode,
                reason_code="RISK_APPROVAL_REQUIRED",
                reason="LIVE intent requires explicit risk approval.",
            )
        execution_blocked = run_mode == RunMode.READ_ONLY
        if filled_quantity_override is None:
            filled_quantity, fill_status, fill_latency_ms = self._simulate_fill(
                requested_quantity, run_mode
            )
        else:
            filled_quantity = filled_quantity_override
            fill_status = fill_status_override or "FULL"
            fill_latency_ms = fill_latency_ms_override
        transitions: list[LifecycleTransition] = []

        try:
            if intent == LifecycleIntent.OPEN:
                if position.state != PositionState.FLAT:
                    raise LifecycleTransitionError(
                        "INVALID_STATE",
                        "OPEN intent requires FLAT state.",
                    )
                position.quantity += filled_quantity
                transitions.append(
                    self._apply_transition(
                        position=position,
                        to_state=PositionState.OPEN,
                        intent=intent,
                        run_mode=run_mode,
                        requested_quantity=requested_quantity,
                        filled_quantity=filled_quantity,
                        fill_status=fill_status,
                        execution_blocked=execution_blocked,
                        fill_latency_ms=fill_latency_ms,
                        reason_code="OPEN_INTENT_ACCEPTED",
                        reason=reason,
                    )
                )
            elif intent in {LifecycleIntent.ADD, LifecycleIntent.ADD_TO_WINNER}:
                if position.state != PositionState.OPEN:
                    raise LifecycleTransitionError(
                        "INVALID_STATE",
                        "ADD intent requires OPEN state.",
                    )
                position.quantity += filled_quantity
                transitions.append(
                    self._apply_transition(
                        position=position,
                        to_state=PositionState.SCALING_IN,
                        intent=intent,
                        run_mode=run_mode,
                        requested_quantity=requested_quantity,
                        filled_quantity=filled_quantity,
                        fill_status=fill_status,
                        execution_blocked=execution_blocked,
                        fill_latency_ms=fill_latency_ms,
                        reason_code="ADD_TO_WINNER_ACCEPTED" if intent == LifecycleIntent.ADD_TO_WINNER else "ADD_INTENT_ACCEPTED",
                        reason=reason,
                    )
                )
                transitions.append(
                    self._apply_transition(
                        position=position,
                        to_state=PositionState.OPEN,
                        intent=intent,
                        run_mode=run_mode,
                        requested_quantity=requested_quantity,
                        filled_quantity=filled_quantity,
                        fill_status=fill_status,
                        execution_blocked=execution_blocked,
                        fill_latency_ms=fill_latency_ms,
                        reason_code="SCALING_IN_COMPLETE",
                        reason="Scaling in completed.",
                    )
                )
            elif intent in {LifecycleIntent.SCALE_OUT, LifecycleIntent.PARTIAL_PROFIT}:
                if position.state != PositionState.OPEN:
                    raise LifecycleTransitionError(
                        "INVALID_STATE",
                        "SCALE_OUT intent requires OPEN state.",
                    )
                if requested_quantity >= position.quantity:
                    raise LifecycleTransitionError(
                        "SCALE_OUT_EXCEEDS_POSITION",
                        "Scale-out quantity must be less than current position.",
                    )
                position.quantity = max(position.quantity - filled_quantity, 0)
                transitions.append(
                    self._apply_transition(
                        position=position,
                        to_state=PositionState.REDUCING,
                        intent=intent,
                        run_mode=run_mode,
                        requested_quantity=requested_quantity,
                        filled_quantity=filled_quantity,
                        fill_status=fill_status,
                        execution_blocked=execution_blocked,
                        fill_latency_ms=fill_latency_ms,
                        reason_code="PARTIAL_PROFIT_ACCEPTED" if intent == LifecycleIntent.PARTIAL_PROFIT else "SCALE_OUT_ACCEPTED",
                        reason=reason,
                    )
                )
                transitions.append(
                    self._apply_transition(
                        position=position,
                        to_state=PositionState.OPEN,
                        intent=intent,
                        run_mode=run_mode,
                        requested_quantity=requested_quantity,
                        filled_quantity=filled_quantity,
                        fill_status=fill_status,
                        execution_blocked=execution_blocked,
                        fill_latency_ms=fill_latency_ms,
                        reason_code="REDUCING_COMPLETE",
                        reason="Scale-out completed.",
                    )
                )
            elif intent == LifecycleIntent.TRAILING_STOP_UPDATE:
                if position.state != PositionState.OPEN:
                    raise LifecycleTransitionError(
                        "INVALID_STATE",
                        "TRAILING_STOP_UPDATE requires OPEN state.",
                    )
                position.trailing_stop_price = float(reason.split("=")[-1]) if "=" in reason else position.trailing_stop_price
                if self._trailing_stop_sync_fn and position.trailing_stop_price is not None and position.stop_order_id:
                    self._trailing_stop_sync_fn(position.symbol, position.stop_order_id, position.trailing_stop_price)
                transitions.append(
                    self._apply_transition(
                        position=position,
                        to_state=PositionState.OPEN,
                        intent=intent,
                        run_mode=run_mode,
                        requested_quantity=requested_quantity,
                        filled_quantity=0,
                        fill_status="NONE",
                        execution_blocked=execution_blocked,
                        fill_latency_ms=fill_latency_ms,
                        reason_code="TRAILING_STOP_UPDATED",
                        reason=reason,
                    )
                )
            else:
                if position.state != PositionState.OPEN:
                    raise LifecycleTransitionError(
                        "INVALID_STATE",
                        "Exit intent requires OPEN state.",
                    )
                if filled_quantity_override is None:
                    filled_quantity = (
                        position.quantity if run_mode in {RunMode.SIM, RunMode.PAPER} else filled_quantity
                    )
                    if run_mode in {RunMode.SIM, RunMode.PAPER}:
                        fill_status = "FULL"
                position.quantity = max(position.quantity - filled_quantity, 0)
                transitions.append(
                    self._apply_transition(
                        position=position,
                        to_state=PositionState.CLOSING,
                        intent=intent,
                        run_mode=run_mode,
                        requested_quantity=requested_quantity,
                        filled_quantity=filled_quantity,
                        fill_status=fill_status,
                        execution_blocked=execution_blocked,
                        fill_latency_ms=fill_latency_ms,
                        reason_code="EXIT_INTENT_ACCEPTED",
                        reason=reason,
                    )
                )
                if position.quantity == 0:
                    transitions.append(
                        self._apply_transition(
                            position=position,
                            to_state=PositionState.CLOSED,
                            intent=intent,
                            run_mode=run_mode,
                            requested_quantity=requested_quantity,
                            filled_quantity=filled_quantity,
                            fill_status=fill_status,
                            execution_blocked=execution_blocked,
                            fill_latency_ms=fill_latency_ms,
                            reason_code="POSITION_CLOSED",
                            reason="Exit completed.",
                        )
                    )
        except LifecycleTransitionError as exc:
            return self._reject(
                position=position,
                intent=intent,
                run_mode=run_mode,
                reason_code=exc.reason_code,
                reason=str(exc),
            )

        self._persist_transitions(transitions)
        return LifecycleResult(accepted=True, transitions=transitions)

    @staticmethod
    def replay_transitions(transitions: Iterable[dict]) -> dict[tuple[str, str], PositionLifecycle]:
        ordered = sorted(transitions, key=lambda item: item.get("transition_seq", 0))
        positions: dict[tuple[str, str], PositionLifecycle] = {}
        for transition in ordered:
            key = (transition.get("symbol"), transition.get("trader_type"))
            position = positions.get(key)
            if position is None:
                position = PositionLifecycle(
                    symbol=transition.get("symbol"),
                    trader_type=transition.get("trader_type"),
                )
                positions[key] = position
            position.state = normalize_state(transition.get("to_state"))
            position.quantity = int(transition.get("quantity_after", 0))
            position.state_history.append(
                {
                    "from": transition.get("from_state"),
                    "to": transition.get("to_state"),
                    "reason": transition.get("reason"),
                    "reason_code": transition.get("reason_code"),
                    "transition_seq": transition.get("transition_seq"),
                }
            )
        return positions
