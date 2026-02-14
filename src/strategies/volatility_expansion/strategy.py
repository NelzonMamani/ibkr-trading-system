"""Volatility Expansion strategy adapter for StrategyRunner."""

from __future__ import annotations

from typing import List

from src.config.runtime_config import RunMode
from src.models.data_models import PatternResult, TradeIntent
from src.strategy.base_strategy import BaseStrategy


class VolatilityExpansionStrategy(BaseStrategy):
    name = "VolatilityExpansionStrategy"
    trader_type = "QUANT"

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
            day_high = _first_number(entry, "hod", "opening_range_high")
            day_low = _first_number(entry, "lod", "opening_range_low")
            price = _first_number(entry, "last_price", "price")
            if price is None:
                snap = snapshots.get(symbol)
                snap_last = getattr(snap, "last", None)
                price = float(snap_last) if snap_last is not None else None
            rvol = _first_number(entry, "rvol", "relative_volume")
            compression = _first_number(entry, "consolidation_range_pct")
            if None in (day_high, day_low, price):
                continue
            base_range = day_high - day_low
            if base_range <= 0:
                continue
            compressed = compression is not None and compression <= 2.5
            expanded = price >= day_high * 1.002
            if compressed and expanded and (rvol is None or rvol >= 1.4):
                intents.append(
                    TradeIntent(
                        symbol=symbol,
                        direction="LONG",
                        strategy_name=self.name,
                        confidence=0.64,
                        rationale="Volatility contraction followed by expansion breakout.",
                        trader_type=self.trader_type,
                        pattern_name="VOLATILITY_EXPANSION_BREAKOUT",
                        rvol=rvol,
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
                        rationale="SIM/PAPER deterministic fallback intent for volatility-expansion validation.",
                        trader_type=self.trader_type,
                        pattern_name="VOLATILITY_EXPANSION_FALLBACK",
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
