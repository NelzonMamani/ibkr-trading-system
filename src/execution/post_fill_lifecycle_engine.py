from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
from typing import Any

from src.core.take_profit_authority import TakeProfitAuthority, TakeProfitDecision, TakeProfitTargetType
from src.core.stop_loss_authority import (
    StopAuditEventType,
    StopAuditTrail,
    StopAuthority,
    StopAuthorityError,
    StopProtectionEvidence,
    StopRecoveryClassification,
    assess_stop_protection,
    classify_stop_recovery,
    validate_stop_price,
    validate_stop_update,
)


class PositionLifecycleState(str, Enum):
    ENTRY_SUBMITTED = "ENTRY_SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED_UNPROTECTED = "FILLED_UNPROTECTED"
    PROTECTION_PENDING = "PROTECTION_PENDING"
    PROTECTED = "PROTECTED"
    TARGET_ACTIVE = "TARGET_ACTIVE"
    TRAILING_ELIGIBLE = "TRAILING_ELIGIBLE"
    TRAILING_ACTIVE = "TRAILING_ACTIVE"
    EXIT_PENDING = "EXIT_PENDING"
    EXITED = "EXITED"
    RECOVERY_PENDING = "RECOVERY_PENDING"
    RECOVERED = "RECOVERED"
    ORPHANED_POSITION = "ORPHANED_POSITION"
    FAILSAFE_TRIGGERED = "FAILSAFE_TRIGGERED"
    LIFECYCLE_FAILURE = "LIFECYCLE_FAILURE"


@dataclass
class ProtectionOrderMeta:
    order_type: str
    side: str
    trigger_price: float
    broker_order_id: str | None = None
    status: str = "REGISTERED"
    lifecycle_trade_id: str | None = None
    strategy_owner: str | None = None
    entry_order_id: str | None = None
    entry_intent_id: str | None = None
    pending_intent_id: str | None = None
    emergency_stop_exception: str | None = None
    quantity: int = 0
    target_id: str | None = None
    target_type: str | None = None
    target_stage: str | None = None
    source_strategy: str | None = None
    rationale: str | None = None


@dataclass
class ManagedTradeLifecycle:
    trade_id: str
    symbol: str
    strategy_id: str
    side: str
    run_mode: str
    session_label: str
    intended_qty: int
    filled_qty: int
    avg_fill_price: float
    exited_qty: int = 0
    exit_fill_price: float | None = None
    exit_fill_time: str | None = None
    exit_order_id: str | None = None
    realized_pnl: float = 0.0
    realized_pnl_by_exit_reason: dict[str, float] = field(default_factory=dict)
    state: PositionLifecycleState = PositionLifecycleState.ENTRY_SUBMITTED
    stop: ProtectionOrderMeta | None = None
    target: ProtectionOrderMeta | None = None
    trailing_active: bool = False
    partial_exit_count: int = 0
    trailing_mode: str = "break_even_then_offset"
    break_even_activation: float = 0.0
    trailing_activation: float = 0.0
    high_water_mark: float | None = None
    last_update_ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_recovery_status: str | None = None
    failure_flags: list[str] = field(default_factory=list)
    take_profit_events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        return payload


@dataclass
class LifecyclePolicy:
    default_stop_pct: float = 0.01
    default_target_pct: float = 0.02
    break_even_pct: float = 0.01
    trailing_activation_pct: float = 0.015
    trailing_offset_pct: float = 0.0075
    install_retry_limit: int = 2
    fail_safe_action_live: str = "BLOCK_NEW_ENTRIES"
    fail_safe_action_paper: str = "DEGRADED_ALERT"


_ALLOWED_TRANSITIONS: dict[PositionLifecycleState, set[PositionLifecycleState]] = {
    PositionLifecycleState.ENTRY_SUBMITTED: {
        PositionLifecycleState.PARTIALLY_FILLED,
        PositionLifecycleState.FILLED_UNPROTECTED,
        PositionLifecycleState.LIFECYCLE_FAILURE,
    },
    PositionLifecycleState.PARTIALLY_FILLED: {
        PositionLifecycleState.PROTECTION_PENDING,
        PositionLifecycleState.FILLED_UNPROTECTED,
        PositionLifecycleState.LIFECYCLE_FAILURE,
    },
    PositionLifecycleState.FILLED_UNPROTECTED: {
        PositionLifecycleState.PROTECTION_PENDING,
        PositionLifecycleState.LIFECYCLE_FAILURE,
    },
    PositionLifecycleState.PROTECTION_PENDING: {
        PositionLifecycleState.PROTECTED,
        PositionLifecycleState.LIFECYCLE_FAILURE,
    },
    PositionLifecycleState.PROTECTED: {
        PositionLifecycleState.TARGET_ACTIVE,
        PositionLifecycleState.TRAILING_ELIGIBLE,
        PositionLifecycleState.EXIT_PENDING,
        PositionLifecycleState.FAILSAFE_TRIGGERED,
    },
    PositionLifecycleState.TARGET_ACTIVE: {PositionLifecycleState.TRAILING_ELIGIBLE, PositionLifecycleState.EXIT_PENDING, PositionLifecycleState.FAILSAFE_TRIGGERED},
    PositionLifecycleState.TRAILING_ELIGIBLE: {PositionLifecycleState.TRAILING_ACTIVE, PositionLifecycleState.EXIT_PENDING, PositionLifecycleState.FAILSAFE_TRIGGERED},
    PositionLifecycleState.TRAILING_ACTIVE: {PositionLifecycleState.EXIT_PENDING, PositionLifecycleState.FAILSAFE_TRIGGERED},
    PositionLifecycleState.EXIT_PENDING: {PositionLifecycleState.EXITED, PositionLifecycleState.FAILSAFE_TRIGGERED},
    PositionLifecycleState.RECOVERY_PENDING: {PositionLifecycleState.RECOVERED, PositionLifecycleState.LIFECYCLE_FAILURE},
    PositionLifecycleState.RECOVERED: {PositionLifecycleState.PROTECTED, PositionLifecycleState.TARGET_ACTIVE, PositionLifecycleState.TRAILING_ELIGIBLE, PositionLifecycleState.FAILSAFE_TRIGGERED},
    PositionLifecycleState.FAILSAFE_TRIGGERED: {PositionLifecycleState.LIFECYCLE_FAILURE},
}


