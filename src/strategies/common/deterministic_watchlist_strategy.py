"""Shared deterministic watchlist strategy helpers for Batch A strategies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Mapping, Sequence

from src.config.runtime_config import RunMode
from src.domain.market_snapshot import MarketSnapshot
from src.models.data_models import TradeIntent


@dataclass(frozen=True)
class DeterministicPolicy:
    strategy_name: str
    strategy_label: str
    trader_type: str
    allowed_sessions: tuple[str, ...]
    allowed_modes_for_intents: tuple[RunMode, ...]
    min_price: float
    min_volume: float
    max_intents_per_cycle: int = 1


def _symbol_seed(symbol: str) -> int:
    return sum(ord(ch) for ch in symbol)


def _extract_symbol(entry: object) -> str | None:
    if isinstance(entry, str):
        return entry.strip().upper() or None
    if isinstance(entry, Mapping):
        symbol = entry.get("symbol")
        return str(symbol).strip().upper() if symbol else None
    symbol = getattr(entry, "symbol", None)
    return str(symbol).strip().upper() if symbol else None


def _extract_price(entry: object, snapshot: MarketSnapshot | None) -> float | None:
    if snapshot and snapshot.last is not None:
        return float(snapshot.last)
    if isinstance(entry, Mapping):
        last = entry.get("last") or entry.get("price")
        return float(last) if isinstance(last, (int, float)) else None
    value = getattr(entry, "last", None)
    return float(value) if isinstance(value, (int, float)) else None


def _extract_volume(entry: object, snapshot: MarketSnapshot | None) -> float | None:
    if snapshot and snapshot.volume is not None:
        return float(snapshot.volume)
    if isinstance(entry, Mapping):
        vol = entry.get("volume")
        return float(vol) if isinstance(vol, (int, float)) else None
    value = getattr(entry, "volume", None)
    return float(value) if isinstance(value, (int, float)) else None


def build_deterministic_watchlist_intents(
    *,
    policy: DeterministicPolicy,
    watchlist: Sequence[object],
    snapshots: Mapping[str, MarketSnapshot],
    mode: RunMode,
    session_label: str,
    timestamp_utc: str,
) -> List[TradeIntent]:
    if mode not in policy.allowed_modes_for_intents:
        return []
    if session_label not in policy.allowed_sessions:
        return []

    generated: List[TradeIntent] = []
    for entry in watchlist:
        symbol = _extract_symbol(entry)
        if not symbol:
            continue
        snapshot = snapshots.get(symbol)
        price = _extract_price(entry, snapshot)
        volume = _extract_volume(entry, snapshot)
        if price is not None and price < policy.min_price:
            continue
        if volume is not None and volume < policy.min_volume:
            continue

        seed = _symbol_seed(f"{policy.strategy_name}:{symbol}")
        direction = "LONG" if seed % 2 == 0 else "SHORT"
        rationale = (
            f"{policy.strategy_label} deterministic fallback for {symbol}; "
            f"mode={mode.value} session={session_label}"
        )
        generated.append(
            TradeIntent(
                symbol=symbol,
                direction=direction,
                strategy_name=policy.strategy_name,
                confidence=0.55,
                rationale=rationale,
                trader_type=policy.trader_type,
                pattern_name=f"{policy.strategy_name.upper()}_DETERMINISTIC_FALLBACK",
            )
        )
        if len(generated) >= policy.max_intents_per_cycle:
            break
    return generated
