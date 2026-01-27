from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import time
from typing import Optional
import threading

from ib_insync import IB, Stock

from src.config.config_resolver import get_config
from src.config.runtime_config import (
    get_ibkr_client_id,
    get_ibkr_default_currency,
    get_ibkr_default_exchange,
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
    bid_size: Optional[float]
    ask_size: Optional[float]
    last_size: Optional[float]
    volume: Optional[float]
    vwap: Optional[float]
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    change_percent: Optional[float]
    spread: Optional[float]
    timestamp_utc: str
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
        default_exchange: str | None = None,
        default_currency: str | None = None,
    ) -> None:
        self.host = host or get_ibkr_host()
        self.port = port or get_ibkr_port()
        self.client_id = client_id or get_ibkr_client_id()
        self.market_data_type = market_data_type or get_ibkr_market_data_type()
        self.snapshot_timeout_seconds = (
            snapshot_timeout_seconds or get_ibkr_snapshot_timeout_seconds()
        )
        self.default_exchange = default_exchange or get_ibkr_default_exchange()
        self.default_currency = default_currency or get_ibkr_default_currency()
        self.ib = IB()

    def connect(self) -> None:
        if self.ib.isConnected():
            return
        print(
            "[IBKR][MD] Connecting "
            f"host={self.host} port={self.port} client_id={self.client_id}"
        )
        if not self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=5):
            raise RuntimeError("IBKR market data connection failed")
        server_version = None
        try:
            server_version = self.ib.client.serverVersion()
        except Exception:
            server_version = None
        data_type_code = _market_data_type_code(self.market_data_type)
        print(
            "[IBKR][MD] Connected "
            f"serverVersion={server_version} host={self.host} port={self.port}"
        )
        print(
            "[IBKR][MD] Market data type set "
            f"type={self.market_data_type} code={data_type_code}"
        )
        self.ib.reqMarketDataType(data_type_code)

    def disconnect(self) -> None:
        if not self.ib.isConnected():
            return
        try:
            client = getattr(self.ib, "client", None)
            thread = getattr(client, "_thread", None)
            if thread is not None and thread is threading.current_thread():
                print("[IBKR][MD] Disconnect skipped to avoid joining current thread")
                if client is not None:
                    client.disconnect()
                return
            self.ib.disconnect()
            print("[IBKR][MD] Disconnected")
        except RuntimeError as exc:
            if "cannot join current thread" in str(exc):
                print("[IBKR][MD] Disconnect skipped to avoid joining current thread")
                client = getattr(self.ib, "client", None)
                if client is not None:
                    client.disconnect()
                return
            raise

    def qualify_contract(self, symbol: str):
        contract = Stock(symbol, self.default_exchange, self.default_currency)
        try:
            import asyncio

            async def _coro():
                return await self.ib.qualifyContractsAsync(contract)

            runner = getattr(self.ib, "run", None)
            if callable(runner):
                qualified = runner(
                    asyncio.wait_for(_coro(), timeout=self.snapshot_timeout_seconds)
                )
            else:
                qualified = asyncio.run(
                    asyncio.wait_for(_coro(), timeout=self.snapshot_timeout_seconds)
                )
        except Exception:
            return None
        if not qualified:
            return None
        return qualified[0]

    def snapshot_stock(self, symbol: str) -> MarketDataSnapshot:
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
        snapshot_complete = False
        while time.time() < timeout_at:
            self.ib.waitOnUpdate(timeout=0.2)
            if self._ticker_has_required_snapshot(ticker):
                snapshot_complete = True
                break
            if self._ticker_snapshot_complete(ticker):
                snapshot_complete = True
                break
        else:
            flags.append("MD_TIMEOUT")

        if not snapshot_complete:
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
        change_percent = _clean(getattr(ticker, "changePercent", None))
        if get_config("DEBUG_MARKET_DATA"):
            print(
                "[IBKR][MD][DEBUG] ticks "
                f"symbol={symbol} bid={bid} ask={ask} last={last} close={close} "
                f"volume={volume} vwap={vwap} high={high} low={low} open={open_price}"
            )
        spread = (ask - bid) if bid is not None and ask is not None else None
        if bid is None and ask is None and last is None:
            flags.append("MD_EMPTY")
        if last is None:
            flags.append("MD_MISSING_LAST")
        if close is None:
            flags.append("MD_MISSING_CLOSE")
        if volume is None:
            flags.append("MD_MISSING_VOLUME")

        return MarketDataSnapshot(
            symbol=symbol,
            bid=bid,
            ask=ask,
            last=last,
            bid_size=bid_size,
            ask_size=ask_size,
            last_size=last_size,
            volume=volume,
            vwap=vwap,
            open=open_price,
            high=high,
            low=low,
            close=close,
            change_percent=change_percent,
            spread=spread,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            data_quality_flags=flags,
        )

    @staticmethod
    def _ticker_has_data(ticker) -> bool:
        for attr in ("bid", "ask", "last", "close", "volume"):
            value = _clean(getattr(ticker, attr, None))
            if value is not None:
                return True
        return False

    @staticmethod
    def _ticker_has_required_snapshot(ticker) -> bool:
        last = _clean(getattr(ticker, "last", None))
        close = _clean(getattr(ticker, "close", None))
        volume = _clean(getattr(ticker, "volume", None))
        return last is not None and close is not None and volume is not None

    @staticmethod
    def _ticker_snapshot_complete(ticker) -> bool:
        return bool(getattr(ticker, "snapshotEnd", False))

    def prev_close_from_history(self, symbol: str, use_rth: bool = True) -> Optional[float]:
        try:
            contract = self.qualify_contract(symbol)
        except Exception:
            return None
        if contract is None:
            return None
        try:
            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr="3 D",
                barSizeSetting="1 day",
                whatToShow="TRADES",
                useRTH=use_rth,
                formatDate=1,
            )
        except Exception:
            return None
        if not bars:
            return None
        latest = bars[-1]
        return _clean(getattr(latest, "close", None))

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
            bid_size=None,
            ask_size=None,
            last_size=None,
            volume=None,
            vwap=None,
            open=None,
            high=None,
            low=None,
            close=None,
            change_percent=None,
            spread=None,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            data_quality_flags=flags,
        )

    def snapshot_for_symbol(self, symbol: str) -> MarketDataSnapshot:
        return self.snapshot_stock(symbol)
