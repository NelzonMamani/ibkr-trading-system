from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


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
    state: PositionLifecycleState = PositionLifecycleState.ENTRY_SUBMITTED
    stop: ProtectionOrderMeta | None = None
    target: ProtectionOrderMeta | None = None
    trailing_active: bool = False
    trailing_mode: str = "break_even_then_offset"
    break_even_activation: float = 0.0
    trailing_activation: float = 0.0
    high_water_mark: float | None = None
    last_update_ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_recovery_status: str | None = None
    failure_flags: list[str] = field(default_factory=list)
    exit_reason: str | None = None
    exit_order_id: str | None = None
    exit_fill_price: float | None = None
    exit_fill_time: str | None = None
    realized_pnl: float | None = None
    exited_qty: int = 0

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
    def __init__(self, run_mode: str, policy: LifecyclePolicy | None = None, execution_provider: Any | None = None) -> None:
        self.run_mode = str(run_mode or "SIM").upper()
        self.policy = policy or LifecyclePolicy()
        self.execution_provider = execution_provider
        self._trades: dict[str, ManagedTradeLifecycle] = {}

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
        return {
            "order_id": order_id,
            "symbol": symbol,
            "order_type": order_type,
            "status": status,
            "order_ref": order_ref,
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

    def _compute_stop_target(self, avg_fill_price: float, side: str) -> tuple[float, float]:
        side_u = str(side).upper()
        if side_u not in {"LONG", "BUY"}:
            raise ValueError("post-fill v1 supports long-side lifecycle hardening")
        stop = avg_fill_price * (1.0 - self.policy.default_stop_pct)
        target = avg_fill_price * (1.0 + self.policy.default_target_pct)
        if stop >= avg_fill_price:
            raise ValueError("invalid stop geometry: protective stop must be below long fill")
        if target <= avg_fill_price:
            raise ValueError("invalid target geometry: target must be above long fill")
        print(
            "[LIFECYCLE][PROTECTION_POLICY] "
            f"side={side_u} fill={avg_fill_price:.4f} stop_pct={self.policy.default_stop_pct:.4f} target_pct={self.policy.default_target_pct:.4f}"
        )
        print(f"[LIFECYCLE][STOP_COMPUTED] stop={stop:.4f}")
        print(f"[LIFECYCLE][TARGET_COMPUTED] target={target:.4f}")
        return stop, target

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
        print(f"[LIFECYCLE][STATE] trade_id={trade.trade_id} state={trade.state.value}")

        if self.run_mode == "READ_ONLY":
            trade.failure_flags.append("READ_ONLY_NO_MUTATION")
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
            try:
                stop, target = self._compute_stop_target(avg_fill_price=float(avg_fill_price), side=side)
                trade.stop = ProtectionOrderMeta(order_type="STOP", side="SELL", trigger_price=stop, status="PENDING_SUBMIT")
                trade.target = ProtectionOrderMeta(order_type="LIMIT", side="SELL", trigger_price=target, status="PENDING_SUBMIT")
                print(
                    "[LIFECYCLE][ORDER_INSTALL][STOP] "
                    f"trade_id={trade.trade_id} symbol={trade.symbol} stop={stop:.4f}"
                )
                print(
                    "[LIFECYCLE][ORDER_INSTALL][TARGET] "
                    f"trade_id={trade.trade_id} symbol={trade.symbol} target={target:.4f}"
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
                        quantity=trade.filled_qty,
                        limit_price=trade.target.trigger_price,
                        trade_id=trade.trade_id,
                        parent_order_id=trade.trade_id,
                    )
                    trade.stop.broker_order_id = str(stop_result.get("broker_order_id"))
                    trade.target.broker_order_id = str(target_result.get("broker_order_id"))
                    trade.stop.status = str(stop_result.get("status") or "Submitted")
                    trade.target.status = str(target_result.get("status") or "Submitted")
                else:
                    trade.stop.status = "REGISTERED"
                    trade.target.status = "REGISTERED"
                self._transition(trade, PositionLifecycleState.PROTECTED, "stop_installed")
                self._transition(trade, PositionLifecycleState.TARGET_ACTIVE, "target_registered")
                self._transition(trade, PositionLifecycleState.TRAILING_ELIGIBLE, "baseline_trailing_ready")
                installed = True
                break
            except Exception as exc:  # defensive lifecycle boundary
                failure_reason = str(exc)
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
        return {"updated": True, "stop_price": trade.stop.trigger_price, "state": trade.state.value}

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
                if event_type == "execdetails" or status == "FILLED":
                    print(f"[IBKR][EXEC_DETAILS] trade_id={trade.trade_id} symbol={trade.symbol} exit_leg=STOP")
                    fill_price = float(payload.get("price") or payload.get("avg_fill_price") or trade.avg_fill_price)
                    fill_qty = int(payload.get("shares") or payload.get("filled") or trade.filled_qty)
                    fill_time = str(payload.get("fill_time") or payload.get("time") or self._ts())
                    self.mark_exit_pending_with_order(trade_id=trade.trade_id, reason="stop_fill_broker", exit_order_id=order_id)
                    self.record_exit_fill(
                        trade_id=trade.trade_id,
                        fill_price=fill_price,
                        fill_qty=fill_qty,
                        fill_time=fill_time,
                        exit_order_id=order_id,
                        reason="stop_fill_broker",
                    )
                    if target:
                        target.status = "CANCEL_PENDING"
                        if self.execution_provider is not None and target.broker_order_id:
                            try:
                                self.execution_provider.cancel_order(broker_order_id=str(target.broker_order_id))
                                target.status = "CANCELLED"
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
                        "cancel_order_id": target.broker_order_id if target else None,
                    }
                return {"handled": True, "trade_id": trade.trade_id, "leg": "STOP", "status": stop.status}

            if target and str(target.broker_order_id or "") == order_id:
                if event_type == "orderstatus" and status:
                    target.status = status
                if event_type == "execdetails" or status == "FILLED":
                    print(f"[IBKR][EXEC_DETAILS] trade_id={trade.trade_id} symbol={trade.symbol} exit_leg=TARGET")
                    fill_price = float(payload.get("price") or payload.get("avg_fill_price") or trade.avg_fill_price)
                    fill_qty = int(payload.get("shares") or payload.get("filled") or trade.filled_qty)
                    fill_time = str(payload.get("fill_time") or payload.get("time") or self._ts())
                    self.mark_exit_pending_with_order(trade_id=trade.trade_id, reason="target_fill_broker", exit_order_id=order_id)
                    self.record_exit_fill(
                        trade_id=trade.trade_id,
                        fill_price=fill_price,
                        fill_qty=fill_qty,
                        fill_time=fill_time,
                        exit_order_id=order_id,
                        reason="target_fill_broker",
                    )
                    if stop:
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
                        "cancel_order_id": stop.broker_order_id if stop else None,
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
            print(
                "[LIFECYCLE][CRITICAL][PROTECTION_REPAIRED] "
                f"trade_id={trade.trade_id} symbol={trade.symbol} reason={reason} stop_order_id={trade.stop.broker_order_id}"
            )
            return True
        except Exception as exc:
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
            result = self.execution_provider.place_target_order(
                symbol=trade.symbol,
                side=trade.target.side,
                quantity=trade.filled_qty,
                limit_price=trade.target.trigger_price,
                trade_id=trade.trade_id,
                parent_order_id=trade.trade_id,
            )
            trade.target.broker_order_id = str(result.get("broker_order_id"))
            trade.target.status = str(result.get("status") or "Submitted")
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
                findings.append({"trade_id": trade.trade_id, "symbol": trade.symbol, "issue": "MISSING_STOP"})
                print(f"[LIFECYCLE][RECONCILIATION][MISSING_STOP] trade_id={trade.trade_id} symbol={trade.symbol}")
                repaired_stop = repair and self._repair_missing_stop(trade, "reconciliation_missing_stop")
                if repaired_stop:
                    repaired += 1
                elif repair:
                    findings.append({"trade_id": trade.trade_id, "symbol": trade.symbol, "issue": "STOP_REPAIR_FAILED"})
                    block_new_entries = True
                    trade.failure_flags.append("STOP_REPAIR_FAILED")
                    print(f"[LIFECYCLE][CRITICAL][STOP_REPAIR_FAILED] trade_id={trade.trade_id} symbol={trade.symbol}")
                    self._escalate_failsafe(trade, reason="stop_repair_failed")
                    action = self.policy.fail_safe_action_live if self.run_mode == "LIVE" else self.policy.fail_safe_action_paper
                    print(f"[LIFECYCLE][FAILSAFE][{action}] trade_id={trade.trade_id} symbol={trade.symbol}")
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
            print(f"[LIFECYCLE][RECONCILIATION][ORPHAN_ORDER] order_id={order_id}")
        return {
            "findings": findings,
            "repaired": repaired,
            "orphan_orders": orphan_orders,
            "block_new_entries": block_new_entries,
        }

    def mark_exit_pending(self, trade_id: str, reason: str) -> None:
        self.mark_exit_pending_with_order(trade_id=trade_id, reason=reason, exit_order_id=None)

    def mark_exit_pending_with_order(self, trade_id: str, reason: str, exit_order_id: str | None = None) -> None:
        trade = self._trades.get(str(trade_id))
        if trade is None:
            return
        if trade.state == PositionLifecycleState.EXIT_PENDING:
            print(
                "[TRADE][UPDATE] "
                f"trade_id={trade.trade_id} symbol={trade.symbol} exit_submitted=true dedupe=true state={trade.state.value}"
            )
            return
        if trade.state == PositionLifecycleState.EXITED:
            print(
                "[TRADE][UPDATE] "
                f"trade_id={trade.trade_id} symbol={trade.symbol} exit_submitted=false reason=already_exited"
            )
            return
        trade.exit_reason = reason
        if exit_order_id is not None:
            trade.exit_order_id = str(exit_order_id)
        trade.last_update_ts = self._ts()
        if self._transition(trade, PositionLifecycleState.EXIT_PENDING, reason):
            print(
                "[TRADE][UPDATE] "
                f"trade_id={trade.trade_id} symbol={trade.symbol} exit_submitted=true exit_reason={reason} "
                f"exit_order_id={trade.exit_order_id or 'NA'}"
            )
            print(f"[TRAIL][EXIT_TRIGGERED] trade_id={trade.trade_id} reason={reason}")

    def mark_exited(self, trade_id: str, reason: str = "fill_exit") -> None:
        trade = self._trades.get(str(trade_id))
        if trade is None:
            return
        self._transition(trade, PositionLifecycleState.EXITED, reason)

    def record_exit_fill(
        self,
        trade_id: str,
        *,
        fill_price: float,
        fill_qty: int,
        fill_time: str,
        exit_order_id: str | None = None,
        reason: str = "fill_exit",
    ) -> dict[str, Any]:
        trade = self._trades.get(str(trade_id))
        if trade is None:
            print(f"[TRADE][UPDATE] trade_id={trade_id} exit_fill_error=trade_not_found")
            return {"ok": False, "reason": "trade_not_found"}
        if trade.state != PositionLifecycleState.EXIT_PENDING:
            print(
                "[TRADE][UPDATE] "
                f"trade_id={trade.trade_id} symbol={trade.symbol} exit_fill_error=invalid_state state={trade.state.value}"
            )
            return {"ok": False, "reason": "invalid_state", "state": trade.state.value}

        actual_qty = max(0, min(int(fill_qty), int(trade.filled_qty)))
        if actual_qty <= 0:
            print(
                "[TRADE][UPDATE] "
                f"trade_id={trade.trade_id} symbol={trade.symbol} exit_fill_error=invalid_qty qty={fill_qty}"
            )
            return {"ok": False, "reason": "invalid_qty"}

        entry_price = float(trade.avg_fill_price)
        resolved_fill_price = float(fill_price)
        side_sign = 1.0 if str(trade.side).upper() in {"LONG", "BUY"} else -1.0
        realized_pnl = (resolved_fill_price - entry_price) * float(actual_qty) * side_sign

        trade.exit_fill_price = resolved_fill_price
        trade.exit_fill_time = str(fill_time)
        trade.exit_order_id = str(exit_order_id) if exit_order_id is not None else trade.exit_order_id
        trade.exit_reason = trade.exit_reason or reason
        trade.realized_pnl = float(realized_pnl)
        trade.exited_qty = actual_qty
        trade.last_update_ts = self._ts()

        self.mark_exited(trade.trade_id, reason=reason)
        print(
            "[TRADE][PNL] "
            f"trade_id={trade.trade_id} symbol={trade.symbol} entry={entry_price:.4f} exit={resolved_fill_price:.4f} "
            f"qty={actual_qty} realized_pnl={trade.realized_pnl:.4f}"
        )
        print(
            "[TRADE][EXIT] "
            f"trade_id={trade.trade_id} symbol={trade.symbol} qty={actual_qty} exit_price={resolved_fill_price:.4f} "
            f"exit_time={trade.exit_fill_time} exit_order_id={trade.exit_order_id or 'NA'}"
        )
        print(f"[POSITION][SYNC] symbol={trade.symbol} action=close trade_id={trade.trade_id}")
        return {
            "ok": True,
            "trade_id": trade.trade_id,
            "state": trade.state.value,
            "realized_pnl": trade.realized_pnl,
            "exit_fill_price": trade.exit_fill_price,
            "exit_fill_time": trade.exit_fill_time,
            "exit_order_id": trade.exit_order_id,
        }

    def submit_exit_order_once(
        self,
        trade_id: str,
        *,
        reason: str,
        submitter: Any,
    ) -> dict[str, Any]:
        trade = self._trades.get(str(trade_id))
        if trade is None:
            return {"submitted": False, "reason": "trade_not_found"}
        if trade.state == PositionLifecycleState.EXIT_PENDING:
            print(
                "[TRADE][UPDATE] "
                f"trade_id={trade.trade_id} symbol={trade.symbol} exit_submitted=false reason=already_exit_pending"
            )
            return {"submitted": False, "reason": "already_exit_pending"}
        if trade.state == PositionLifecycleState.EXITED:
            print(
                "[TRADE][UPDATE] "
                f"trade_id={trade.trade_id} symbol={trade.symbol} exit_submitted=false reason=already_exited"
            )
            return {"submitted": False, "reason": "already_exited"}
        try:
            submit_result = submitter(trade)
            order_id = None
            if isinstance(submit_result, dict):
                order_id = submit_result.get("broker_order_id") or submit_result.get("order_id")
            self.mark_exit_pending_with_order(trade_id=trade.trade_id, reason=reason, exit_order_id=str(order_id) if order_id else None)
            return {"submitted": True, "order_id": order_id}
        except Exception as exc:
            print(
                "[TRADE][UPDATE] "
                f"trade_id={trade.trade_id} symbol={trade.symbol} exit_submit_error={exc}"
            )
            return {"submitted": False, "reason": "submit_failed", "error": str(exc)}

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
                stop=ProtectionOrderMeta(order_type="STOP", side="SELL", trigger_price=float(stop)),
                target=(
                    ProtectionOrderMeta(order_type="LIMIT", side="SELL", trigger_price=float(getattr(position, "take_profit_price")))
                    if getattr(position, "take_profit_price", None) is not None
                    else None
                ),
                state=PositionLifecycleState.RECOVERED,
                last_recovery_status="matched_broker_position",
                high_water_mark=float(getattr(position, "entry_price", 0.0) or 0.0),
            )
            self._trades[trade_id] = trade
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
