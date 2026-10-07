from __future__ import annotations

import os
import math
import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Callable

from src.core.take_profit_authority import TakeProfitAuthority
from src.core.trailing_stop_authority import TrailingStopAuthority, TrailingStopDecisionStatus
from src.strategies.ross_momentum.exit_intelligence import ExitDecision, RossExitIntelligence


@dataclass
class PositionState:
    symbol: str
    entry_price: float
    quantity: int
    entry_timestamp: datetime
    highest_price_seen: float
    lowest_price_seen: float
    current_price: float
    unrealized_pnl: float
    holding_time_seconds: int
    strategy_name: str
    setup_family: str
    entry_reason: str
    stop_loss_price: float
    break_even_price: float
    last_trail_price: float
    first_target_price: float | None
    second_target_price: float | None
    target_type: str
    exit_stage: str = "NONE"  # NONE / PARTIAL / FINAL
    reference_order_id: str | None = None
    partial_taken: bool = False
    trailing_active: bool = False
    target_model: str | None = None
    relationship_id: str | None = None


@dataclass
class BullFlagMicroPlan:
    """Durable facts for the approved relationship, owned by the fill manager."""
    relationship_id: str
    symbol: str
    security_id: str
    parent_id: str
    initial_order_id: str
    original_stop: float
    entry_quantity: int = 0
    entry_notional: float = 0.0
    entry_terminal: bool = False
    reconciled: bool = False
    e0: float | None = None
    r0: float | None = None
    milestone_price: float | None = None
    milestone_quantity: int | None = None
    milestone_filled: int = 0
    milestone_order_id: str | None = None
    milestone_consumed: bool = False
    protection_trade_id: str | None = None
    protection_broker_order_id: str | None = None
    pending_stop_cancel: str | None = None
    add_count: int = 0
    consumed_children: list[str] = field(default_factory=list)
    orders: dict = field(default_factory=dict)
    paused: bool = False

    def freeze(self) -> None:
        if self.e0 is not None or not self.entry_terminal or not self.reconciled or self.entry_quantity <= 0:
            return
        entry = self.entry_notional / self.entry_quantity
        risk = entry - self.original_stop
        if not math.isfinite(risk) or risk <= 0:
            self.paused = True
            return
        self.e0, self.r0 = entry, risk
        self.milestone_price = entry + 2 * risk


@dataclass(frozen=True)
class TradeIntent:
    symbol: str
    direction: str
    quantity: int
    strategy_name: str
    rationale: str
    reference_order_id: str | None
    exit_type: str | None = None
    action: str = "EXIT"
    reason: str = ""
    relationship_id: str | None = None
    management_action_id: str | None = None

    def __post_init__(self) -> None:
        if self.action != "EXIT" and self.direction.upper() == "SELL":
            object.__setattr__(self, "action", "EXIT")
        if not self.reason:
            object.__setattr__(self, "reason", self.rationale)


