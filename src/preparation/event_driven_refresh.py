from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from src.preparation.context_builder import SymbolContext


@dataclass(frozen=True)
class RefreshThresholds:
    price_move_pct: float = 1.5
    volume_spike_ratio: float = 1.2
    rvol_delta: float = 0.2
    spread_pct_delta: float = 0.01


@dataclass
class RuntimeContextRegistry:
    symbol_context_registry: dict[str, SymbolContext] = field(default_factory=dict)
    thresholds: RefreshThresholds = field(default_factory=RefreshThresholds)

    def upsert(self, context: SymbolContext) -> None:
        self.symbol_context_registry[context.symbol] = context

    def get(self, symbol: str) -> SymbolContext | None:
        return self.symbol_context_registry.get(symbol)

    def should_refresh(self, previous: SymbolContext | None, latest: SymbolContext) -> tuple[bool, list[str]]:
        if previous is None:
            return True, ["NEW_SYMBOL"]
        reasons: list[str] = []

        if previous.last_price and latest.last_price:
            move = abs((latest.last_price - previous.last_price) / previous.last_price) * 100.0
            if move >= self.thresholds.price_move_pct:
                reasons.append("price_move")

        if previous.volume and latest.volume and previous.volume > 0:
            ratio = latest.volume / previous.volume
            if ratio >= self.thresholds.volume_spike_ratio:
                reasons.append("new_volume_spike")

        if abs((latest.rvol or 0.0) - (previous.rvol or 0.0)) >= self.thresholds.rvol_delta:
            reasons.append("rvol_update")

        if abs((latest.spread_pct or 0.0) - (previous.spread_pct or 0.0)) >= self.thresholds.spread_pct_delta:
            reasons.append("liquidity_change")

        if latest.news_catalyst and latest.news_catalyst != previous.news_catalyst:
            reasons.append("new_news_event")

        return bool(reasons), reasons

    def refresh_if_needed(
        self,
        latest: SymbolContext,
        *,
        on_refresh: Callable[[SymbolContext, list[str]], None] | None = None,
    ) -> tuple[bool, list[str]]:
        previous = self.get(latest.symbol)
        should_refresh, reasons = self.should_refresh(previous, latest)
        if should_refresh:
            self.upsert(latest)
            if on_refresh:
                on_refresh(latest, reasons)
        return should_refresh, reasons
