from dataclasses import dataclass


@dataclass(frozen=True)
class PricePoint:
    symbol: str
    tick: int
    price: float


class DeterministicPriceFeed:
    """
    Teaching-only deterministic price generator.
    """

    BASE_PRICES = {
        "ABC": 12.35,
        "XYZ": 47.80,
        "LMN": 6.75,
        "QRS": 83.40,
    }

    INCREMENTS = {
        "ABC": 0.02,
        "LMN": 0.03,
        "XYZ": 0.01,
        "QRS": 0.00,
    }

    def price_for(self, symbol: str, tick: int) -> float:
        base = self.BASE_PRICES.get(symbol, 10.0)
        inc = self.INCREMENTS.get(symbol, 0.0)
        price = round(base + inc * tick, 2)
        print(f"[PRICE_FEED] symbol={symbol} tick={tick} price={price}")
        return price
