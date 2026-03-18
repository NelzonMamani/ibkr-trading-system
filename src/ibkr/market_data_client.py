from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import time
from typing import Optional, TYPE_CHECKING
import threading

from src.runtime.async_runtime_bootstrap import safe_import_ib_insync

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

if TYPE_CHECKING:
    from src.adapters.brokers.ibkr.ibkr_connection_manager import IbkrConnectionManager


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


def _market_data_type_flags(market_data_type: str | None) -> list[str]:
    normalized = (market_data_type or "").upper()
    flags: list[str] = []
    if normalized in {"DELAYED", "DELAYED_FROZEN"}:
        flags.append("MD_DELAYED")
    if normalized in {"FROZEN", "DELAYED_FROZEN"}:
        flags.append("MD_FROZEN")
    return flags


def _resolve_snapshot_timestamp(ticker, fallback: datetime) -> datetime:
    raw_time = getattr(ticker, "time", None) or getattr(ticker, "lastTime", None)
    if isinstance(raw_time, datetime):
        if raw_time.tzinfo is None:
            raw_time = raw_time.replace(tzinfo=timezone.utc)
        return raw_time.astimezone(timezone.utc)
    return fallback


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
        connection_manager: "IbkrConnectionManager | None" = None,
        allow_direct_connection: bool = True,
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
        self.connection_manager = connection_manager
        self.allow_direct_connection = allow_direct_connection
        self.ib = None
        if self.connection_manager is None:
            IB, _, _ = safe_import_ib_insync()
            self.ib = IB()
        self._scanner_results_received = False
        self._scanner_request_active = False
        self._recent_error_codes: dict[str, int] = {}
        try:
            if self.ib is not None:
                self.ib.errorEvent += self._on_ib_error
        except Exception:
            pass

    def _resolve_ib_client(self):
        if self.connection_manager is not None:
            if self.ib is None or not self.ib.isConnected():
                self.ib = self.connection_manager.get_client()
            return self.ib
        if self.ib is None:
            raise RuntimeError("IBKR client not initialized")
        return self.ib


    def _on_ib_error(self, req_id, error_code, error_string, contract=None) -> None:
        code = str(error_code)
        self._recent_error_codes[code] = self._recent_error_codes.get(code, 0) + 1
        if int(error_code) == 162 and self._scanner_results_received and not self._scanner_request_active:
            print(f"[IBKR][INFO] code=162 msg={error_string} context=scanner_cancel_after_results")
        elif int(error_code) in {10197}:
            print(f"[IBKR][WARN] code={error_code} msg={error_string}")

    def request_scanner_data(self, subscription):
        ib = self._resolve_ib_client()
        self._scanner_request_active = True
        self._scanner_results_received = False
        try:
            rows = ib.reqScannerData(subscription)
            self._scanner_results_received = bool(rows)
            return rows
        finally:
            self._scanner_request_active = False

    def connect(self) -> None:
        if self.connection_manager is not None:
            self.ib = self.connection_manager.get_client()
            return
        if not self.allow_direct_connection:
            raise RuntimeError(
                "IBKR connections must be created only by IBKRConnectionManager"
            )
        ib = self._resolve_ib_client()
        if ib.isConnected():
            return
        print(
            "[IBKR][MD] Connecting "
            f"host={self.host} port={self.port} client_id={self.client_id}"
        )
        connect_coro = ib.connectAsync(
            self.host,
            self.port,
            clientId=self.client_id,
            timeout=5,
        )
        try:
            if callable(getattr(ib, "run", None)):
                connected = ib.run(connect_coro)
            else:
                connected = asyncio.run(connect_coro)
        except Exception:
            connect_coro.close()
            raise
        if not connected:
            raise RuntimeError("IBKR market data connection failed")
        server_version = None
        try:
            server_version = ib.client.serverVersion()
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
        ib.reqMarketDataType(data_type_code)

    def disconnect(self) -> None:
        if self.connection_manager is not None:
            return
        ib = self._resolve_ib_client()
        if not ib.isConnected():
            return
        try:
            client = getattr(ib, "client", None)
            thread = getattr(client, "_thread", None)
            if thread is not None and thread is threading.current_thread():
                print("[IBKR][MD] Disconnect skipped to avoid joining current thread")
                if client is not None:
                    client.disconnect()
                return
            ib.disconnect()
            print("[IBKR][MD] Disconnected")
        except RuntimeError as exc:
            if "cannot join current thread" in str(exc):
                print("[IBKR][MD] Disconnect skipped to avoid joining current thread")
                client = getattr(ib, "client", None)
                if client is not None:
                    client.disconnect()
                return
            raise

    def qualify_contract(self, symbol: str):
        _, Stock, _ = safe_import_ib_insync()
        contract = Stock(symbol, self.default_exchange, self.default_currency)
        try:
            import asyncio

            async def _qualify_with_timeout():
                return await asyncio.wait_for(
                    self._resolve_ib_client().qualifyContractsAsync(contract),
                    timeout=self.snapshot_timeout_seconds,
                )

            qualify_coro = _qualify_with_timeout()

            ib = self._resolve_ib_client()
            runner = getattr(ib, "run", None)
            if callable(runner):
                qualified = runner(qualify_coro)
            else:
                qualified = asyncio.run(qualify_coro)
        except Exception:
            if "qualify_coro" in locals():
                qualify_coro.close()
            return None
        if not qualified:
            return None
        return qualified[0]

    def qualifyContracts(self, *contracts):
        """
        Compatibility wrapper for ib_insync-style APIs used by the
        snapshot enrichment layer.
        """
        ib = self._resolve_ib_client()
        try:
            return ib.qualifyContracts(*contracts)
        except Exception:
            return []

    def snapshot_stock(self, symbol: str) -> MarketDataSnapshot:
        now_utc = datetime.now(timezone.utc)
        flags = _market_data_type_flags(self.market_data_type)
        try:
            contract = self.qualify_contract(symbol)
        except Exception as exc:
            flags.append("CONTRACT_QUALIFY_FAILED")
            return self._empty_snapshot(symbol, flags, error=str(exc))
        if contract is None:
            flags.append("CONTRACT_QUALIFY_FAILED")
            return self._empty_snapshot(symbol, flags)

        ib = self._resolve_ib_client()
        ticker = ib.reqMktData(
            contract,
            genericTickList="",
            snapshot=True,
            regulatorySnapshot=False,
        )
        timeout_at = time.time() + self.snapshot_timeout_seconds
        snapshot_complete = False
        while time.time() < timeout_at:
            ib.waitOnUpdate(timeout=0.2)
            if self._ticker_has_required_snapshot(ticker):
                snapshot_complete = True
                break
            if self._ticker_snapshot_complete(ticker):
                snapshot_complete = True
                break
        else:
            flags.append("MD_TIMEOUT")

        if not snapshot_complete:
            ib.cancelMktData(contract)
        if "MD_TIMEOUT" in flags and not self._ticker_has_data(ticker):
            return self._empty_snapshot(symbol, flags)

        snapshot_timestamp = _resolve_snapshot_timestamp(ticker, now_utc)
        max_age_seconds = int(get_config("IBKR_SNAPSHOT_MAX_AGE_SECONDS"))
        age_seconds = (now_utc - snapshot_timestamp).total_seconds()
        if age_seconds > max_age_seconds:
            flags.append("MD_STALE")

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
        if self._recent_error_codes.get("10197"):
            flags.append("MD_CONFLICT_10197")
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
            timestamp_utc=snapshot_timestamp.isoformat(),
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

    def _canonicalize_history_contract(self, contract_or_symbol):
        contract = contract_or_symbol
        if isinstance(contract_or_symbol, str):
            try:
                contract = self.qualify_contract(contract_or_symbol)
            except Exception:
                return None
            return contract
        if contract_or_symbol is None:
            return None
        con_id = getattr(contract_or_symbol, "conId", None)
        primary_exchange = getattr(contract_or_symbol, "primaryExchange", None)
        if con_id not in {None, 0} and primary_exchange not in {None, ""}:
            return contract_or_symbol
        qualified = self.qualifyContracts(contract_or_symbol)
        if not qualified:
            return None
        return qualified[0]

    def _request_daily_history_with_fallback(self, contract, *, lookback_days: int, use_rth: bool = True, end_datetime: str = ""):
        attempts = [
            {
                "label": "primary",
                "useRTH": use_rth,
                "endDateTime": end_datetime,
                "durationStr": f"{max(lookback_days, 3)} D",
            }
        ]
        explicit_end = end_datetime or f"{datetime.now().strftime('%Y%m%d')} 09:29:59 US/Eastern"
        if use_rth:
            attempts.append(
                {
                    "label": "fallback_useRTH_false",
                    "useRTH": False,
                    "endDateTime": explicit_end,
                    "durationStr": f"{max(lookback_days, 3)} D",
                }
            )
        for attempt in attempts:
            print(
                "[IBKR][HIST_ATTEMPT] "
                f"symbol={getattr(contract, 'symbol', None)} label={attempt['label']} "
                f"useRTH={attempt['useRTH']} endDateTime='{attempt['endDateTime']}' durationStr={attempt['durationStr']}"
            )
            try:
                bars = self._resolve_ib_client().reqHistoricalData(
                    contract,
                    endDateTime=attempt["endDateTime"],
                    durationStr=attempt["durationStr"],
                    barSizeSetting="1 day",
                    whatToShow="TRADES",
                    useRTH=attempt["useRTH"],
                    formatDate=1,
                ) or []
            except Exception as exc:
                print(
                    "[IBKR][HIST_ATTEMPT_FAIL] "
                    f"symbol={getattr(contract, 'symbol', None)} label={attempt['label']} error={exc}"
                )
                bars = []
            print(
                "[IBKR][HIST_ATTEMPT_RESULT] "
                f"symbol={getattr(contract, 'symbol', None)} label={attempt['label']} raw_bar_count={len(bars)}"
            )
            if bars:
                return bars
        return []

    def prev_close_from_history(self, symbol: str, use_rth: bool = True) -> Optional[float]:
        try:
            contract = self.qualify_contract(symbol)
        except Exception:
            return None
        if contract is None:
            return None
        bars = self._request_daily_history_with_fallback(contract, lookback_days=3, use_rth=use_rth)
        if not bars:
            return None
        latest = bars[-1]
        return _clean(getattr(latest, "close", None))

    def daily_bars_from_history(self, contract_or_symbol, *, lookback_days: int = 25, use_rth: bool = True, end_datetime: str = ""):
        contract = self._canonicalize_history_contract(contract_or_symbol)
        if contract is None:
            return []
        return self._request_daily_history_with_fallback(
            contract,
            lookback_days=lookback_days,
            use_rth=use_rth,
            end_datetime=end_datetime,
        )

    def average_daily_volume_from_history(self, contract_or_symbol, *, window: int = 20, use_rth: bool = True) -> tuple[Optional[int], Optional[int]]:
        bars = self.daily_bars_from_history(contract_or_symbol, lookback_days=max(window, 3), use_rth=use_rth)
        volumes = [_clean(getattr(bar, "volume", None)) for bar in bars]
        volumes = [int(v) for v in volumes if v is not None]
        if not volumes:
            return None, None
        sample = volumes[-min(window, len(volumes)):]
        return int(sum(sample) / len(sample)), len(sample)

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
