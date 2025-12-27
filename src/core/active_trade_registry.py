from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ActiveTrade:
    symbol: str
    trader_type: str
    entry_tick: int
    entry_price: float
    close_tick: Optional[int] = None
    close_price: Optional[float] = None
    realised_pnl: Optional[float] = None


class ActiveTradeRegistry:
    """
    Central registry tracking active trades by symbol and trader type.
    Teaching-first, in-memory only.
    """

    def __init__(self):
        self._active_trades: List[ActiveTrade] = []

    def register_trade(self, active_trade: ActiveTrade):
        print(
            "[REGISTRY] REGISTER "
            f"symbol={active_trade.symbol} "
            f"trader_type={active_trade.trader_type} "
            f"entry_tick={active_trade.entry_tick} "
            f"entry_price={active_trade.entry_price}"
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
