from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import math
from typing import Any
from uuid import uuid4

from src.config.config_resolver import get_config


class StrategyAllocationStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REDUCED = "REDUCED"
    BLOCKED = "BLOCKED"
    STRATEGY_DISABLED = "STRATEGY_DISABLED"
    STRATEGY_CAPITAL_EXCEEDED = "STRATEGY_CAPITAL_EXCEEDED"
    STRATEGY_POSITION_LIMIT_EXCEEDED = "STRATEGY_POSITION_LIMIT_EXCEEDED"
    STRATEGY_TRADE_LIMIT_EXCEEDED = "STRATEGY_TRADE_LIMIT_EXCEEDED"
    CAPITAL_UNAVAILABLE = "CAPITAL_UNAVAILABLE"
    RECOVERY_NOT_COMPLETE = "RECOVERY_NOT_COMPLETE"
    READ_ONLY_BLOCKED = "READ_ONLY_BLOCKED"


@dataclass
class StrategyAllocationDecision:
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
    strategy_capital_limit: float
    strategy_available_capital: float
    strategy_reserved_capital: float
    strategy_used_exposure: float
    strategy_open_positions: int
    strategy_max_positions: int
    strategy_daily_trade_count: int
    strategy_max_daily_trades: int
    global_capital_decision_id: str | None = None
    reason: str = "REJECTED"
    audit_payload: dict[str, Any] = field(default_factory=dict)
    status: StrategyAllocationStatus = StrategyAllocationStatus.REJECTED

    @property
    def approved(self) -> bool:
        return self.status in {StrategyAllocationStatus.APPROVED, StrategyAllocationStatus.REDUCED}

    @property
    def executable(self) -> bool:
        return self.approved and self.approved_quantity > 0 and self.approved_notional > 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass
