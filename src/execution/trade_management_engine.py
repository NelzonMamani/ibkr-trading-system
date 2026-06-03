from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from src.core.take_profit_authority import TakeProfitAuthority
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
    first_target_price: float
    second_target_price: float
    target_type: str
    exit_stage: str = "NONE"  # NONE / PARTIAL / FINAL
    reference_order_id: str | None = None
    partial_taken: bool = False
    trailing_active: bool = False


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
    ) -> None:
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
        self._exit_intelligence_enabled = os.getenv("TRADE_MGMT_EXIT_INTELLIGENCE_ENABLED", "1").lower() in {"1", "true", "yes", "on"}
        self._exit_intelligence = exit_intelligence or RossExitIntelligence(
            max_hold_time_seconds=self._max_hold_time_seconds,
            fast_failure_seconds=self._fast_failure_seconds,
            fast_failure_min_progress=self._fast_failure_min_progress,
            stall_candles_without_high=self._stall_candles_without_high,
            stall_rejections_threshold=self._stall_rejections_threshold,
        )

    def on_exec_details(self, *, symbol: str, shares: int, price: float, exec_id: str | None) -> PositionState | None:
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
                strategy_name="ROSS_MOMENTUM",
                setup_family="UNKNOWN",
                entry_reason="EXECUTION_FILL",
                stop_loss_price=float(price) - self._trail_buffer,
                break_even_price=float(price),
                last_trail_price=float(price) - self._trail_buffer,
                first_target_price=first_target,
                second_target_price=second_target,
                target_type=target_type,
                exit_stage="NONE",
                reference_order_id=exec_id,
                partial_taken=False,
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
                f"target1={position.first_target_price:.4f} target2={position.second_target_price:.4f} "
                f"target_type={position.target_type}"
            )

            if symbol in self._pending_exit:
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
                position.stop_loss_price = max(position.stop_loss_price, position.break_even_price, position.last_trail_price)
            else:
                position.stop_loss_price = max(position.stop_loss_price, position.last_trail_price)

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
        return self._apply_exit_decision(position, decision)

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
            position.partial_taken = True
            position.stop_loss_price = max(position.stop_loss_price, position.break_even_price)
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
            position.stop_loss_price = candidate
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

    def _resolve_price(self, symbol: str, state: dict) -> float | None:
        raw = state.get("current_price")
        if raw is not None:
            return float(raw)
        if self._price_lookup is None:
            return None
        return float(self._price_lookup(symbol))

    def _emit_exit_intent(self, position: PositionState, *, qty: int, rationale: str, exit_type: str, stage: str) -> TradeIntent:
        self._pending_exit.add(position.symbol)
        position.exit_stage = stage
        self._log_exit_reason(position.symbol, rationale, qty)
        print(f"[EXIT][INTENT] symbol={position.symbol} qty={qty} rationale={rationale} type={exit_type}")
        return TradeIntent(
            symbol=position.symbol,
            direction="SELL",
            quantity=int(qty),
            strategy_name="ROSS_MOMENTUM",
            rationale=rationale,
            reference_order_id=position.reference_order_id,
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
