from dataclasses import dataclass, field
from typing import List, Optional

from src.core.position_lifecycle_engine import (
    LifecycleTransitionError,
    PositionState,
    is_transition_allowed,
    normalize_state,
)


@dataclass
class ActiveTrade:
    symbol: str
    trader_type: str
    entry_tick: int
    entry_price: float
    direction: str = "UNKNOWN"
    quantity: int = 1
    strategy_name: str = "UNKNOWN"
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    entry_order_id: Optional[str] = None
    stop_order_id: Optional[str] = None
    target_order_id: Optional[str] = None
    broker_status: Optional[str] = None
    pattern_name: Optional[str] = None
    invalidation_level: Optional[float] = None
    state: PositionState = PositionState.FLAT
    state_history: List[dict] = field(default_factory=list)
    close_tick: Optional[int] = None
    close_price: Optional[float] = None
    realised_pnl: Optional[float] = None

    def hold_duration(self, current_tick: int) -> int:
        """Return how many ticks this trade has been held so far."""

        return max(0, current_tick - self.entry_tick)

    def transition_state(
        self,
        new_state: PositionState | str,
        tick: int,
        reason: str,
        reason_code: str = "UNSPECIFIED",
    ) -> None:
        target_state = normalize_state(new_state)
        current_state = normalize_state(self.state)
        if target_state == current_state:
            return
        if current_state == PositionState.CLOSED:
            raise LifecycleTransitionError(
                "STATE_IMMUTABLE",
                "Closed positions are immutable.",
            )
        if not is_transition_allowed(current_state, target_state):
            raise LifecycleTransitionError(
                "INVALID_TRANSITION",
                f"Invalid trade state transition {current_state.value} -> {target_state.value}",
            )
        self.state_history.append(
            {
                "from": current_state.value,
                "to": target_state.value,
                "tick": tick,
                "reason": reason,
                "reason_code": reason_code,
            }
        )
        self.state = target_state


class ActiveTradeRegistry:
    """
    Central registry tracking active trades by symbol and trader type.
    Teaching-first, in-memory only.
    """

    def __init__(self):
        self._active_trades: List[ActiveTrade] = []

    def register_trade(self, active_trade: ActiveTrade):
        if getattr(active_trade, "quantity", 0) <= 0:
            raise ValueError("Cannot register a trade with non-positive quantity.")
        if getattr(active_trade, "stop_loss_price", None) is None:
            raise ValueError(
                "Protective stop required; cannot register trade without stop_loss_price."
            )
        print(
            "[REGISTRY] REGISTER "
            f"symbol={active_trade.symbol} "
            f"trader_type={active_trade.trader_type} "
            f"entry_tick={active_trade.entry_tick} "
            f"entry_price={active_trade.entry_price} "
            f"direction={active_trade.direction} "
            f"quantity={active_trade.quantity} "
            f"strategy={active_trade.strategy_name}"
        )
        if active_trade.state != PositionState.OPEN:
            active_trade.transition_state(
                PositionState.OPEN,
                tick=active_trade.entry_tick,
                reason="Trade opened",
                reason_code="OPEN_INTENT_ACCEPTED",
            )
        self._active_trades.append(active_trade)

    def unregister_trade(self, symbol: str, trader_type: str):
        print(f"[REGISTRY] UNREGISTER symbol={symbol} trader_type={trader_type}")
        self._active_trades = [
            t for t in self._active_trades
            if not (t.symbol == symbol and t.trader_type == trader_type)
        ]

    def get_trade(self, symbol: str, trader_type: str) -> Optional[ActiveTrade]:
        for trade in self._active_trades:
            if trade.symbol == symbol and trade.trader_type == trader_type:
                return trade
        return None

    def mark_closed(
        self,
        symbol: str,
        trader_type: str,
        close_tick: int,
        close_price: float,
        realised_pnl: float,
    ):
        trade = self.get_trade(symbol, trader_type)
        if trade is None:
            return
        trade.close_tick = close_tick
        trade.close_price = close_price
        trade.realised_pnl = realised_pnl
        print(
            "[REGISTRY] MARK_CLOSED "
            f"symbol={symbol} "
            f"trader_type={trader_type} "
            f"close_tick={close_tick} "
            f"close_price={close_price} "
            f"realised_pnl={realised_pnl}"
        )

    def count_active_by_trader(self, trader_type: str) -> int:
        return len(
            [t for t in self._active_trades if t.trader_type == trader_type]
        )

    def count_active(self) -> int:
        return len(self._active_trades)

    def snapshot(self):
        return list(self._active_trades)

    def close_all_trades(self):
        """
        Teaching-first lifecycle reset.
        Closes all active trades deterministically.
        """
        closed = list(self._active_trades)
        self._active_trades.clear()
        return closed

    def verify_empty(self) -> bool:
        """
        Teaching-first integrity check to confirm registry state on shutdown.
        """

        active_count = len(self._active_trades)
        if active_count == 0:
            print("[REGISTRY] Verification passed — no active trades remain.")
            return True
        print(
            "[REGISTRY] Verification failed — active trades remain at shutdown: "
            f"{active_count}"
        )
        return False
