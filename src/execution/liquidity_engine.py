import hashlib
from decimal import Decimal
from typing import Dict, Optional

from execution.liquidity_model import LiquidityModel
from utils.price_math import D, quantize_money


class LiquidityEngine:
    """
    Deterministic spread-aware liquidity helper.

    Responsibilities:
    - Provide deterministic bid/ask quotes derived solely from (symbol, tick, trader_type)
    - Preserve replay determinism (no randomness or time)
    - Keep monetary values in Decimal with cent-level quantisation
    """

    _MIN_SPREAD = Decimal("0.01")

    @classmethod
    def _spread_cents(cls, symbol: str, tick: int, trader_type: str) -> Decimal:
        """
        Deterministically map inputs to a 1–3 cent spread to avoid float drift.
        """

        key = f"{symbol}|{tick}|{trader_type or 'UNKNOWN'}|SPREAD"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        mapped = int(digest[:6], 16)
        cents = (mapped % 3) + 1  # 1, 2, or 3 cents
        return Decimal(cents) / Decimal(100)

    @classmethod
    def quote(
        cls,
        symbol: str,
        tick: int,
        trader_type: str,
        mid_price: float,
    ) -> Dict[str, Decimal]:
        mid = quantize_money(D(mid_price))
        spread = max(cls._spread_cents(symbol, tick, trader_type), cls._MIN_SPREAD)
        half_spread = spread / Decimal(2)
        bid = quantize_money(mid - half_spread)
        ask = quantize_money(mid + half_spread)
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
