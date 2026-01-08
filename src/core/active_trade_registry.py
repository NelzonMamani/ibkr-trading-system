from dataclasses import dataclass
from typing import List, Optional


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
    close_tick: Optional[int] = None
    close_price: Optional[float] = None
    realised_pnl: Optional[float] = None

    def hold_duration(self, current_tick: int) -> int:
        """Return how many ticks this trade has been held so far."""

        return max(0, current_tick - self.entry_tick)


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
