from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.core.take_profit_authority import TakeProfitAuthority


@dataclass
class PositionManagementConfig:
    add_size_fraction: float = 0.25
    partial_at_1r_fraction: float = 0.50
    partial_at_2r_fraction: float = 0.25
    structure_buffer: float = 0.01


@dataclass
class ManagedPosition:
    symbol: str
    side: str
    quantity: int
    entry_price: float
    stop_price: float
    execution_mode: str = "NORMAL"
    timeframe: str = "1m"
    initial_quantity: int | None = None
    add_count: int = 0
    partials_taken: set[str] = field(default_factory=set)
    closed: bool = False
    exit_reason: str | None = None

    def __post_init__(self) -> None:
        if self.initial_quantity is None:
            self.initial_quantity = max(int(self.quantity), 0)


class PositionManagementEngine:
    """Deterministic position lifecycle manager between intent and completion."""

    def __init__(self, config: PositionManagementConfig | None = None) -> None:
        self.config = config or PositionManagementConfig()

    def manage_position(self, position: ManagedPosition, market_state: dict[str, Any]) -> ManagedPosition:
        if position.closed or position.quantity <= 0:
            return position

        current_price = self._to_float(market_state.get("current_price"))
        if current_price is None:
            return position

        self._apply_add_logic(position, market_state, current_price)
        self._apply_partial_logic(position, current_price)
        self._apply_trailing_logic(position, market_state, current_price)
        self._apply_exit_logic(position, market_state)
        return position

    def _apply_add_logic(self, position: ManagedPosition, market_state: dict[str, Any], current_price: float) -> None:
        side = str(position.side).upper()
        is_winner = current_price > position.entry_price if side == "LONG" else current_price < position.entry_price
        breakout = bool(market_state.get("breaks_new_level"))
        support_hold = bool(market_state.get("pullback_holds_support"))

        if not is_winner:
            return
        if not breakout and not support_hold:
            return

        add_qty = max(1, int(round(position.quantity * self.config.add_size_fraction)))
        position.quantity += add_qty
        position.add_count += 1
        print(
            "[POSITION][ADD] "
            f"symbol={position.symbol} qty_add={add_qty} total_qty={position.quantity} "
            f"reason={'breakout' if breakout else 'support_hold'}"
        )

    def _apply_partial_logic(self, position: ManagedPosition, current_price: float) -> None:
        risk_per_share = abs(position.entry_price - position.stop_price)
        if risk_per_share <= 0:
            return

        side = str(position.side).upper()
        one_r_price = TakeProfitAuthority.r_multiple_price(
            entry_price=position.entry_price,
            stop_loss_price=position.stop_price,
            side=side,
            r_multiple=1.0,
            decimals=4,
        )
        two_r_price = TakeProfitAuthority.r_multiple_price(
            entry_price=position.entry_price,
            stop_loss_price=position.stop_price,
            side=side,
            r_multiple=2.0,
            decimals=4,
        )

        if TakeProfitAuthority._hits_target(side, current_price, one_r_price) and "1R" not in position.partials_taken:
            qty = self._partial_qty(position, self.config.partial_at_1r_fraction)
            if qty > 0:
                position.quantity -= qty
                position.partials_taken.add("1R")
                print(f"[POSITION][PARTIAL] symbol={position.symbol} level=1R qty={qty} remaining={position.quantity}")

        if TakeProfitAuthority._hits_target(side, current_price, two_r_price) and "2R" not in position.partials_taken:
            qty = self._partial_qty(position, self.config.partial_at_2r_fraction)
            if qty > 0:
                position.quantity -= qty
                position.partials_taken.add("2R")
                print(f"[POSITION][PARTIAL] symbol={position.symbol} level=2R qty={qty} remaining={position.quantity}")

    def _apply_trailing_logic(self, position: ManagedPosition, market_state: dict[str, Any], current_price: float) -> None:
        side = str(position.side).upper()
        risk_per_share = abs(position.entry_price - position.stop_price)
        if risk_per_share <= 0:
            return

        one_r_price = position.entry_price + risk_per_share if side == "LONG" else position.entry_price - risk_per_share
        mode = str(position.execution_mode or "").upper()
        buffer_mult = 0.5 if mode == "FAST_MICRO_PULLBACK" else 1.0
        structure_buffer = self.config.structure_buffer * buffer_mult

        if self._hits_target(side, current_price, one_r_price):
            if (side == "LONG" and position.stop_price < position.entry_price) or (
                side == "SHORT" and position.stop_price > position.entry_price
            ):
                position.stop_price = position.entry_price
                print(f"[POSITION][BREAKEVEN] symbol={position.symbol} stop={position.stop_price}")
                print(f"[POSITION][TRAIL] symbol={position.symbol} stop=break_even value={position.stop_price}")

        higher_low = self._to_float(market_state.get("higher_low"))
        if higher_low is None:
            return

        if side == "LONG":
            trailed_stop = higher_low - structure_buffer
            if trailed_stop > position.stop_price:
                position.stop_price = trailed_stop
                print(f"[POSITION][TRAIL] symbol={position.symbol} stop=structure value={position.stop_price:.4f}")
        else:
            trailed_stop = higher_low + structure_buffer
            if trailed_stop < position.stop_price:
                position.stop_price = trailed_stop
                print(f"[POSITION][TRAIL] symbol={position.symbol} stop=structure value={position.stop_price:.4f}")

    def _apply_exit_logic(self, position: ManagedPosition, market_state: dict[str, Any]) -> None:
        mode = str(position.execution_mode or "").upper()
        structure_break = bool(market_state.get("structure_broken"))
        vwap_loss = bool(market_state.get("vwap_lost"))
        false_breakout = bool(market_state.get("false_breakout"))
        momentum_mode = mode in {"FAST_MICRO_PULLBACK", "EARLY_FAST", "MOMENTUM"}

        if structure_break:
            self._close(position, "structure_break")
            return
        if momentum_mode and vwap_loss:
            self._close(position, "vwap_loss")
            return
        if false_breakout:
            self._close(position, "false_breakout")

    def _close(self, position: ManagedPosition, reason: str) -> None:
        if position.closed:
            return
        position.closed = True
        position.exit_reason = reason
        position.quantity = 0
        if reason in {"structure_break", "vwap_loss", "false_breakout"}:
            print(f"[POSITION][FAILURE_EXIT] symbol={position.symbol}")
        print(f"[POSITION][EXIT] symbol={position.symbol} reason={reason}")

    @staticmethod
    def _to_float(value: Any) -> float | None:
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _hits_target(side: str, current_price: float, target_price: float) -> bool:
        return current_price >= target_price if side == "LONG" else current_price <= target_price

    @staticmethod
    def _partial_qty(position: ManagedPosition, fraction: float) -> int:
        base_qty = max(int(position.initial_quantity or 0), 0)
        target_qty = TakeProfitAuthority.scale_out_quantity(
            live_position_quantity=base_qty,
            fraction=fraction,
            allow_full_exit_for_single_share=False,
        )
        return min(target_qty, max(position.quantity - 1, 0))
