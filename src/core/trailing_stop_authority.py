from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any


class TrailingStopDecisionStatus(str, Enum):
    NO_ACTION = "NO_ACTION"
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class TrailingStopDecision:
    status: TrailingStopDecisionStatus
    reason: str
    symbol: str
    side: str
    current_stop_price: float | None
    proposed_stop_price: float | None
    quantity: int
    trigger_price: float | None = None
    reference_price: float | None = None
    is_tightening: bool = False
    blocked_reason: str | None = None
    audit_payload: dict[str, Any] = field(default_factory=dict)

    @property
    def approved(self) -> bool:
        return self.status == TrailingStopDecisionStatus.APPROVED

    def to_audit_payload(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "reason": self.reason,
            "symbol": self.symbol,
            "side": self.side,
            "current_stop_price": self.current_stop_price,
            "proposed_stop_price": self.proposed_stop_price,
            "quantity": self.quantity,
            "trigger_price": self.trigger_price,
            "reference_price": self.reference_price,
            "is_tightening": self.is_tightening,
            "blocked_reason": self.blocked_reason,
            **dict(self.audit_payload or {}),
        }


class TrailingStopAuthority:
    """Canonical deterministic authority for post-protection stop tightening."""

    def evaluate_update(
        self,
        *,
        symbol: str,
        side: str,
        current_stop_price: float | None,
        proposed_stop_price: float | None,
        quantity: int,
        live_position_quantity: int,
        has_active_stop: bool,
        recovery_complete: bool,
        run_mode: str,
        trigger_price: float | None = None,
        reference_price: float | None = None,
        allow_same_price: bool = False,
        source: str = "runtime",
    ) -> TrailingStopDecision:
        symbol_u = str(symbol or "").upper()
        side_u = self._normalize_side(side)
        qty = int(quantity or 0)
        live_qty = int(live_position_quantity or 0)

        base_payload = {
            "source": source,
            "run_mode": str(run_mode or "").upper(),
            "live_position_quantity": live_qty,
            "has_active_stop": bool(has_active_stop),
            "recovery_complete": bool(recovery_complete),
            "allow_same_price": bool(allow_same_price),
        }

        if not symbol_u:
            return self._decision(
                TrailingStopDecisionStatus.REJECTED,
                "SYMBOL_REQUIRED",
                symbol_u,
                side_u,
                current_stop_price,
                proposed_stop_price,
                qty,
                trigger_price,
                reference_price,
                False,
                audit_payload=base_payload,
            )
        if side_u not in {"LONG", "SHORT"}:
            return self._decision(
                TrailingStopDecisionStatus.REJECTED,
                "INVALID_SIDE",
                symbol_u,
                side_u,
                current_stop_price,
                proposed_stop_price,
                qty,
                trigger_price,
                reference_price,
                False,
                audit_payload=base_payload,
            )
        if not has_active_stop:
            return self._decision(
                TrailingStopDecisionStatus.BLOCKED,
                "INITIAL_PROTECTIVE_STOP_REQUIRED",
                symbol_u,
                side_u,
                current_stop_price,
                proposed_stop_price,
                qty,
                trigger_price,
                reference_price,
                False,
                blocked_reason="INITIAL_PROTECTIVE_STOP_REQUIRED",
                audit_payload=base_payload,
            )
        if not recovery_complete:
            return self._decision(
                TrailingStopDecisionStatus.BLOCKED,
                "STARTUP_RECOVERY_NOT_COMPLETE",
                symbol_u,
                side_u,
                current_stop_price,
                proposed_stop_price,
                qty,
                trigger_price,
                reference_price,
                False,
                blocked_reason="STARTUP_RECOVERY_NOT_COMPLETE",
                audit_payload=base_payload,
            )
        if qty <= 0 or live_qty <= 0:
            return self._decision(
                TrailingStopDecisionStatus.REJECTED,
                "INVALID_TRAILING_QUANTITY",
                symbol_u,
                side_u,
                current_stop_price,
                proposed_stop_price,
                qty,
                trigger_price,
                reference_price,
                False,
                audit_payload=base_payload,
            )
        if qty > live_qty:
            return self._decision(
                TrailingStopDecisionStatus.REJECTED,
                "TRAILING_QUANTITY_EXCEEDS_POSITION",
                symbol_u,
                side_u,
                current_stop_price,
                proposed_stop_price,
                qty,
                trigger_price,
                reference_price,
                False,
                audit_payload=base_payload,
            )

        try:
            current = self._finite_positive(current_stop_price, "current_stop_price")
            proposed = self._finite_positive(proposed_stop_price, "proposed_stop_price")
        except ValueError as exc:
            return self._decision(
                TrailingStopDecisionStatus.REJECTED,
                str(exc),
                symbol_u,
                side_u,
                current_stop_price,
                proposed_stop_price,
                qty,
                trigger_price,
                reference_price,
                False,
                audit_payload=base_payload,
            )

        tightening = self.is_tightening(side=side_u, current_stop_price=current, proposed_stop_price=proposed)
        if not tightening:
            return self._decision(
                TrailingStopDecisionStatus.REJECTED,
                "STOP_LOOSENING_REJECTED",
                symbol_u,
                side_u,
                current,
                proposed,
                qty,
                trigger_price,
                reference_price,
                False,
                audit_payload=base_payload,
            )

        if str(run_mode or "").upper() == "READ_ONLY":
            return self._decision(
                TrailingStopDecisionStatus.BLOCKED,
                "READ_ONLY_NO_ORDER_MUTATION",
                symbol_u,
                side_u,
                current,
                proposed,
                qty,
                trigger_price,
                reference_price,
                True,
                blocked_reason="READ_ONLY_NO_ORDER_MUTATION",
                audit_payload=base_payload,
            )

        if abs(proposed - current) <= 1e-9 and not allow_same_price:
            return self._decision(
                TrailingStopDecisionStatus.NO_ACTION,
                "STOP_UNCHANGED",
                symbol_u,
                side_u,
                current,
                proposed,
                qty,
                trigger_price,
                reference_price,
                True,
                audit_payload=base_payload,
            )

        reason = "STOP_QUANTITY_RESIZE_ALLOWED" if abs(proposed - current) <= 1e-9 else "TRAILING_STOP_TIGHTENING_APPROVED"
        return self._decision(
            TrailingStopDecisionStatus.APPROVED,
            reason,
            symbol_u,
            side_u,
            current,
            proposed,
            qty,
            trigger_price,
            reference_price,
            True,
            audit_payload=base_payload,
        )

    @staticmethod
    def is_tightening(*, side: str, current_stop_price: float, proposed_stop_price: float) -> bool:
        side_u = TrailingStopAuthority._normalize_side(side)
        current = TrailingStopAuthority._finite_positive(current_stop_price, "current_stop_price")
        proposed = TrailingStopAuthority._finite_positive(proposed_stop_price, "proposed_stop_price")
        if side_u == "LONG":
            return proposed >= current
        if side_u == "SHORT":
            return proposed <= current
        return False

    @staticmethod
    def _normalize_side(side: str) -> str:
        side_u = str(side or "").upper()
        if side_u in {"LONG", "BUY"}:
            return "LONG"
        if side_u in {"SHORT", "SELL"}:
            return "SHORT"
        return side_u

    @staticmethod
    def _finite_positive(value: float | None, name: str) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name.upper()}_INVALID") from exc
        if not math.isfinite(numeric) or numeric <= 0.0:
            raise ValueError(f"{name.upper()}_INVALID")
        return numeric

    @staticmethod
    def _decision(
        status: TrailingStopDecisionStatus,
        reason: str,
        symbol: str,
        side: str,
        current_stop_price: float | None,
        proposed_stop_price: float | None,
        quantity: int,
        trigger_price: float | None,
        reference_price: float | None,
        is_tightening: bool,
        *,
        blocked_reason: str | None = None,
        audit_payload: dict[str, Any] | None = None,
    ) -> TrailingStopDecision:
        return TrailingStopDecision(
            status=status,
            reason=reason,
            symbol=symbol,
            side=side,
            current_stop_price=current_stop_price,
            proposed_stop_price=proposed_stop_price,
            quantity=int(quantity or 0),
            trigger_price=trigger_price,
            reference_price=reference_price,
            is_tightening=bool(is_tightening),
            blocked_reason=blocked_reason,
            audit_payload=dict(audit_payload or {}),
        )


__all__ = [
    "TrailingStopAuthority",
    "TrailingStopDecision",
    "TrailingStopDecisionStatus",
]
