from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable


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
    exit_stage: str = "NONE"  # NONE / PARTIAL / FINAL
    reference_order_id: str | None = None
    partial_taken: bool = False


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
        *,
        quick_profit_threshold: float = 0.15,
        max_hold_time_seconds: int = 600,
        trail_buffer: float = 0.01,
    ) -> None:
        self._positions: dict[str, PositionState] = {}
        self._seen_exec_ids: set[str] = set()
        self._pending_exit: set[str] = set()
        self._price_lookup = price_lookup
        self._quick_profit_threshold = float(quick_profit_threshold)
        self._max_hold_time_seconds = int(max_hold_time_seconds)
        self._trail_buffer = float(trail_buffer)

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
            state = market_state.get(symbol, {})

            price = self._resolve_price(symbol, state)
            if price is None or price <= 0:
                continue

            self._update_position_cycle(position, state, price)
            print(
                "[POSITION][UPDATE] "
                f"symbol={symbol} px={position.current_price:.4f} high={position.highest_price_seen:.4f} "
                f"stop={position.stop_loss_price:.4f} stage={position.exit_stage}"
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
        if position.current_price <= position.stop_loss_price:
            return self._emit_exit_intent(position, qty=position.quantity, rationale="STOP_LOSS_HIT", exit_type="STOP", stage="FINAL")

        profit_per_share = position.current_price - position.entry_price
        if (not position.partial_taken) and profit_per_share >= self._quick_profit_threshold and position.quantity > 1:
            qty = max(1, position.quantity // 2)
            position.partial_taken = True
            position.exit_stage = "PARTIAL"
            position.stop_loss_price = max(position.stop_loss_price, position.break_even_price)
            return self._emit_exit_intent(position, qty=qty, rationale="QUICK_PROFIT_TAKEN", exit_type="TARGET", stage="PARTIAL")

        if position.partial_taken:
            position.stop_loss_price = max(position.stop_loss_price, position.break_even_price)

        if position.partial_taken and position.current_price < position.last_trail_price:
            return self._emit_exit_intent(position, qty=position.quantity, rationale="TRAILING_STOP_BROKEN", exit_type="TRAIL", stage="FINAL")

        weakness = bool(state.get("large_upper_wick", False)) or bool(state.get("stall_near_hod", False)) or bool(state.get("failed_new_high", False))
        red_vs_green = float(state.get("red_volume_ratio", 0.0) or 0.0) > float(state.get("green_volume_ratio", 0.0) or 0.0)
        if weakness or red_vs_green:
            qty = position.quantity if position.partial_taken else max(1, position.quantity // 2)
            stage = "FINAL" if qty >= position.quantity else "PARTIAL"
            return self._emit_exit_intent(position, qty=qty, rationale="MOMENTUM_WEAKNESS", exit_type="WEAKNESS", stage=stage)

        if position.holding_time_seconds > self._max_hold_time_seconds:
            return self._emit_exit_intent(position, qty=position.quantity, rationale="MAX_HOLD_TIME_EXCEEDED", exit_type="TIME", stage="FINAL")

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
