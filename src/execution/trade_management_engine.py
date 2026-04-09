from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class PositionState:
    symbol: str
    entry_price: float
    quantity: int
    high_watermark: float
    last_pullback_low: float
    current_price: float
    green_volume_ratio: float
    red_volume_ratio: float
    unrealized_pnl: float
    trailing_stop: float | None = None
    add_count: int = 0


@dataclass(frozen=True)
class TradeIntent:
    action: str
    symbol: str
    quantity: int
    reason: str


class TradeManagementEngine:
    """Deterministic post-fill position management using broker-truth fills."""

    def __init__(self, price_lookup: Callable[[str], float] | None = None, *, max_adds: int = 2) -> None:
        self._positions: dict[str, PositionState] = {}
        self._seen_exec_ids: set[str] = set()
        self._pending_exit: set[str] = set()
        self._price_lookup = price_lookup
        self._max_adds = max(0, int(max_adds))

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
            position = PositionState(
                symbol=normalized,
                entry_price=float(price),
                quantity=int(shares),
                high_watermark=float(price),
                last_pullback_low=float(price),
                current_price=float(price),
                green_volume_ratio=1.0,
                red_volume_ratio=1.0,
                unrealized_pnl=0.0,
                trailing_stop=None,
                add_count=0,
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
            position.high_watermark = max(position.high_watermark, float(price))
        else:
            reduce_qty = min(position.quantity, abs(int(shares)))
            position.quantity -= reduce_qty
            if position.quantity <= 0:
                del self._positions[normalized]
                self._pending_exit.discard(normalized)
                print(f"[POSITION][CLOSED] symbol={normalized}")
                return None

        position.current_price = float(price)
        position.unrealized_pnl = (position.current_price - position.entry_price) * position.quantity
        return position

    def evaluate_cycle(self, market_state: dict[str, dict]) -> list[TradeIntent]:
        intents: list[TradeIntent] = []
        for symbol in sorted(self._positions.keys()):
            position = self._positions[symbol]
            state = market_state.get(symbol, {})

            price = self._resolve_price(symbol, state)
            if price is None or price <= 0:
                continue
            position.current_price = price
            position.high_watermark = max(position.high_watermark, price)
            position.green_volume_ratio = float(state.get("green_volume_ratio", position.green_volume_ratio or 1.0) or 1.0)
            position.red_volume_ratio = float(state.get("red_volume_ratio", position.red_volume_ratio or 1.0) or 1.0)
            position.unrealized_pnl = (position.current_price - position.entry_price) * position.quantity

            retrace = self._compute_retrace(position)
            print(
                "[MANAGEMENT][EVAL] "
                f"symbol={symbol} px={position.current_price:.4f} hwm={position.high_watermark:.4f} retrace={retrace:.4f} "
                f"gvr={position.green_volume_ratio:.2f} rvr={position.red_volume_ratio:.2f}"
            )

            self._maybe_update_trailing_stop(position, state)

            if symbol in self._pending_exit:
                continue

            if retrace > 0.5:
                intents.append(self._emit_exit(position, reason="RETRACE_FAILURE"))
                continue
            if position.red_volume_ratio >= 1.5:
                intents.append(self._emit_exit(position, reason="RED_VOLUME_EXIT"))
                continue

            level_hit = bool(state.get("key_level_hit", False))
            if level_hit:
                partial = bool(state.get("partial_exit", True))
                qty = max(1, position.quantity // 2) if partial else position.quantity
                intents.append(self._emit_intent("EXIT", position.symbol, qty, "LEVEL_TARGET"))
                continue

            if position.trailing_stop is not None and position.current_price < position.trailing_stop:
                intents.append(self._emit_exit(position, reason="TRAILING_STOP"))
                continue

            structure_intact = bool(state.get("structure_intact", False))
            near_resistance = bool(state.get("near_resistance", True))
            if (
                position.green_volume_ratio >= 1.5
                and structure_intact
                and not near_resistance
                and position.add_count < self._max_adds
            ):
                add_qty = max(1, int(position.quantity * 0.25))
                position.add_count += 1
                intents.append(self._emit_intent("ADD", position.symbol, add_qty, "GREEN_VOLUME_SCALE"))
                print(
                    "[MANAGEMENT][SCALE_TRIGGER] "
                    f"symbol={position.symbol} qty={add_qty} add_count={position.add_count}"
                )

        return intents

    def snapshot_positions(self) -> dict[str, PositionState]:
        return dict(self._positions)

    def _resolve_price(self, symbol: str, state: dict) -> float | None:
        raw = state.get("current_price")
        if raw is not None:
            return float(raw)
        if self._price_lookup is None:
            return None
        return float(self._price_lookup(symbol))

    @staticmethod
    def _compute_retrace(position: PositionState) -> float:
        denom = position.high_watermark - position.entry_price
        if denom <= 0:
            return 0.0
        retrace = (position.high_watermark - position.current_price) / denom
        return max(0.0, float(retrace))

    def _maybe_update_trailing_stop(self, position: PositionState, state: dict) -> None:
        higher_low_raw = state.get("last_higher_low")
        if higher_low_raw is None:
            return
        higher_low = float(higher_low_raw)
        if higher_low <= position.last_pullback_low:
            return
        position.last_pullback_low = higher_low
        buffer = float(state.get("trail_buffer", 0.01) or 0.01)
        new_trail = higher_low - buffer
        if position.trailing_stop is None or new_trail > position.trailing_stop:
            position.trailing_stop = new_trail
            print(
                "[MANAGEMENT][TRAIL_UPDATE] "
                f"symbol={position.symbol} higher_low={higher_low:.4f} trailing_stop={position.trailing_stop:.4f}"
            )

    def _emit_exit(self, position: PositionState, *, reason: str) -> TradeIntent:
        self._pending_exit.add(position.symbol)
        intent = self._emit_intent("EXIT", position.symbol, position.quantity, reason)
        print(
            "[MANAGEMENT][EXIT_TRIGGER] "
            f"symbol={position.symbol} qty={position.quantity} reason={reason}"
        )
        return intent

    @staticmethod
    def _emit_intent(action: str, symbol: str, quantity: int, reason: str) -> TradeIntent:
        return TradeIntent(action=action, symbol=symbol, quantity=int(quantity), reason=reason)