class StrategyAllocationReservation:
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
    global_capital_decision_id: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StrategyCapitalAllocationAuthority:
    """Canonical per-strategy allocation gate that sits above P7 capital authority."""

    DEFAULT_ALLOCATION_PCT = 0.50
    DEFAULT_MAX_POSITIONS = 5

    def __init__(
        self,
        *,
        run_mode: str = "SIM",
        storage_engine: Any | None = None,
        strategy_limits: dict[str, Any] | None = None,
        default_allocation_pct: float | None = None,
    ) -> None:
        self.run_mode = str(run_mode or "SIM").upper()
        self.storage_engine = storage_engine
        self.strategy_limits = self._normalize_limits(
            strategy_limits
            if strategy_limits is not None
            else self._config_dict("STRATEGY_CAPITAL_ALLOCATIONS", {})
        )
        self.default_allocation_pct = float(
            default_allocation_pct
            if default_allocation_pct is not None
            else self._config_float("STRATEGY_CAPITAL_DEFAULT_ALLOCATION_PCT", self.DEFAULT_ALLOCATION_PCT)
        )
        self._reservations: dict[str, StrategyAllocationReservation] = {}
        self._used_exposure_by_strategy: dict[str, float] = {}
        self._open_positions_by_strategy: dict[str, int] = {}
        self._daily_trade_count_by_strategy: dict[str, int] = {}

    @property
    def active_reservations(self) -> dict[str, StrategyAllocationReservation]:
        return {
            reservation_id: reservation
            for reservation_id, reservation in self._reservations.items()
            if reservation.status == "ACTIVE" and reservation.remaining_notional > 0.0
        }

    def strategy_reserved_capital(self, strategy_id: str) -> float:
        normalized = self._normalize_strategy(strategy_id)
        return sum(
            float(reservation.remaining_notional)
            for reservation in self.active_reservations.values()
            if reservation.strategy_id == normalized
        )

    def strategy_used_exposure(self, strategy_id: str) -> float:
        return float(self._used_exposure_by_strategy.get(self._normalize_strategy(strategy_id), 0.0))

    def strategy_open_positions(self, strategy_id: str) -> int:
        return int(self._open_positions_by_strategy.get(self._normalize_strategy(strategy_id), 0))

    def evaluate_entry(
        self,
        *,
        run_mode: str | None = None,
        strategy_id: str,
        symbol: str,
        side: str,
        requested_quantity: int,
        reference_price: float,
        available_capital: float | None = None,
        account_equity: float | None = None,
        current_strategy_exposure: float | None = None,
        current_strategy_open_positions: int | None = None,
        current_symbol_position_exists: bool = False,
        strategy_daily_trade_count: int | None = None,
        recovery_complete: bool = True,
        broker_truth_available: bool = True,
        intent_id: str | None = None,
        reserve: bool = True,
        audit_payload: dict[str, Any] | None = None,
    ) -> StrategyAllocationDecision:
        effective_mode = str(run_mode or self.run_mode or "SIM").upper()
        normalized_strategy = self._normalize_strategy(strategy_id)
        normalized_symbol = str(symbol or "").upper()
        normalized_side = str(side or "").upper()
        requested_qty = int(requested_quantity or 0)
        price = float(reference_price or 0.0)
        requested_notional = max(0.0, float(requested_qty) * price)
        limits = self._resolve_strategy_limits(normalized_strategy)
        used_exposure = max(
            float(current_strategy_exposure or 0.0),
            self.strategy_used_exposure(normalized_strategy),
        )
        reserved_capital = self.strategy_reserved_capital(normalized_strategy)
        open_positions = max(
            int(current_strategy_open_positions or 0),
            self.strategy_open_positions(normalized_strategy),
        )
        daily_count = max(
            int(strategy_daily_trade_count or 0),
            int(self._daily_trade_count_by_strategy.get(normalized_strategy, 0)),
        )
        position_slot_increase = 0 if current_symbol_position_exists else 1
        projected_open_positions = open_positions + position_slot_increase
        capital_pool = self._resolve_capital_pool(
            available_capital=available_capital,
            account_equity=account_equity,
        )
        strategy_capital_limit = self._strategy_capital_limit(limits, capital_pool)
        strategy_available = max(0.0, strategy_capital_limit - used_exposure - reserved_capital)
        max_positions = int(limits["max_positions"])
        max_daily_trades = int(limits["max_daily_trades"])
        decision_context = {
            "mode": effective_mode,
            "strategy_id": normalized_strategy,
            "symbol": normalized_symbol,
            "side": normalized_side,
            "requested_quantity": requested_qty,
            "reference_price": price,
            "current_symbol_position_exists": current_symbol_position_exists,
            "projected_open_positions": projected_open_positions,
            "broker_truth_available": broker_truth_available,
            "recovery_complete": recovery_complete,
        }

        if effective_mode == "READ_ONLY":
            decision = self._decision(
                status=StrategyAllocationStatus.READ_ONLY_BLOCKED,
                reason="READ_ONLY_BLOCKED",
                run_mode=effective_mode,
                strategy_id=normalized_strategy,
                symbol=normalized_symbol,
                side=normalized_side,
                requested_quantity=requested_qty,
                requested_notional=requested_notional,
                approved_quantity=0,
                approved_notional=0.0,
                strategy_capital_limit=strategy_capital_limit,
                strategy_available_capital=strategy_available,
                strategy_reserved_capital=reserved_capital,
                strategy_used_exposure=used_exposure,
                strategy_open_positions=open_positions,
                strategy_max_positions=max_positions,
                strategy_daily_trade_count=daily_count,
                strategy_max_daily_trades=max_daily_trades,
                audit_payload={**decision_context, **(audit_payload or {})},
            )
            self._emit_decision(decision)
            return decision

        if not recovery_complete:
            decision = self._blocked_decision(
                StrategyAllocationStatus.RECOVERY_NOT_COMPLETE,
                "RECOVERY_NOT_COMPLETE",
                effective_mode,
                normalized_strategy,
                normalized_symbol,
                normalized_side,
                requested_qty,
                requested_notional,
                strategy_capital_limit,
                strategy_available,
                reserved_capital,
                used_exposure,
                open_positions,
                max_positions,
                daily_count,
                max_daily_trades,
                decision_context,
                audit_payload,
            )
            self._emit_decision(decision)
            return decision

        if effective_mode == "LIVE" and not broker_truth_available:
            decision = self._blocked_decision(
                StrategyAllocationStatus.CAPITAL_UNAVAILABLE,
                "STRATEGY_CAPITAL_TRUTH_UNAVAILABLE",
                effective_mode,
                normalized_strategy,
                normalized_symbol,
                normalized_side,
                requested_qty,
                requested_notional,
                strategy_capital_limit,
                strategy_available,
                reserved_capital,
                used_exposure,
                open_positions,
                max_positions,
                daily_count,
                max_daily_trades,
                decision_context,
                audit_payload,
            )
            self._emit_decision(decision)
            return decision

        if not bool(limits["enabled"]):
            decision = self._blocked_decision(
                StrategyAllocationStatus.STRATEGY_DISABLED,
                "STRATEGY_DISABLED",
                effective_mode,
                normalized_strategy,
                normalized_symbol,
                normalized_side,
                requested_qty,
                requested_notional,
                strategy_capital_limit,
                strategy_available,
                reserved_capital,
                used_exposure,
                open_positions,
                max_positions,
                daily_count,
                max_daily_trades,
                decision_context,
                audit_payload,
            )
            self._emit_decision(decision)
            return decision

        if requested_qty <= 0 or price <= 0.0:
            decision = self._blocked_decision(
                StrategyAllocationStatus.REJECTED,
                "INVALID_STRATEGY_ALLOCATION_REQUEST",
                effective_mode,
                normalized_strategy,
                normalized_symbol,
                normalized_side,
                requested_qty,
                requested_notional,
                strategy_capital_limit,
                strategy_available,
                reserved_capital,
                used_exposure,
                open_positions,
                max_positions,
                daily_count,
                max_daily_trades,
                decision_context,
                audit_payload,
            )
            self._emit_decision(decision)
            return decision

        if projected_open_positions > max_positions:
            decision = self._blocked_decision(
                StrategyAllocationStatus.STRATEGY_POSITION_LIMIT_EXCEEDED,
                "STRATEGY_POSITION_LIMIT_EXCEEDED",
                effective_mode,
                normalized_strategy,
                normalized_symbol,
                normalized_side,
                requested_qty,
                requested_notional,
                strategy_capital_limit,
                strategy_available,
                reserved_capital,
                used_exposure,
                open_positions,
                max_positions,
                daily_count,
                max_daily_trades,
                decision_context,
                audit_payload,
            )
            self._emit_decision(decision)
            return decision

        if max_daily_trades > 0 and daily_count >= max_daily_trades:
            decision = self._blocked_decision(
                StrategyAllocationStatus.STRATEGY_TRADE_LIMIT_EXCEEDED,
                "STRATEGY_TRADE_LIMIT_EXCEEDED",
                effective_mode,
                normalized_strategy,
                normalized_symbol,
                normalized_side,
                requested_qty,
                requested_notional,
                strategy_capital_limit,
                strategy_available,
                reserved_capital,
                used_exposure,
                open_positions,
                max_positions,
                daily_count,
                max_daily_trades,
                decision_context,
                audit_payload,
            )
            self._emit_decision(decision)
            return decision

        approved_qty = requested_qty
        approved_notional = requested_notional
        status = StrategyAllocationStatus.APPROVED
        reason = "STRATEGY_ALLOCATION_APPROVED"
        if requested_notional > strategy_available:
            if bool(limits["allow_reduction"]) and strategy_available > 0.0:
                approved_qty = int(math.floor(strategy_available / price))
                approved_notional = float(approved_qty) * price
                if approved_qty > 0:
                    status = StrategyAllocationStatus.REDUCED
                    reason = "STRATEGY_ALLOCATION_REDUCED_TO_AVAILABLE_CAPITAL"
                else:
                    approved_notional = 0.0
            if approved_qty <= 0 or requested_notional > strategy_available and status != StrategyAllocationStatus.REDUCED:
                decision = self._blocked_decision(
                    StrategyAllocationStatus.STRATEGY_CAPITAL_EXCEEDED,
                    "STRATEGY_CAPITAL_EXCEEDED",
                    effective_mode,
                    normalized_strategy,
                    normalized_symbol,
                    normalized_side,
                    requested_qty,
                    requested_notional,
                    strategy_capital_limit,
                    strategy_available,
                    reserved_capital,
                    used_exposure,
                    open_positions,
                    max_positions,
                    daily_count,
                    max_daily_trades,
                    decision_context,
                    audit_payload,
                )
                self._emit_decision(decision)
                return decision

        decision = self._decision(
            status=status,
            reason=reason,
            run_mode=effective_mode,
            strategy_id=normalized_strategy,
            symbol=normalized_symbol,
            side=normalized_side,
            requested_quantity=requested_qty,
            requested_notional=requested_notional,
            approved_quantity=approved_qty,
            approved_notional=approved_notional,
            strategy_capital_limit=strategy_capital_limit,
            strategy_available_capital=strategy_available,
            strategy_reserved_capital=reserved_capital,
            strategy_used_exposure=used_exposure,
            strategy_open_positions=open_positions,
            strategy_max_positions=max_positions,
            strategy_daily_trade_count=daily_count,
            strategy_max_daily_trades=max_daily_trades,
            audit_payload={**decision_context, **(audit_payload or {})},
        )
        if reserve and decision.executable:
            self.reserve(decision, intent_id=intent_id)
        self._emit_decision(decision)
        return decision

    authorize_entry = evaluate_entry

    def reserve(
        self,
        decision: StrategyAllocationDecision,
        *,
        intent_id: str | None = None,
        order_id: str | None = None,
    ) -> StrategyAllocationReservation:
        if not decision.executable:
            raise ValueError("Cannot reserve strategy allocation for a non-executable decision.")
        reservation = StrategyAllocationReservation(
            reservation_id=f"strat-res-{uuid4().hex}",
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
            global_capital_decision_id=decision.global_capital_decision_id,
        )
        self._reservations[reservation.reservation_id] = reservation
        print(
            "[STRATEGY_ALLOC][RESERVED] "
            f"decision_id={decision.decision_id} strategy_id={decision.strategy_id} "
            f"symbol={decision.symbol} notional={reservation.notional:.2f}"
        )
        self._audit(
            "RESERVED",
            decision_id=decision.decision_id,
            reservation_id=reservation.reservation_id,
            strategy_id=reservation.strategy_id,
            symbol=reservation.symbol,
            run_mode=reservation.run_mode,
            status=reservation.status,
            requested_quantity=decision.requested_quantity,
            approved_quantity=decision.approved_quantity,
            requested_notional=decision.requested_notional,
            approved_notional=decision.approved_notional,
            strategy_capital_limit=decision.strategy_capital_limit,
            reserved_capital=reservation.remaining_notional,
            used_exposure=decision.strategy_used_exposure,
            reason=decision.reason,
            intent_id=intent_id,
            order_id=order_id,
            global_capital_decision_id=decision.global_capital_decision_id,
        )
        return reservation

    def attach_order(
        self,
        *,
        decision_id: str,
        order_id: str,
        global_capital_decision_id: str | None = None,
    ) -> None:
        for reservation in self.active_reservations.values():
            if reservation.decision_id == decision_id:
                reservation.order_id = order_id
                if global_capital_decision_id:
                    reservation.global_capital_decision_id = global_capital_decision_id

    def resize_reservation(
        self,
        *,
        decision_id: str,
        quantity: int,
        notional: float,
        reason: str = "RESIZED",
    ) -> None:
        resized_qty = max(0, int(quantity or 0))
        resized_notional = max(0.0, float(notional or 0.0))
        for reservation in self.active_reservations.values():
            if reservation.decision_id != decision_id:
                continue
            reservation.quantity = min(reservation.quantity, resized_qty)
            reservation.notional = min(reservation.notional, resized_notional)
            reservation.remaining_quantity = min(reservation.remaining_quantity, resized_qty)
            reservation.remaining_notional = min(reservation.remaining_notional, resized_notional)
            reservation.reason = reason
            print(
                "[STRATEGY_ALLOC][RESERVED] "
                f"decision_id={decision_id} resized_qty={reservation.remaining_quantity} "
                f"resized_notional={reservation.remaining_notional:.2f} reason={reason}"
            )
            self._audit(
                "RESIZED",
                decision_id=reservation.decision_id,
                reservation_id=reservation.reservation_id,
                strategy_id=reservation.strategy_id,
                symbol=reservation.symbol,
                run_mode=reservation.run_mode,
                status=reservation.status,
                approved_quantity=reservation.quantity,
                approved_notional=reservation.notional,
                reserved_capital=reservation.remaining_notional,
                used_exposure=self.strategy_used_exposure(reservation.strategy_id),
                reason=reason,
                intent_id=reservation.intent_id,
                order_id=reservation.order_id,
                global_capital_decision_id=reservation.global_capital_decision_id,
            )

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
                "[STRATEGY_ALLOC][RELEASED] "
                f"decision_id={reservation.decision_id} strategy_id={reservation.strategy_id} "
                f"notional={released:.2f} reason={reason}"
            )
            self._audit(
                "RELEASED",
                decision_id=reservation.decision_id,
                reservation_id=reservation.reservation_id,
                strategy_id=reservation.strategy_id,
                symbol=reservation.symbol,
                run_mode=reservation.run_mode,
                status=reservation.status,
                approved_quantity=reservation.quantity,
                approved_notional=reservation.notional,
                reserved_capital=0.0,
                used_exposure=self.strategy_used_exposure(reservation.strategy_id),
                reason=reason,
                intent_id=reservation.intent_id,
                order_id=reservation.order_id,
                global_capital_decision_id=reservation.global_capital_decision_id,
            )
        return released

    def convert_reservation_to_exposure(
        self,
        *,
        decision_id: str | None = None,
        order_id: str | None = None,
        strategy_id: str | None = None,
        symbol: str | None = None,
        fill_quantity: int,
        fill_price: float,
        trade_id: str | None = None,
        reason: str = "FILL_RECORDED",
    ) -> float:
        fill_qty = int(fill_quantity or 0)
        fill_notional = max(0.0, float(fill_qty) * float(fill_price or 0.0))
        if fill_qty <= 0 or fill_notional <= 0.0:
            return 0.0
        reservation = self._find_reservation(decision_id=decision_id, order_id=order_id)
        normalized_strategy = self._normalize_strategy(
            strategy_id or getattr(reservation, "strategy_id", None) or "UNKNOWN"
        )
        first_fill_for_reservation = reservation is None or reservation.filled_quantity <= 0
        self._used_exposure_by_strategy[normalized_strategy] = (
            self.strategy_used_exposure(normalized_strategy) + fill_notional
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
        if first_fill_for_reservation:
            self._daily_trade_count_by_strategy[normalized_strategy] = (
                self._daily_trade_count_by_strategy.get(normalized_strategy, 0) + 1
            )
            self._open_positions_by_strategy[normalized_strategy] = (
                self._open_positions_by_strategy.get(normalized_strategy, 0) + 1
            )
        print(
            "[STRATEGY_ALLOC][EXPOSURE] "
            f"strategy_id={normalized_strategy} fill_qty={fill_qty} "
            f"fill_notional={fill_notional:.2f}"
        )
        self._audit(
            "EXPOSURE",
            decision_id=getattr(reservation, "decision_id", decision_id),
            reservation_id=getattr(reservation, "reservation_id", None),
            strategy_id=normalized_strategy,
            symbol=symbol or getattr(reservation, "symbol", None),
            run_mode=getattr(reservation, "run_mode", self.run_mode),
            status=getattr(reservation, "status", "EXPOSURE"),
            approved_quantity=getattr(reservation, "quantity", fill_qty),
            approved_notional=getattr(reservation, "notional", fill_notional),
            reserved_capital=getattr(reservation, "remaining_notional", 0.0),
            used_exposure=self.strategy_used_exposure(normalized_strategy),
            reason=reason,
            intent_id=getattr(reservation, "intent_id", None),
            order_id=order_id,
            trade_id=trade_id,
            global_capital_decision_id=getattr(reservation, "global_capital_decision_id", None),
        )
        return fill_notional

    def release_exposure(
        self,
        *,
        strategy_id: str,
        quantity: int | None = None,
        price: float | None = None,
        notional: float | None = None,
        reason: str = "EXIT_RECORDED",
    ) -> float:
        normalized_strategy = self._normalize_strategy(strategy_id)
        release_notional = float(notional if notional is not None else float(quantity or 0) * float(price or 0.0))
        release_notional = max(0.0, release_notional)
        current = self.strategy_used_exposure(normalized_strategy)
        released = min(current, release_notional)
        self._used_exposure_by_strategy[normalized_strategy] = max(0.0, current - released)
        if released > 0:
            self._open_positions_by_strategy[normalized_strategy] = max(
                0,
                self._open_positions_by_strategy.get(normalized_strategy, 0) - 1,
            )
        print(
            "[STRATEGY_ALLOC][EXPOSURE] "
            f"strategy_id={normalized_strategy} released={released:.2f} "
            f"reason={reason}"
        )
        self._audit(
            "EXPOSURE_RELEASED",
            strategy_id=normalized_strategy,
            run_mode=self.run_mode,
            reserved_capital=self.strategy_reserved_capital(normalized_strategy),
            used_exposure=self.strategy_used_exposure(normalized_strategy),
            reason=reason,
        )
        return released

    def recover_from_lifecycle(self, open_lifecycle_trades: list[Any]) -> int:
        self._used_exposure_by_strategy.clear()
        self._open_positions_by_strategy.clear()
        recovered = 0
        for trade in open_lifecycle_trades or []:
            quantity = int(self._value(trade, "quantity_open", 0) or 0)
            price = float(self._value(trade, "entry_avg_price", 0.0) or 0.0)
            strategy_id = self._normalize_strategy(self._value(trade, "strategy_name", "RECOVERY") or "RECOVERY")
            if quantity <= 0 or price <= 0.0:
                continue
            notional = float(quantity) * price
            self._used_exposure_by_strategy[strategy_id] = self.strategy_used_exposure(strategy_id) + notional
            self._open_positions_by_strategy[strategy_id] = self._open_positions_by_strategy.get(strategy_id, 0) + 1
            recovered += 1
        print(f"[STRATEGY_ALLOC][RECOVER] lifecycle_strategy_exposures={recovered}")
        self._audit(
            "RECOVER",
            run_mode=self.run_mode,
            status="RECOVERED",
            reason="LIFECYCLE_STRATEGY_ALLOCATION_RECOVERY",
            payload={"recovered": recovered},
        )
        return recovered

    def _blocked_decision(
        self,
        status: StrategyAllocationStatus,
        reason: str,
        run_mode: str,
        strategy_id: str,
        symbol: str,
        side: str,
        requested_quantity: int,
        requested_notional: float,
        strategy_capital_limit: float,
        strategy_available_capital: float,
        strategy_reserved_capital: float,
        strategy_used_exposure: float,
        strategy_open_positions: int,
        strategy_max_positions: int,
        strategy_daily_trade_count: int,
        strategy_max_daily_trades: int,
        decision_context: dict[str, Any],
        audit_payload: dict[str, Any] | None,
    ) -> StrategyAllocationDecision:
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
            strategy_capital_limit=strategy_capital_limit,
            strategy_available_capital=strategy_available_capital,
            strategy_reserved_capital=strategy_reserved_capital,
            strategy_used_exposure=strategy_used_exposure,
            strategy_open_positions=strategy_open_positions,
            strategy_max_positions=strategy_max_positions,
            strategy_daily_trade_count=strategy_daily_trade_count,
            strategy_max_daily_trades=strategy_max_daily_trades,
            audit_payload={**decision_context, **(audit_payload or {})},
        )

    def _decision(
        self,
        *,
        status: StrategyAllocationStatus,
        reason: str,
        run_mode: str,
        strategy_id: str,
        symbol: str,
        side: str,
        requested_quantity: int,
        requested_notional: float,
        approved_quantity: int,
        approved_notional: float,
        strategy_capital_limit: float,
        strategy_available_capital: float,
        strategy_reserved_capital: float,
        strategy_used_exposure: float,
        strategy_open_positions: int,
        strategy_max_positions: int,
        strategy_daily_trade_count: int,
        strategy_max_daily_trades: int,
        audit_payload: dict[str, Any],
    ) -> StrategyAllocationDecision:
        return StrategyAllocationDecision(
            decision_id=f"strat-alloc-{uuid4().hex}",
            timestamp=self._now(),
            run_mode=run_mode,
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            requested_quantity=int(requested_quantity),
            requested_notional=float(requested_notional),
            approved_quantity=int(approved_quantity),
            approved_notional=float(approved_notional),
            strategy_capital_limit=float(strategy_capital_limit),
            strategy_available_capital=float(strategy_available_capital),
            strategy_reserved_capital=float(strategy_reserved_capital),
            strategy_used_exposure=float(strategy_used_exposure),
            strategy_open_positions=int(strategy_open_positions),
            strategy_max_positions=int(strategy_max_positions),
            strategy_daily_trade_count=int(strategy_daily_trade_count),
            strategy_max_daily_trades=int(strategy_max_daily_trades),
            reason=reason,
            audit_payload=audit_payload,
            status=status,
        )

    def _emit_decision(self, decision: StrategyAllocationDecision) -> None:
        print(
            "[STRATEGY_ALLOC][DECISION] "
            f"decision_id={decision.decision_id} status={decision.status.value} "
            f"strategy_id={decision.strategy_id} symbol={decision.symbol} "
            f"approved_qty={decision.approved_quantity} reason={decision.reason}"
        )
        tag = {
            StrategyAllocationStatus.APPROVED: "APPROVED",
            StrategyAllocationStatus.REDUCED: "REDUCED",
            StrategyAllocationStatus.REJECTED: "REJECTED",
            StrategyAllocationStatus.STRATEGY_DISABLED: "REJECTED",
            StrategyAllocationStatus.STRATEGY_CAPITAL_EXCEEDED: "REJECTED",
            StrategyAllocationStatus.STRATEGY_POSITION_LIMIT_EXCEEDED: "REJECTED",
            StrategyAllocationStatus.STRATEGY_TRADE_LIMIT_EXCEEDED: "REJECTED",
            StrategyAllocationStatus.BLOCKED: "BLOCKED",
            StrategyAllocationStatus.CAPITAL_UNAVAILABLE: "BLOCKED",
            StrategyAllocationStatus.RECOVERY_NOT_COMPLETE: "BLOCKED",
            StrategyAllocationStatus.READ_ONLY_BLOCKED: "BLOCKED",
        }[decision.status]
        print(f"[STRATEGY_ALLOC][{tag}] decision_id={decision.decision_id} reason={decision.reason}")
        self._audit(
            "DECISION",
            decision_id=decision.decision_id,
            strategy_id=decision.strategy_id,
            symbol=decision.symbol,
            run_mode=decision.run_mode,
            status=decision.status.value,
            requested_quantity=decision.requested_quantity,
            approved_quantity=decision.approved_quantity,
            requested_notional=decision.requested_notional,
            approved_notional=decision.approved_notional,
            strategy_capital_limit=decision.strategy_capital_limit,
            reserved_capital=decision.strategy_reserved_capital,
            used_exposure=decision.strategy_used_exposure,
            reason=decision.reason,
            payload=decision.to_dict(),
        )

    def _audit(self, event_type: str, **payload: Any) -> None:
        print(f"[STRATEGY_ALLOC][AUDIT] event={event_type} reason={payload.get('reason')}")
        if self.storage_engine is None or not hasattr(self.storage_engine, "insert_strategy_allocation_audit_event"):
            return
        now = self._now()
        event = {
            "event_id": f"strat-alloc-audit-{uuid4().hex}",
            "timestamp": now,
            "event_type": event_type,
            "decision_id": payload.get("decision_id"),
            "reservation_id": payload.get("reservation_id"),
            "trade_id": payload.get("trade_id"),
            "intent_id": payload.get("intent_id"),
            "order_id": payload.get("order_id"),
            "strategy_id": payload.get("strategy_id"),
            "symbol": payload.get("symbol"),
            "run_mode": payload.get("run_mode"),
            "status": payload.get("status"),
            "requested_quantity": payload.get("requested_quantity"),
            "approved_quantity": payload.get("approved_quantity"),
            "requested_notional": payload.get("requested_notional"),
            "approved_notional": payload.get("approved_notional"),
            "strategy_capital_limit": payload.get("strategy_capital_limit"),
            "reserved_capital": payload.get("reserved_capital"),
            "used_exposure": payload.get("used_exposure"),
            "reason": payload.get("reason"),
            "global_capital_decision_id": payload.get("global_capital_decision_id"),
            "payload_json": json.dumps(payload.get("payload", payload), sort_keys=True, default=str),
            "created_at": now,
        }
        self.storage_engine.insert_strategy_allocation_audit_event(event)

    def _resolve_strategy_limits(self, strategy_id: str) -> dict[str, Any]:
        raw = dict(self.strategy_limits.get(strategy_id) or self.strategy_limits.get("DEFAULT") or {})
        allocation_pct = float(raw.get("allocation_pct", self.default_allocation_pct))
        allocation_pct = max(0.0, min(allocation_pct, 1.0))
        return {
            "enabled": bool(raw.get("enabled", True)),
            "allocation_pct": allocation_pct,
            "max_allocation_usd": self._float_or_none(raw.get("max_allocation_usd")),
            "max_positions": int(raw.get("max_positions", self.DEFAULT_MAX_POSITIONS) or self.DEFAULT_MAX_POSITIONS),
            "max_daily_trades": int(raw.get("max_daily_trades", 0) or 0),
            "allow_reduction": bool(raw.get("allow_reduction", False)),
        }

    @staticmethod
    def _strategy_capital_limit(limits: dict[str, Any], capital_pool: float) -> float:
        limit = max(0.0, float(capital_pool) * float(limits["allocation_pct"]))
        max_usd = limits.get("max_allocation_usd")
        if max_usd is not None:
            limit = min(limit, max(0.0, float(max_usd)))
        return limit

    @staticmethod
    def _resolve_capital_pool(*, available_capital: float | None, account_equity: float | None) -> float:
        if account_equity is not None:
            return max(0.0, float(account_equity))
        if available_capital is not None:
            return max(0.0, float(available_capital))
        return max(0.0, StrategyCapitalAllocationAuthority._config_float("TRADING_DEFAULT_CAPITAL", 10_000.0))

    @classmethod
    def _normalize_limits(cls, limits: dict[str, Any]) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for strategy_id, payload in dict(limits or {}).items():
            if not isinstance(payload, dict):
                continue
            normalized[cls._normalize_strategy(strategy_id)] = dict(payload)
        if "DEFAULT" not in normalized:
            normalized["DEFAULT"] = {
                "enabled": True,
                "allocation_pct": cls.DEFAULT_ALLOCATION_PCT,
                "max_positions": cls.DEFAULT_MAX_POSITIONS,
                "max_daily_trades": 0,
                "allow_reduction": False,
            }
        return normalized

    def _find_reservation(
        self,
        *,
        decision_id: str | None = None,
        order_id: str | None = None,
    ) -> StrategyAllocationReservation | None:
        for reservation in self.active_reservations.values():
            if decision_id and reservation.decision_id != decision_id:
                continue
            if order_id and reservation.order_id != order_id:
                continue
            return reservation
        return None

    @staticmethod
    def _normalize_strategy(strategy_id: str | None) -> str:
        return str(strategy_id or "UNKNOWN").upper()

    @staticmethod
    def _value(obj: Any, name: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _config_float(name: str, default: float) -> float:
        try:
            return float(get_config(name, default))
        except Exception:
            return float(default)

    @staticmethod
    def _config_dict(name: str, default: dict[str, Any]) -> dict[str, Any]:
        try:
            value = get_config(name, default)
            return dict(value or {})
        except Exception:
            return dict(default)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
