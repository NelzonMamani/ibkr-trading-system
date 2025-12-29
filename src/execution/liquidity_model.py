import hashlib


class LiquidityModel:
    """
    Deterministic, replay-safe liquidity model.

    Liquidity is derived solely from (symbol, tick, trader_type) using a
    stable SHA-256 hash. No randomness, time, or external data is involved.
    """

    _MAX_PER_TRADER = {
        "SCALPER": 1,
        "MOMENTUM": 2,
    }

    @staticmethod
    def max_liquidity_per_tick(trader_type: str) -> int:
        """
        Return the deterministic liquidity ceiling for the provided trader type.
        """

        return LiquidityModel._MAX_PER_TRADER.get((trader_type or "").upper(), 0)

    @staticmethod
    def available_liquidity(symbol: str, tick: int, trader_type: str) -> int:
        """
        Compute deterministic liquidity for a symbol at a given tick.

        Algorithm (stable and replay-safe):
        1) key = f"{symbol}|{tick}"
        2) digest = sha256(key.encode("utf-8")).hexdigest()
        3) take first 8 hex chars -> int
        4) map into range [0..MAX_LIQUIDITY_PER_TICK]
        """

        max_liquidity = LiquidityModel.max_liquidity_per_tick(trader_type)
        if max_liquidity <= 0:
            return 0

        key = f"{symbol}|{tick}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        mapped_value = int(digest[:8], 16)
        available = mapped_value % (max_liquidity + 1)
        return available
