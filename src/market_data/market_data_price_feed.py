from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.market_data.market_data_hub import MarketDataHub
from src.sim.price_feed import DeterministicPriceFeed, PriceFeed


@dataclass
class MarketDataPriceFeed(PriceFeed):
    """Price feed backed by IBKR market snapshots captured in MarketDataHub."""

    market_data_hub: MarketDataHub
    fallback_feed: Optional[DeterministicPriceFeed] = None

    def price_for(self, symbol: str, tick: int) -> float:
        try:
            observation = self.market_data_hub.snapshot(symbol, request_source="PriceFeed")
        except Exception as exc:
            self.market_data_hub.emit_fallback(
                reason=str(exc),
                request_source="PriceFeed",
                symbols=[symbol],
            )
            fallback = self.fallback_feed or DeterministicPriceFeed()
            price = fallback.price_for(symbol, tick)
            print(
                "[PRICE_FEED][WARN] Falling back to deterministic price "
                f"symbol={symbol} tick={tick} err={exc}"
            )
            return price

        snapshot = observation.snapshot
        bid = snapshot.bid
        ask = snapshot.ask
        last = snapshot.last
        if last is not None:
            price = float(last)
        elif bid is not None and ask is not None:
            price = round((bid + ask) / 2, 4)
        elif bid is not None:
            price = float(bid)
        elif ask is not None:
            price = float(ask)
        else:
            price = 0.0
        print(
            "[PRICE_FEED] "
            f"symbol={symbol} tick={tick} price={price} mode={observation.data_mode}"
        )
        return price
