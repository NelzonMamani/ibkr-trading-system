class ActiveTradeRegistry:
    """
    Central registry tracking active trades by symbol and trader type.
    Teaching-first, in-memory only.
    """

    def __init__(self):
        self._active_trades = []

    def register_trade(self, symbol: str, trader_type: str):
        self._active_trades.append(
            {"symbol": symbol, "trader_type": trader_type}
        )

    def unregister_trade(self, symbol: str, trader_type: str):
        self._active_trades = [
            t for t in self._active_trades
            if not (t["symbol"] == symbol and t["trader_type"] == trader_type)
        ]

    def count_active_by_trader(self, trader_type: str) -> int:
        return len(
            [t for t in self._active_trades if t["trader_type"] == trader_type]
        )

    def snapshot(self):
        return list(self._active_trades)


# Shared singleton-style registry for teaching flows that do not inject one.
DEFAULT_ACTIVE_TRADE_REGISTRY = ActiveTradeRegistry()