class PostFillLifecycleEngine:
    def __init__(
        self,
        run_mode: str,
        policy: LifecyclePolicy | None = None,
        execution_provider: Any | None = None,
        stop_audit_trail: StopAuditTrail | None = None,
        storage_engine: Any | None = None,
        take_profit_authority: TakeProfitAuthority | None = None,
    ) -> None:
        self.run_mode = str(run_mode or "SIM").upper()
        self.policy = policy or LifecyclePolicy()
        self.execution_provider = execution_provider
        self.stop_audit_trail = stop_audit_trail or StopAuditTrail(storage_engine=storage_engine)
        self.take_profit_authority = take_profit_authority or TakeProfitAuthority()
        self._trades: dict[str, ManagedTradeLifecycle] = {}
        self._active_trade_ids: set[str] = set()
        self._active_position_qty_by_symbol: dict[str, int] = {}
        self._pending_exit_requests: dict[str, dict[str, Any]] = {}

    def _authority_for_trade(self, trade: ManagedTradeLifecycle) -> StopAuthority:
        return StopAuthority(
            symbol=trade.symbol,
            lifecycle_trade_id=trade.trade_id,
            position_id=trade.trade_id,
            strategy_owner=trade.strategy_id,
            entry_order_id=trade.trade_id,
            entry_intent_id=trade.trade_id,
        )

    def _record_stop_event(
        self,
        trade: ManagedTradeLifecycle,
        event_type: StopAuditEventType,
        *,
        stop_price: float | None = None,
        previous_stop_price: float | None = None,
        active_stop_order_id: str | None = None,
        pending_stop_order_intent: str | None = None,
        status: str | None = None,
        reason: str | None = None,
        recovery_classification: StopRecoveryClassification | str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.stop_audit_trail.record(
            event_type,
            self._authority_for_trade(trade),
            stop_price=stop_price,
            previous_stop_price=previous_stop_price,
            active_stop_order_id=active_stop_order_id,
            pending_stop_order_intent=pending_stop_order_intent,
            quantity=int(trade.filled_qty or 0),
            status=status,
            reason=reason,
            recovery_classification=recovery_classification,
            payload=payload,
        )

    def assess_trade_stop_protection(self, trade_id: str) -> dict[str, Any]:
        trade = self._trades.get(str(trade_id))
        if trade is None:
            return {"status": "UNSAFE", "protected": False, "reason_code": "TRADE_NOT_FOUND"}
        evidence = StopProtectionEvidence(
            symbol=trade.symbol,
            state="OPEN" if self._is_open_trade_state(trade.state) and int(trade.filled_qty or 0) > 0 else "CLOSED",
            active_stop_order_id=trade.stop.broker_order_id if trade.stop else None,
            pending_stop_order_intent=trade.stop.pending_intent_id if trade.stop else None,
            emergency_stop_exception=trade.stop.emergency_stop_exception if trade.stop else None,
        )
        return assess_stop_protection(evidence)

    @staticmethod
    def _is_open_trade_state(state: PositionLifecycleState) -> bool:
        return state not in {PositionLifecycleState.EXITED, PositionLifecycleState.LIFECYCLE_FAILURE}

    def _update_in_memory_state(self) -> None:
        open_trade_ids: set[str] = set()
        open_qty_by_symbol: dict[str, int] = {}
        for trade_id, trade in self._trades.items():
            if not self._is_open_trade_state(trade.state):
                continue
            remaining_qty = int(trade.filled_qty or 0)
            if remaining_qty <= 0:
                continue
            open_trade_ids.add(trade_id)
            open_qty_by_symbol[trade.symbol] = open_qty_by_symbol.get(trade.symbol, 0) + remaining_qty
        self._active_trade_ids = open_trade_ids
        self._active_position_qty_by_symbol = open_qty_by_symbol

    def _get_open_trades_for_symbol(self, symbol: str) -> list[str]:
        symbol_u = str(symbol or "").upper()
        if not symbol_u:
            return []
        open_trade_ids: list[str] = []
        for trade_id, trade in self._trades.items():
            if trade.symbol != symbol_u:
                continue
            if not self._is_open_trade_state(trade.state):
                continue
            if int(trade.filled_qty or 0) <= 0:
                continue
            open_trade_ids.append(trade_id)
        return open_trade_ids

    @staticmethod
    def _ts() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _is_filled_status(status: str | None) -> bool:
        return str(status or "").upper() in {"FILLED"}

    @staticmethod
    def _is_cancelled_status(status: str | None) -> bool:
        return str(status or "").upper() in {"CANCELLED", "CANCELED"}

    @staticmethod
    def _order_fields(order: Any) -> dict[str, str]:
        if isinstance(order, dict):
            order_obj = order
            order_state = order
            contract = order
        else:
            order_obj = getattr(order, "order", None)
            order_state = getattr(order, "orderState", None)
            contract = getattr(order, "contract", None)
        order_id = str(
            getattr(order, "orderId", None)
            or getattr(order, "order_id", None)
            or (order_obj.get("orderId") if isinstance(order_obj, dict) else "")
            or (order_obj.get("order_id") if isinstance(order_obj, dict) else "")
            or ""
        )
        symbol = str(
            getattr(contract, "symbol", None)
            or getattr(order, "symbol", None)
            or (contract.get("symbol") if isinstance(contract, dict) else "")
            or ""
        ).upper()
        order_type = str(
            getattr(order_obj, "orderType", None)
            or getattr(order, "order_type", None)
            or (order_obj.get("order_type") if isinstance(order_obj, dict) else "")
            or (order.get("orderType") if isinstance(order, dict) else "")
            or (order.get("order_type") if isinstance(order, dict) else "")
            or ""
        ).upper()
        status = str(
            getattr(order_state, "status", None)
            or getattr(order, "status", None)
            or (order_state.get("status") if isinstance(order_state, dict) else "")
            or (order.get("status") if isinstance(order, dict) else "")
            or ""
        ).upper()
        order_ref = str(getattr(order_obj, "orderRef", None) or (order_obj.get("order_ref") if isinstance(order_obj, dict) else "") or "")
        metadata = {}
        if isinstance(order, dict):
            metadata = order.get("metadata") or {}
        else:
            metadata = getattr(order, "metadata", {}) or {}
        stop_price = (
            getattr(order_obj, "auxPrice", None)
            or getattr(order, "stop_price", None)
            or (order_obj.get("auxPrice") if isinstance(order_obj, dict) else None)
            or (order.get("stop_price") if isinstance(order, dict) else None)
            or metadata.get("stop_price")
        )
        return {
            "order_id": order_id,
            "symbol": symbol,
            "order_type": order_type,
            "status": status,
            "order_ref": order_ref,
            "stop_price": stop_price,
        }

    def _transition(self, trade: ManagedTradeLifecycle, target: PositionLifecycleState, reason: str) -> bool:
        if trade.state == target:
            return True
        allowed = _ALLOWED_TRANSITIONS.get(trade.state, set())
        if target not in allowed:
            print(
                "[LIFECYCLE][ILLEGAL_TRANSITION] "
                f"trade_id={trade.trade_id} symbol={trade.symbol} from={trade.state.value} to={target.value} reason={reason}"
            )
            return False
        print(
            "[LIFECYCLE][TRANSITION] "
            f"trade_id={trade.trade_id} symbol={trade.symbol} from={trade.state.value} to={target.value} reason={reason}"
        )
        trade.state = target
        trade.last_update_ts = self._ts()
        print(f"[LIFECYCLE][STATE] trade_id={trade.trade_id} state={trade.state.value}")
        return True

    def _record_take_profit_event(
        self,
        trade: ManagedTradeLifecycle,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event_type_u = str(event_type or "").upper()
        payload = dict(payload or {})
        event_payload = {
            "event_type": event_type_u,
            "trade_id": trade.trade_id,
            "symbol": trade.symbol,
            "timestamp": self._ts(),
            **payload,
        }
        trade.take_profit_events.append(event_payload)
        tag_map = {
            "TAKE_PROFIT_CREATED": "CREATE",
            "TAKE_PROFIT_SUBMITTED": "SUBMIT",
            "TAKE_PROFIT_PARTIALLY_FILLED": "PARTIAL",
            "TAKE_PROFIT_FILLED": "FILL",
            "TAKE_PROFIT_CANCELLED": "CANCEL",
            "TAKE_PROFIT_SUPERSEDED": "SUPERSEDE",
            "TAKE_PROFIT_REJECTED": "REJECT",
        }
        tag = tag_map.get(event_type_u, "AUDIT")
        print(
            f"[TAKE_PROFIT][{tag}] "
            f"trade_id={trade.trade_id} symbol={trade.symbol} event={event_type_u} "
            f"target_id={payload.get('target_id') or payload.get('target', {}).get('target_id') or 'NONE'}"
        )
        print(f"[TAKE_PROFIT][AUDIT] trade_id={trade.trade_id} event={event_type_u} payload={payload}")

    def _clear_unsubmitted_take_profit_target(
        self,
        *,
        trade: ManagedTradeLifecycle,
        target_decision: TakeProfitDecision | None,
        reason: str,
        attempt: int,
    ) -> None:
        target_id = trade.target.target_id if trade.target is not None else None
        if target_id is None and target_decision is not None:
            target_id = target_decision.target_id
        if not target_id:
            self._record_take_profit_event(
                trade,
                "TAKE_PROFIT_REJECTED",
                {"reason": reason, "attempt": attempt},
            )
            return

        broker_order_id = trade.target.broker_order_id if trade.target is not None else None
        if broker_order_id:
            self._record_take_profit_event(
                trade,
                "TAKE_PROFIT_REJECTED",
                {
                    "target_id": target_id,
                    "broker_order_id": broker_order_id,
                    "reason": reason,
                    "attempt": attempt,
                },
            )
            return

        try:
            rejected = self.take_profit_authority.mark_rejected(
                target_id=target_id,
                reason=f"protection_install_failed_attempt_{attempt}: {reason}",
            )
            payload = rejected.to_audit_payload()
            payload["attempt"] = attempt
            self._record_take_profit_event(trade, rejected.lifecycle_event, payload)
        except Exception as cleanup_exc:
            self._record_take_profit_event(
                trade,
                "TAKE_PROFIT_REJECTED",
                {
                    "target_id": target_id,
                    "reason": reason,
                    "attempt": attempt,
                    "cleanup_error": str(cleanup_exc),
                },
            )
        if trade.target is not None and not trade.target.broker_order_id:
            trade.target.status = "REJECTED"
            trade.target = None

    @staticmethod
    def _exit_attribution(reason: str) -> str:
        normalized = str(reason or "").upper()
        if "TARGET" in normalized or "TAKE_PROFIT" in normalized:
            return "TAKE_PROFIT"
        if "TRAIL" in normalized:
            return "TRAILING_STOP"
        if "STOP" in normalized:
            return "STOP_LOSS"
        if "MANUAL" in normalized or "FORCED" in normalized or "TIME" in normalized:
            return "MANUAL_FORCED"
        if "BROKER" in normalized or "EXTERNAL" in normalized:
            return "BROKER_EXTERNAL"
        return "UNKNOWN"

    def _compute_stop_target(self, trade: ManagedTradeLifecycle) -> tuple[float, TakeProfitDecision]:
        side_u = str(trade.side).upper()
        if side_u not in {"LONG", "BUY"}:
            raise ValueError("post-fill v1 supports long-side lifecycle hardening")
        stop = trade.avg_fill_price * (1.0 - self.policy.default_stop_pct)
        target_decision = self.take_profit_authority.create_fixed_percent_target(
            trade_id=trade.trade_id,
            symbol=trade.symbol,
            side=trade.side,
            entry_price=trade.avg_fill_price,
            target_pct=self.policy.default_target_pct,
            live_position_quantity=trade.filled_qty,
            source_strategy=trade.strategy_id,
            target_stage="PARTIAL_1" if int(trade.filled_qty or 0) > 1 else "FULL",
            fraction=0.5 if int(trade.filled_qty or 0) > 1 else None,
        )
        if not target_decision.accepted or target_decision.target_price is None:
            raise ValueError(target_decision.rationale)
        target = float(target_decision.target_price)
        if stop >= trade.avg_fill_price:
            raise ValueError("invalid stop geometry: protective stop must be below long fill")
        if target <= trade.avg_fill_price:
            raise ValueError("invalid target geometry: target must be above long fill")
        print(
            "[LIFECYCLE][PROTECTION_POLICY] "
            f"side={side_u} fill={trade.avg_fill_price:.4f} stop_pct={self.policy.default_stop_pct:.4f} target_pct={self.policy.default_target_pct:.4f}"
        )
        print(f"[LIFECYCLE][STOP_COMPUTED] stop={stop:.4f}")
        print(f"[LIFECYCLE][TARGET_COMPUTED] target={target:.4f}")
        return stop, target_decision

    def activate_trade_management_after_fill(
        self,
        *,
        trade_id: str,
        symbol: str,
        side: str,
        filled_qty: int,
        avg_fill_price: float,
        strategy_id: str,
        session_label: str = "runtime",
        intended_qty: int | None = None,
    ) -> dict[str, Any]:
        trade = ManagedTradeLifecycle(
            trade_id=str(trade_id),
            symbol=str(symbol).upper(),
            strategy_id=str(strategy_id or "UNKNOWN"),
            side=str(side).upper(),
            run_mode=self.run_mode,
            session_label=session_label,
            intended_qty=int(intended_qty or filled_qty),
            filled_qty=int(filled_qty),
            avg_fill_price=float(avg_fill_price),
            state=PositionLifecycleState.FILLED_UNPROTECTED,
            break_even_activation=float(avg_fill_price) * (1.0 + self.policy.break_even_pct),
            trailing_activation=float(avg_fill_price) * (1.0 + self.policy.trailing_activation_pct),
            high_water_mark=float(avg_fill_price),
        )
        self._trades[trade.trade_id] = trade
        self._update_in_memory_state()
        print(f"[LIFECYCLE][STATE] trade_id={trade.trade_id} state={trade.state.value}")
        self._record_stop_event(
            trade,
            StopAuditEventType.STOP_REQUIRED,
            reason="entry_fill_requires_protective_stop",
            status="REQUIRED",
        )

        if self.run_mode == "READ_ONLY":
            trade.failure_flags.append("READ_ONLY_NO_MUTATION")
            self._record_stop_event(
                trade,
                StopAuditEventType.STOP_REJECTED,
                reason="READ_ONLY_NO_ORDER_MUTATION",
                status="REJECTED",
            )
            print(
                "[LIFECYCLE][CRITICAL][UNPROTECTED_POSITION] "
                f"trade_id={trade.trade_id} symbol={trade.symbol} reason=READ_ONLY_NO_ORDER_MUTATION"
            )
            self._transition(trade, PositionLifecycleState.LIFECYCLE_FAILURE, "read_only_no_install")
            return {"success": False, "trade": trade.to_dict(), "failure_reason": "READ_ONLY_MODE"}

        installed = False
        failure_reason: str | None = None
        for attempt in range(1, self.policy.install_retry_limit + 1):
            self._transition(trade, PositionLifecycleState.PROTECTION_PENDING, f"install_attempt_{attempt}")
            target_decision: TakeProfitDecision | None = None
            try:
                stop, target_decision = self._compute_stop_target(trade)
                self._record_take_profit_event(
                    trade,
                    target_decision.lifecycle_event,
                    target_decision.to_audit_payload(),
                )
                validate_stop_price(side=side, stop_price=stop, entry_price=float(avg_fill_price))
                pending_stop_intent = f"stop-submit:{trade.trade_id}:{attempt}"
                trade.stop = ProtectionOrderMeta(
                    order_type="STOP",
                    side="SELL",
                    trigger_price=stop,
                    status="PENDING_SUBMIT",
                    lifecycle_trade_id=trade.trade_id,
                    strategy_owner=trade.strategy_id,
                    entry_order_id=trade.trade_id,
                    entry_intent_id=trade.trade_id,
                    pending_intent_id=pending_stop_intent,
                )
                trade.target = ProtectionOrderMeta(
                    order_type="LIMIT",
                    side="SELL",
                    trigger_price=float(target_decision.target_price or 0.0),
                    status="PENDING_SUBMIT",
                    quantity=target_decision.target_quantity,
                    target_id=target_decision.target_id,
                    target_type=target_decision.target_type,
                    target_stage=target_decision.target_stage,
                    source_strategy=target_decision.source_strategy,
                    rationale=target_decision.rationale,
                )
                self._record_stop_event(
                    trade,
                    StopAuditEventType.STOP_SUBMITTED,
                    stop_price=stop,
                    pending_stop_order_intent=pending_stop_intent,
                    status="PENDING_SUBMIT",
                    reason="protective_stop_submit_attempt",
                )
                print(
                    "[LIFECYCLE][ORDER_INSTALL][STOP] "
                    f"trade_id={trade.trade_id} symbol={trade.symbol} stop={stop:.4f}"
                )
                print(
                    "[LIFECYCLE][ORDER_INSTALL][TARGET] "
                    f"trade_id={trade.trade_id} symbol={trade.symbol} target={trade.target.trigger_price:.4f}"
                )
                print(
                    "[LIFECYCLE][ORDER_LINKAGE] "
                    f"trade_id={trade.trade_id} symbol={trade.symbol} entry_order_id={trade.trade_id}"
                )
                if self.execution_provider is not None and self.run_mode in {"PAPER", "LIVE"}:
                    stop_result = self.execution_provider.place_stop_order(
                        symbol=trade.symbol,
                        side=trade.stop.side,
                        quantity=trade.filled_qty,
                        stop_price=trade.stop.trigger_price,
                        trade_id=trade.trade_id,
                        parent_order_id=trade.trade_id,
                    )
                    target_result = self.execution_provider.place_target_order(
                        symbol=trade.symbol,
                        side=trade.target.side,
                        quantity=trade.target.quantity or trade.filled_qty,
                        limit_price=trade.target.trigger_price,
                        trade_id=trade.trade_id,
                        parent_order_id=trade.trade_id,
                    )
                    trade.stop.broker_order_id = str(stop_result.get("broker_order_id"))
                    trade.target.broker_order_id = str(target_result.get("broker_order_id"))
                    trade.stop.status = str(stop_result.get("status") or "Submitted")
                    trade.target.status = str(target_result.get("status") or "Submitted")
                    if trade.target.target_id:
                        submitted = self.take_profit_authority.mark_submitted(
                            target_id=trade.target.target_id,
                            broker_order_id=trade.target.broker_order_id,
                        )
                        self._record_take_profit_event(
                            trade,
                            submitted.lifecycle_event,
                            submitted.to_audit_payload(),
                        )
                else:
                    trade.stop.status = "REGISTERED"
                    trade.target.status = "REGISTERED"
                self._record_stop_event(
                    trade,
                    StopAuditEventType.STOP_ACKNOWLEDGED,
                    stop_price=trade.stop.trigger_price,
                    active_stop_order_id=trade.stop.broker_order_id,
                    pending_stop_order_intent=trade.stop.pending_intent_id,
                    status=trade.stop.status,
                    reason="protective_stop_acknowledged",
                )
                self._transition(trade, PositionLifecycleState.PROTECTED, "stop_installed")
                self._transition(trade, PositionLifecycleState.TARGET_ACTIVE, "target_registered")
                self._transition(trade, PositionLifecycleState.TRAILING_ELIGIBLE, "baseline_trailing_ready")
                installed = True
                failure_reason = None
                break
            except Exception as exc:  # defensive lifecycle boundary
                failure_reason = str(exc)
                self._clear_unsubmitted_take_profit_target(
                    trade=trade,
                    target_decision=target_decision,
                    reason=failure_reason,
                    attempt=attempt,
                )
                self._record_stop_event(
                    trade,
                    StopAuditEventType.STOP_REJECTED,
                    stop_price=trade.stop.trigger_price if trade.stop else None,
                    pending_stop_order_intent=trade.stop.pending_intent_id if trade.stop else None,
                    status="REJECTED",
                    reason=failure_reason,
                )
                print(f"[LIFECYCLE][POLICY_INVALID] trade_id={trade.trade_id} reason={failure_reason}")
                print(f"[LIFECYCLE][FAILSAFE][RETRY] trade_id={trade.trade_id} attempt={attempt}")

        if not installed:
            print(
                "[LIFECYCLE][CRITICAL][UNPROTECTED_POSITION] "
                f"trade_id={trade.trade_id} symbol={trade.symbol} reason={failure_reason or 'unknown'}"
            )
            trade.failure_flags.append("UNPROTECTED_POSITION")
            self._transition(trade, PositionLifecycleState.LIFECYCLE_FAILURE, "protection_install_failed")
            action = self.policy.fail_safe_action_live if self.run_mode == "LIVE" else self.policy.fail_safe_action_paper
            print(f"[LIFECYCLE][FAILSAFE][{action}] trade_id={trade.trade_id} symbol={trade.symbol}")

        print(
            "[LIFECYCLE][ORDER_INSTALL][RESULT] "
            f"trade_id={trade.trade_id} success={installed} state={trade.state.value}"
        )
        print(f"[LIFECYCLE][SUMMARY] trade_id={trade.trade_id} symbol={trade.symbol} state={trade.state.value}")
        return {
            "success": installed,
            "installed_stop_metadata": asdict(trade.stop) if trade.stop else None,
            "installed_target_metadata": asdict(trade.target) if trade.target else None,
            "protection_state": trade.state.value,
            "rationale": "initial_protection_installed" if installed else "protection_install_failed",
            "failure_reason": failure_reason,
            "trade": trade.to_dict(),
        }

    def evaluate_trailing(self, trade_id: str, current_price: float) -> dict[str, Any]:
        trade = self._trades.get(str(trade_id))
        if trade is None or trade.stop is None:
            return {"updated": False, "reason": "trade_missing_or_unprotected"}
        if trade.state not in {PositionLifecycleState.TRAILING_ELIGIBLE, PositionLifecycleState.TRAILING_ACTIVE}:
            return {"updated": False, "reason": f"state_not_trailing:{trade.state.value}"}

        if trade.partial_exit_count <= 0 and trade.state != PositionLifecycleState.PROTECTED:
            return {"updated": False, "reason": "profit_protection_not_reached", "stop_price": trade.stop.trigger_price}

        print(f"[TRAIL][ELIGIBLE] trade_id={trade.trade_id} symbol={trade.symbol} state={trade.state.value}")
        current = float(current_price)
        trade.high_water_mark = max(float(trade.high_water_mark or trade.avg_fill_price), current)

        if current < trade.trailing_activation:
            print(f"[TRAIL][NO_CHANGE] trade_id={trade.trade_id} reason=activation_not_reached")
            return {"updated": False, "reason": "activation_not_reached", "stop_price": trade.stop.trigger_price}

        if trade.state != PositionLifecycleState.TRAILING_ACTIVE:
            self._transition(trade, PositionLifecycleState.TRAILING_ACTIVE, "price_reached_trailing_activation")
            print(f"[TRAIL][ACTIVATE] trade_id={trade.trade_id} trigger={trade.trailing_activation:.4f}")

        candidate = max(
            trade.avg_fill_price,
            float(trade.high_water_mark) * (1.0 - self.policy.trailing_offset_pct),
        )
        if candidate < trade.stop.trigger_price:
            print(
                f"[TRAIL][REJECT_LOOSEN] trade_id={trade.trade_id} current_stop={trade.stop.trigger_price:.4f} candidate={candidate:.4f}"
            )
            return {"updated": False, "reason": "reject_loosen", "stop_price": trade.stop.trigger_price}
        if abs(candidate - trade.stop.trigger_price) < 1e-9:
            print(f"[TRAIL][NO_CHANGE] trade_id={trade.trade_id} reason=unchanged")
            return {"updated": False, "reason": "unchanged", "stop_price": trade.stop.trigger_price}

        previous_stop = float(trade.stop.trigger_price)
        validate_stop_update(
            authority=self._authority_for_trade(trade),
            requested_by_strategy=trade.strategy_id,
            side=trade.side,
            current_stop_price=previous_stop,
            candidate_stop_price=candidate,
            entry_price=trade.avg_fill_price,
            current_price=current,
        )
        trade.stop.trigger_price = candidate
        trade.last_update_ts = self._ts()
        print(f"[TRAIL][UPDATE] trade_id={trade.trade_id} new_stop={candidate:.4f} high_water={trade.high_water_mark:.4f}")
        if (
            self.execution_provider is not None
            and self.run_mode in {"PAPER", "LIVE"}
            and trade.stop.broker_order_id
        ):
            self.execution_provider.modify_stop_order(
                broker_order_id=trade.stop.broker_order_id,
                symbol=trade.symbol,
                side=trade.stop.side,
                quantity=trade.filled_qty,
                new_stop_price=trade.stop.trigger_price,
                trade_id=trade.trade_id,
            )
        self._record_stop_event(
            trade,
            StopAuditEventType.STOP_TIGHTENED,
            stop_price=trade.stop.trigger_price,
            previous_stop_price=previous_stop,
            active_stop_order_id=trade.stop.broker_order_id,
            status=trade.stop.status,
            reason="trailing_update",
        )
        return {"updated": True, "stop_price": trade.stop.trigger_price, "state": trade.state.value}

    def replace_stop(
        self,
        *,
        trade_id: str,
        requested_by_strategy: str,
        new_stop_price: float,
        risk_authorized_override: bool = False,
        override_reason: str | None = None,
    ) -> dict[str, Any]:
        trade = self._trades.get(str(trade_id))
        if trade is None or trade.stop is None:
            return {"allowed": False, "reason_code": "TRADE_MISSING_OR_UNPROTECTED"}
        previous_stop = float(trade.stop.trigger_price)
        try:
            decision = validate_stop_update(
                authority=self._authority_for_trade(trade),
                requested_by_strategy=requested_by_strategy,
                side=trade.side,
                current_stop_price=previous_stop,
                candidate_stop_price=float(new_stop_price),
                entry_price=trade.avg_fill_price,
                risk_authorized_override=risk_authorized_override,
                override_reason=override_reason,
            )
        except StopAuthorityError as exc:
            return {"allowed": False, "reason_code": exc.reason_code, "reason": str(exc)}

        trade.stop.trigger_price = float(new_stop_price)
        trade.stop.status = "REPLACED"
        trade.last_update_ts = self._ts()
        if (
            self.execution_provider is not None
            and self.run_mode in {"PAPER", "LIVE"}
            and trade.stop.broker_order_id
        ):
            self.execution_provider.modify_stop_order(
                broker_order_id=trade.stop.broker_order_id,
                symbol=trade.symbol,
                side=trade.stop.side,
                quantity=trade.filled_qty,
                new_stop_price=trade.stop.trigger_price,
                trade_id=trade.trade_id,
            )
        event_type = (
            StopAuditEventType.STOP_TIGHTENED
            if decision["tightening"]
            else StopAuditEventType.STOP_REPLACED
        )
        self._record_stop_event(
            trade,
            event_type,
            stop_price=trade.stop.trigger_price,
            previous_stop_price=previous_stop,
            active_stop_order_id=trade.stop.broker_order_id,
            status=trade.stop.status,
            reason=decision["reason_code"],
            payload={"risk_authorized_override": bool(risk_authorized_override), "override_reason": override_reason},
        )
        return {"allowed": True, **decision, "stop_price": trade.stop.trigger_price}

    def cancel_stop(
        self,
        *,
        trade_id: str,
        requested_by_strategy: str,
        risk_authorized_override: bool = False,
        reason: str | None = None,
    ) -> dict[str, Any]:
        trade = self._trades.get(str(trade_id))
        if trade is None or trade.stop is None:
            return {"allowed": False, "reason_code": "TRADE_MISSING_OR_UNPROTECTED"}
        if str(requested_by_strategy or "") != trade.strategy_id:
            return {
                "allowed": False,
                "reason_code": "STOP_OWNERSHIP_CONFLICT",
                "owner_strategy": trade.strategy_id,
            }
        if not risk_authorized_override:
            return {"allowed": False, "reason_code": "STOP_CANCEL_REQUIRES_RISK_AUTHORITY"}
        if not str(reason or "").strip():
            return {"allowed": False, "reason_code": "RISK_OVERRIDE_REASON_REQUIRED"}
        broker_order_id = trade.stop.broker_order_id
        if self.execution_provider is not None and broker_order_id and self.run_mode in {"PAPER", "LIVE"}:
            self.execution_provider.cancel_order(broker_order_id=str(broker_order_id))
        trade.stop.status = "CANCELLED"
        trade.stop.broker_order_id = None
        trade.stop.pending_intent_id = None
        trade.stop.emergency_stop_exception = str(reason or "").strip()
        self._record_stop_event(
            trade,
            StopAuditEventType.STOP_CANCELLED,
            stop_price=trade.stop.trigger_price,
            active_stop_order_id=broker_order_id,
            status=trade.stop.status,
            reason=reason,
        )
        return {"allowed": True, "reason_code": "RISK_AUTHORIZED_STOP_CANCEL", "broker_order_id": broker_order_id}

    @staticmethod
    def _extract_fill_price(payload: dict[str, Any]) -> float | None:
        for key in ("price", "avg_fill_price", "avgPrice", "fill_price"):
            raw = payload.get(key)
            if raw is None:
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if math.isfinite(value) and value > 0.0:
                return value
        return None

    @staticmethod
    def _extract_fill_time(payload: dict[str, Any]) -> str | None:
        for key in ("fill_time", "time", "timestamp"):
            raw = payload.get(key)
            if raw is None:
                continue
            text = str(raw).strip()
            if text:
                return text
        return None

    def _tighten_stop_after_take_profit(self, trade: ManagedTradeLifecycle, remaining_qty: int) -> None:
        if trade.stop is None:
            return
        side_u = str(trade.side or "").upper()
        previous_stop = float(trade.stop.trigger_price)
        if side_u in {"LONG", "BUY"}:
            trade.stop.trigger_price = max(float(trade.stop.trigger_price), float(trade.avg_fill_price))
        elif side_u == "SHORT":
            trade.stop.trigger_price = min(float(trade.stop.trigger_price), float(trade.avg_fill_price))
        trade.stop.quantity = int(remaining_qty)
        print(
            "[TAKE_PROFIT][PARTIAL] "
            f"trade_id={trade.trade_id} symbol={trade.symbol} stop_qty={remaining_qty} stop={trade.stop.trigger_price:.4f}"
        )
        self._record_stop_event(
            trade,
            StopAuditEventType.STOP_TIGHTENED,
            stop_price=trade.stop.trigger_price,
            previous_stop_price=previous_stop,
            active_stop_order_id=trade.stop.broker_order_id,
            status=trade.stop.status,
            reason="take_profit_partial_break_even",
        )
        if self.execution_provider is None or self.run_mode not in {"PAPER", "LIVE"} or not trade.stop.broker_order_id:
            return
        self.execution_provider.modify_stop_order(
            broker_order_id=trade.stop.broker_order_id,
            symbol=trade.symbol,
            side=trade.stop.side,
            quantity=int(remaining_qty),
            new_stop_price=trade.stop.trigger_price,
            trade_id=trade.trade_id,
        )

    def record_exit_fill(
        self,
        *,
        trade_id: str,
        fill_price: float,
        fill_time: str,
        actual_qty: int,
        exit_order_id: str | None = None,
        reason: str,
    ) -> dict[str, Any]:
        trade = self._trades.get(str(trade_id))
        if trade is None:
            return {"success": False, "error": "trade_not_found"}
        if not math.isfinite(float(fill_price)) or float(fill_price) <= 0.0:
            print(f"[LIFECYCLE][EXIT_FILL_REJECTED] trade_id={trade_id} reason=invalid_fill_price value={fill_price}")
            return {"success": False, "error": "invalid_fill_price"}
        fill_time_text = str(fill_time or "").strip()
        if not fill_time_text:
            print(f"[LIFECYCLE][EXIT_FILL_REJECTED] trade_id={trade_id} reason=missing_fill_time")
            return {"success": False, "error": "missing_fill_time"}
        qty = int(actual_qty or 0)
        if qty <= 0:
            return {"success": False, "error": "invalid_qty"}
        if qty > int(trade.filled_qty):
            print(
                "[LIFECYCLE][EXIT_FILL_REJECTED] "
                f"trade_id={trade_id} reason=qty_exceeds_open requested={qty} open={trade.filled_qty}"
            )
            return {"success": False, "error": "qty_exceeds_open"}

        side_u = str(trade.side or "").upper()
        if side_u in {"LONG", "BUY"}:
            realized_increment = (float(fill_price) - float(trade.avg_fill_price)) * float(qty)
        else:
            realized_increment = (float(trade.avg_fill_price) - float(fill_price)) * float(qty)

        attribution = self._exit_attribution(reason)
        target_fill_result = None
        if attribution == "TAKE_PROFIT" and trade.target is not None and trade.target.target_id:
            target_fill_result = self.take_profit_authority.record_fill(
                target_id=trade.target.target_id,
                fill_quantity=qty,
                live_position_quantity_before=int(trade.filled_qty),
                broker_order_id=str(exit_order_id) if exit_order_id is not None else trade.target.broker_order_id,
                realized_pnl=float(realized_increment),
            )
            if not target_fill_result.accepted:
                self._record_take_profit_event(
                    trade,
                    target_fill_result.lifecycle_event,
                    target_fill_result.to_audit_payload(),
                )
                return {"success": False, "error": target_fill_result.reason_code}

        remaining_qty = int(trade.filled_qty) - qty
        trade.filled_qty = remaining_qty
        trade.exited_qty += qty
        trade.exit_fill_price = float(fill_price)
        trade.exit_fill_time = fill_time_text
        trade.exit_order_id = str(exit_order_id) if exit_order_id is not None else trade.exit_order_id
        trade.realized_pnl += float(realized_increment)
        trade.realized_pnl_by_exit_reason[attribution] = (
            float(trade.realized_pnl_by_exit_reason.get(attribution, 0.0)) + float(realized_increment)
        )
        trade.last_update_ts = self._ts()
        self._pending_exit_requests.pop(trade.trade_id, None)
        print(
            "[TRADE][EXIT_FILLED] "
            f"trade_id={trade.trade_id} qty={qty} pnl={float(trade.realized_pnl):.4f}"
        )

        if remaining_qty > 0:
            trade.partial_exit_count += 1
            if target_fill_result is not None:
                trade.target.status = target_fill_result.status
                self._record_take_profit_event(
                    trade,
                    target_fill_result.lifecycle_event,
                    target_fill_result.to_audit_payload(),
                )
            if attribution == "TAKE_PROFIT":
                self._tighten_stop_after_take_profit(trade, remaining_qty)
            self._update_in_memory_state()
            print(
                "[LIFECYCLE][EXIT_PARTIAL] "
                f"symbol={trade.symbol} trade_id={trade.trade_id} partial_qty={qty} remaining_qty={remaining_qty} "
                f"partial_exit_count={trade.partial_exit_count} "
                f"fill_price={float(fill_price):.4f} realized_increment={float(realized_increment):.4f}"
            )
            return {
                "success": True,
                "trade_id": trade.trade_id,
                "partial": True,
                "remaining_qty": remaining_qty,
                "realized_increment": float(realized_increment),
                "realized_pnl": float(trade.realized_pnl),
                "state": trade.state.value,
            }

        if target_fill_result is not None:
            trade.target.status = target_fill_result.status
            self._record_take_profit_event(
                trade,
                target_fill_result.lifecycle_event,
                target_fill_result.to_audit_payload(),
            )
        self.mark_exit_pending(trade.trade_id, reason)
        self.mark_exited(trade.trade_id, reason)
        assert remaining_qty == 0, "EXITED invariant violation: remaining_qty must be zero"
        self._update_in_memory_state()
        return {
            "success": True,
            "trade_id": trade.trade_id,
            "partial": False,
            "remaining_qty": 0,
            "realized_increment": float(realized_increment),
            "realized_pnl": float(trade.realized_pnl),
            "state": trade.state.value,
        }

    def evaluate_trade_management(self, *, trade_id: str, current_price: float) -> list[dict[str, Any]]:
        trade = self._trades.get(str(trade_id))
        if trade is None or int(trade.filled_qty or 0) <= 0:
            return []
        if trade.state in {PositionLifecycleState.EXIT_PENDING, PositionLifecycleState.EXITED, PositionLifecycleState.LIFECYCLE_FAILURE}:
            return []
        if trade.trade_id in self._pending_exit_requests:
            return []

        price = float(current_price)
        intents: list[dict[str, Any]] = []
        expected_partial_exits = 1
        if trade.target is not None and TakeProfitAuthority._hits_target(trade.side, price, float(trade.target.trigger_price)):
            if trade.partial_exit_count >= expected_partial_exits:
                return []
            partial_qty = int(trade.target.quantity or 0)
            if partial_qty <= 0:
                partial_qty = TakeProfitAuthority.scale_out_quantity(
                    live_position_quantity=int(trade.filled_qty),
                    fraction=0.5,
                )
            partial_qty = min(partial_qty, int(trade.filled_qty))
            intents.extend(self._create_exit_request(trade=trade, qty=partial_qty, reason="TARGET1_PARTIAL"))
            return intents

        if trade.stop is not None and price <= float(trade.stop.trigger_price):
            intents.extend(self._create_exit_request(trade=trade, qty=int(trade.filled_qty), reason="STOP_EXIT"))
        return intents

    def _create_exit_request(self, *, trade: ManagedTradeLifecycle, qty: int, reason: str) -> list[dict[str, Any]]:
        if trade.trade_id in self._pending_exit_requests:
            return []
        requested_qty = int(qty or 0)
        if requested_qty <= 0:
            return []
        intent_id = f"{trade.trade_id}-EXIT-{len(self._pending_exit_requests) + 1}"
        self._pending_exit_requests[trade.trade_id] = {
            "intent_id": intent_id,
            "requested_qty": requested_qty,
            "reason": str(reason),
            "created_at": self._ts(),
        }
        self.mark_exit_pending(trade.trade_id, f"exit_request:{reason}")
        print(
            "[TRADE][EXIT_REQUEST] "
            f"trade_id={trade.trade_id} qty={requested_qty} reason={reason}"
        )
        return [
            {
                "trade_id": trade.trade_id,
                "symbol": trade.symbol,
                "side": "SELL",
                "action": "EXIT",
                "qty": requested_qty,
                "reason": str(reason),
                "intent_id": intent_id,
            }
        ]

    def execute_exit_intents(self, *, intents: list[Any], execute_intents_fn: Any) -> list[Any]:
        if not intents:
            return []
        for intent in intents:
            print(
                "[EXECUTION][EXIT_SUBMIT] "
                f"trade_id={intent.get('trade_id', 'UNKNOWN')} intent_id={intent.get('intent_id', 'UNKNOWN')}"
            )
        return list(execute_intents_fn(intents=intents))

    def handle_broker_callback(self, payload: dict[str, Any]) -> dict[str, Any]:
        event_type = str(payload.get("event_type", "") or "").lower()
        if event_type not in {"execdetails", "orderstatus"}:
            return {"handled": False, "reason": "unsupported_event"}
        order_id = str(payload.get("order_id") or payload.get("orderId") or "").strip()
        status = str(payload.get("status", "") or "").upper()
        if not order_id:
            return {"handled": False, "reason": "missing_order_id"}

        for trade in self._trades.values():
            stop = trade.stop
            target = trade.target
            if stop and str(stop.broker_order_id or "") == order_id:
                if event_type == "orderstatus" and status:
                    stop.status = status
                if event_type == "execdetails":
                    print(f"[IBKR][EXEC_DETAILS] trade_id={trade.trade_id} symbol={trade.symbol} exit_leg=STOP")
                    fill_price = self._extract_fill_price(payload)
                    fill_time = self._extract_fill_time(payload)
                    if fill_price is None or fill_time is None:
                        return {"handled": False, "trade_id": trade.trade_id, "error": "missing_fill_truth"}
                    self._record_stop_event(
                        trade,
                        StopAuditEventType.STOP_TRIGGERED,
                        stop_price=stop.trigger_price,
                        active_stop_order_id=stop.broker_order_id,
                        status="FILLED",
                        reason="stop_fill_broker",
                        payload={"fill_price": fill_price, "fill_time": fill_time},
                    )
                    exit_result = self.record_exit_fill(
                        trade_id=trade.trade_id,
                        fill_price=fill_price,
                        fill_time=fill_time,
                        actual_qty=int(payload.get("shares") or payload.get("filled") or payload.get("qty") or 0),
                        exit_order_id=order_id,
                        reason="stop_fill_broker",
                    )
                    if not exit_result.get("success"):
                        return {"handled": False, "trade_id": trade.trade_id, **exit_result}
                    if target:
                        if trade.state == PositionLifecycleState.EXITED:
                            target.status = "CANCEL_PENDING"
                            if self.execution_provider is not None and target.broker_order_id:
                                try:
                                    self.execution_provider.cancel_order(broker_order_id=str(target.broker_order_id))
                                    target.status = "CANCELLED"
                                    if target.target_id:
                                        cancelled = self.take_profit_authority.mark_cancelled(
                                            target_id=target.target_id,
                                            reason="stop_exit_filled_cancel_remaining_target",
                                        )
                                        self._record_take_profit_event(
                                            trade,
                                            cancelled.lifecycle_event,
                                            cancelled.to_audit_payload(),
                                        )
                                except Exception as exc:
                                    target.status = "CANCEL_FAILED"
                                    print(
                                        "[LIFECYCLE][CANCEL_FAILED] "
                                        f"trade_id={trade.trade_id} symbol={trade.symbol} order_id={target.broker_order_id} reason={exc}"
                                    )
                    return {
                        "handled": True,
                        "trade_id": trade.trade_id,
                        "exit_reason": "STOP_FILLED",
                        "cancel_order_id": target.broker_order_id if target and trade.state == PositionLifecycleState.EXITED else None,
                        "partial": bool(exit_result.get("partial")),
                    }
                return {"handled": True, "trade_id": trade.trade_id, "leg": "STOP", "status": stop.status}

            if target and str(target.broker_order_id or "") == order_id:
                if event_type == "orderstatus" and status:
                    target.status = status
                    if status in {"CANCELLED", "CANCELED"} and target.target_id:
                        cancelled = self.take_profit_authority.mark_cancelled(
                            target_id=target.target_id,
                            reason="broker_cancel_status",
                        )
                        self._record_take_profit_event(
                            trade,
                            cancelled.lifecycle_event,
                            cancelled.to_audit_payload(),
                        )
                    elif status in {"REJECTED", "INACTIVE"} and target.target_id:
                        rejected = self.take_profit_authority.mark_rejected(
                            target_id=target.target_id,
                            reason=f"broker_status:{status}",
                        )
                        self._record_take_profit_event(
                            trade,
                            rejected.lifecycle_event,
                            rejected.to_audit_payload(),
                        )
                if event_type == "execdetails":
                    print(f"[IBKR][EXEC_DETAILS] trade_id={trade.trade_id} symbol={trade.symbol} exit_leg=TARGET")
                    fill_price = self._extract_fill_price(payload)
                    fill_time = self._extract_fill_time(payload)
                    if fill_price is None or fill_time is None:
                        return {"handled": False, "trade_id": trade.trade_id, "error": "missing_fill_truth"}
                    exit_result = self.record_exit_fill(
                        trade_id=trade.trade_id,
                        fill_price=fill_price,
                        fill_time=fill_time,
                        actual_qty=int(payload.get("shares") or payload.get("filled") or payload.get("qty") or 0),
                        exit_order_id=order_id,
                        reason="target_fill_broker",
                    )
                    if not exit_result.get("success"):
                        return {"handled": False, "trade_id": trade.trade_id, **exit_result}
                    if stop:
                        if trade.state == PositionLifecycleState.EXITED:
                            stop.status = "CANCEL_PENDING"
                            if self.execution_provider is not None and stop.broker_order_id:
                                try:
                                    self.execution_provider.cancel_order(broker_order_id=str(stop.broker_order_id))
                                    stop.status = "CANCELLED"
                                except Exception as exc:
                                    stop.status = "CANCEL_FAILED"
                                    print(
                                        "[LIFECYCLE][CANCEL_FAILED] "
                                        f"trade_id={trade.trade_id} symbol={trade.symbol} order_id={stop.broker_order_id} reason={exc}"
                                    )
                    return {
                        "handled": True,
                        "trade_id": trade.trade_id,
                        "exit_reason": "TARGET_FILLED",
                        "cancel_order_id": stop.broker_order_id if stop and trade.state == PositionLifecycleState.EXITED else None,
                        "partial": bool(exit_result.get("partial")),
                    }
                return {"handled": True, "trade_id": trade.trade_id, "leg": "TARGET", "status": target.status}
        return {"handled": False, "reason": "order_not_mapped"}

    def _repair_missing_stop(self, trade: ManagedTradeLifecycle, reason: str) -> bool:
        if self.execution_provider is None or self.run_mode not in {"PAPER", "LIVE"}:
            return False
        if trade.stop is None:
            return False
        try:
            result = self.execution_provider.place_stop_order(
                symbol=trade.symbol,
                side=trade.stop.side,
                quantity=trade.filled_qty,
                stop_price=trade.stop.trigger_price,
                trade_id=trade.trade_id,
                parent_order_id=trade.trade_id,
            )
            trade.stop.broker_order_id = str(result.get("broker_order_id"))
            trade.stop.status = str(result.get("status") or "Submitted")
            self._record_stop_event(
                trade,
                StopAuditEventType.STOP_RECOVERY_RESULT,
                stop_price=trade.stop.trigger_price,
                active_stop_order_id=trade.stop.broker_order_id,
                pending_stop_order_intent=trade.stop.pending_intent_id,
                status=trade.stop.status,
                reason=reason,
                recovery_classification=StopRecoveryClassification.STOP_RECOVERED,
            )
            print(
                "[LIFECYCLE][CRITICAL][PROTECTION_REPAIRED] "
                f"trade_id={trade.trade_id} symbol={trade.symbol} reason={reason} stop_order_id={trade.stop.broker_order_id}"
            )
            return True
        except Exception as exc:
            self._record_stop_event(
                trade,
                StopAuditEventType.STOP_RECOVERY_RESULT,
                stop_price=trade.stop.trigger_price,
                active_stop_order_id=trade.stop.broker_order_id,
                pending_stop_order_intent=trade.stop.pending_intent_id,
                status="REPAIR_FAILED",
                reason=f"{reason}:{exc}",
                recovery_classification=StopRecoveryClassification.STOP_UNSAFE,
            )
            print(
                "[LIFECYCLE][CRITICAL][PROTECTION_REPAIR_FAILED] "
                f"trade_id={trade.trade_id} symbol={trade.symbol} reason={reason} error={exc}"
            )
            return False

    def _repair_missing_target(self, trade: ManagedTradeLifecycle, reason: str) -> bool:
        if self.execution_provider is None or self.run_mode not in {"PAPER", "LIVE"}:
            return False
        if trade.target is None:
            return False
        try:
            if trade.target.target_id:
                superseded = self.take_profit_authority.supersede_target(
                    target_id=trade.target.target_id,
                    reason=reason,
                )
                self._record_take_profit_event(
                    trade,
                    superseded.lifecycle_event,
                    superseded.to_audit_payload(),
                )
                replacement = self.take_profit_authority.create_fixed_price_target(
                    trade_id=trade.trade_id,
                    symbol=trade.symbol,
                    side=trade.side,
                    target_price=trade.target.trigger_price,
                    live_position_quantity=trade.filled_qty,
                    source_strategy=trade.strategy_id,
                    target_stage=trade.target.target_stage or "PARTIAL_1",
                    quantity=min(int(trade.target.quantity or trade.filled_qty), int(trade.filled_qty)),
                    rationale=f"replacement target after missing broker order: {reason}",
                )
                if not replacement.accepted:
                    self._record_take_profit_event(
                        trade,
                        replacement.lifecycle_event,
                        replacement.to_audit_payload(),
                    )
                    return False
                trade.target.target_id = replacement.target_id
                trade.target.quantity = replacement.target_quantity
                trade.target.target_type = replacement.target_type
                trade.target.target_stage = replacement.target_stage
                trade.target.rationale = replacement.rationale
                self._record_take_profit_event(
                    trade,
                    replacement.lifecycle_event,
                    replacement.to_audit_payload(),
                )
            result = self.execution_provider.place_target_order(
                symbol=trade.symbol,
                side=trade.target.side,
                quantity=trade.target.quantity or trade.filled_qty,
                limit_price=trade.target.trigger_price,
                trade_id=trade.trade_id,
                parent_order_id=trade.trade_id,
            )
            trade.target.broker_order_id = str(result.get("broker_order_id"))
            trade.target.status = str(result.get("status") or "Submitted")
            if trade.target.target_id:
                submitted = self.take_profit_authority.mark_submitted(
                    target_id=trade.target.target_id,
                    broker_order_id=trade.target.broker_order_id,
                )
                self._record_take_profit_event(
                    trade,
                    submitted.lifecycle_event,
                    submitted.to_audit_payload(),
                )
            print(
                "[LIFECYCLE][DEGRADED][TARGET_REPAIRED] "
                f"trade_id={trade.trade_id} symbol={trade.symbol} reason={reason} target_order_id={trade.target.broker_order_id}"
            )
            return True
        except Exception as exc:
            print(
                "[LIFECYCLE][DEGRADED][TARGET_REPAIR_FAILED] "
                f"trade_id={trade.trade_id} symbol={trade.symbol} reason={reason} error={exc}"
            )
            return False

    def _escalate_failsafe(self, trade: ManagedTradeLifecycle, *, reason: str) -> None:
        self._transition(trade, PositionLifecycleState.FAILSAFE_TRIGGERED, reason)
        self._transition(trade, PositionLifecycleState.LIFECYCLE_FAILURE, f"{reason}_terminal")

    def reconcile_orders(self, broker_orders: list[Any], *, repair: bool = True) -> dict[str, Any]:
        normalized = [self._order_fields(order) for order in broker_orders]
        open_ids = {
            row["order_id"]
            for row in normalized
            if row["order_id"] and not self._is_filled_status(row["status"]) and not self._is_cancelled_status(row["status"])
        }
        findings: list[dict[str, Any]] = []
        stop_recovery: list[dict[str, Any]] = []
        repaired = 0
        block_new_entries = False

        known_ids: set[str] = set()
        for trade in self._trades.values():
            if trade.stop and trade.stop.broker_order_id:
                known_ids.add(str(trade.stop.broker_order_id))
            if trade.target and trade.target.broker_order_id:
                known_ids.add(str(trade.target.broker_order_id))

            if trade.state in {PositionLifecycleState.EXITED, PositionLifecycleState.LIFECYCLE_FAILURE}:
                continue

            stop_missing = trade.stop is not None and (not trade.stop.broker_order_id or str(trade.stop.broker_order_id) not in open_ids)
            target_missing = trade.target is not None and (not trade.target.broker_order_id or str(trade.target.broker_order_id) not in open_ids)

            if stop_missing:
                recovery = classify_stop_recovery(
                    lifecycle_stop_order_id=trade.stop.broker_order_id if trade.stop else None,
                    lifecycle_stop_price=trade.stop.trigger_price if trade.stop else None,
                    broker_stop_orders=normalized,
                    symbol=trade.symbol,
                    broker_position_quantity=int(trade.filled_qty or 0),
                )
                recovery["trade_id"] = trade.trade_id
                stop_recovery.append(recovery)
                self._record_stop_event(
                    trade,
                    StopAuditEventType.STOP_RECOVERY_RESULT,
                    stop_price=trade.stop.trigger_price if trade.stop else None,
                    active_stop_order_id=trade.stop.broker_order_id if trade.stop else None,
                    status=trade.stop.status if trade.stop else None,
                    reason=recovery["reason_code"],
                    recovery_classification=recovery["classification"],
                    payload=recovery,
                )
                findings.append({"trade_id": trade.trade_id, "symbol": trade.symbol, "issue": "MISSING_STOP"})
                print(f"[LIFECYCLE][RECONCILIATION][MISSING_STOP] trade_id={trade.trade_id} symbol={trade.symbol}")
                repaired_stop = repair and self._repair_missing_stop(trade, "reconciliation_missing_stop")
                if repaired_stop:
                    repaired += 1
                    stop_recovery.append(
                        {
                            "trade_id": trade.trade_id,
                            "symbol": trade.symbol,
                            "classification": StopRecoveryClassification.STOP_RECOVERED.value,
                            "reason_code": "missing_stop_repaired",
                            "broker_order_id": trade.stop.broker_order_id if trade.stop else None,
                        }
                    )
                elif repair:
                    stop_recovery.append(
                        {
                            "trade_id": trade.trade_id,
                            "symbol": trade.symbol,
                            "classification": StopRecoveryClassification.STOP_UNSAFE.value,
                            "reason_code": "stop_repair_failed",
                        }
                    )
                    findings.append({"trade_id": trade.trade_id, "symbol": trade.symbol, "issue": "STOP_REPAIR_FAILED"})
                    block_new_entries = True
                    trade.failure_flags.append("STOP_REPAIR_FAILED")
                    print(f"[LIFECYCLE][CRITICAL][STOP_REPAIR_FAILED] trade_id={trade.trade_id} symbol={trade.symbol}")
                    self._escalate_failsafe(trade, reason="stop_repair_failed")
                    action = self.policy.fail_safe_action_live if self.run_mode == "LIVE" else self.policy.fail_safe_action_paper
                    print(f"[LIFECYCLE][FAILSAFE][{action}] trade_id={trade.trade_id} symbol={trade.symbol}")
            elif trade.stop is not None:
                recovery = classify_stop_recovery(
                    lifecycle_stop_order_id=trade.stop.broker_order_id,
                    lifecycle_stop_price=trade.stop.trigger_price,
                    broker_stop_orders=normalized,
                    symbol=trade.symbol,
                    broker_position_quantity=int(trade.filled_qty or 0),
                )
                recovery["trade_id"] = trade.trade_id
                stop_recovery.append(recovery)
                self._record_stop_event(
                    trade,
                    StopAuditEventType.STOP_RECOVERY_RESULT,
                    stop_price=trade.stop.trigger_price,
                    active_stop_order_id=trade.stop.broker_order_id,
                    status=trade.stop.status,
                    reason=recovery["reason_code"],
                    recovery_classification=recovery["classification"],
                    payload=recovery,
                )
                if recovery["classification"] == StopRecoveryClassification.STOP_STALE.value:
                    findings.append({"trade_id": trade.trade_id, "symbol": trade.symbol, "issue": "STALE_STOP"})
                    print(f"[LIFECYCLE][RECONCILIATION][STALE_STOP] trade_id={trade.trade_id} symbol={trade.symbol}")
                    if repair and self.execution_provider is not None and trade.stop.broker_order_id:
                        self.execution_provider.modify_stop_order(
                            broker_order_id=trade.stop.broker_order_id,
                            symbol=trade.symbol,
                            side=trade.stop.side,
                            quantity=trade.filled_qty,
                            new_stop_price=trade.stop.trigger_price,
                            trade_id=trade.trade_id,
                        )
                        repaired += 1
                        stop_recovery.append(
                            {
                                "trade_id": trade.trade_id,
                                "symbol": trade.symbol,
                                "classification": StopRecoveryClassification.STOP_RECOVERED.value,
                                "reason_code": "stale_stop_repaired",
                                "broker_order_id": trade.stop.broker_order_id,
                            }
                        )
            if target_missing:
                findings.append({"trade_id": trade.trade_id, "symbol": trade.symbol, "issue": "MISSING_TARGET"})
                print(f"[LIFECYCLE][DEGRADED][TARGET_MISSING] trade_id={trade.trade_id} symbol={trade.symbol}")
                repaired_target = repair and self._repair_missing_target(trade, "reconciliation_missing_target")
                if repaired_target:
                    repaired += 1
                elif repair:
                    findings.append({"trade_id": trade.trade_id, "symbol": trade.symbol, "issue": "TARGET_REPAIR_FAILED"})
                    block_new_entries = True
                    trade.failure_flags.append("TARGET_REPAIR_FAILED")
                    print(
                        f"[LIFECYCLE][DEGRADED][TARGET_REPAIR_FAILED] trade_id={trade.trade_id} symbol={trade.symbol} "
                        "policy=stop_intact_no_forced_flatten"
                    )
                    self._escalate_failsafe(trade, reason="target_repair_failed")
                    action = self.policy.fail_safe_action_live if self.run_mode == "LIVE" else self.policy.fail_safe_action_paper
                    print(f"[LIFECYCLE][FAILSAFE][{action}] trade_id={trade.trade_id} symbol={trade.symbol}")

        orphan_orders = sorted(open_ids - known_ids)
        for order_id in orphan_orders:
            findings.append({"order_id": order_id, "issue": "ORPHAN_ORDER"})
            orphan = next((row for row in normalized if row["order_id"] == order_id), {})
            stop_recovery.append(
                {
                    "order_id": order_id,
                    "symbol": orphan.get("symbol"),
                    "classification": StopRecoveryClassification.STOP_ORPHAN.value,
                    "reason_code": "open_order_not_owned_by_lifecycle",
                }
            )
            print(f"[LIFECYCLE][RECONCILIATION][ORPHAN_ORDER] order_id={order_id}")
        return {
            "findings": findings,
            "stop_recovery": stop_recovery,
            "repaired": repaired,
            "orphan_orders": orphan_orders,
            "block_new_entries": block_new_entries,
        }

    def mark_exit_pending(self, trade_id: str, reason: str) -> None:
        trade = self._trades.get(str(trade_id))
        if trade is None:
            return
        if self._transition(trade, PositionLifecycleState.EXIT_PENDING, reason):
            print(f"[TRAIL][EXIT_TRIGGERED] trade_id={trade.trade_id} reason={reason}")

    def mark_exited(self, trade_id: str, reason: str = "fill_exit") -> None:
        trade = self._trades.get(str(trade_id))
        if trade is None:
            return
        if self._transition(trade, PositionLifecycleState.EXITED, reason):
            assert trade.exit_fill_price is not None, "exit_fill_price required before EXITED"
            assert trade.exit_fill_time is not None, "exit_fill_time required before EXITED"
            self._update_in_memory_state()

    def startup_safe_state(self, broker_positions: list[Any], broker_orders: list[Any]) -> dict[str, Any]:
        print("[STARTUP][SAFE_STATE][BEGIN]")
        print(f"[STARTUP][SAFE_STATE][POSITIONS_FOUND] count={len(broker_positions)}")
        print(f"[STARTUP][SAFE_STATE][ORDERS_FOUND] count={len(broker_orders)}")
        print("[RECOVERY][START]")
        print(f"[RECOVERY][BROKER_POSITIONS] count={len(broker_positions)}")
        print(f"[RECOVERY][BROKER_ORDERS] count={len(broker_orders)}")

        recovered = 0
        recovery_pending = 0
        for position in broker_positions:
            symbol = str(getattr(position, "symbol", "") or "").upper()
            qty = int(getattr(position, "quantity", 0) or 0)
            if not symbol or qty <= 0:
                continue
            stop = getattr(position, "stop_loss_price", None)
            trade_id = f"recovery:{symbol}"
            if stop is None:
                print(f"[RECOVERY][ORPHAN_POSITION] symbol={symbol} qty={qty}")
                recovery_pending += 1
                continue
            validate_stop_price(
                side=str(getattr(position, "direction", "LONG") or "LONG").upper(),
                stop_price=float(stop),
                entry_price=float(getattr(position, "entry_price", 0.0) or 0.0) or None,
            )
            trade = ManagedTradeLifecycle(
                trade_id=trade_id,
                symbol=symbol,
                strategy_id=str(getattr(position, "strategy_name", "RECOVERY") or "RECOVERY"),
                side=str(getattr(position, "direction", "LONG") or "LONG").upper(),
                run_mode=self.run_mode,
                session_label="startup_recovery",
                intended_qty=qty,
                filled_qty=qty,
                avg_fill_price=float(getattr(position, "entry_price", 0.0) or 0.0),
                stop=ProtectionOrderMeta(
                    order_type="STOP",
                    side="SELL",
                    trigger_price=float(stop),
                    lifecycle_trade_id=trade_id,
                    strategy_owner=str(getattr(position, "strategy_name", "RECOVERY") or "RECOVERY"),
                    entry_order_id=trade_id,
                    entry_intent_id=trade_id,
                    pending_intent_id=f"startup-stop:{trade_id}",
                ),
                target=(
                    ProtectionOrderMeta(order_type="LIMIT", side="SELL", trigger_price=float(getattr(position, "take_profit_price")))
                    if getattr(position, "take_profit_price", None) is not None
                    else None
                ),
                state=PositionLifecycleState.RECOVERED,
                last_recovery_status=StopRecoveryClassification.STOP_RECOVERED.value,
                high_water_mark=float(getattr(position, "entry_price", 0.0) or 0.0),
            )
            self._trades[trade_id] = trade
            self._record_stop_event(
                trade,
                StopAuditEventType.STOP_RECOVERY_RESULT,
                stop_price=trade.stop.trigger_price if trade.stop else None,
                pending_stop_order_intent=trade.stop.pending_intent_id if trade.stop else None,
                status=trade.stop.status if trade.stop else None,
                reason="startup_recovery_position_with_stop",
                recovery_classification=StopRecoveryClassification.STOP_RECOVERED,
            )
            self._update_in_memory_state()
            recovered += 1
            print(f"[RECOVERY][MATCH] symbol={symbol} trade_id={trade_id}")

        if broker_orders:
            self.reconcile_orders(list(broker_orders), repair=False)

        startup_repaired = 0
        for trade in self._trades.values():
            if trade.stop is None:
                continue
            if not trade.stop.broker_order_id:
                if self._repair_missing_stop(trade, "startup_missing_stop"):
                    startup_repaired += 1

        print(f"[RECOVERY][SUMMARY] recovered={recovered} pending={recovery_pending}")
        decision = "READY" if self.run_mode in {"SIM", "READ_ONLY"} or recovery_pending == 0 else "QUARANTINE"
        print(f"[STARTUP][SAFE_STATE][DECISION] action={decision}")
        print("[STARTUP][SAFE_STATE][READY]")
        return {
            "recovered": recovered,
            "recovery_pending": recovery_pending,
            "decision": decision,
            "startup_repaired": startup_repaired,
        }

    def get_trade(self, trade_id: str) -> ManagedTradeLifecycle | None:
        return self._trades.get(str(trade_id))

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {trade_id: trade.to_dict() for trade_id, trade in self._trades.items()}
