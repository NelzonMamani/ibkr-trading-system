"""Opening Drive strategy adapter for StrategyRunner."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from src.config.runtime_config import RunMode
from src.models.data_models import PatternResult, TradeIntent
from src.strategy.base_strategy import BaseStrategy


class OpeningDriveStrategy(BaseStrategy):
    name = "OpeningDriveStrategy"
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
            price = _price_of(entry, snapshots.get(symbol))
            reference = _first_number(entry, "prev_close", "reference_price", "ref_close_rth")
            gap_pct = _first_number(entry, "gap_pct", "pct_change")
            rvol = _first_number(entry, "rvol", "relative_volume")
            if price is None or reference is None:
                continue
            strength = (price - reference) / reference if reference > 0 else 0.0
            if gap_pct is not None and rvol is not None and gap_pct >= 2.0 and rvol >= 1.5 and strength >= 0.01:
                intents.append(
                    TradeIntent(
                        symbol=symbol,
                        direction="LONG",
                        strategy_name=self.name,
                        confidence=round(min(0.95, 0.55 + strength * 5.0), 2),
                        rationale="Opening drive continuation: positive gap, RVOL confirmation, and early strength.",
                        trader_type=self.trader_type,
                        pattern_name="OPENING_DRIVE_CONTINUATION",
                        gap_percent=gap_pct,
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
                        confidence=0.51,
                        rationale="SIM/PAPER deterministic fallback intent for opening-drive pipeline validation.",
                        trader_type=self.trader_type,
                        pattern_name="OPENING_DRIVE_FALLBACK",
                    )
                )

        _ = _now(timestamp_utc), session_label, session_phase
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


def _price_of(entry: object, snapshot: object) -> float | None:
    for field in ("last_price", "price", "last"):
        value = entry.get(field) if isinstance(entry, dict) else getattr(entry, field, None)
        if value is not None:
            return float(value)
    snap_last = getattr(snapshot, "last", None)
    return float(snap_last) if snap_last is not None else None


def _now(timestamp_utc: str) -> datetime:
    if timestamp_utc:
        return datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)
