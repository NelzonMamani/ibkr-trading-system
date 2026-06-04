from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import math
from typing import Any
from uuid import uuid4

from src.config.config_resolver import get_config
from src.config.runtime_config import (
    get_config_max_position_pct,
    get_default_capital,
    get_risk_account_equity,
)


class CapitalDecisionStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REDUCED = "REDUCED"
    BLOCKED = "BLOCKED"
    READ_ONLY_BLOCKED = "READ_ONLY_BLOCKED"
    INSUFFICIENT_CAPITAL = "INSUFFICIENT_CAPITAL"
    EXPOSURE_LIMIT_EXCEEDED = "EXPOSURE_LIMIT_EXCEEDED"
    MAX_POSITIONS_EXCEEDED = "MAX_POSITIONS_EXCEEDED"
    RECOVERY_NOT_COMPLETE = "RECOVERY_NOT_COMPLETE"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


@dataclass
class CapitalDecision:
    decision_id: str
    timestamp: str
    run_mode: str
    strategy_id: str
    symbol: str
    side: str
    requested_quantity: int
    requested_notional: float
    approved_quantity: int
    approved_notional: float
    account_equity: float
    available_capital: float
    buying_power: float
    current_total_exposure: float
    projected_total_exposure: float
    current_symbol_exposure: float
    projected_symbol_exposure: float
    current_open_positions: int
    max_open_positions: int
    max_position_notional: float
    max_total_exposure: float
    reserved_capital: float
    reason: str
    audit_payload: dict[str, Any] = field(default_factory=dict)
    status: CapitalDecisionStatus = CapitalDecisionStatus.REJECTED

    @property
    def approved(self) -> bool:
        return self.status in {CapitalDecisionStatus.APPROVED, CapitalDecisionStatus.REDUCED}

    @property
    def executable(self) -> bool:
        return self.approved and self.approved_quantity > 0 and self.approved_notional > 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass
