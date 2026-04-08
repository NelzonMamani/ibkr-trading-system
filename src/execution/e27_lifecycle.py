"""E27 shared execution lifecycle contracts and helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4


class ExecutionPolicy(Protocol):
    def build_initial_stop(self, *, entry_price: float, side: str, context: dict[str, Any]) -> dict[str, Any]: ...

    def build_first_target(
        self,
        *,
        entry_price: float,
        stop_price: float,
        side: str,
        context: dict[str, Any],
    ) -> dict[str, Any]: ...

    def build_trailing_rule(self, *, side: str, context: dict[str, Any]) -> dict[str, Any]: ...

    def should_scale_in(self, *, green_volume_ratio: float, context: dict[str, Any]) -> bool: ...

    def should_pause_symbol(self, *, red_volume_ratio: float, retrace_ratio: float, context: dict[str, Any]) -> bool: ...

    def should_rearm_symbol(self, *, setup_ready: bool, momentum_restored: bool, context: dict[str, Any]) -> bool: ...

    def derive_level_context(self, *, symbol: str, context: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ExecutionPlan:
    symbol: str
    strategy_name: str
    setup_family: str
    entry_style: str
    side: str
    planned_quantity: int
    entry_order_spec: dict[str, Any]
    initial_stop_spec: dict[str, Any]
    first_target_spec: dict[str, Any]
    trailing_spec: dict[str, Any]
    scaling_spec: dict[str, Any]
    pause_spec: dict[str, Any]
    level_context: dict[str, Any]
    plan_id: str = field(default_factory=lambda: f"E27PLAN-{uuid4().hex[:12].upper()}")


@dataclass
class LifecycleRecord:
    symbol: str
    strategy_name: str
    parent_order_id: int | None
    stop_order_id: int | None
    target_order_id: int | None
    oca_group: str
    current_state: str
    pause_state: str
    filled_qty: int
    avg_fill_price: float | None
    realized_pnl: float
    unrealized_pnl: float
    last_trail_anchor: float | None
    last_major_level: str | None
    last_red_volume_ratio: float | None
    last_green_volume_ratio: float | None
    updated_at: str


@dataclass(frozen=True)
class RecoveryVerdict:
    symbol: str
    verdict: str
    reason: str
    repair_action: str
    broker_truth_snapshot: dict[str, Any]


class RossExecutionPolicy:
    """Ross consumer profile for E27 without embedding plumbing in strategy code."""

    red_weakness_threshold = 0.7
    red_exit_threshold = 1.0
    red_hard_exit_threshold = 1.5
    green_strong_threshold = 1.2
    green_scale_threshold = 1.5
    green_extreme_threshold = 2.0
    retrace_hard_exit_threshold = 0.5
    breakeven_at_r = 1.0
    partial_take_pct = 0.5
    max_adds = 2

    def build_initial_stop(self, *, entry_price: float, side: str, context: dict[str, Any]) -> dict[str, Any]:
        stop_hint = context.get("stop_price")
        if stop_hint is not None:
            return {"model": "STRUCTURE_PULLBACK_LOW", "price": float(stop_hint), "buffer_ticks": "1-2"}
        risk_buffer = float(context.get("stop_buffer_fraction", 0.02))
        if side.upper() == "BUY":
            return {"model": "STRUCTURE_PULLBACK_LOW", "price": float(entry_price) * (1.0 - risk_buffer), "buffer_ticks": "1-2"}
        return {"model": "STRUCTURE_PULLBACK_HIGH", "price": float(entry_price) * (1.0 + risk_buffer), "buffer_ticks": "1-2"}

    def build_first_target(self, *, entry_price: float, stop_price: float, side: str, context: dict[str, Any]) -> dict[str, Any]:
        risk_per_share = abs(float(entry_price) - float(stop_price))
        two_r = float(entry_price) + (2.0 * risk_per_share if side.upper() == "BUY" else -2.0 * risk_per_share)
        level_candidates = [context.get("next_half_dollar"), context.get("next_whole_dollar"), context.get("hod"), context.get("breakout_level")]
        level_values = [float(v) for v in level_candidates if v is not None]
        level_target = min(level_values, key=lambda value: abs(value - float(entry_price))) if level_values else None
        target_price = level_target if level_target is not None else two_r
        return {"model": "LEVEL_FIRST_HOD_2R", "price": float(target_price), "fallback_2r": float(two_r), "partial_take_pct": self.partial_take_pct}

    def build_trailing_rule(self, *, side: str, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "model": "STRUCTURE_HIGHER_LOW" if side.upper() == "BUY" else "STRUCTURE_LOWER_HIGH",
            "trail_buffer_ticks": "1-2",
            "tighten_near_major_level": True,
            "loosen_on_strong_green": True,
            "move_to_breakeven_at_r": self.breakeven_at_r,
        }

    def should_scale_in(self, *, green_volume_ratio: float, context: dict[str, Any]) -> bool:
        return float(green_volume_ratio) >= self.green_scale_threshold and bool(context.get("room_to_level", True))

    def should_pause_symbol(self, *, red_volume_ratio: float, retrace_ratio: float, context: dict[str, Any]) -> bool:
        if float(retrace_ratio) > self.retrace_hard_exit_threshold:
            return True
        if float(red_volume_ratio) >= self.red_hard_exit_threshold:
            return True
        return bool(context.get("level_rejection", False))

    def should_rearm_symbol(self, *, setup_ready: bool, momentum_restored: bool, context: dict[str, Any]) -> bool:
        return bool(setup_ready and momentum_restored)

    def derive_level_context(self, *, symbol: str, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "whole_dollar_enabled": True,
            "half_dollar_enabled": True,
            "hod_enabled": True,
            "premarket_high_enabled": True,
            "breakout_level_enabled": True,
            "next_half_dollar": context.get("next_half_dollar"),
            "next_whole_dollar": context.get("next_whole_dollar"),
            "hod": context.get("hod"),
            "premarket_high": context.get("premarket_high"),
            "breakout_level": context.get("breakout_level"),
        }


class ExecutionPlanBuilder:
    def build_from_risk_decision(self, *, decision: Any, policy: ExecutionPolicy) -> ExecutionPlan:
        symbol = str(getattr(decision, "symbol", "") or "").upper()
        side = "BUY" if str(getattr(decision, "side", "LONG")).upper() in {"LONG", "BUY"} else "SELL"
        entry_price = float(getattr(decision, "entry_price", 0.0) or 0.0)
        if entry_price <= 0:
            raise ValueError("entry_price_missing")
        planned_qty = max(1, int(float(getattr(decision, "approved_quantity", 0) or 0)))
        context = {
            "stop_price": getattr(decision, "stop_loss_price", None),
            "setup_family": str(getattr(decision, "setup_family", "") or "UNKNOWN"),
            "strategy_name": str(getattr(decision, "strategy_name", "") or "ROSS_MOMENTUM"),
        }
        level_context = policy.derive_level_context(symbol=symbol, context=context)
        stop_spec = policy.build_initial_stop(entry_price=entry_price, side=side, context=context)
        stop_price = float(stop_spec["price"])
        target_spec = policy.build_first_target(entry_price=entry_price, stop_price=stop_price, side=side, context=level_context)
        trail_spec = policy.build_trailing_rule(side=side, context=level_context)
        if not stop_spec or not target_spec:
            raise ValueError("no_naked_entry_violation")
        return ExecutionPlan(
            symbol=symbol,
            strategy_name=context["strategy_name"],
            setup_family=context["setup_family"],
            entry_style="MARKETABLE_BREAKOUT",
            side=side,
            planned_quantity=planned_qty,
            entry_order_spec={"order_type": "MKT", "tif": "DAY", "outside_rth": True},
            initial_stop_spec=stop_spec,
            first_target_spec=target_spec,
            trailing_spec=trail_spec,
            scaling_spec={"max_adds": RossExecutionPolicy.max_adds, "require_green_for_add": True, "block_add_into_major_level": True},
            pause_spec={"pause_on_red_hard_exit": True, "pause_on_retrace_hard_fail": True, "resume_requires_new_structure": True},
            level_context=level_context,
        )


class LifecycleCoordinator:
    def map_status_to_e27_state(self, *, status: str, filled_qty: int, remaining_qty: int) -> str:
        normalized = str(status or "").upper()
        if normalized in {"CANCELLED", "CANCELED", "API_CANCELLED"}:
            return "EXIT_FILLED"
        if normalized in {"INACTIVE", "REJECTED"}:
            return "RECONCILED"
        if normalized == "EXPIRED":
            return "RECONCILED"
        if filled_qty > 0 and remaining_qty > 0:
            return "ENTRY_PARTIALLY_FILLED"
        if filled_qty > 0 and remaining_qty <= 0:
            return "ENTRY_FILLED"
        if normalized == "PRESUBMITTED":
            return "ENTRY_ACKNOWLEDGED_QUEUED_FOR_OPEN"
        if normalized == "SUBMITTED":
            return "ENTRY_WORKING"
        return "ENTRY_SUBMITTING"


class RecoveryEngine:
    def evaluate_broker_truth(
        self,
        *,
        open_orders: list[Any],
        positions: list[Any],
        tracked_order_symbols: set[str],
        tracked_position_symbols: set[str],
    ) -> list[RecoveryVerdict]:
        verdicts: list[RecoveryVerdict] = []
        broker_open_order_symbols = {str(getattr(row, "symbol", "") or getattr(getattr(row, "contract", None), "symbol", "") or "").upper() for row in open_orders}
        broker_position_symbols = {str(getattr(row, "symbol", "") or "").upper() for row in positions}

        for symbol in sorted(broker_position_symbols - tracked_position_symbols):
            verdicts.append(
                RecoveryVerdict(
                    symbol=symbol,
                    verdict="orphan_position",
                    reason="broker_position_without_local_lifecycle_record",
                    repair_action="rebuild_local_state_or_attach_protection",
                    broker_truth_snapshot={"position_seen": True},
                )
            )
        for symbol in sorted(broker_open_order_symbols - tracked_order_symbols):
            verdicts.append(
                RecoveryVerdict(
                    symbol=symbol,
                    verdict="orphan_order",
                    reason="broker_open_order_without_local_lifecycle_record",
                    repair_action="rebuild_local_state",
                    broker_truth_snapshot={"open_order_seen": True},
                )
            )
        if not verdicts:
            verdicts.append(
                RecoveryVerdict(
                    symbol="*",
                    verdict="healthy",
                    reason="broker_truth_aligned",
                    repair_action="none",
                    broker_truth_snapshot={"open_orders": len(open_orders), "positions": len(positions)},
                )
            )
        return verdicts
