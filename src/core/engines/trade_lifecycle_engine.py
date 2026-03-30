from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LifecycleTrade:
    trade_id: str
    symbol: str
    quantity: int
    entry_price: float
    stop_price: float
    status: str = "OPEN"
    last_price: float | None = None
    unrealized_pnl: float | None = None


class TradeLifecycleEngine:
    """Canonical accounting state for executed trades (observer-only)."""

    def __init__(self) -> None:
        self._trades: dict[str, LifecycleTrade] = {}
        self._symbol_to_open_trade_id: dict[str, str] = {}

    def register_trade(
        self,
        *,
        trade_id: str,
        symbol: str,
        quantity: int,
        entry_price: float,
        stop_price: float,
    ) -> LifecycleTrade:
        trade = LifecycleTrade(
            trade_id=trade_id,
            symbol=symbol,
            quantity=int(quantity),
            entry_price=float(entry_price),
            stop_price=float(stop_price),
        )
        self._trades[trade_id] = trade
        self._symbol_to_open_trade_id[symbol] = trade_id
        return trade

    def get_trade(self, trade_id: str) -> LifecycleTrade | None:
        return self._trades.get(trade_id)

    def find_open_trade_id_for_symbol(self, symbol: str) -> str | None:
        trade_id = self._symbol_to_open_trade_id.get(symbol)
        if not trade_id:
            return None
        trade = self._trades.get(trade_id)
        if trade is None or trade.status != "OPEN":
            return None
        return trade_id

    def reconcile_position(self, *, trade_id: str, closed: bool) -> LifecycleTrade | None:
        trade = self._trades.get(trade_id)
        if trade is None:
            return None
        if bool(closed):
            trade.status = "CLOSED"
            if self._symbol_to_open_trade_id.get(trade.symbol) == trade_id:
                self._symbol_to_open_trade_id.pop(trade.symbol, None)
        return trade

    def open_trades(self) -> list[LifecycleTrade]:
        return [trade for trade in self._trades.values() if trade.status == "OPEN"]

    def mark_to_market(self, *, trade_id: str, price: float) -> LifecycleTrade | None:
        trade = self._trades.get(trade_id)
        if trade is None:
            return None
        current_price = float(price)
        trade.last_price = current_price
        trade.unrealized_pnl = (current_price - trade.entry_price) * float(trade.quantity)
        return trade

    def summarize_session_metrics(self) -> dict[str, Any]:
        open_trades = self.open_trades()
        closed_trades = [trade for trade in self._trades.values() if trade.status == "CLOSED"]
        open_unrealized = sum(float(trade.unrealized_pnl or 0.0) for trade in open_trades)
        return {
            "total_trades": len(self._trades),
            "open_trades": len(open_trades),
            "closed_trades": len(closed_trades),
            "open_unrealized_pnl": open_unrealized,
        }
