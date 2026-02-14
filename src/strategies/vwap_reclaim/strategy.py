"""VWAP Reclaim strategy adapter for StrategyRunner."""

from __future__ import annotations

from typing import List

from src.config.runtime_config import RunMode
from src.models.data_models import PatternResult, TradeIntent
from src.strategy.base_strategy import BaseStrategy


class VwapReclaimStrategy(BaseStrategy):
    name = "VwapReclaimStrategy"
    trader_type = "MOMENTUM"

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
            price = _first_number(entry, "last_price", "price", "last")
            if price is None:
                snap = snapshots.get(symbol)
                snap_last = getattr(snap, "last", None)
                price = float(snap_last) if snap_last is not None else None
            vwap = _first_number(entry, "vwap", "reference_price", "ref_close_rth")
            hold = _first_number(entry, "vwap_hold_minutes") or 0.0
            rvol = _first_number(entry, "rvol", "relative_volume")
            if price is None or vwap is None:
                continue
            reclaimed = price >= vwap * 1.002
            confirmed = hold >= 2.0 and (rvol is None or rvol >= 1.2)
            if reclaimed and confirmed:
                intents.append(
                    TradeIntent(
                        symbol=symbol,
                        direction="LONG",
                        strategy_name=self.name,
                        confidence=0.63,
                        rationale="Price reclaimed and held above VWAP with deterministic confirmation filters.",
                        trader_type=self.trader_type,
                        pattern_name="VWAP_RECLAIM",
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
                        rationale="SIM/PAPER deterministic fallback intent for VWAP reclaim pipeline validation.",
                        trader_type=self.trader_type,
                        pattern_name="VWAP_RECLAIM_FALLBACK",
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
