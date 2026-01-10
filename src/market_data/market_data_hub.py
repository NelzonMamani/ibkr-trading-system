from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, Optional
from src.config.config_resolver import get_config
from src.core.event_collector import EventCollector
from src.domain.market_snapshot import MarketSnapshot

if TYPE_CHECKING:
    from src.brokers import IbkrBroker


@dataclass(frozen=True)
class MarketDataObservation:
    snapshot: MarketSnapshot
    data_mode: str
    request_mode: str


class MarketDataHub:
    """Centralizes IBKR market data snapshots with event capture and caching."""

    def __init__(
        self,
        event_collector: Optional[EventCollector] = None,
        broker: Optional["IbkrBroker"] = None,
        max_symbols_per_cycle: Optional[int] = None,
    ) -> None:
        self.event_collector = event_collector
        self.broker = broker
        self.market_data_type = get_config("IBKR_MARKET_DATA_TYPE")
        self.max_symbols_per_cycle = (
            max_symbols_per_cycle
            if max_symbols_per_cycle is not None
            else get_config("IBKR_MAX_SYMBOLS_PER_CYCLE")
        )
        self.readonly_enabled = get_config("IBKR_READONLY_ENABLED")
        self._connected = False
        self._cache: Dict[str, MarketDataObservation] = {}

    def reset_cycle(self) -> None:
        self._cache.clear()

    def connect(self) -> bool:
        if self.broker is None:
            return False
        if self._connected:
            return True
        self.broker.connect()
        self._connected = True
        data_mode = self._resolve_data_mode(self.market_data_type)
        print(
            "[MARKET_DATA] Connected to IBKR market data "
            f"mode={data_mode} readonly={self.readonly_enabled}"
        )
        if self.event_collector:
            self.event_collector.emit(
                event_type="MARKET_DATA_CONNECTED",
                source="MarketDataHub",
                payload={
                    "connected": True,
                    "market_data_type": self.market_data_type,
                    "data_mode": data_mode,
                    "readonly_enabled": self.readonly_enabled,
                },
            )
        return True

    def disconnect(self) -> None:
        if self.broker is None or not self._connected:
            return
        self.broker.disconnect()
        self._connected = False

    def snapshot(self, symbol: str, request_source: str) -> MarketDataObservation:
        cached = self._cache.get(symbol)
        if cached is not None:
            return cached
        if self.max_symbols_per_cycle and len(self._cache) >= self.max_symbols_per_cycle:
            raise RuntimeError(
                "IBKR_MAX_SYMBOLS_PER_CYCLE reached; refusing additional market data requests."
            )
        if self.broker is None:
            raise RuntimeError("IBKR market data broker unavailable.")
        if not self._connected:
            self.connect()
        snapshot = self.broker.get_market_snapshot(symbol)
        observation = MarketDataObservation(
            snapshot=snapshot,
            data_mode=self._resolve_data_mode(snapshot.market_data_type),
            request_mode="SNAPSHOT",
        )
        self._cache[symbol] = observation
        self._emit_snapshot(observation, request_source=request_source)
        return observation

    def emit_fallback(
        self,
        reason: str,
        request_source: str,
        symbols: list[str] | None = None,
        fallback_source: str = "STATIC",
    ) -> None:
        print(
            "[MARKET_DATA] FALLBACK activated "
            f"source={request_source} reason={reason}"
        )
        if self.event_collector:
            self.event_collector.emit(
                event_type="MARKET_DATA_FALLBACK",
                source="MarketDataHub",
                payload={
                    "reason": reason,
                    "fallback_source": fallback_source,
                    "data_mode": "FALLBACK",
                    "request_source": request_source,
                    "symbols": symbols or [],
                    "asof_utc": datetime.now(timezone.utc).isoformat(),
                },
            )

    @staticmethod
    def _resolve_data_mode(market_data_type: str) -> str:
        normalized = (market_data_type or "").upper()
        if normalized in {"DELAYED", "DELAYED_FROZEN"}:
            return "DELAYED"
        if normalized == "LIVE":
            return "LIVE"
        if normalized == "FROZEN":
            return "SNAPSHOT"
        return "SNAPSHOT"

    def _emit_snapshot(self, observation: MarketDataObservation, request_source: str) -> None:
        snapshot = observation.snapshot
        spread = None
        if snapshot.bid is not None and snapshot.ask is not None:
            spread = round(snapshot.ask - snapshot.bid, 4)
        print(
            "[MARKET_DATA] SNAPSHOT "
            f"symbol={snapshot.symbol} mode={observation.data_mode} "
            f"request={observation.request_mode} bid={snapshot.bid} ask={snapshot.ask} "
            f"last={snapshot.last} spread={spread} volume={snapshot.volume}"
        )
        if self.event_collector:
            self.event_collector.emit(
                event_type="MARKET_DATA_SNAPSHOT",
                source="MarketDataHub",
                payload={
                    "symbol": snapshot.symbol,
                    "bid": snapshot.bid,
                    "ask": snapshot.ask,
                    "last": snapshot.last,
                    "spread": spread,
                    "volume": snapshot.volume,
                    "asof_utc": snapshot.asof_utc.isoformat(),
                    "market_data_type": snapshot.market_data_type,
                    "data_mode": observation.data_mode,
                    "request_mode": observation.request_mode,
                    "request_source": request_source,
                    "source": snapshot.source,
                },
            )
