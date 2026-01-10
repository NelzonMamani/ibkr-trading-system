from decimal import Decimal
from typing import Dict, Optional

from src.execution.liquidity_model import LiquidityModel
from src.utils.price_math import (
    D,
    apply_spread_mid_to_quote,
    deterministic_spread,
    q_price,
)


class LiquidityEngine:
    """
    Deterministic spread-aware liquidity helper.

    Responsibilities:
    - Provide deterministic bid/ask quotes derived solely from (symbol, tick, trader_type)
    - Preserve replay determinism (no randomness or time)
    - Keep monetary values in Decimal with cent-level quantisation
    """

    @classmethod
    def quote(
        cls,
        symbol: str,
        tick: int,
        trader_type: str,
        mid_price: float,
    ) -> Dict[str, Decimal]:
        mid = q_price(D(mid_price))
        spread = deterministic_spread(symbol, tick, trader_type)
        bid, ask = apply_spread_mid_to_quote(mid, spread)
        return {
            "mid": mid,
            "bid": bid,
            "ask": ask,
            "spread": spread,
        }

    @staticmethod
    def available_liquidity(symbol: str, tick: int, trader_type: str) -> int:
        return LiquidityModel.available_liquidity(
            symbol=symbol,
            tick=tick,
            trader_type=trader_type,
        )

    @staticmethod
    def side_price(direction: Optional[str], quote: Dict[str, Decimal]) -> Decimal:
        normalized_direction = (direction or "").upper()
        if normalized_direction == "SHORT":
            return quote["bid"]
        return quote["ask"]