class CapitalReservation:
    reservation_id: str
    decision_id: str
    timestamp: str
    run_mode: str
    strategy_id: str
    symbol: str
    side: str
    quantity: int
    notional: float
    remaining_quantity: int
    remaining_notional: float
    status: str = "ACTIVE"
    intent_id: str | None = None
    order_id: str | None = None
    trade_id: str | None = None
    filled_quantity: int = 0
    exposure_notional: float = 0.0
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CapitalManagementAuthority:
    """Canonical capital admission and reservation authority."""

    def __init__(
        self,
        *,
        run_mode: str = "SIM",
        storage_engine: Any | None = None,
        account_equity: float | None = None,
        available_capital: float | None = None,
        buying_power: float | None = None,
        broker_truth_available: bool | None = None,
    ) -> None:
        self.run_mode = str(run_mode or "SIM").upper()
        self.storage_engine = storage_engine
        self.account_equity = account_equity
        self.available_capital = available_capital
        self.buying_power = buying_power
        self.broker_truth_available = broker_truth_available
        self._reservations: dict[str, CapitalReservation] = {}
        self._used_exposure_by_symbol: dict[str, float] = {}
        self._used_exposure_by_strategy: dict[str, float] = {}
        self._recovered_trade_ids: set[str] = set()
        self.recovery_failed: bool = False
        self.recovery_failure_reason: str | None = None

    @property
    def active_reservations(self) -> dict[str, CapitalReservation]:
        return {
            reservation_id: reservation
            for reservation_id, reservation in self._reservations.items()
            if reservation.status == "ACTIVE" and reservation.remaining_notional > 0.0
        }

    @property
    def total_reserved_capital(self) -> float:
        return sum(float(reservation.remaining_notional) for reservation in self.active_reservations.values())

    @property
    def total_used_exposure(self) -> float:
        return sum(float(value) for value in self._used_exposure_by_symbol.values())

    def symbol_exposure(self, symbol: str) -> float:
        return float(self._used_exposure_by_symbol.get(str(symbol or "").upper(), 0.0))

    def evaluate_entry(
        self,
        *,
        run_mode: str | None = None,
        strategy_id: str,
        symbol: str,
        side: str,
        requested_quantity: int,
        reference_price: float,
        account_equity: float | None = None,
        available_capital: float | None = None,
        buying_power: float | None = None,
        current_total_exposure: float | None = None,
        current_symbol_exposure: float | None = None,
        current_open_positions: int | None = None,
        current_symbol_position_exists: bool = False,
        max_open_positions: int | None = None,
        max_position_notional: float | None = None,
        max_total_exposure: float | None = None,
        max_symbol_exposure: float | None = None,
        recovery_complete: bool = True,
        risk_approved: bool = True,
        broker_truth_available: bool | None = None,
        intent_id: str | None = None,
        reserve: bool = True,
        audit_payload: dict[str, Any] | None = None,
    ) -> CapitalDecision:
        effective_mode = str(run_mode or self.run_mode or "SIM").upper()
        normalized_symbol = str(symbol or "").upper()
        normalized_side = str(side or "").upper()
        requested_qty = int(requested_quantity or 0)
        price = float(reference_price or 0.0)
        requested_notional = max(0.0, float(requested_qty) * price)
        limits = self._resolve_limits(
            account_equity=account_equity,
            available_capital=available_capital,
            buying_power=buying_power,
            max_open_positions=max_open_positions,
            max_position_notional=max_position_notional,
            max_total_exposure=max_total_exposure,
        )
        current_total = max(float(current_total_exposure or 0.0), self.total_used_exposure) + self.total_reserved_capital
        current_symbol = (
            max(float(current_symbol_exposure or 0.0), self.symbol_exposure(normalized_symbol))
            + self._reserved_symbol_notional(normalized_symbol)
        )
        open_positions = int(current_open_positions or 0)
        position_slot_increase = 0 if current_symbol_position_exists else 1
        projected_open_positions = open_positions + position_slot_increase
        symbol_limit = float(max_symbol_exposure if max_symbol_exposure is not None else limits["max_position_notional"])
        decision_context = {
            "mode": effective_mode,
            "symbol": normalized_symbol,
            "side": normalized_side,
            "requested_quantity": requested_qty,
            "reference_price": price,
            "recovery_complete": recovery_complete,
            "risk_approved": risk_approved,
            "current_symbol_position_exists": current_symbol_position_exists,
            "projected_open_positions": projected_open_positions,
        }

        if effective_mode == "READ_ONLY":
            decision = self._decision(
                status=CapitalDecisionStatus.READ_ONLY_BLOCKED,
                reason="READ_ONLY_BLOCKED",
                run_mode=effective_mode,
                strategy_id=strategy_id,
                symbol=normalized_symbol,
                side=normalized_side,
                requested_quantity=requested_qty,
                requested_notional=requested_notional,
                approved_quantity=0,
                approved_notional=0.0,
                current_total_exposure=current_total,
                projected_total_exposure=current_total,
                current_symbol_exposure=current_symbol,
                projected_symbol_exposure=current_symbol,
                current_open_positions=open_positions,
                limits=limits,
                audit_payload={**decision_context, **(audit_payload or {})},
            )
            self._emit_decision(decision)
            return decision

        if not recovery_complete:
            decision = self._blocked_decision(
                CapitalDecisionStatus.RECOVERY_NOT_COMPLETE,
                "RECOVERY_NOT_COMPLETE",
                effective_mode,
                strategy_id,
                normalized_symbol,
                normalized_side,
                requested_qty,
                requested_notional,
                current_total,
                current_symbol,
                open_positions,
                limits,
                decision_context,
                audit_payload,
            )
            self._emit_decision(decision)
            return decision

        if not risk_approved:
            decision = self._blocked_decision(
                CapitalDecisionStatus.BLOCKED,
                "RISK_NOT_APPROVED",
                effective_mode,
                strategy_id,
                normalized_symbol,
                normalized_side,
                requested_qty,
                requested_notional,
                current_total,
                current_symbol,
                open_positions,
                limits,
                decision_context,
                audit_payload,
            )
            self._emit_decision(decision)
            return decision

        if broker_truth_available is None and effective_mode == "LIVE":
            broker_truth_available = (
                account_equity is not None
                and available_capital is not None
                and buying_power is not None
            )
        truth_available = self._broker_truth_available(effective_mode, broker_truth_available)
        if effective_mode == "LIVE":
            truth_available = truth_available and self._live_account_values_available(
                account_equity=account_equity,
                available_capital=available_capital,
                buying_power=buying_power,
            )
        if effective_mode == "LIVE" and not truth_available:
            decision = self._blocked_decision(
                CapitalDecisionStatus.DATA_UNAVAILABLE,
                "CAPITAL_TRUTH_UNAVAILABLE",
                effective_mode,
                strategy_id,
                normalized_symbol,
                normalized_side,
                requested_qty,
                requested_notional,
                current_total,
                current_symbol,
                open_positions,
                limits,
                decision_context,
                audit_payload,
            )
            self._emit_decision(decision)
            return decision

        if requested_qty <= 0 or price <= 0.0:
            decision = self._blocked_decision(
                CapitalDecisionStatus.REJECTED,
                "INVALID_CAPITAL_REQUEST",
                effective_mode,
                strategy_id,
                normalized_symbol,
                normalized_side,
                requested_qty,
                requested_notional,
                current_total,
                current_symbol,
                open_positions,
                limits,
                decision_context,
                audit_payload,
            )
            self._emit_decision(decision)
            return decision

        if projected_open_positions > int(limits["max_open_positions"]):
            decision = self._blocked_decision(
                CapitalDecisionStatus.MAX_POSITIONS_EXCEEDED,
                "MAX_POSITIONS_EXCEEDED",
                effective_mode,
                strategy_id,
                normalized_symbol,
                normalized_side,
                requested_qty,
                requested_notional,
                current_total,
                current_symbol,
                open_positions,
                limits,
                decision_context,
                audit_payload,
            )
            self._emit_decision(decision)
            return decision

        if requested_notional > float(limits["max_position_notional"]):
            decision = self._blocked_decision(
                CapitalDecisionStatus.EXPOSURE_LIMIT_EXCEEDED,
                "MAX_POSITION_NOTIONAL_EXCEEDED",
                effective_mode,
                strategy_id,
                normalized_symbol,
                normalized_side,
                requested_qty,
                requested_notional,
                current_total,
                current_symbol,
                open_positions,
                limits,
                decision_context,
                audit_payload,
            )
            self._emit_decision(decision)
            return decision

        if current_symbol + requested_notional > symbol_limit:
            decision = self._blocked_decision(
                CapitalDecisionStatus.EXPOSURE_LIMIT_EXCEEDED,
                "SYMBOL_EXPOSURE_LIMIT_EXCEEDED",
                effective_mode,
                strategy_id,
                normalized_symbol,
                normalized_side,
                requested_qty,
                requested_notional,
                current_total,
                current_symbol,
                open_positions,
                limits,
                decision_context,
                audit_payload,
            )
            self._emit_decision(decision)
            return decision

        if current_total + requested_notional > float(limits["max_total_exposure"]):
            decision = self._blocked_decision(
                CapitalDecisionStatus.EXPOSURE_LIMIT_EXCEEDED,
                "TOTAL_EXPOSURE_LIMIT_EXCEEDED",
                effective_mode,
                strategy_id,
                normalized_symbol,
                normalized_side,
                requested_qty,
                requested_notional,
                current_total,
                current_symbol,
                open_positions,
                limits,
                decision_context,
                audit_payload,
            )
            self._emit_decision(decision)
            return decision

        capital_cap = min(float(limits["available_capital"]), float(limits["buying_power"]))
        approved_qty = requested_qty
        reason = "CAPITAL_APPROVED"
        status = CapitalDecisionStatus.APPROVED
        if requested_notional > capital_cap:
            approved_qty = int(math.floor(capital_cap / price))
            if approved_qty <= 0:
                decision = self._blocked_decision(
                    CapitalDecisionStatus.INSUFFICIENT_CAPITAL,
                    "INSUFFICIENT_CAPITAL",
                    effective_mode,
                    strategy_id,
                    normalized_symbol,
                    normalized_side,
                    requested_qty,
                    requested_notional,
                    current_total,
                    current_symbol,
                    open_positions,
                    limits,
                    decision_context,
                    audit_payload,
                )
                self._emit_decision(decision)
                return decision
            status = CapitalDecisionStatus.REDUCED
            reason = "CAPITAL_REDUCED_TO_AVAILABLE_FUNDS"

        approved_notional = float(approved_qty) * price
        decision = self._decision(
            status=status,
            reason=reason,
            run_mode=effective_mode,
            strategy_id=strategy_id,
            symbol=normalized_symbol,
            side=normalized_side,
            requested_quantity=requested_qty,
            requested_notional=requested_notional,
            approved_quantity=approved_qty,
            approved_notional=approved_notional,
            current_total_exposure=current_total,
            projected_total_exposure=current_total + approved_notional,
            current_symbol_exposure=current_symbol,
            projected_symbol_exposure=current_symbol + approved_notional,
            current_open_positions=open_positions,
            limits=limits,
            audit_payload={**decision_context, **(audit_payload or {})},
        )
        if reserve and decision.executable:
            self.reserve(decision, intent_id=intent_id)
        self._emit_decision(decision)
        return decision

    authorize_entry = evaluate_entry

    def reserve(self, decision: CapitalDecision, *, intent_id: str | None = None, order_id: str | None = None) -> CapitalReservation:
        if not decision.executable:
            raise ValueError("Cannot reserve capital for a non-executable decision.")
        reservation = CapitalReservation(
            reservation_id=f"cap-res-{uuid4().hex}",
            decision_id=decision.decision_id,
            timestamp=self._now(),
            run_mode=decision.run_mode,
            strategy_id=decision.strategy_id,
            symbol=decision.symbol,
            side=decision.side,
            quantity=decision.approved_quantity,
            notional=decision.approved_notional,
            remaining_quantity=decision.approved_quantity,
            remaining_notional=decision.approved_notional,
            intent_id=intent_id,
            order_id=order_id,
        )
        self._reservations[reservation.reservation_id] = reservation
        decision.reserved_capital = reservation.remaining_notional
        print(
            "[CAPITAL][RESERVED] "
            f"decision_id={decision.decision_id} symbol={decision.symbol} "
            f"quantity={reservation.quantity} notional={reservation.notional:.2f}"
        )
        self._audit(
            "RESERVED",
            decision_id=decision.decision_id,
            reservation_id=reservation.reservation_id,
            symbol=decision.symbol,
            strategy_id=decision.strategy_id,
            run_mode=decision.run_mode,
            status=decision.status.value,
            requested_quantity=decision.requested_quantity,
            approved_quantity=decision.approved_quantity,
            requested_notional=decision.requested_notional,
            approved_notional=decision.approved_notional,
            reserved_capital=reservation.remaining_notional,
            exposure_before=decision.current_total_exposure,
            exposure_after=decision.projected_total_exposure,
            reason=decision.reason,
            intent_id=intent_id,
        )
        return reservation

    def attach_order(self, *, decision_id: str, order_id: str) -> None:
        for reservation in self.active_reservations.values():
            if reservation.decision_id == decision_id:
                reservation.order_id = order_id

    def release_reservation(
        self,
        *,
        decision_id: str | None = None,
        order_id: str | None = None,
        reason: str = "RELEASED",
    ) -> float:
        released = 0.0
        for reservation in list(self.active_reservations.values()):
            if decision_id and reservation.decision_id != decision_id:
                continue
            if order_id and reservation.order_id != order_id:
                continue
            reservation.status = "RELEASED"
            reservation.reason = reason
            released += float(reservation.remaining_notional)
            reservation.remaining_quantity = 0
            reservation.remaining_notional = 0.0
            print(
                "[CAPITAL][RELEASED] "
                f"decision_id={reservation.decision_id} symbol={reservation.symbol} "
                f"notional={released:.2f} reason={reason}"
            )
            self._audit(
                "RELEASED",
                decision_id=reservation.decision_id,
                reservation_id=reservation.reservation_id,
                order_id=reservation.order_id,
                symbol=reservation.symbol,
                strategy_id=reservation.strategy_id,
                run_mode=reservation.run_mode,
                status=reservation.status,
                approved_quantity=reservation.quantity,
                approved_notional=reservation.notional,
                reserved_capital=0.0,
                exposure_before=self.total_used_exposure,
                exposure_after=self.total_used_exposure,
                reason=reason,
                intent_id=reservation.intent_id,
            )
        return released

    def convert_reservation_to_exposure(
        self,
        *,
        decision_id: str | None = None,
        order_id: str | None = None,
        symbol: str | None = None,
        strategy_id: str | None = None,
        fill_quantity: int,
        fill_price: float,
        trade_id: str | None = None,
        reason: str = "FILL_RECORDED",
    ) -> float:
        fill_qty = int(fill_quantity or 0)
        fill_notional = max(0.0, float(fill_qty) * float(fill_price or 0.0))
        if fill_qty <= 0 or fill_notional <= 0.0:
            return 0.0
        reservation = self._find_reservation(decision_id=decision_id, order_id=order_id, symbol=symbol)
        normalized_symbol = str(symbol or getattr(reservation, "symbol", "") or "").upper()
        normalized_strategy = str(strategy_id or getattr(reservation, "strategy_id", "") or "UNKNOWN")
        exposure_before = self.total_used_exposure
        self._used_exposure_by_symbol[normalized_symbol] = self.symbol_exposure(normalized_symbol) + fill_notional
        self._used_exposure_by_strategy[normalized_strategy] = (
            self._used_exposure_by_strategy.get(normalized_strategy, 0.0) + fill_notional
        )
        if reservation is not None:
            reservation.filled_quantity += fill_qty
            reservation.exposure_notional += fill_notional
            reservation.trade_id = trade_id or reservation.trade_id
            reservation.remaining_quantity = max(0, reservation.remaining_quantity - fill_qty)
            reservation.remaining_notional = max(0.0, reservation.remaining_notional - fill_notional)
            if reservation.remaining_quantity <= 0 or reservation.remaining_notional <= 0.0:
                reservation.status = "CONVERTED"
                reservation.remaining_quantity = 0
                reservation.remaining_notional = 0.0
        print(
            "[CAPITAL][EXPOSURE] "
            f"symbol={normalized_symbol} fill_qty={fill_qty} fill_notional={fill_notional:.2f} "
            f"total_exposure={self.total_used_exposure:.2f}"
        )
        self._audit(
            "EXPOSURE",
            decision_id=getattr(reservation, "decision_id", decision_id),
            reservation_id=getattr(reservation, "reservation_id", None),
            order_id=order_id,
            trade_id=trade_id,
            symbol=normalized_symbol,
            strategy_id=normalized_strategy,
            run_mode=getattr(reservation, "run_mode", self.run_mode),
            status=getattr(reservation, "status", "EXPOSURE"),
            approved_quantity=getattr(reservation, "quantity", fill_qty),
            approved_notional=getattr(reservation, "notional", fill_notional),
            reserved_capital=getattr(reservation, "remaining_notional", 0.0),
            exposure_before=exposure_before,
            exposure_after=self.total_used_exposure,
            reason=reason,
            intent_id=getattr(reservation, "intent_id", None),
        )
        return fill_notional

    def release_exposure(
        self,
        *,
        symbol: str,
        quantity: int | None = None,
        price: float | None = None,
        notional: float | None = None,
        strategy_id: str | None = None,
        reason: str = "EXIT_RECORDED",
    ) -> float:
        normalized_symbol = str(symbol or "").upper()
        release_notional = float(notional if notional is not None else float(quantity or 0) * float(price or 0.0))
        release_notional = max(0.0, release_notional)
        exposure_before = self.total_used_exposure
        current_symbol = self.symbol_exposure(normalized_symbol)
        released = min(current_symbol, release_notional)
        self._used_exposure_by_symbol[normalized_symbol] = max(0.0, current_symbol - released)
        if strategy_id:
            current_strategy = self._used_exposure_by_strategy.get(strategy_id, 0.0)
            self._used_exposure_by_strategy[strategy_id] = max(0.0, current_strategy - released)
        print(
            "[CAPITAL][EXPOSURE] "
            f"symbol={normalized_symbol} released={released:.2f} total_exposure={self.total_used_exposure:.2f}"
        )
        self._audit(
            "EXPOSURE_RELEASED",
            symbol=normalized_symbol,
            strategy_id=strategy_id,
            run_mode=self.run_mode,
            reserved_capital=self.total_reserved_capital,
            exposure_before=exposure_before,
            exposure_after=self.total_used_exposure,
            reason=reason,
        )
        return released

    def recover_from_lifecycle(self, open_lifecycle_trades: list[Any]) -> int:
        self._used_exposure_by_symbol.clear()
        self._used_exposure_by_strategy.clear()
        self._recovered_trade_ids.clear()
        recovered = 0
        for trade in open_lifecycle_trades or []:
            quantity = int(self._value(trade, "quantity_open", 0) or 0)
            price = float(self._value(trade, "entry_avg_price", 0.0) or 0.0)
            symbol = str(self._value(trade, "symbol", "") or "").upper()
            if not symbol or quantity <= 0 or price <= 0.0:
                continue
            notional = float(quantity) * price
            strategy_id = str(self._value(trade, "strategy_name", "RECOVERY") or "RECOVERY")
            trade_id = str(self._value(trade, "lifecycle_trade_id", "") or "")
            self._used_exposure_by_symbol[symbol] = self.symbol_exposure(symbol) + notional
            self._used_exposure_by_strategy[strategy_id] = (
                self._used_exposure_by_strategy.get(strategy_id, 0.0) + notional
            )
            if trade_id:
                self._recovered_trade_ids.add(trade_id)
            recovered += 1
        print(f"[CAPITAL][RECOVER] lifecycle_exposures={recovered} total_exposure={self.total_used_exposure:.2f}")
        self._audit(
            "RECOVER",
            run_mode=self.run_mode,
            status="RECOVERED",
            exposure_before=0.0,
            exposure_after=self.total_used_exposure,
            reason="LIFECYCLE_EXPOSURE_RECOVERY",
        )
        return recovered

    def recover_from_open_orders(self, open_orders: list[Any]) -> int:
        for reservation in self.active_reservations.values():
            reservation.status = "STALE_DISCARDED"
            reservation.remaining_quantity = 0
            reservation.remaining_notional = 0.0
        recovered = 0
        unresolved = 0
        for order in open_orders or []:
            metadata = dict(self._value(order, "metadata", {}) or {})
            status = str(self._value(order, "status", "") or "").upper()
            order_type = str(self._value(order, "order_type", "") or "").upper()
            side = str(metadata.get("side") or self._value(order, "side", "") or "").upper()
            trade_id = str(metadata.get("trade_id") or metadata.get("lifecycle_trade_id") or "")
            if status in {"CANCELLED", "CANCELED", "REJECTED", "FILLED"}:
                continue
            if trade_id and trade_id in self._recovered_trade_ids:
                continue
            if order_type in {"STP", "STOP", "STP LMT"} or (order_type == "LMT" and side == "SELL"):
                continue
            quantity = int(metadata.get("quantity") or self._value(order, "quantity", 0) or 0)
            price = float(
                metadata.get("entry_price")
                or metadata.get("limit_price")
                or metadata.get("price")
                or metadata.get("reference_price")
                or 0.0
            )
            symbol = str(self._value(order, "symbol", "") or "").upper()
            if not symbol or quantity <= 0 or price <= 0.0:
                if self.run_mode == "LIVE":
                    unresolved += 1
                continue
            decision_id = str(metadata.get("capital_decision_id") or f"recovered-{self._value(order, 'order_id', uuid4().hex)}")
            reservation = CapitalReservation(
                reservation_id=f"cap-rec-{uuid4().hex}",
                decision_id=decision_id,
                timestamp=self._now(),
                run_mode=self.run_mode,
                strategy_id=str(metadata.get("strategy_id") or metadata.get("strategy_name") or "RECOVERY"),
                symbol=symbol,
                side=side or "BUY",
                quantity=quantity,
                notional=float(quantity) * price,
                remaining_quantity=quantity,
                remaining_notional=float(quantity) * price,
                order_id=str(self._value(order, "order_id", "") or ""),
                trade_id=trade_id or None,
                reason="BROKER_OPEN_ORDER_RECOVERY",
            )
            self._reservations[reservation.reservation_id] = reservation
            recovered += 1
        if unresolved > 0:
            self.recovery_failed = True
            self.recovery_failure_reason = "CAPITAL_OPEN_ORDER_RECONSTRUCTION_FAILED"
        print(f"[CAPITAL][RECOVER] open_order_reservations={recovered} reserved={self.total_reserved_capital:.2f}")
        self._audit(
            "RECOVER",
            run_mode=self.run_mode,
            status="RECOVERED",
            reserved_capital=self.total_reserved_capital,
            exposure_after=self.total_used_exposure,
            reason="OPEN_ORDER_RESERVATION_RECOVERY",
        )
        return recovered

    def _resolve_limits(
        self,
        *,
        account_equity: float | None,
        available_capital: float | None,
        buying_power: float | None,
        max_open_positions: int | None,
        max_position_notional: float | None,
        max_total_exposure: float | None,
    ) -> dict[str, float | int]:
        resolved_equity = float(account_equity if account_equity is not None else self.account_equity if self.account_equity is not None else get_risk_account_equity())
        default_capital = float(get_default_capital())
        resolved_available = available_capital if available_capital is not None else self.available_capital
        resolved_buying_power = buying_power if buying_power is not None else self.buying_power
        if resolved_available is None:
            resolved_available = default_capital
        if resolved_buying_power is None:
            resolved_buying_power = resolved_available
        configured_pct_notional = resolved_equity * float(get_config_max_position_pct())
        lifecycle_position = self._config_float("LIFECYCLE_MAX_POSITION_EXPOSURE", configured_pct_notional)
        risk_total_pct = self._config_float("RISK_MAX_TOTAL_EXPOSURE_PCT", 15.0)
        lifecycle_total = self._config_float("LIFECYCLE_MAX_PORTFOLIO_EXPOSURE", resolved_equity * risk_total_pct / 100.0)
        return {
            "account_equity": resolved_equity,
            "available_capital": float(resolved_available),
            "buying_power": float(resolved_buying_power),
            "max_open_positions": int(max_open_positions if max_open_positions is not None else min(self._config_int("RISK_MAX_OPEN_POSITIONS", 5), self._config_int("LIFECYCLE_MAX_POSITIONS", 5))),
            "max_position_notional": float(max_position_notional if max_position_notional is not None else min(configured_pct_notional, lifecycle_position)),
            "max_total_exposure": float(max_total_exposure if max_total_exposure is not None else min(resolved_equity * risk_total_pct / 100.0, lifecycle_total)),
        }

    def _broker_truth_available(self, run_mode: str, broker_truth_available: bool | None) -> bool:
        explicit = broker_truth_available if broker_truth_available is not None else self.broker_truth_available
        if run_mode == "LIVE":
            has_values = (
                self.account_equity is not None
                and self.available_capital is not None
                and self.buying_power is not None
            )
            return bool(explicit) or has_values
        return True

    def _live_account_values_available(
        self,
        *,
        account_equity: float | None,
        available_capital: float | None,
        buying_power: float | None,
    ) -> bool:
        return (
            (account_equity is not None or self.account_equity is not None)
            and (available_capital is not None or self.available_capital is not None)
            and (buying_power is not None or self.buying_power is not None)
        )

    def _blocked_decision(
        self,
        status: CapitalDecisionStatus,
        reason: str,
        run_mode: str,
        strategy_id: str,
        symbol: str,
        side: str,
        requested_quantity: int,
        requested_notional: float,
        current_total: float,
        current_symbol: float,
        current_open_positions: int,
        limits: dict[str, float | int],
        decision_context: dict[str, Any],
        audit_payload: dict[str, Any] | None,
    ) -> CapitalDecision:
        return self._decision(
            status=status,
            reason=reason,
            run_mode=run_mode,
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            requested_quantity=requested_quantity,
            requested_notional=requested_notional,
            approved_quantity=0,
            approved_notional=0.0,
            current_total_exposure=current_total,
            projected_total_exposure=current_total,
            current_symbol_exposure=current_symbol,
            projected_symbol_exposure=current_symbol,
            current_open_positions=current_open_positions,
            limits=limits,
            audit_payload={**decision_context, **(audit_payload or {})},
        )

    def _decision(
        self,
        *,
        status: CapitalDecisionStatus,
        reason: str,
        run_mode: str,
        strategy_id: str,
        symbol: str,
        side: str,
        requested_quantity: int,
        requested_notional: float,
        approved_quantity: int,
        approved_notional: float,
        current_total_exposure: float,
        projected_total_exposure: float,
        current_symbol_exposure: float,
        projected_symbol_exposure: float,
        current_open_positions: int,
        limits: dict[str, float | int],
        audit_payload: dict[str, Any],
    ) -> CapitalDecision:
        return CapitalDecision(
            decision_id=f"cap-{uuid4().hex}",
            timestamp=self._now(),
            run_mode=run_mode,
            strategy_id=str(strategy_id or "UNKNOWN"),
            symbol=symbol,
            side=side,
            requested_quantity=int(requested_quantity),
            requested_notional=float(requested_notional),
            approved_quantity=int(approved_quantity),
            approved_notional=float(approved_notional),
            account_equity=float(limits["account_equity"]),
            available_capital=float(limits["available_capital"]),
            buying_power=float(limits["buying_power"]),
            current_total_exposure=float(current_total_exposure),
            projected_total_exposure=float(projected_total_exposure),
            current_symbol_exposure=float(current_symbol_exposure),
            projected_symbol_exposure=float(projected_symbol_exposure),
            current_open_positions=int(current_open_positions),
            max_open_positions=int(limits["max_open_positions"]),
            max_position_notional=float(limits["max_position_notional"]),
            max_total_exposure=float(limits["max_total_exposure"]),
            reserved_capital=0.0,
            reason=reason,
            audit_payload=audit_payload,
            status=status,
        )

    def _emit_decision(self, decision: CapitalDecision) -> None:
        print(
            "[CAPITAL][DECISION] "
            f"decision_id={decision.decision_id} status={decision.status.value} "
            f"symbol={decision.symbol} requested_qty={decision.requested_quantity} "
            f"approved_qty={decision.approved_quantity} reason={decision.reason}"
        )
        tag = {
            CapitalDecisionStatus.APPROVED: "APPROVED",
            CapitalDecisionStatus.REDUCED: "REDUCED",
            CapitalDecisionStatus.REJECTED: "REJECTED",
            CapitalDecisionStatus.INSUFFICIENT_CAPITAL: "REJECTED",
            CapitalDecisionStatus.EXPOSURE_LIMIT_EXCEEDED: "REJECTED",
            CapitalDecisionStatus.MAX_POSITIONS_EXCEEDED: "REJECTED",
            CapitalDecisionStatus.READ_ONLY_BLOCKED: "BLOCKED",
            CapitalDecisionStatus.RECOVERY_NOT_COMPLETE: "BLOCKED",
            CapitalDecisionStatus.DATA_UNAVAILABLE: "BLOCKED",
            CapitalDecisionStatus.BLOCKED: "BLOCKED",
        }[decision.status]
        print(f"[CAPITAL][{tag}] decision_id={decision.decision_id} reason={decision.reason}")
        self._audit(
            "DECISION",
            decision_id=decision.decision_id,
            symbol=decision.symbol,
            strategy_id=decision.strategy_id,
            run_mode=decision.run_mode,
            status=decision.status.value,
            requested_quantity=decision.requested_quantity,
            approved_quantity=decision.approved_quantity,
            requested_notional=decision.requested_notional,
            approved_notional=decision.approved_notional,
            reserved_capital=decision.reserved_capital,
            exposure_before=decision.current_total_exposure,
            exposure_after=decision.projected_total_exposure,
            reason=decision.reason,
            payload=decision.to_dict(),
        )

    def _audit(self, event_type: str, **payload: Any) -> None:
        print(f"[CAPITAL][AUDIT] event={event_type} reason={payload.get('reason')}")
        if self.storage_engine is None or not hasattr(self.storage_engine, "insert_capital_audit_event"):
            return
        now = self._now()
        event = {
            "event_id": f"cap-audit-{uuid4().hex}",
            "timestamp": now,
            "event_type": event_type,
            "decision_id": payload.get("decision_id"),
            "reservation_id": payload.get("reservation_id"),
            "trade_id": payload.get("trade_id"),
            "intent_id": payload.get("intent_id"),
            "order_id": payload.get("order_id"),
            "symbol": payload.get("symbol"),
            "strategy_id": payload.get("strategy_id"),
            "run_mode": payload.get("run_mode"),
            "status": payload.get("status"),
            "requested_quantity": payload.get("requested_quantity"),
            "approved_quantity": payload.get("approved_quantity"),
            "requested_notional": payload.get("requested_notional"),
            "approved_notional": payload.get("approved_notional"),
            "reserved_capital": payload.get("reserved_capital"),
            "exposure_before": payload.get("exposure_before"),
            "exposure_after": payload.get("exposure_after"),
            "reason": payload.get("reason"),
            "payload_json": json.dumps(payload.get("payload", payload), sort_keys=True, default=str),
            "created_at": now,
        }
        self.storage_engine.insert_capital_audit_event(event)

    def _reserved_symbol_notional(self, symbol: str) -> float:
        normalized = str(symbol or "").upper()
        return sum(
            float(reservation.remaining_notional)
            for reservation in self.active_reservations.values()
            if reservation.symbol == normalized
        )

    def _find_reservation(
        self,
        *,
        decision_id: str | None = None,
        order_id: str | None = None,
        symbol: str | None = None,
    ) -> CapitalReservation | None:
        normalized_symbol = str(symbol or "").upper()
        for reservation in self.active_reservations.values():
            if decision_id and reservation.decision_id != decision_id:
                continue
            if order_id and reservation.order_id != order_id:
                continue
            if normalized_symbol and reservation.symbol != normalized_symbol:
                continue
            return reservation
        return None

    @staticmethod
    def _config_float(name: str, default: float) -> float:
        try:
            return float(get_config(name, default))
        except Exception:
            return float(default)

    @staticmethod
    def _config_int(name: str, default: int) -> int:
        try:
            return int(get_config(name, default))
        except Exception:
            return int(default)

    @staticmethod
    def _value(obj: Any, name: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
