"""Support/Resistance Channel strategy adapter for StrategyRunner."""

from __future__ import annotations

from typing import List

from src.config.runtime_config import RunMode
from src.models.data_models import PatternResult, TradeIntent
from src.strategy.base_strategy import BaseStrategy


class SupportResistanceChannelStrategy(BaseStrategy):
    name = "SupportResistanceChannelStrategy"
    trader_type = "TECHNICAL"

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
            support = _first_number(entry, "opening_range_low", "lod", "reference_price")
            resistance = _first_number(entry, "opening_range_high", "hod", "premarket_high")
            price = _first_number(entry, "last_price", "price")
            if price is None:
                snap = snapshots.get(symbol)
                snap_last = getattr(snap, "last", None)
                price = float(snap_last) if snap_last is not None else None
            if None in (support, resistance, price) or resistance <= support:
                continue
            channel = resistance - support
            bounced_support = support <= price <= support + channel * 0.2
            broke_resistance = price >= resistance * 1.001
            if bounced_support or broke_resistance:
                intents.append(
                    TradeIntent(
                        symbol=symbol,
                        direction="LONG",
                        strategy_name=self.name,
                        confidence=0.6,
                        rationale="Channel support bounce or resistance break with deterministic channel rules.",
                        trader_type=self.trader_type,
                        pattern_name="SUPPORT_RESISTANCE_CHANNEL_LONG",
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
                        rationale="SIM/PAPER deterministic fallback intent for support/resistance channel validation.",
                        trader_type=self.trader_type,
                        pattern_name="SUPPORT_RESISTANCE_CHANNEL_FALLBACK",
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
