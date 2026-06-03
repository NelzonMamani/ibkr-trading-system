from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class TakeProfitTargetType(str, Enum):
    FIXED_PRICE = "FIXED_PRICE"
    FIXED_PERCENT = "FIXED_PERCENT"
    R_MULTIPLE = "R_MULTIPLE"
    PARTIAL_SCALE_OUT = "PARTIAL_SCALE_OUT"
    FULL_EXIT = "FULL_EXIT"


class TakeProfitDecisionStatus(str, Enum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"


TERMINAL_TARGET_STATUSES = {
    TakeProfitDecisionStatus.FILLED,
    TakeProfitDecisionStatus.CANCELLED,
    TakeProfitDecisionStatus.SUPERSEDED,
    TakeProfitDecisionStatus.REJECTED,
}


@dataclass(frozen=True)
class TakeProfitDecision:
    accepted: bool
    decision_id: str
    target_id: str | None
    trade_id: str
    symbol: str
    side: str
    target_type: str
    status: str
    target_price: float | None
    target_quantity: int
    live_position_quantity: int
    remaining_position_quantity: int
    source_strategy: str
    reason_code: str
    rationale: str
    lifecycle_event: str
    target_stage: str = "PRIMARY"
    broker_order_id: str | None = None
    supersedes_target_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_audit_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["authority"] = "TakeProfitAuthority"
        return payload


@dataclass(frozen=True)
class TakeProfitFillResult:
    accepted: bool
    target_id: str | None
    trade_id: str
    symbol: str
    status: str
    fill_quantity: int
    remaining_target_quantity: int
    remaining_position_quantity: int
    reason_code: str
    rationale: str
    lifecycle_event: str
    broker_order_id: str | None = None
    realized_pnl: float | None = None

    def to_audit_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["authority"] = "TakeProfitAuthority"
        return payload


class TakeProfitAuthority:
    """Canonical take-profit calculation and target lifecycle authority."""

    def __init__(self) -> None:
        self._targets: dict[str, TakeProfitDecision] = {}
        self._active_target_by_slice: dict[tuple[str, str], str] = {}

    @staticmethod
    def _ts() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize_side(side: str) -> str:
        normalized = str(side or "").upper()
        if normalized in {"BUY"}:
            return "LONG"
        if normalized in {"SELL"}:
            return "SHORT"
        return normalized

    @staticmethod
    def _round_price(value: float, decimals: int) -> float:
        return round(float(value), int(decimals))

    @staticmethod
    def _hits_target(side: str, current_price: float, target_price: float) -> bool:
        normalized = TakeProfitAuthority._normalize_side(side)
        if normalized == "SHORT":
            return float(current_price) <= float(target_price)
        return float(current_price) >= float(target_price)

    @staticmethod
    def fixed_percent_price(
        *,
        entry_price: float,
        side: str,
        target_pct: float,
        decimals: int = 4,
    ) -> float:
        normalized = TakeProfitAuthority._normalize_side(side)
        if normalized == "SHORT":
            return TakeProfitAuthority._round_price(float(entry_price) * (1.0 - float(target_pct)), decimals)
        return TakeProfitAuthority._round_price(float(entry_price) * (1.0 + float(target_pct)), decimals)

    @staticmethod
    def r_multiple_price(
        *,
        entry_price: float,
        stop_loss_price: float,
        side: str,
        r_multiple: float,
        decimals: int = 2,
    ) -> float:
        risk_amount = max(abs(float(entry_price) - float(stop_loss_price)), 0.01)
        normalized = TakeProfitAuthority._normalize_side(side)
        if normalized == "SHORT":
            return TakeProfitAuthority._round_price(float(entry_price) - (risk_amount * float(r_multiple)), decimals)
        return TakeProfitAuthority._round_price(float(entry_price) + (risk_amount * float(r_multiple)), decimals)

    @staticmethod
    def fixed_staged_targets(*, entry_price: float, side: str, decimals: int = 4) -> tuple[float, float, str]:
        normalized = TakeProfitAuthority._normalize_side(side)
        entry = float(entry_price)
        base_dollars = int(entry)
        if normalized == "SHORT":
            half_level = base_dollars - 0.5
            whole_level = base_dollars - 1.0
            if entry > half_level:
                first_target = half_level
                target_type = "HALF_DOLLAR"
            else:
                first_target = whole_level
                target_type = "WHOLE_DOLLAR"
            second_target = first_target - 0.5
            return (
                TakeProfitAuthority._round_price(first_target, decimals),
                TakeProfitAuthority._round_price(second_target, decimals),
                target_type,
            )
        half_level = base_dollars + 0.5
        whole_level = base_dollars + 1.0
        if entry < half_level:
            first_target = half_level
            target_type = "HALF_DOLLAR"
        else:
            first_target = whole_level
            target_type = "WHOLE_DOLLAR"
        second_target = first_target + 0.5
        return (
            TakeProfitAuthority._round_price(first_target, decimals),
            TakeProfitAuthority._round_price(second_target, decimals),
            target_type,
        )

    @staticmethod
    def scale_out_quantity(
        *,
        live_position_quantity: int,
        fraction: float,
        allow_full_exit_for_single_share: bool = True,
    ) -> int:
        live_qty = max(int(live_position_quantity or 0), 0)
        if live_qty <= 0:
            return 0
        if live_qty == 1 and allow_full_exit_for_single_share:
            return 1
        target_qty = int(round(live_qty * float(fraction)))
        target_qty = max(target_qty, 1)
        return min(target_qty, max(live_qty - 1, 0))

    def create_r_multiple_target(
        self,
        *,
        trade_id: str,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss_price: float,
        live_position_quantity: int,
        source_strategy: str,
        r_multiple: float = 1.0,
        target_stage: str = "PRIMARY",
        fraction: float | None = None,
        target_type: TakeProfitTargetType = TakeProfitTargetType.R_MULTIPLE,
        decimals: int = 2,
        broker_position_degraded: bool = False,
        account_degraded: bool = False,
    ) -> TakeProfitDecision:
        target_price = self.r_multiple_price(
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            side=side,
            r_multiple=r_multiple,
            decimals=decimals,
        )
        return self.create_target(
            trade_id=trade_id,
            symbol=symbol,
            side=side,
            target_price=target_price,
            live_position_quantity=live_position_quantity,
            source_strategy=source_strategy,
            target_type=target_type,
            target_stage=target_stage,
            fraction=fraction,
            broker_position_degraded=broker_position_degraded,
            account_degraded=account_degraded,
            rationale=(
                f"{float(r_multiple):.2f}R target from entry={float(entry_price):.4f} "
                f"stop={float(stop_loss_price):.4f}"
            ),
        )

    def create_fixed_percent_target(
        self,
        *,
        trade_id: str,
        symbol: str,
        side: str,
        entry_price: float,
        target_pct: float,
        live_position_quantity: int,
        source_strategy: str,
        target_stage: str = "PRIMARY",
        fraction: float | None = None,
        decimals: int = 4,
    ) -> TakeProfitDecision:
        target_price = self.fixed_percent_price(
            entry_price=entry_price,
            side=side,
            target_pct=target_pct,
            decimals=decimals,
        )
        return self.create_target(
            trade_id=trade_id,
            symbol=symbol,
            side=side,
            target_price=target_price,
            live_position_quantity=live_position_quantity,
            source_strategy=source_strategy,
            target_type=TakeProfitTargetType.FIXED_PERCENT,
            target_stage=target_stage,
            fraction=fraction,
            rationale=(
                f"fixed percent target_pct={float(target_pct):.4f} "
                f"from entry={float(entry_price):.4f}"
            ),
        )

    def create_fixed_price_target(
        self,
        *,
        trade_id: str,
        symbol: str,
        side: str,
        target_price: float,
        live_position_quantity: int,
        source_strategy: str,
        target_stage: str = "PRIMARY",
        fraction: float | None = None,
        quantity: int | None = None,
        rationale: str | None = None,
    ) -> TakeProfitDecision:
        return self.create_target(
            trade_id=trade_id,
            symbol=symbol,
            side=side,
            target_price=float(target_price),
            live_position_quantity=live_position_quantity,
            source_strategy=source_strategy,
            target_type=TakeProfitTargetType.FIXED_PRICE,
            target_stage=target_stage,
            fraction=fraction,
            quantity=quantity,
            rationale=rationale or f"fixed target price={float(target_price):.4f}",
        )

    def create_target(
        self,
        *,
        trade_id: str,
        symbol: str,
        side: str,
        target_price: float,
        live_position_quantity: int,
        source_strategy: str,
        target_type: TakeProfitTargetType,
        target_stage: str = "PRIMARY",
        fraction: float | None = None,
        quantity: int | None = None,
        rationale: str,
        broker_position_degraded: bool = False,
        account_degraded: bool = False,
    ) -> TakeProfitDecision:
        normalized_trade_id = str(trade_id or "").strip()
        symbol_u = str(symbol or "").upper()
        side_u = self._normalize_side(side)
        stage_u = str(target_stage or "PRIMARY").upper()
        live_qty = max(int(live_position_quantity or 0), 0)
        target_id = f"TP-{uuid4()}"

        if not normalized_trade_id or not symbol_u:
            return self._rejected(
                trade_id=normalized_trade_id,
                symbol=symbol_u,
                side=side_u,
                target_type=target_type,
                live_position_quantity=live_qty,
                source_strategy=source_strategy,
                target_stage=stage_u,
                reason_code="TARGET_CONTEXT_MISSING",
                rationale="Take-profit target requires trade_id and symbol.",
            )
        if broker_position_degraded or account_degraded:
            return self._rejected(
                trade_id=normalized_trade_id,
                symbol=symbol_u,
                side=side_u,
                target_type=target_type,
                live_position_quantity=live_qty,
                source_strategy=source_strategy,
                target_stage=stage_u,
                reason_code="TARGET_STATE_DEGRADED",
                rationale="Broker/account/position state is degraded; target placement blocked.",
            )
        if live_qty <= 0:
            return self._rejected(
                trade_id=normalized_trade_id,
                symbol=symbol_u,
                side=side_u,
                target_type=target_type,
                live_position_quantity=live_qty,
                source_strategy=source_strategy,
                target_stage=stage_u,
                reason_code="NO_LIVE_POSITION",
                rationale="Cannot create take-profit target without broker-owned position quantity.",
            )
        requested_qty = int(quantity) if quantity is not None else live_qty
        if fraction is not None:
            requested_qty = self.scale_out_quantity(live_position_quantity=live_qty, fraction=fraction)
        if requested_qty <= 0:
            return self._rejected(
                trade_id=normalized_trade_id,
                symbol=symbol_u,
                side=side_u,
                target_type=target_type,
                live_position_quantity=live_qty,
                source_strategy=source_strategy,
                target_stage=stage_u,
                reason_code="INVALID_TARGET_QUANTITY",
                rationale="Take-profit target quantity must be positive.",
            )
        if requested_qty > live_qty:
            return self._rejected(
                trade_id=normalized_trade_id,
                symbol=symbol_u,
                side=side_u,
                target_type=target_type,
                live_position_quantity=live_qty,
                source_strategy=source_strategy,
                target_stage=stage_u,
                reason_code="TARGET_QTY_EXCEEDS_POSITION",
                rationale=(
                    "Take-profit target quantity exceeds live position quantity "
                    f"target_qty={requested_qty} live_qty={live_qty}."
                ),
            )
        slice_key = (normalized_trade_id, stage_u)
        duplicate_target_id = self._active_target_by_slice.get(slice_key)
        if duplicate_target_id:
            duplicate = self._targets.get(duplicate_target_id)
            if duplicate and TakeProfitDecisionStatus(duplicate.status) not in TERMINAL_TARGET_STATUSES:
                return self._rejected(
                    trade_id=normalized_trade_id,
                    symbol=symbol_u,
                    side=side_u,
                    target_type=target_type,
                    live_position_quantity=live_qty,
                    source_strategy=source_strategy,
                    target_stage=stage_u,
                    reason_code="DUPLICATE_TARGET_SLICE",
                    rationale=f"Active take-profit target already exists for slice {stage_u}.",
                )

        decision = TakeProfitDecision(
            accepted=True,
            decision_id=str(uuid4()),
            target_id=target_id,
            trade_id=normalized_trade_id,
            symbol=symbol_u,
            side=side_u,
            target_type=target_type.value,
            status=TakeProfitDecisionStatus.CREATED.value,
            target_price=float(target_price),
            target_quantity=requested_qty,
            live_position_quantity=live_qty,
            remaining_position_quantity=max(live_qty - requested_qty, 0),
            source_strategy=str(source_strategy or "UNKNOWN"),
            reason_code="TAKE_PROFIT_CREATED",
            rationale=rationale,
            lifecycle_event="TAKE_PROFIT_CREATED",
            target_stage=stage_u,
        )
        self._targets[target_id] = decision
        self._active_target_by_slice[slice_key] = target_id
        print(
            "[TAKE_PROFIT][DECISION] "
            f"trade_id={decision.trade_id} symbol={decision.symbol} target_id={target_id} "
            f"type={decision.target_type} qty={decision.target_quantity} price={decision.target_price}"
        )
        return decision

    def mark_submitted(self, *, target_id: str, broker_order_id: str) -> TakeProfitDecision:
        existing = self._require_target(target_id)
        updated = self._replace_decision(
            existing,
            status=TakeProfitDecisionStatus.SUBMITTED,
            broker_order_id=str(broker_order_id),
            reason_code="TAKE_PROFIT_SUBMITTED",
            lifecycle_event="TAKE_PROFIT_SUBMITTED",
            rationale=f"Take-profit target submitted to broker order_id={broker_order_id}.",
        )
        print(
            "[TAKE_PROFIT][SUBMIT] "
            f"trade_id={updated.trade_id} symbol={updated.symbol} target_id={updated.target_id} order_id={broker_order_id}"
        )
        return updated

    def mark_cancelled(self, *, target_id: str, reason: str) -> TakeProfitDecision:
        existing = self._require_target(target_id)
        updated = self._replace_decision(
            existing,
            status=TakeProfitDecisionStatus.CANCELLED,
            reason_code="TAKE_PROFIT_CANCELLED",
            lifecycle_event="TAKE_PROFIT_CANCELLED",
            rationale=reason,
        )
        self._active_target_by_slice.pop((updated.trade_id, updated.target_stage), None)
        print(f"[TAKE_PROFIT][CANCEL] trade_id={updated.trade_id} target_id={updated.target_id} reason={reason}")
        return updated

    def mark_rejected(self, *, target_id: str, reason: str) -> TakeProfitDecision:
        existing = self._require_target(target_id)
        updated = self._replace_decision(
            existing,
            status=TakeProfitDecisionStatus.REJECTED,
            reason_code="TAKE_PROFIT_REJECTED",
            lifecycle_event="TAKE_PROFIT_REJECTED",
            rationale=reason,
        )
        self._active_target_by_slice.pop((updated.trade_id, updated.target_stage), None)
        print(f"[TAKE_PROFIT][REJECT] trade_id={updated.trade_id} target_id={updated.target_id} reason={reason}")
        return updated

    def supersede_target(
        self,
        *,
        target_id: str,
        reason: str,
        replacement_price: float | None = None,
        replacement_quantity: int | None = None,
    ) -> TakeProfitDecision:
        existing = self._require_target(target_id)
        superseded = self._replace_decision(
            existing,
            status=TakeProfitDecisionStatus.SUPERSEDED,
            reason_code="TAKE_PROFIT_SUPERSEDED",
            lifecycle_event="TAKE_PROFIT_SUPERSEDED",
            rationale=reason,
        )
        self._active_target_by_slice.pop((superseded.trade_id, superseded.target_stage), None)
        print(f"[TAKE_PROFIT][SUPERSEDE] trade_id={superseded.trade_id} target_id={superseded.target_id} reason={reason}")
        if replacement_price is None and replacement_quantity is None:
            return superseded
        replacement = self.create_target(
            trade_id=superseded.trade_id,
            symbol=superseded.symbol,
            side=superseded.side,
            target_price=replacement_price if replacement_price is not None else float(superseded.target_price or 0.0),
            live_position_quantity=superseded.live_position_quantity,
            source_strategy=superseded.source_strategy,
            target_type=TakeProfitTargetType(superseded.target_type),
            target_stage=superseded.target_stage,
            quantity=replacement_quantity if replacement_quantity is not None else superseded.target_quantity,
            rationale=f"replacement target after supersession: {reason}",
        )
        return self._replace_decision(
            replacement,
            supersedes_target_id=str(superseded.target_id),
        )

    def record_fill(
        self,
        *,
        target_id: str,
        fill_quantity: int,
        live_position_quantity_before: int,
        broker_order_id: str | None = None,
        realized_pnl: float | None = None,
    ) -> TakeProfitFillResult:
        existing = self._require_target(target_id)
        qty = int(fill_quantity or 0)
        live_before = max(int(live_position_quantity_before or 0), 0)
        if qty <= 0:
            return TakeProfitFillResult(
                accepted=False,
                target_id=existing.target_id,
                trade_id=existing.trade_id,
                symbol=existing.symbol,
                status=existing.status,
                fill_quantity=qty,
                remaining_target_quantity=existing.target_quantity,
                remaining_position_quantity=live_before,
                reason_code="INVALID_FILL_QUANTITY",
                rationale="Take-profit fill quantity must be positive.",
                lifecycle_event="TAKE_PROFIT_REJECTED",
                broker_order_id=broker_order_id,
                realized_pnl=realized_pnl,
            )
        if qty > live_before:
            return TakeProfitFillResult(
                accepted=False,
                target_id=existing.target_id,
                trade_id=existing.trade_id,
                symbol=existing.symbol,
                status=existing.status,
                fill_quantity=qty,
                remaining_target_quantity=existing.target_quantity,
                remaining_position_quantity=live_before,
                reason_code="FILL_QTY_EXCEEDS_POSITION",
                rationale="Take-profit fill quantity exceeds live position quantity.",
                lifecycle_event="TAKE_PROFIT_REJECTED",
                broker_order_id=broker_order_id,
                realized_pnl=realized_pnl,
            )
        remaining_position = max(live_before - qty, 0)
        remaining_target = max(int(existing.target_quantity) - qty, 0)
        status = TakeProfitDecisionStatus.FILLED if remaining_position == 0 or remaining_target == 0 else TakeProfitDecisionStatus.PARTIALLY_FILLED
        event = "TAKE_PROFIT_FILLED" if status == TakeProfitDecisionStatus.FILLED and remaining_position == 0 else "TAKE_PROFIT_PARTIALLY_FILLED"
        self._replace_decision(
            existing,
            status=status,
            broker_order_id=broker_order_id or existing.broker_order_id,
            reason_code=event,
            lifecycle_event=event,
            rationale=f"Broker fill truth applied qty={qty} remaining_position={remaining_position}.",
        )
        if status == TakeProfitDecisionStatus.FILLED:
            self._active_target_by_slice.pop((existing.trade_id, existing.target_stage), None)
        print(
            f"[TAKE_PROFIT][{'FILL' if event == 'TAKE_PROFIT_FILLED' else 'PARTIAL'}] "
            f"trade_id={existing.trade_id} target_id={existing.target_id} qty={qty} remaining={remaining_position}"
        )
        return TakeProfitFillResult(
            accepted=True,
            target_id=existing.target_id,
            trade_id=existing.trade_id,
            symbol=existing.symbol,
            status=status.value,
            fill_quantity=qty,
            remaining_target_quantity=remaining_target,
            remaining_position_quantity=remaining_position,
            reason_code=event,
            rationale=f"Broker fill truth applied qty={qty}.",
            lifecycle_event=event,
            broker_order_id=broker_order_id or existing.broker_order_id,
            realized_pnl=realized_pnl,
        )

    def validate_target_order(
        self,
        *,
        requested_quantity: int,
        live_position_quantity: int,
        broker_position_degraded: bool = False,
        account_degraded: bool = False,
    ) -> dict[str, Any]:
        requested = int(requested_quantity or 0)
        live_qty = int(live_position_quantity or 0)
        if broker_position_degraded or account_degraded:
            return {"allowed": False, "reason_code": "TARGET_STATE_DEGRADED", "constrained_quantity": 0}
        if live_qty <= 0:
            return {"allowed": False, "reason_code": "NO_LIVE_POSITION", "constrained_quantity": 0}
        if requested <= 0:
            return {"allowed": False, "reason_code": "INVALID_TARGET_QUANTITY", "constrained_quantity": 0}
        if requested > live_qty:
            return {"allowed": False, "reason_code": "TARGET_QTY_EXCEEDS_POSITION", "constrained_quantity": live_qty}
        return {"allowed": True, "reason_code": "TARGET_RISK_ACCEPTED", "constrained_quantity": requested}

    def _rejected(
        self,
        *,
        trade_id: str,
        symbol: str,
        side: str,
        target_type: TakeProfitTargetType,
        live_position_quantity: int,
        source_strategy: str,
        target_stage: str,
        reason_code: str,
        rationale: str,
    ) -> TakeProfitDecision:
        decision = TakeProfitDecision(
            accepted=False,
            decision_id=str(uuid4()),
            target_id=None,
            trade_id=str(trade_id or ""),
            symbol=str(symbol or "").upper(),
            side=self._normalize_side(side),
            target_type=target_type.value,
            status=TakeProfitDecisionStatus.REJECTED.value,
            target_price=None,
            target_quantity=0,
            live_position_quantity=max(int(live_position_quantity or 0), 0),
            remaining_position_quantity=max(int(live_position_quantity or 0), 0),
            source_strategy=str(source_strategy or "UNKNOWN"),
            reason_code=reason_code,
            rationale=rationale,
            lifecycle_event="TAKE_PROFIT_REJECTED",
            target_stage=str(target_stage or "PRIMARY").upper(),
        )
        print(
            "[TAKE_PROFIT][REJECT] "
            f"trade_id={decision.trade_id or 'UNKNOWN'} symbol={decision.symbol or 'UNKNOWN'} "
            f"reason={reason_code}"
        )
        return decision

    def _require_target(self, target_id: str) -> TakeProfitDecision:
        existing = self._targets.get(str(target_id))
        if existing is None:
            raise KeyError(f"unknown take-profit target_id={target_id}")
        return existing

    def _replace_decision(self, decision: TakeProfitDecision, **updates: Any) -> TakeProfitDecision:
        payload = asdict(decision)
        for key, value in updates.items():
            if isinstance(value, Enum):
                payload[key] = value.value
            else:
                payload[key] = value
        updated = TakeProfitDecision(**payload)
        if updated.target_id:
            self._targets[updated.target_id] = updated
        return updated


__all__ = [
    "TakeProfitAuthority",
    "TakeProfitDecision",
    "TakeProfitDecisionStatus",
    "TakeProfitFillResult",
    "TakeProfitTargetType",
]