class TradeManagementEngine:
    """Deterministic post-fill position management using broker-truth fills."""

    def __init__(
        self,
        price_lookup: Callable[[str], float] | None = None,
        exit_intelligence: RossExitIntelligence | None = None,
        *,
        quick_profit_threshold: float = 0.15,
        max_hold_time_seconds: int = 120,
        trail_buffer: float = 0.01,
        fast_failure_seconds: int = 20,
        fast_failure_min_progress: float = 0.01,
        stall_candles_without_high: int = 3,
        stall_rejections_threshold: int = 2,
        stop_update_callback: Callable | None = None,
        cancel_order_callback: Callable | None = None,
        persistence_adapter=None,
        state_namespace: str = "SIM",
    ) -> None:
        self._persistence = persistence_adapter
        self._state_namespace = "ross-bull-micro:" + state_namespace
        self._relationship_plans: dict[str, BullFlagMicroPlan] = {}
        self._parents: dict[str, dict] = {}
        self._stop_update_callback = stop_update_callback
        self._cancel_order_callback = cancel_order_callback
        self._positions: dict[str, PositionState] = {}
        self._seen_exec_ids: set[str] = set()
        self._pending_exit: set[str] = set()
        self._price_lookup = price_lookup
        self._quick_profit_threshold = float(quick_profit_threshold)
        self._max_hold_time_seconds = int(max_hold_time_seconds)
        self._trail_buffer = float(trail_buffer)
        self._fast_failure_seconds = int(fast_failure_seconds)
        self._fast_failure_min_progress = float(fast_failure_min_progress)
        self._stall_candles_without_high = int(stall_candles_without_high)
        self._stall_rejections_threshold = int(stall_rejections_threshold)
        self.trailing_stop_authority = TrailingStopAuthority()
        self._exit_intelligence_enabled = os.getenv("TRADE_MGMT_EXIT_INTELLIGENCE_ENABLED", "1").lower() in {"1", "true", "yes", "on"}
        self._exit_intelligence = exit_intelligence or RossExitIntelligence(
            max_hold_time_seconds=self._max_hold_time_seconds,
            fast_failure_seconds=self._fast_failure_seconds,
            fast_failure_min_progress=self._fast_failure_min_progress,
            stall_candles_without_high=self._stall_candles_without_high,
            stall_rejections_threshold=self._stall_rejections_threshold,
        )

    def _save_relationship_state(self) -> None:
        if self._persistence is None:
            return
        if not getattr(self._persistence, "enabled", True) or getattr(self._persistence, "backend", "sqlite") != "sqlite":
            raise RuntimeError("relationship_persistence_disabled")
        payload = {
            "version": 1, "parents": self._parents,
            "plans": {key: asdict(value) for key, value in self._relationship_plans.items()},
            "positions": {key: asdict(value) for key, value in self._positions.items() if value.relationship_id},
            "seen_exec_ids": sorted(self._seen_exec_ids),
            "pending_exit": sorted(self._pending_exit),
        }
        self._persistence.store_management_state(self._state_namespace, payload)

    def restore_relationship_state(self) -> None:
        if self._persistence is None:
            return
        payload = self._persistence.fetch_management_state(self._state_namespace)
        if payload is None:
            return
        if payload.get("version") != 1:
            raise ValueError("unsupported_relationship_state")
        self._parents = payload["parents"]
        self._relationship_plans = {key: BullFlagMicroPlan(**value) for key, value in payload["plans"].items()}
        for plan in self._relationship_plans.values():
            plan.reconciled = False  # persistence is not current broker truth
        for key, value in payload["positions"].items():
            value["entry_timestamp"] = datetime.fromisoformat(value["entry_timestamp"])
            self._positions[key] = PositionState(**value)
        self._seen_exec_ids.update(payload["seen_exec_ids"])
        self._pending_exit.update(payload["pending_exit"])

    def compose_bull_flag(self, pattern, inputs, *, security_id: str, now: datetime):
        """Ross composition; detectors remain pure and standalone calls unchanged."""
        from dataclasses import replace
        from src.setup_engine.setup_families.micro_pullback import MicroPullbackPattern
        from src.strategies.ross_momentum.patterns.setup_fidelity import blocking_input_reason
        from src.strategies.ross_momentum.strategy_policy import BULL_FLAG_MICRO_MANAGEMENT_PROFILE
        if not security_id:
            return pattern._rejected("relationship_security_unavailable", inputs)
        from src.core.engines.execution_mode_engine import ExecutionModeEngine
        block = ExecutionModeEngine().ross_exposure_block_reason(session_label=inputs.session_label,
            rvol=inputs.liquidity_context.rvol, spread=inputs.liquidity_context.spread)
        if block:
            return pattern._rejected(block, inputs)
        session = str(inputs.session_label or "").upper()
        key = f"RossMomentumStrategyV1:{security_id}"
        primary = inputs.primary_timeframe
        refinement = inputs.execution_refinement_timeframe
        seconds = {"10s": 10, "1m": 60, "3m": 180, "5m": 300}
        def closed(candles, timeframe):
            width = seconds.get(timeframe)
            return bool(width and candles and all(isinstance(c.timestamp, datetime) and c.timestamp.tzinfo
                and c.timestamp.timestamp() + width <= now.timestamp() for c in candles))
        # Runtime streams can contain an in-progress bar. Only actual closed bars
        # participate; no synthetic close or timeframe substitution is permitted.
        def closed_stream(candles, timeframe):
            width = seconds.get(timeframe)
            if not width or any(not isinstance(c.timestamp, datetime) or not c.timestamp.tzinfo for c in candles):
                return []
            return [c for c in candles if c.timestamp.timestamp() + width <= now.timestamp()]
        streams = {tf: closed_stream(list(rows), tf) for tf, rows in inputs.timeframe_candles.items()}
        inputs = replace(inputs, candles=closed_stream(inputs.candles, primary), timeframe_candles=streams)
        parent = self._parents.get(key)
        if (session not in {"PRE", "RTH_OPEN", "RTH_MID", "RTH_LATE"}
                or inputs.timeframe_provenance.get(primary) != "PRESENT"
                or not closed(inputs.candles, primary)):
            return pattern._rejected("parent_input_unavailable", inputs)
        formation = pattern.evaluate_formation(inputs)
        if parent:
            timestamps = {c.timestamp.isoformat() for c in inputs.candles}
            if (parent["symbol"] != inputs.symbol or parent["origin_timestamp"] not in timestamps or parent["session"] != session
                    or min((c.low for c in inputs.candles if c.timestamp.isoformat() >= parent["completed_timestamp"]), default=float("inf")) < parent["invalidation"]):
                parent["state"] = "INVALIDATED"
                self._save_relationship_state()
            if parent["state"] != "ARMED":
                if formation.detected and formation.setup_metadata["origin_timestamp"].isoformat() > parent["completed_timestamp"]:
                    parent = None
                else:
                    return pattern._rejected("parent_invalidated_or_expired", inputs)
        if parent is None and formation.detected:
            metadata = formation.setup_metadata
            origin = metadata["origin_timestamp"].isoformat()
            parent_id = hashlib.sha256(f"{key}:{session}:{primary}:{origin}".encode()).hexdigest()[:24]
            parent = {"parent_id": parent_id, "security_id": security_id, "symbol": inputs.symbol,
                "session": session, "origin_timestamp": origin,
                "completed_timestamp": metadata["structure_completed_timestamp"].isoformat(),
                "structure_timeframe": primary, "invalidation": formation.invalidation_level,
                "flag_high": formation.trigger_level, "state": "ARMED", "consumed_children": []}
            self._parents[key] = parent
            self._save_relationship_state()
        if parent is None:
            return pattern._rejected("relationship_parent_unavailable", inputs)
        if (inputs.timeframe_provenance.get(refinement) != "PRESENT"
                or not closed(streams.get(refinement), refinement)
                or blocking_input_reason(inputs, "P_MICRO_PULLBACK")
                or blocking_input_reason(inputs, "P_BULL_FLAG")):
            return pattern._rejected("child_input_unavailable", inputs)
        child_candles = streams[refinement]
        child = MicroPullbackPattern().evaluate(replace(inputs, candles=child_candles, timeframe=refinement))
        if not child.detected:
            return pattern._rejected("parent_armed_no_eligible_child", inputs)
        parent_end = datetime.fromisoformat(parent["completed_timestamp"]).timestamp() + seconds[primary]
        if child_candles[-1].timestamp.timestamp() < parent_end:
            return pattern._rejected("child_predates_closed_parent", inputs)
        child_id = hashlib.sha256(f"{parent['parent_id']}:{refinement}:{child_candles[-1].timestamp.isoformat()}".encode()).hexdigest()[:24]
        if child_id in parent["consumed_children"]:
            return pattern._rejected("child_already_consumed", inputs)
        if child.stop_level < parent["invalidation"]:
            return pattern._rejected("child_below_parent_invalidation", inputs)
        context = {"profile": BULL_FLAG_MICRO_MANAGEMENT_PROFILE,
            "parent_id": parent["parent_id"], "child_id": child_id, "security_id": security_id,
            "parent_invalidation": parent["invalidation"], "parent_origin": parent["origin_timestamp"],
            "parent_completed": parent["completed_timestamp"], "structure_timeframe": primary,
            "child_timeframe": refinement, "child_timestamp": child_candles[-1].timestamp.isoformat()}
        return replace(child, setup_id=pattern.pattern_id, setup_family_id="BULL_FLAG", pattern_name=pattern.name,
            target_suggestion=BULL_FLAG_MICRO_MANAGEMENT_PROFILE,
            rationale_text="Armed Bull Flag with confirmed same-security Micro Pullback. " + child.rationale_text,
            setup_metadata={**child.setup_metadata, "relationship": context})

    def prepare_relationship_intent(self, intent, context: dict) -> bool:
        parent = next((p for p in self._parents.values() if p["parent_id"] == context["parent_id"]), None)
        if parent is None or parent["state"] != "ARMED" or context.get("warning") or context["child_id"] in parent["consumed_children"]:
            return False
        position = self._positions.get(intent.symbol)
        action = "ENTRY"
        relationship_id = context["parent_id"] + ":" + context["child_id"]
        if position:
            if not position.relationship_id:
                return False
            plan = self._relationship_plans[position.relationship_id]
            if plan.parent_id != context["parent_id"] or plan.security_id != context["security_id"]:
                return False
            quantity = self.relationship_add_quantity(position.relationship_id, price=float(intent.entry_price),
                warning=False, parent_valid=True, child_id=context["child_id"])
            if quantity <= 0:
                return False
            action, relationship_id = "ADD", position.relationship_id
            intent.quantity = quantity
            intent.requested_quantity = quantity
        elif parent["consumed_children"]:
            prior = [p for p in self._relationship_plans.values() if p.security_id == context["security_id"]]
            if any(not p.reconciled or p.paused or any(not o["terminal"] for o in p.orders.values()) for p in prior):
                return False
            action = "REENTRY"
        # Prevent same-event intents across cycles, including rejected attempts.
        parent["consumed_children"].append(context["child_id"])
        intent.relationship_context = {**context, "relationship_id": relationship_id, "action": action}
        self._save_relationship_state()
        return True

    def is_relationship_add(self, intent) -> bool:
        context = getattr(intent, "relationship_context", None) or {}
        plan = self._relationship_plans.get(context.get("relationship_id"))
        position = self._positions.get(intent.symbol)
        return bool(context.get("profile") == "BULL_FLAG_MICRO_2R_V1" and context.get("action") == "ADD"
            and plan and position and position.quantity > 0 and position.relationship_id == plan.relationship_id
            and (plan.symbol, plan.security_id, plan.parent_id) == (intent.symbol, context.get("security_id"), context.get("parent_id")))

    def risk_quantity(self, intent, *, quantity_cap: int, value_cap: float,
                      risk_cap: float | None = None, max_adds: int | None = None,
                      incremental_value_cap: float | None = None) -> int:
        context = intent.relationship_context
        if context.get("profile") != "BULL_FLAG_MICRO_2R_V1" or context.get("warning"):
            return 0
        price = float(intent.entry_price)
        if not math.isfinite(price) or price <= 0:
            return 0
        position = self._positions.get(intent.symbol)
        confirmed = position.quantity if position else 0
        pending = sum(max(0, o["requested"] - o["filled"])
            for p in self._relationship_plans.values() if p.symbol == intent.symbol
            for o in p.orders.values() if not o["terminal"] and o["action"] in {"ENTRY", "REENTRY", "ADD"})
        if pending:
            return 0
        requested = int(getattr(intent, "quantity", 1) or 0)
        if context["action"] == "ADD":
            if not self.is_relationship_add(intent):
                return 0
            if max_adds is not None and self._relationship_plans[context["relationship_id"]].add_count >= max_adds:
                return 0
            requested = min(requested, self.relationship_add_quantity(context["relationship_id"],
                price=price, warning=False, parent_valid=True, child_id=context["child_id"]))
        elif confirmed:
            return 0
        if incremental_value_cap is not None:
            requested = min(requested, max(0, int(incremental_value_cap // price)))
        if risk_cap is not None:
            stop = float(position.stop_loss_price if position else intent.stop_loss_price)
            if not math.isfinite(stop) or stop <= 0:
                return 0
            existing_risk = max(0.0, position.entry_price - stop) * confirmed if position else 0.0
            incremental_risk = max(0.0, price - stop)
            if risk_cap < existing_risk or incremental_risk <= 0:
                return 0
            requested = min(requested, int((risk_cap - existing_risk) // incremental_risk))
        return max(0, min(requested, quantity_cap - confirmed - pending,
                          int(value_cap // price) - confirmed - pending))

    def register_relationship_order(self, *, relationship_id: str, symbol: str, security_id: str,
                                    parent_id: str, child_id: str, order_id: str, quantity: int,
                                    stop: float, action: str = "ENTRY") -> bool:
        from src.strategies.ross_momentum.strategy_policy import POLICY_V2
        if quantity <= 0 or not all((relationship_id, security_id, parent_id, child_id, order_id)):
            return False
        plan = self._relationship_plans.get(relationship_id)
        if plan is None:
            if action not in {"ENTRY", "REENTRY"} or not math.isfinite(stop) or stop <= 0:
                return False
            plan = BullFlagMicroPlan(relationship_id, symbol, security_id, parent_id, order_id, stop)
            self._relationship_plans[relationship_id] = plan
        if (plan.symbol, plan.security_id, plan.parent_id) != (symbol, security_id, parent_id):
            return False
        if child_id in plan.consumed_children or order_id in plan.orders:
            return False
        if action == "ADD":
            if not plan.reconciled or plan.paused or plan.e0 is None or plan.add_count >= POLICY_V2.position_management.max_adds_per_position:
                return False
            plan.add_count += 1  # logical action, not each partial fill
        plan.consumed_children.append(child_id)
        plan.orders[order_id] = {"action": action, "requested": quantity, "filled": 0, "notional": 0.0, "terminal": False}
        self._save_relationship_state()  # reservation durable before dispatch
        return True

    def bind_recovered_protection(self, lifecycle) -> None:
        if not self._relationship_plans:
            return
        for plan in self._relationship_plans.values():
            position = self._positions.get(plan.symbol)
            if position is None or position.relationship_id != plan.relationship_id:
                continue
            matches = [trade for trade in lifecycle._trades.values()
                       if trade.symbol == plan.symbol and trade.filled_qty == position.quantity
                       and trade.stop is not None and trade.stop.quantity == position.quantity
                       and plan.protection_broker_order_id
                       and str(trade.stop.broker_order_id) == plan.protection_broker_order_id
                       and trade.stop.trigger_price >= plan.original_stop and trade.target is None]
            if len(matches) != 1:
                plan.paused = True
                continue
            trade = matches[0]
            trade.strategy_id = position.strategy_name
            trade.preserve_selected_protection = True
            trade.selected_stop_price = plan.original_stop
            trade.target_model = "BULL_FLAG_MICRO_2R_V1"
            plan.protection_trade_id = trade.trade_id
            position.reference_order_id = trade.trade_id
        self._save_relationship_state()

    def reconcile_broker_snapshot(self, *, positions: dict, open_orders: list,
                                  complete: bool, as_of: datetime, orders_as_of: datetime | None = None) -> None:
        """Consume an existing coherent broker snapshot; never perform broker I/O."""
        def read(item, key, default=None):
            return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)
        for plan in self._relationship_plans.values():
            observed = {}
            unknown = False
            for order in open_orders:
                if str(read(order, "symbol", "")).upper() != plan.symbol:
                    continue
                if str(read(order, "order_type", "")).upper() in {"STP", "STOP", "STOP_LIMIT"}:
                    continue
                metadata = read(order, "metadata", {}) or {}
                identity = str(metadata.get("client_order_id") or metadata.get("order_ref") or read(order, "order_id", ""))
                remaining = metadata.get("remaining_quantity", metadata.get("remaining"))
                if identity not in plan.orders or remaining is None:
                    unknown = True
                    continue
                observed[identity] = int(remaining)
            broker = positions.get(plan.symbol)
            quantity = int(read(broker, "quantity", 0)) if broker is not None else 0
            con_id = read(broker, "con_id") if broker is not None else None
            same_security = broker is None or (type(con_id) is int and con_id > 0 and plan.security_id == f"conId:{con_id}")
            position = self._positions.get(plan.symbol)
            local_qty = position.quantity if position and position.relationship_id == plan.relationship_id else 0
            if complete and not unknown and same_security and quantity == local_qty:
                for order_id, order in plan.orders.items():
                    uncertain_at = order.get("submission_uncertain_at")
                    if uncertain_at and not order["terminal"] and order_id not in observed and orders_as_of is not None:
                        failed_at = datetime.fromisoformat(uncertain_at)
                        if as_of >= failed_at and orders_as_of >= failed_at:
                            order.update(terminal=True, status="RECONCILED_ABSENT", release_reservation=True)
                            self._pending_exit.discard(plan.symbol)
            self.reconcile_relationship(plan.relationship_id, confirmed_quantity=quantity,
                pending_orders=observed, complete=complete and not unknown and same_security)

    def reconcile_relationship(self, relationship_id: str, *, confirmed_quantity: int,
                               pending_orders: dict[str, int], complete: bool) -> bool:
        plan = self._relationship_plans[relationship_id]
        position = self._positions.get(plan.symbol)
        local_qty = position.quantity if position and position.relationship_id == relationship_id else 0
        expected_pending = {key: max(0, order["requested"] - order["filled"])
                            for key, order in plan.orders.items() if not order["terminal"]}
        plan.reconciled = bool(complete and confirmed_quantity == local_qty and expected_pending == pending_orders)
        plan.freeze()
        self._save_relationship_state()
        return plan.reconciled

    def on_relationship_order_update(self, *, relationship_id: str, order_id: str,
                                     cumulative_quantity: int, average_price: float | None,
                                     terminal: bool, status: str) -> None:
        plan = self._relationship_plans[relationship_id]
        order = plan.orders[order_id]
        total = int(cumulative_quantity)
        if order["terminal"] and not terminal and 0 <= total <= order["filled"]:
            return  # late nonterminal snapshots cannot reopen confirmed terminal truth
        if total < order["filled"] or total > order["requested"]:
            plan.paused = True
            self._save_relationship_state()
            return
        delta = total - order["filled"]
        if order["terminal"] and not terminal:
            terminal = True  # late fill facts still count; terminal state is monotonic
            status = order.get("status", status)
        if delta:
            if average_price is None or not math.isfinite(average_price) or average_price <= 0:
                plan.paused = True
                self._save_relationship_state()
                return
            notional = total * float(average_price)
            delta_price = (notional - order["notional"]) / delta
            if not math.isfinite(delta_price) or delta_price <= 0:
                plan.paused = True
                self._save_relationship_state()
                return
            reduction = order["action"] in {"REDUCE", "EXIT"}
            position = self.on_exec_details(symbol=plan.symbol, shares=-delta if reduction else delta,
                price=delta_price, exec_id=f"{relationship_id}:{order_id}:{total}",
                strategy_name="RossMomentumStrategyV1", setup_family="BULL_FLAG",
                stop_loss_price=plan.original_stop, reference_order_id=plan.initial_order_id,
                target_model="BULL_FLAG_MICRO_2R_V1")
            if position is not None:
                position.relationship_id = relationship_id
                position.reference_order_id = plan.protection_trade_id or plan.initial_order_id
                position.first_target_price = None  # only the frozen milestone owns profit-taking
                position.second_target_price = None
            order["filled"], order["notional"] = total, notional
            if order_id == plan.initial_order_id:
                plan.entry_quantity, plan.entry_notional = total, notional
            if order["action"] == "REDUCE":
                plan.milestone_filled += delta
                plan.milestone_consumed = plan.milestone_filled >= int(plan.milestone_quantity or 0)
        order["terminal"] = bool(terminal)
        order["status"] = status
        if order_id == plan.initial_order_id:
            plan.entry_terminal = bool(terminal)
        if terminal:
            self._pending_exit.discard(plan.symbol)
        elif order["action"] in {"REDUCE", "EXIT"}:
            self._pending_exit.add(plan.symbol)
        # Every changed order requires fresh reconciliation before exposure or milestone.
        plan.reconciled = False
        self._save_relationship_state()
        self.cancel_excess_milestone_orders(plan)

    def cancel_excess_milestone_orders(self, plan: BullFlagMicroPlan) -> None:
        """Cancel oversized retries after late fills; never presume cancellation filled."""
        if plan.milestone_quantity is None:
            return
        allowance = max(0, plan.milestone_quantity - plan.milestone_filled)
        for order in plan.orders.values():
            if order["action"] != "REDUCE" or order["terminal"]:
                continue
            remaining = max(0, order["requested"] - order["filled"])
            if remaining <= allowance:
                allowance -= remaining
                continue
            if not order.get("request") and not order.get("broker_order_id"):
                order.update(terminal=True, status="SUPERSEDED_BEFORE_DISPATCH")
            elif order.get("broker_order_id") and not order.get("cancel_requested") and self._cancel_order_callback:
                order["cancel_requested"] = True
                self._save_relationship_state()
                try:
                    self._cancel_order_callback(broker_order_id=order["broker_order_id"])
                except Exception as exc:
                    order["cancel_requested"] = False
                    order["cancel_error"] = type(exc).__name__
            self._save_relationship_state()

    def relationship_add_quantity(self, relationship_id: str, *, price: float,
                                  warning: bool, parent_valid: bool, child_id: str) -> int:
        from src.strategies.ross_momentum.strategy_policy import POLICY_V2
        plan = self._relationship_plans[relationship_id]
        position = self._positions.get(plan.symbol)
        if (position is None or not plan.reconciled or plan.paused or plan.e0 is None or warning
                or not parent_valid or child_id in plan.consumed_children
                or plan.add_count >= POLICY_V2.position_management.max_adds_per_position
                or any(not order["terminal"] for order in plan.orders.values())
                or not math.isfinite(price) or price <= position.entry_price):
            return 0
        return position.quantity // 4  # zero is deliberately not promoted to one

    def _relationship_milestone(self, position: PositionState) -> TradeIntent | None:
        plan = self._relationship_plans[position.relationship_id]
        if not plan.reconciled or plan.paused or plan.milestone_price is None or plan.milestone_consumed:
            return None
        if any(not order["terminal"] for order in plan.orders.values()):
            return None
        if position.current_price < plan.milestone_price:
            return None
        if plan.milestone_quantity is None:
            plan.milestone_quantity = 1 if position.quantity == 1 else position.quantity // 2
        remaining = min(position.quantity, plan.milestone_quantity - plan.milestone_filled)
        if remaining <= 0:
            plan.milestone_consumed = True
            self._save_relationship_state()
            return None
        # A cancelled partial may resume only its unfilled balance, after reconciliation.
        attempt = sum(order["action"] == "REDUCE" for order in plan.orders.values())
        action_id = f"{plan.relationship_id}:2R:{attempt}"
        plan.milestone_order_id = action_id
        plan.orders[action_id] = {"action": "REDUCE", "requested": remaining, "filled": 0, "notional": 0.0, "terminal": False}
        self._pending_exit.add(position.symbol)
        self._save_relationship_state()
        return TradeIntent(symbol=position.symbol, direction="SELL", quantity=remaining,
            strategy_name=position.strategy_name, rationale="BULL_FLAG_MICRO_2R",
            reference_order_id=position.reference_order_id, exit_type="TARGET",
            relationship_id=plan.relationship_id, management_action_id=action_id)

    def on_exec_details(
        self, *, symbol: str, shares: int, price: float, exec_id: str | None,
        strategy_name: str | None = None, setup_family: str | None = None,
        stop_loss_price: float | None = None, take_profit_price: float | None = None,
        reference_order_id: str | None = None,
        target_model: str | None = None,
    ) -> PositionState | None:
        normalized = str(symbol or "").upper()
        if not normalized or shares == 0 or price <= 0:
            return None
        if exec_id and exec_id in self._seen_exec_ids:
            return self._positions.get(normalized)
        if exec_id:
            self._seen_exec_ids.add(exec_id)

        position = self._positions.get(normalized)
        if position is None and shares > 0:
            now = datetime.now(timezone.utc)
            first_target, second_target, target_type = self._calculate_profit_targets(float(price))
            selected_stop = float(price) - self._trail_buffer
            if stop_loss_price is not None and "ROSS" in str(strategy_name or "").upper():
                selected_stop = float(stop_loss_price)
                first_target = take_profit_price
                second_target = None
                target_type = "SELECTED_PRICE" if take_profit_price is not None else "DESCRIPTIVE_ONLY"

            position = PositionState(
                symbol=normalized,
                entry_price=float(price),
                quantity=int(shares),
                entry_timestamp=now,
                highest_price_seen=float(price),
                lowest_price_seen=float(price),
                current_price=float(price),
                unrealized_pnl=0.0,
                holding_time_seconds=0,
                strategy_name=strategy_name or "ROSS_MOMENTUM",
                setup_family=setup_family or "UNKNOWN",
                entry_reason="EXECUTION_FILL",
                stop_loss_price=selected_stop,
                break_even_price=float(price),
                last_trail_price=selected_stop,
                first_target_price=first_target,
                second_target_price=second_target,
                target_type=target_type,
                exit_stage="NONE",
                reference_order_id=reference_order_id or exec_id,
                partial_taken=False,
                target_model=target_model,
            )
            self._positions[normalized] = position
            self._pending_exit.discard(normalized)
            print(f"[POSITION][OPEN] symbol={normalized} qty={position.quantity} entry={position.entry_price:.4f}")
            return position

        if position is None:
            return None

        if shares > 0:
            total_cost = (position.entry_price * position.quantity) + (float(price) * int(shares))
            position.quantity += int(shares)
            position.entry_price = total_cost / max(position.quantity, 1)
            position.highest_price_seen = max(position.highest_price_seen, float(price))
            position.lowest_price_seen = min(position.lowest_price_seen, float(price))
            position.break_even_price = position.entry_price
        else:
            reduce_qty = min(position.quantity, abs(int(shares)))
            position.quantity -= reduce_qty
            self._pending_exit.discard(normalized)
            if position.quantity <= 0:
                del self._positions[normalized]
                self._pending_exit.discard(normalized)
                print(f"[POSITION][CLOSED] symbol={normalized}")
                return None
            position.partial_taken = True
            position.current_price = float(price)
            self._apply_authorized_stop_update(
                position,
                proposed_stop_price=max(position.stop_loss_price, position.break_even_price),
                reason="confirmed_partial_break_even",
            )
            position.exit_stage = "PARTIAL"
            print(f"[POSITION][PARTIAL_EXIT] symbol={normalized} qty_remaining={position.quantity}")

        position.current_price = float(price)
        position.unrealized_pnl = (position.current_price - position.entry_price) * position.quantity
        position.holding_time_seconds = int((datetime.now(timezone.utc) - position.entry_timestamp).total_seconds())
        print(
            "[POSITION][UPDATE] "
            f"symbol={normalized} qty={position.quantity} px={position.current_price:.4f} "
            f"u_pnl={position.unrealized_pnl:.4f} hold_s={position.holding_time_seconds}"
        )
        return position

    def evaluate_cycle(self, market_state: dict[str, dict]) -> list[TradeIntent]:
        intents: list[TradeIntent] = []
        for symbol in sorted(self._positions.keys()):
            position = self._positions[symbol]
            state = market_state.get(symbol)
            if not state:
                print(f"[ROSS][EXIT_INTELLIGENCE][SKIP] symbol={position.symbol} reason=MISSING_INTRADAY_CANDLES")
                continue
            print(
                "[ROSS][EXIT_INTELLIGENCE][EVAL] "
                f"symbol={position.symbol} qty={position.quantity} avg_price={position.entry_price:.4f}"
            )

            price = self._resolve_price(symbol, state)
            if price is None or price <= 0:
                price = float(position.current_price)

            self._update_position_cycle(position, state, price)
            print(
                "[POSITION][UPDATE] "
                f"symbol={symbol} px={position.current_price:.4f} high={position.highest_price_seen:.4f} "
                f"stop={position.stop_loss_price:.4f} stage={position.exit_stage} "
                f"target1={position.first_target_price} target2={position.second_target_price} "
                f"target_type={position.target_type}"
            )

            if symbol in self._pending_exit and not position.relationship_id:
                continue

            intent = self._evaluate_exit_rules(position, state)
            if intent is not None:
                intents.append(intent)

        return intents

    def snapshot_positions(self) -> dict[str, PositionState]:
        return dict(self._positions)

    def _update_position_cycle(self, position: PositionState, state: dict, price: float) -> None:
        position.current_price = float(price)
        position.highest_price_seen = max(position.highest_price_seen, price)
        position.lowest_price_seen = min(position.lowest_price_seen, price)
        position.unrealized_pnl = (position.current_price - position.entry_price) * position.quantity
        position.holding_time_seconds = int((datetime.now(timezone.utc) - position.entry_timestamp).total_seconds())

        pullback_low = float(state.get("last_pullback_low", position.last_trail_price) or position.last_trail_price)
        candle_low = float(state.get("recent_candle_low", pullback_low) or pullback_low)
        candidate_trail = max(position.stop_loss_price, min(pullback_low, candle_low) - float(state.get("trail_buffer", self._trail_buffer) or self._trail_buffer))
        if position.current_price >= position.highest_price_seen:
            position.last_trail_price = max(position.last_trail_price, candidate_trail)
            if position.partial_taken:
                self._apply_authorized_stop_update(
                    position,
                    proposed_stop_price=max(position.stop_loss_price, position.break_even_price, position.last_trail_price),
                    reason="cycle_partial_trail",
                )
            else:
                self._apply_authorized_stop_update(
                    position,
                    proposed_stop_price=max(position.stop_loss_price, position.last_trail_price),
                    reason="cycle_trail",
                )

    def _evaluate_exit_rules(self, position: PositionState, state: dict) -> TradeIntent | None:
        if not self._exit_intelligence_enabled:
            print(f"[EXIT][SKIP] symbol={position.symbol} action=DISABLED reason=EXIT_INTELLIGENCE_DISABLED")
            return None
        decision = self._exit_intelligence.evaluate(
            trade=position,
            current_price=float(position.current_price),
            current_volume=state.get("current_volume"),
            time_in_trade_sec=float(position.holding_time_seconds),
            market_state=state,
        )
        print(
            "[ROSS][EXIT_DECISION] "
            f"symbol={position.symbol} action={decision.action} reason={decision.reason} "
            f"price={position.current_price:.4f} hold_s={position.holding_time_seconds}"
        )
        if decision.should_exit:
            print(f"[ROSS][EXIT_SIGNAL] symbol={position.symbol} reason={decision.reason}")
        intent = self._apply_exit_decision(position, decision)
        if intent is None and position.relationship_id:
            return self._relationship_milestone(position)
        return intent

    def _apply_exit_decision(self, position: PositionState, decision: ExitDecision) -> TradeIntent | None:
        action = str(decision.action or "HOLD").upper()
        if action == "HOLD":
            return None
        if action == "EXIT_MARKET":
            return self._emit_exit_intent(
                position,
                qty=position.quantity,
                rationale=decision.reason,
                exit_type=self._exit_type_from_reason(decision.reason),
                stage="FINAL",
            )
        if action == "SCALE_OUT":
            requested_qty = int(decision.scale_quantity or max(1, position.quantity // 2))
            max_partial_qty = max(1, position.quantity - 1) if position.quantity > 1 else 1
            qty = min(max(requested_qty, 1), max_partial_qty)
            if qty >= position.quantity:
                return self._emit_exit_intent(
                    position,
                    qty=position.quantity,
                    rationale=decision.reason,
                    exit_type=self._exit_type_from_reason(decision.reason),
                    stage="FINAL",
                )
            return self._emit_exit_intent(
                position,
                qty=qty,
                rationale=decision.reason,
                exit_type=self._exit_type_from_reason(decision.reason),
                stage="PARTIAL",
            )
        if action == "MOVE_STOP":
            if decision.new_stop_price is None:
                print(f"[EXIT][SKIP] symbol={position.symbol} action=MOVE_STOP reason=MISSING_NEW_STOP")
                return None
            candidate = float(decision.new_stop_price)
            if candidate <= position.stop_loss_price:
                print(
                    f"[EXIT][SKIP] symbol={position.symbol} action=MOVE_STOP "
                    f"reason=NON_PROTECTIVE candidate={candidate:.4f} current={position.stop_loss_price:.4f}"
                )
                return None
            if not self._apply_authorized_stop_update(
                position,
                proposed_stop_price=candidate,
                reason="exit_decision_move_stop",
            ):
                return None
            print(f"[EXIT][EXECUTE] symbol={position.symbol} action=MOVE_STOP stop={position.stop_loss_price:.4f} reason={decision.reason}")
            return None
        if action == "ACTIVATE_TRAILING":
            if position.trailing_active:
                print(f"[EXIT][SKIP] symbol={position.symbol} action=ACTIVATE_TRAILING reason=ALREADY_ACTIVE")
                return None
            position.trailing_active = True
            print(f"[EXIT][EXECUTE] symbol={position.symbol} action=ACTIVATE_TRAILING reason={decision.reason}")
            return None
        print(f"[EXIT][SKIP] symbol={position.symbol} action={action} reason=UNSUPPORTED_ACTION")
        return None

    def _apply_authorized_stop_update(
        self,
        position: PositionState,
        *,
        proposed_stop_price: float,
        reason: str,
    ) -> bool:
        decision = self.trailing_stop_authority.evaluate_update(
            symbol=position.symbol,
            side="LONG",
            current_stop_price=position.stop_loss_price,
            proposed_stop_price=proposed_stop_price,
            quantity=int(position.quantity),
            live_position_quantity=int(position.quantity),
            has_active_stop=float(position.stop_loss_price or 0.0) > 0.0,
            recovery_complete=True,
            run_mode="SIM",
            trigger_price=position.current_price,
            reference_price=position.highest_price_seen,
            source=f"trade_management:{reason}",
        )
        print(
            "[TRAILING_STOP][DECISION] "
            f"symbol={decision.symbol} status={decision.status.value} reason={decision.reason}"
        )
        if decision.approved:
            if self._stop_update_callback is not None:
                try:
                    installed = self._stop_update_callback(
                        trade_id=position.reference_order_id,
                        requested_by_strategy=position.strategy_name,
                        new_stop_price=float(decision.proposed_stop_price),
                    )
                except Exception as exc:
                    print(f"[TRAILING_STOP][BLOCKED] symbol={position.symbol} reason=protection_update_failed:{type(exc).__name__}")
                    return False
                if not installed.get("allowed"):
                    return False
            position.stop_loss_price = float(decision.proposed_stop_price)
            print(f"[TRAILING_STOP][MODIFY] symbol={position.symbol} stop={position.stop_loss_price:.4f} reason={reason}")
            return True
        if decision.status == TrailingStopDecisionStatus.NO_ACTION:
            print(f"[TRAILING_STOP][BLOCKED] symbol={position.symbol} reason={decision.reason}")
        else:
            stage = "BLOCKED" if decision.status == TrailingStopDecisionStatus.BLOCKED else "REJECT"
            print(f"[TRAILING_STOP][{stage}] symbol={position.symbol} reason={decision.reason}")
        return False

    def _resolve_price(self, symbol: str, state: dict) -> float | None:
        raw = state.get("current_price")
        if raw is not None:
            return float(raw)
        if self._price_lookup is None:
            return None
        return float(self._price_lookup(symbol))

    def _emit_exit_intent(self, position: PositionState, *, qty: int, rationale: str, exit_type: str, stage: str) -> TradeIntent:
        context = None
        action_id = None
        if position.relationship_id:
            plan = self._relationship_plans[position.relationship_id]
            pending = [order for order in plan.orders.values()
                       if not order["terminal"]]
            if pending:
                # A failure exit may preempt profit-taking, but cancellation is
                # not a fill/terminal acknowledgement. Wait for callback facts.
                for order in pending:
                    if order["action"] != "EXIT" and not order.get("cancel_requested") and order.get("broker_order_id") and self._cancel_order_callback:
                        order["cancel_requested"] = True
                        self._save_relationship_state()
                        try:
                            self._cancel_order_callback(broker_order_id=order["broker_order_id"])
                        except Exception as exc:
                            # Cancel is idempotent, but dispatch failure is not
                            # terminal proof. Keep the reservation and retry later.
                            order["cancel_requested"] = False
                            order["cancel_error"] = type(exc).__name__
                            self._save_relationship_state()
                return None
            if not plan.reconciled:
                return None
            action_id = f"{plan.relationship_id}:exit:{len(plan.orders)}"
            plan.orders[action_id] = {"action": "EXIT", "requested": qty, "filled": 0, "notional": 0.0, "terminal": False}
            context = plan.relationship_id
        self._pending_exit.add(position.symbol)
        position.exit_stage = stage
        if context:
            self._save_relationship_state()
        self._log_exit_reason(position.symbol, rationale, qty)
        print(f"[EXIT][INTENT] symbol={position.symbol} qty={qty} rationale={rationale} type={exit_type}")
        return TradeIntent(
            symbol=position.symbol,
            direction="SELL",
            quantity=int(qty),
            strategy_name="ROSS_MOMENTUM",
            rationale=rationale,
            reference_order_id=position.reference_order_id,
            relationship_id=context, management_action_id=action_id,
            exit_type=exit_type,
            action="EXIT",
            reason=rationale,
        )

    @staticmethod
    def _calculate_profit_targets(entry_price: float) -> tuple[float, float, str]:
        return TakeProfitAuthority.fixed_staged_targets(entry_price=entry_price, side="LONG")

    @staticmethod
    def _exit_type_from_reason(rationale: str) -> str:
        mapping = {
            "STOP_LOSS_HIT": "STOP",
            "STOP_LOSS_BREAK": "STOP",
            "TARGET_HIT": "TARGET",
            "NO_IMMEDIATE_FOLLOW_THROUGH": "FAST_FAILURE",
            "STALL_AT_LEVEL": "WEAKNESS",
            "MOMENTUM_WEAKNESS": "WEAKNESS",
            "VOLUME_REVERSAL": "WEAKNESS",
            "MACD_INVALID": "WEAKNESS",
            "TRAILING_STOP_BROKEN": "TRAIL",
            "MAX_HOLD_TIME_EXCEEDED": "TIME",
            "TIME_STOP": "TIME",
        }
        return mapping.get(rationale, "RULE")

    @staticmethod
    def _log_exit_reason(symbol: str, rationale: str, qty: int) -> None:
        tag_map = {
            "TARGET_HIT": "TARGET_HIT",
            "NO_IMMEDIATE_FOLLOW_THROUGH": "FAST_FAILURE",
            "STALL_AT_LEVEL": "STALL",
            "MOMENTUM_WEAKNESS": "WEAKNESS",
            "STOP_LOSS_HIT": "STOP",
            "STOP_LOSS_BREAK": "STOP",
            "VOLUME_REVERSAL": "WEAKNESS",
            "MACD_INVALID": "WEAKNESS",
            "TIME_STOP": "TIME_STOP",
        }
        tag = tag_map.get(rationale)
        if tag:
            print(f"[EXIT][{tag}] symbol={symbol} qty={qty} rationale={rationale}")
