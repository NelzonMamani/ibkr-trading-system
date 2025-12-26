from datetime import datetime
from typing import List, Optional

from domain.active_trade import ActiveTrade


class ActiveTradeRegistry:
    def __init__(self) -> None:
        self._trades: List[ActiveTrade] = []
        print("[BOOT] ActiveTradeRegistry instantiated — lifecycle tracking enabled")

    def register_trade(self, active_trade: ActiveTrade) -> None:
        self._trades.append(active_trade)
        print(
            "[TRADE:REGISTRY] Registered ActiveTrade trade_id="
            f"{active_trade.trade_id} symbol={active_trade.symbol} "
            f"strategy={active_trade.strategy_name} status={active_trade.status} "
            "(CREATED→OPEN)"
        )

    def close_trade(self, trade_id: str, reason: str) -> Optional[ActiveTrade]:
        for trade in self._trades:
            if trade.trade_id == trade_id and trade.status == "OPEN":
                trade.close(reason)
                print(
                    "[TRADE:REGISTRY] Closed ActiveTrade trade_id="
                    f"{trade.trade_id} symbol={trade.symbol} "
                    f"strategy={trade.strategy_name} status={trade.status}"
                )
                return trade
        print(
            "[TRADE:REGISTRY] No OPEN trade found for trade_id="
            f"{trade_id}; nothing closed"
        )
        return None

    def get_active_trades(self) -> List[ActiveTrade]:
        active_trades = [trade for trade in self._trades if trade.status == "OPEN"]
        print(
            "[TRADE:REGISTRY] Retrieved open trades count="
            f"{len(active_trades)}"
        )
        return active_trades

    def get_active_trades_by_strategy(self, strategy_name: str) -> List[ActiveTrade]:
        active_trades = [
            trade
            for trade in self._trades
            if trade.status == "OPEN" and trade.strategy_name == strategy_name
        ]
        print(
            "[TRADE:REGISTRY] Retrieved open trades for strategy="
            f"{strategy_name} count={len(active_trades)}"
        )
        return active_trades

    def get_active_trades_by_trader_type(self, trader_type: str) -> List[ActiveTrade]:
        active_trades = [
            trade
            for trade in self._trades
            if trade.status == "OPEN" and trade.trader_type == trader_type
        ]
        print(
            "[TRADE:REGISTRY] Retrieved open trades for trader_type="
            f"{trader_type} count={len(active_trades)}"
        )
        return active_trades

    def count_active_by_strategy(self, strategy_name: str) -> int:
        count = len(self.get_active_trades_by_strategy(strategy_name))
        print(
            "[TRADE:REGISTRY] Active count by strategy="
            f"{strategy_name} count={count}"
        )
        return count

    def count_active_by_trader_type(self, trader_type: str) -> int:
        count = len(self.get_active_trades_by_trader_type(trader_type))
        print(
            "[TRADE:REGISTRY] Active count by trader_type="
            f"{trader_type} count={count}"
        )
        return count


active_trade_registry = ActiveTradeRegistry()
