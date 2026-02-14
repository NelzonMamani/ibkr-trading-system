"""Power Hour strategy adapter for StrategyRunner."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from src.config.runtime_config import RunMode
from src.models.data_models import PatternResult, TradeIntent
from src.strategy.base_strategy import BaseStrategy


class PowerHourStrategy(BaseStrategy):
    name = "PowerHourStrategy"
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
        now = _parse_ts(timestamp_utc)
        in_window = session_phase.upper() in {"AFTERNOON", "POWER_HOUR"} or now.hour >= 19
        intents: List[TradeIntent] = []
        if in_window:
            for entry in watchlist:
                symbol = _symbol_of(entry)
                if not symbol:
                    continue
                price = _first_number(entry, "last_price", "price")
                if price is None:
                    snap = snapshots.get(symbol)
                    snap_last = getattr(snap, "last", None)
                    price = float(snap_last) if snap_last is not None else None
                day_high = _first_number(entry, "hod", "opening_range_high", "premarket_high")
                rvol = _first_number(entry, "rvol", "relative_volume")
                if price is None or day_high is None:
                    continue
                if price >= day_high * 0.998 and (rvol is None or rvol >= 1.3):
                    intents.append(
                        TradeIntent(
                            symbol=symbol,
                            direction="LONG",
                            strategy_name=self.name,
                            confidence=0.62,
                            rationale="Power-hour continuation near highs with liquidity confirmation.",
                            trader_type=self.trader_type,
                            pattern_name="POWER_HOUR_BREAKOUT",
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
                        rationale="SIM/PAPER deterministic fallback intent for power-hour pipeline validation.",
                        trader_type=self.trader_type,
                        pattern_name="POWER_HOUR_FALLBACK",
                    )
                )

        _ = session_label
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


def _parse_ts(timestamp_utc: str) -> datetime:
    if timestamp_utc:
        return datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)
