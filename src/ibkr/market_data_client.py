from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import time
from typing import Optional

from ib_insync import IB, Stock

from config.runtime_config import (
    get_ibkr_client_id,
    get_ibkr_host,
    get_ibkr_market_data_type,
    get_ibkr_port,
    get_ibkr_snapshot_timeout_seconds,
)


def _market_data_type_code(market_data_type: str) -> int:
    normalized = (market_data_type or "").upper()
    if normalized == "LIVE":
        return 1
    if normalized == "DELAYED":
        return 3
    if normalized == "DELAYED_FROZEN":
        return 4
    if normalized == "FROZEN":
        return 2
    return 1


def _clean(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric) or not math.isfinite(numeric):
        return None
    return numeric


@dataclass(frozen=True)
class MarketDataSnapshot:
    symbol: str
    bid: Optional[float]
    ask: Optional[float]
    last: Optional[float]
    last_size: Optional[float]
    bid_size: Optional[float]
    ask_size: Optional[float]
    volume: Optional[float]
    vwap: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    open: Optional[float]
    timestamp: datetime
    spread: Optional[float]
    data_quality_flags: list[str] = field(default_factory=list)


class MarketDataClient:
    """Read-only market data client backed by ib_insync."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
        market_data_type: str | None = None,
        snapshot_timeout_seconds: int | None = None,
    ) -> None:
        self.host = host or get_ibkr_host()
        self.port = port or get_ibkr_port()
        self.client_id = client_id or get_ibkr_client_id()
        self.market_data_type = market_data_type or get_ibkr_market_data_type()
        self.snapshot_timeout_seconds = (
            snapshot_timeout_seconds or get_ibkr_snapshot_timeout_seconds()
        )
        self.ib = IB()

    def connect(self) -> None:
        if self.ib.isConnected():
            return
        print(
            "[MD] Connecting to IBKR "
            f"host={self.host} port={self.port} client_id={self.client_id}"
        )
        if not self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=5):
            raise RuntimeError("IBKR market data connection failed")
        data_type_code = _market_data_type_code(self.market_data_type)
        print(
            "[MD] Setting market data type "
            f"type={self.market_data_type} code={data_type_code}"
        )
        self.ib.reqMarketDataType(data_type_code)

    def disconnect(self) -> None:
        if self.ib.isConnected():
            self.ib.disconnect()
            print("[MD] Disconnected from IBKR market data")

    def qualify_contract(self, symbol: str):
        contract = Stock(symbol, "SMART", "USD")
        qualified = self.ib.qualifyContracts(contract)
        if not qualified:
            return None
        return qualified[0]

    def snapshot_for_symbol(self, symbol: str) -> MarketDataSnapshot:
        flags: list[str] = []
        try:
            contract = self.qualify_contract(symbol)
        except Exception as exc:
            flags.append("CONTRACT_QUALIFY_FAILED")
            return self._empty_snapshot(symbol, flags, error=str(exc))
        if contract is None:
            flags.append("CONTRACT_QUALIFY_FAILED")
            return self._empty_snapshot(symbol, flags)

        ticker = self.ib.reqMktData(
            contract,
            genericTickList="",
            snapshot=True,
            regulatorySnapshot=False,
        )
        timeout_at = time.time() + self.snapshot_timeout_seconds
        while time.time() < timeout_at:
            self.ib.waitOnUpdate(timeout=0.2)
            if self._ticker_has_data(ticker):
                break
        else:
            flags.append("MD_TIMEOUT")

        self.ib.cancelMktData(contract)
        if "MD_TIMEOUT" in flags and not self._ticker_has_data(ticker):
            return self._empty_snapshot(symbol, flags)

        bid = _clean(getattr(ticker, "bid", None))
        ask = _clean(getattr(ticker, "ask", None))
        last = _clean(getattr(ticker, "last", None))
        last_size = _clean(getattr(ticker, "lastSize", None))
        bid_size = _clean(getattr(ticker, "bidSize", None))
        ask_size = _clean(getattr(ticker, "askSize", None))
        volume = _clean(getattr(ticker, "volume", None))
        vwap = _clean(getattr(ticker, "vwap", None))
        high = _clean(getattr(ticker, "high", None))
        low = _clean(getattr(ticker, "low", None))
        close = _clean(getattr(ticker, "close", None))
        open_price = _clean(getattr(ticker, "open", None))
        spread = (ask - bid) if bid is not None and ask is not None else None

        return MarketDataSnapshot(
            symbol=symbol,
            bid=bid,
            ask=ask,
            last=last,
            last_size=last_size,
            bid_size=bid_size,
            ask_size=ask_size,
            volume=volume,
            vwap=vwap,
            high=high,
            low=low,
            close=close,
            open=open_price,
            timestamp=datetime.now(timezone.utc),
            spread=spread,
            data_quality_flags=flags,
        )

    @staticmethod
    def _ticker_has_data(ticker) -> bool:
        for attr in ("bid", "ask", "last", "close", "volume"):
            value = _clean(getattr(ticker, attr, None))
            if value is not None:
                return True
        return False

    def _empty_snapshot(
        self,
        symbol: str,
        flags: list[str],
        error: str | None = None,
    ) -> MarketDataSnapshot:
        if error:
            flags.append("MD_ERROR")
        return MarketDataSnapshot(
            symbol=symbol,
            bid=None,
            ask=None,
            last=None,
            last_size=None,
            bid_size=None,
            ask_size=None,
            volume=None,
            vwap=None,
            high=None,
            low=None,
            close=None,
            open=None,
            timestamp=datetime.now(timezone.utc),
            spread=None,
            data_quality_flags=flags,
        )
