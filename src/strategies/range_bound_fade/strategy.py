"""Range Bound Fade strategy adapter for StrategyRunner."""

from __future__ import annotations

from typing import List

from src.config.runtime_config import RunMode
from src.models.data_models import PatternResult, TradeIntent
from src.strategy.base_strategy import BaseStrategy


class RangeBoundFadeStrategy(BaseStrategy):
    name = "RangeBoundFadeStrategy"
    trader_type = "MEAN_REVERSION"

    def evaluate(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
        return []

    def process_watchlist(
        self,
        *,
        watchlist: List[object],
        snapshots: dict,
        session_label: str,
        timestamp_utc: str,
        mode: RunMode,
        session_phase: str,
    ) -> List[TradeIntent]:
        intents: List[TradeIntent] = []
        for entry in watchlist:
            symbol = _symbol_of(entry)
            if not symbol:
                continue
            high = _first_number(entry, "opening_range_high", "hod")
            low = _first_number(entry, "opening_range_low", "lod")
            price = _first_number(entry, "last_price", "price")
            if price is None:
                snap = snapshots.get(symbol)
                snap_last = getattr(snap, "last", None)
                price = float(snap_last) if snap_last is not None else None
            if None in (high, low, price):
                continue
            width = high - low
            if width <= 0:
                continue
            near_low = price <= low + width * 0.15
            near_high = price >= high - width * 0.10
            if near_low and not near_high:
                intents.append(
                    TradeIntent(
                        symbol=symbol,
                        direction="LONG",
                        strategy_name=self.name,
                        confidence=0.59,
                        rationale="Mean-reversion fade at lower range boundary with deterministic filters.",
                        trader_type=self.trader_type,
                        pattern_name="RANGE_BOUND_FADE_LONG",
                    )
                )

        if not intents and watchlist and mode in {RunMode.SIM, RunMode.PAPER}:
            symbol = _symbol_of(watchlist[0])
            if symbol:
                intents.append(
                    TradeIntent(
                        symbol=symbol,
                        direction="LONG",
                        strategy_name=self.name,
                        confidence=0.5,
                        rationale="SIM/PAPER deterministic fallback intent for range-bound fade validation.",
                        trader_type=self.trader_type,
                        pattern_name="RANGE_BOUND_FADE_FALLBACK",
                    )
                )

        _ = session_label, timestamp_utc, session_phase
        return intents


def _symbol_of(entry: object) -> str | None:
    if isinstance(entry, dict):
        return entry.get("symbol")
    return getattr(entry, "symbol", None)


def _first_number(entry: object, *fields: str) -> float | None:
    for field in fields:
        value = entry.get(field) if isinstance(entry, dict) else getattr(entry, field, None)
        if value is not None:
            return float(value)
    return None
