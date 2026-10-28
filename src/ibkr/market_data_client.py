from __future__ import annotations

from src.domain.quote_freshness import quote_time_rejection

from src.core.acquisition import AcquisitionCancelled, AcquisitionDeadlineExceeded, checkpoint, cycle_cache, contract_key, cooperative_await, bounded_timeout, historical_enrichment_attempt, history_enrichment, HISTORY_ATTEMPT_MAX_REQUESTS

import asyncio
import copy
from contextlib import nullcontext, contextmanager
from dataclasses import dataclass, field, replace
from collections.abc import Sequence
from datetime import datetime, timezone
import math
import json
import time
from typing import Any, Optional, TYPE_CHECKING
import threading

from src.runtime.async_runtime_bootstrap import safe_import_ib_insync
from src.adapters.data.historical_bar_timeframes import resolve_intraday_timeframe_request
from src.ibkr.contract_qualification import qualify_contracts_resilient
from src.ibkr.evidence_safety import sanitize


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


@dataclass(frozen=True)
class HistoricalDataResult(Sequence):
    """End-confirmed history facts. Incomplete partial bars are never exposed.

    Sequence compatibility preserves bar consumers, not completion authority:
    adapters must retain this object (or explicitly project its outcome).
    """
    status: str
    bars: tuple = ()
    end_received: bool = False
    request_id: int | None = None
    error_code: int | None = None
    partial_count: int = 0
    fallback_attempted: bool = False
    reused: bool = False

    def __post_init__(self):
        if self.status in {"COMPLETE_BARS", "COMPLETE_EMPTY"} and not self.end_received:
            object.__setattr__(self, "status", "UNVERIFIED")
        if self.status == "COMPLETE_EMPTY" and self.bars:
            object.__setattr__(self, "status", "UNVERIFIED")
        if not self.completed:
            object.__setattr__(self, "bars", ())
        else:
            object.__setattr__(self, "bars", tuple(self.bars))

    @property
    def completed(self):
        return self.end_received and self.status in {"COMPLETE_BARS", "COMPLETE_EMPTY"}

    def __len__(self):
        return len(self.bars)

    def __getitem__(self, index):
        return self.bars[index]


@dataclass(frozen=True)
class HistoricalVolumeResult(Sequence):
    average: int | None
    window: int | None
    history: HistoricalDataResult

    def __post_init__(self):
        if not isinstance(self.history, HistoricalDataResult):
            object.__setattr__(self, "history", HistoricalDataResult("UNVERIFIED"))
        if not self.history.completed or not self.history:
            object.__setattr__(self, "average", None)
            object.__setattr__(self, "window", None)

    def __len__(self):
        return 2

    def __getitem__(self, index):
        return (self.average, self.window)[index]


def historical_result(value):
    # A plain list has no end witness, including an empty list. Never manufacture
    # completion from truthiness, SDK return, publisher flags or a cached value.
    if isinstance(value, HistoricalDataResult):
        return value
    return HistoricalDataResult("UNVERIFIED")


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


def _returned_market_data_type(ticker) -> str:
    # A requested mode (and ib_insync's default value of 1) is not a callback.
    if getattr(ticker, "marketDataTypeConfirmed", False) is not True:
        return "UNKNOWN"
    return {1: "LIVE", 2: "FROZEN", 3: "DELAYED", 4: "DELAYED_FROZEN"}.get(
        getattr(ticker, "marketDataType", None), "UNKNOWN"
    )


def _market_data_type_flags(market_data_type: str | None) -> list[str]:
    normalized = (market_data_type or "UNKNOWN").upper()
    flags: list[str] = []
    if normalized not in {"LIVE", "FROZEN", "DELAYED", "DELAYED_FROZEN"}:
        flags.append("MD_TYPE_UNKNOWN")
    if normalized in {"DELAYED", "DELAYED_FROZEN"}:
        flags.append("MD_DELAYED")
    if normalized in {"FROZEN", "DELAYED_FROZEN"}:
        flags.append("MD_FROZEN")
    return flags


def _resolve_snapshot_timestamp(ticker) -> datetime | None:
    # ib_insync.time is transport receipt time, not the time of the market data.
    raw_time = getattr(ticker, "lastTime", None) or getattr(ticker, "rtTime", None)
    if raw_time is None and getattr(ticker, "timestampSource", None) == "BROKER":
        raw_time = getattr(ticker, "time", None)
    if isinstance(raw_time, datetime):
        if raw_time.tzinfo is None:
            raw_time = raw_time.replace(tzinfo=timezone.utc)
        return raw_time.astimezone(timezone.utc)
    return None


_PRICE_TICKS = {1: "bid", 2: "ask", 4: "last", 6: "high", 7: "low", 9: "close", 14: "open",
                66: "bid", 67: "ask", 68: "last", 72: "high", 73: "low", 75: "close", 76: "open"}
_SIZE_TICKS = {0: "bid_size", 3: "ask_size", 5: "last_size", 8: "volume",
               69: "bid_size", 70: "ask_size", 71: "last_size", 74: "volume"}


def _record_field_receipt(ticker, fields) -> None:
    received = datetime.now(timezone.utc)
    ticker.receivedAt = received
    if not hasattr(ticker, "fieldReceivedAt"):
        ticker.fieldReceivedAt = {}
    for name in fields:
        if name:
            ticker.fieldReceivedAt[name] = received.isoformat()


def _copy_snapshot_ticker(ticker):
    # Numeric/time attributes are immutable. Copy mutable authority metadata too,
    # without traversing SDK event handlers, contracts or synchronization objects.
    observed = copy.copy(ticker)
    observed.fieldReceivedAt = dict(getattr(ticker, "fieldReceivedAt", {}) or {})
    observed.brokerErrors = copy.deepcopy(getattr(ticker, "brokerErrors", []) or [])
    return observed


def _snapshot_authority_metadata(ticker, fields, *, completed_at, completion_reason):
    def utc(attr):
        value = getattr(ticker, attr, None)
        return value.isoformat() if isinstance(value, datetime) else None

    return {
        "market_data_type_confirmation_source": (
            "IBKR_MARKET_DATA_TYPE_CALLBACK"
            if _returned_market_data_type(ticker) != "UNKNOWN" else "UNKNOWN"
        ),
        "request_started_at_utc": utc("requestStartedAt"),
        "request_completed_at_utc": completed_at.isoformat(),
        "snapshot_completed_at_utc": utc("snapshotEndedAt"),
        "completion_reason": completion_reason,
        "field_availability": {name: value is not None for name, value in fields.items()},
        "field_received_at_utc": dict(getattr(ticker, "fieldReceivedAt", {})),
        # This is when absence was observed, never a fabricated market timestamp.
        "missing_fields_observed_at_utc": {
            name: completed_at.isoformat() for name, value in fields.items() if value is None
        },
        "broker_errors": list(getattr(ticker, "brokerErrors", [])),
    }


def _track_insync_snapshot_callbacks(ib):
    """Retain callback authority omitted by ib_insync's reusable Ticker objects."""
    wrapper = getattr(ib, "wrapper", None)
    if not isinstance(getattr(wrapper, "reqId2Ticker", None), dict):
        return None
    tracked = getattr(wrapper, "_snapshot_authority_requests", None)
    if tracked is not None:
        return tracked
    tracked = {}
    wrapper._snapshot_authority_requests = tracked
    original_type = wrapper.marketDataType
    original_end = wrapper.tickSnapshotEnd
    original_string = wrapper.tickString
    original_price = wrapper.priceSizeTick
    original_size = wrapper.tickSize
    original_error = wrapper.error

    def market_data_type(req_id, data_type):
        original_type(req_id, data_type)
        ticker = tracked.get(req_id)
        if ticker is not None:
            ticker.marketDataTypeConfirmed = data_type in {1, 2, 3, 4}
            ticker.marketDataTypeReceivedAt = datetime.now(timezone.utc)

    def snapshot_end(req_id):
        ticker = tracked.get(req_id)
        if ticker is not None:
            ticker.snapshotEnd = True
            ticker.snapshotEndedAt = datetime.now(timezone.utc)
        original_end(req_id)

    def tick_string(req_id, tick_type, value):
        original_string(req_id, tick_type, value)
        ticker = tracked.get(req_id)
        if ticker is not None and tick_type in {45, 88}:
            try:
                ticker.lastTime = datetime.fromtimestamp(float(value), timezone.utc)
            except (TypeError, ValueError, OverflowError, OSError):
                return
            _record_field_receipt(ticker, ["market_timestamp"])

    def price_size_tick(req_id, tick_type, price, size):
        original_price(req_id, tick_type, price, size)
        ticker = tracked.get(req_id)
        if ticker is not None and tick_type in _PRICE_TICKS:
            field = _PRICE_TICKS[tick_type]
            _record_field_receipt(ticker, [field] + ([field + "_size"] if field in {"bid", "ask", "last"} else []))

    def tick_size(req_id, tick_type, size):
        original_size(req_id, tick_type, size)
        ticker = tracked.get(req_id)
        if ticker is not None and tick_type in _SIZE_TICKS:
            _record_field_receipt(ticker, [_SIZE_TICKS[tick_type]])

    def error(req_id, code, message, *args):
        ticker = tracked.get(req_id)
        if ticker is not None:
            ticker.brokerErrors.append(sanitize({
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "req_id": req_id, "code": int(code), "message": message,
                "symbol": getattr(ticker.contract, "symbol", None),
                "request_type": "MARKET_SNAPSHOT",
            }))
        original_error(req_id, code, message, *args)

    wrapper.marketDataType = market_data_type
    wrapper.tickSnapshotEnd = snapshot_end
    wrapper.tickString = tick_string
    wrapper.priceSizeTick = price_size_tick
    wrapper.tickSize = tick_size
    wrapper.error = error
    return tracked


def _prepare_snapshot_ticker(ib, ticker, requested_type, tracked, started_at):
    if tracked is None and hasattr(ticker, "marketDataTypeConfirmed"):
        # Native adapter constructs a fresh ticker before sending the request.
        return
    # ib_insync reuses tickers: cached values and its default LIVE type cannot
    # certify the current request. Its event loop has not yielded yet. Keep
    # numeric defaults as NaN because the SDK performs numeric operations.
    for attr in (
        "bid", "ask", "last", "close", "volume", "open", "high", "low", "vwap",
        "bidSize", "askSize", "lastSize", "changePercent",
    ):
        setattr(ticker, attr, float("nan"))
    for attr in ("lastTime", "rtTime", "time", "receivedAt", "marketDataType",
                 "marketDataTypeReceivedAt", "snapshotEndedAt"):
        setattr(ticker, attr, None)
    ticker.snapshotEnd = False
    ticker.marketDataTypeConfirmed = False
    ticker.requestedMarketDataType = _market_data_type_code(requested_type)
    ticker.requestStartedAt = started_at
    ticker.fieldReceivedAt = {}
    ticker.brokerErrors = []
    if tracked is not None:
        req_id = ib.wrapper.ticker2ReqId["mktData"].get(ticker)
        if req_id is not None and ib.wrapper.reqId2Ticker.get(req_id) is ticker:
            ticker.reqId = req_id
            tracked[req_id] = ticker


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
    timestamp_utc: Optional[str]
    data_quality_flags: list[str] = field(default_factory=list)
    requested_market_data_type: str = "UNKNOWN"
    returned_market_data_type: str = "UNKNOWN"
    market_data_type_confirmed: bool = False
    timestamp_source: str = "UNKNOWN"
    received_at_utc: Optional[str] = None
    market_data_type_received_at_utc: Optional[str] = None
    request_id: Optional[int] = None
    snapshot_complete: bool = False
    market_data_type_confirmation_source: str = "UNKNOWN"
    request_started_at_utc: Optional[str] = None
    request_completed_at_utc: Optional[str] = None
    snapshot_completed_at_utc: Optional[str] = None
    completion_reason: str = "NOT_REQUESTED"
    field_availability: dict[str, bool] = field(default_factory=dict)
    field_received_at_utc: dict[str, str] = field(default_factory=dict)
    missing_fields_observed_at_utc: dict[str, str] = field(default_factory=dict)
    broker_errors: list[dict] = field(default_factory=list)
    snapshot_attempts: list[dict] = field(default_factory=list)


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
        self._broker_error_events: list[dict] = []
        self.last_snapshot_debug: dict[str, Any] = {}
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

    def _run_async(self, coro):
        """
        Robust async runner that works in:
        - main thread
        - ThreadPoolExecutor threads
        - ib_insync environments
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError as exc:
            if "There is no current event loop in thread" in str(exc):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            else:
                raise

        if loop.is_running():
            ib = self._resolve_ib_client()
            runner = getattr(ib, "run", None)
            if callable(runner):
                return runner(coro)
            raise RuntimeError(
                "No valid async runner available (loop running but no ib.run)"
            )

        return loop.run_until_complete(coro)

    def _on_ib_error(self, req_id, error_code, error_string, contract=None) -> None:
        event = sanitize({
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "req_id": req_id,
            "symbol": getattr(contract, "symbol", None),
            "code": int(error_code),
            "message": error_string,
        })
        self._broker_error_events.append(event)
        del self._broker_error_events[:-256]
        print(f"[IBKR][BROKER_ERROR] {json.dumps(event, sort_keys=True)}")
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
            disconnect = getattr(self.connection_manager, "disconnect", None)
            if callable(disconnect):
                try:
                    disconnect(reason="market_data_client_disconnect")
                except TypeError:
                    disconnect()
            self.ib = None
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
        from ib_insync import Contract

        contract = Contract(
            symbol=str(symbol or "").upper(),
            secType="STK",
            exchange="SMART",
            currency="USD",
        )
        qualified = self.qualifyContracts(contract)
        if qualified:
            return qualified[0]
        raise RuntimeError(
            f"CONTRACT_QUALIFY_FAILED symbol={contract.symbol} error=NO_QUALIFIED_CONTRACT"
        )

    def get_contract_reference_metadata(self, contract) -> dict:
        """Read existing adapter evidence without connecting or issuing requests."""
        reader = getattr(self.ib, "get_contract_reference_metadata", None)
        return reader(contract) if callable(reader) else {}

    def qualifyContracts(self, *contracts):
        """
        Compatibility wrapper for ib_insync-style APIs used by the
        snapshot enrichment layer.
        """
        checkpoint()
        cache = cycle_cache()
        result = []
        for contract in contracts:
            key = ("qualified", id(self), contract_key(contract))
            if cache is not None and key in cache:
                result.extend(cache[key])
                continue
            rows = qualify_contracts_resilient(
                self._resolve_ib_client(), contract,
                timeout_seconds=self.snapshot_timeout_seconds,
                log_prefix="[EXECUTION][QUALIFY]",
            )
            checkpoint()
            if cache is not None and rows:
                cache[key] = rows
                for row in rows:
                    cache[("qualified", id(self), contract_key(row))] = rows
            result.extend(rows)
        return result

    def snapshot_stock(self, contract_or_symbol, *, refresh: bool = False) -> MarketDataSnapshot:
        checkpoint()
        cache = cycle_cache()
        key = ("snapshot", id(self), contract_key(contract_or_symbol), self.market_data_type)
        if cache is not None and key in cache and not refresh:
            snapshot, debug = cache[key]
            self.last_snapshot_debug = debug
            # Reuse data, never the age decision from the earlier acquisition.
            # Keep the original broker timestamp, authority and request evidence.
            reason = quote_time_rejection(snapshot.timestamp_utc, getattr(snapshot, "timestamp_source", "UNKNOWN"),
                                          now=datetime.now(timezone.utc))
            if reason and reason not in snapshot.data_quality_flags:
                snapshot.data_quality_flags.append(reason)
            return snapshot
        snapshot = self._snapshot_stock_uncached(contract_or_symbol)
        checkpoint()
        reason = quote_time_rejection(snapshot.timestamp_utc, getattr(snapshot, "timestamp_source", "UNKNOWN"),
                                      now=datetime.now(timezone.utc))
        if reason and reason not in snapshot.data_quality_flags:
            snapshot.data_quality_flags.append(reason)
        if cache is not None and not any(flag in snapshot.data_quality_flags for flag in (
                "MD_TIMEOUT", "CONTRACT_QUALIFY_FAILED", "MD_EMPTY")):
            cache[key] = (snapshot, self.last_snapshot_debug)
        return snapshot

    def _snapshot_stock_uncached(self, contract_or_symbol) -> MarketDataSnapshot:
        base_flags = _market_data_type_flags("UNKNOWN")
        symbol = getattr(contract_or_symbol, "symbol", None) or str(contract_or_symbol or "").upper()
        self.last_snapshot_debug = {
            "requested_symbol": symbol,
            "requested_market_data_type": self.market_data_type,
            "returned_market_data_type": "UNKNOWN",
            "market_data_type_confirmed": False,
            "attempts": [],
            "requested_contract": {
                name: getattr(contract_or_symbol, name, None)
                for name in ("symbol", "conId", "exchange", "primaryExchange", "tradingClass", "localSymbol")
            } if not isinstance(contract_or_symbol, str) else None,
        }
        try:
            contract = self._canonicalize_history_contract(contract_or_symbol)
        except Exception as exc:
            self.last_snapshot_debug.update(
                {"qualification_error": str(exc), "timeout_occurred": False, "waited_seconds": 0.0}
            )
            return self._empty_snapshot(symbol, base_flags + ["CONTRACT_QUALIFY_FAILED"], error=str(exc))
        if contract is None:
            self.last_snapshot_debug.update(
                {"qualification_error": "contract_none", "timeout_occurred": False, "waited_seconds": 0.0}
            )
            return self._empty_snapshot(symbol, base_flags + ["CONTRACT_QUALIFY_FAILED"])
        self.last_snapshot_debug["contract"] = {
            name: getattr(contract, name, None)
            for name in ("symbol", "conId", "exchange", "primaryExchange", "tradingClass", "localSymbol")
        }
        ib = self._resolve_ib_client()
        attempts = [(self.market_data_type, "primary"), (self.market_data_type, "snapshot_retry")]
        if (self.market_data_type or "").upper() not in {"DELAYED", "DELAYED_FROZEN"}:
            attempts.append(("DELAYED", "delayed_fallback"))
        best_fields = None
        best_debug = None
        best_score = (-1, -1, -1, -1)
        final_flags = list(base_flags)
        snapshot_timestamp = None
        received_at = None
        required_fields = ("bid", "ask", "last", "close", "volume")
        for attempt_index, (requested_type, attempt_label) in enumerate(attempts, start=1):
            checkpoint()
            req_market_data_type = getattr(ib, "reqMarketDataType", None)
            if callable(req_market_data_type):
                req_market_data_type(_market_data_type_code(requested_type))
            tracked = _track_insync_snapshot_callbacks(ib)
            request_started_at = datetime.now(timezone.utc)
            checkpoint()
            ticker = ib.reqMktData(contract, genericTickList="", snapshot=True, regulatorySnapshot=False)
            _prepare_snapshot_ticker(ib, ticker, requested_type, tracked, request_started_at)
            started_at = time.monotonic()
            snapshot_complete = False
            completion_reason = "timeout"
            attempt_finished = False
            try:
                while True:
                    checkpoint()
                    if self._ticker_snapshot_complete(ticker):
                        snapshot_complete = True
                        completion_reason = "snapshot_end"
                        break
                    if self._ticker_has_required_snapshot(ticker) and _returned_market_data_type(ticker) != "UNKNOWN":
                        completion_reason = "required_fields"
                        break
                    remaining = self.snapshot_timeout_seconds - (time.monotonic() - started_at)
                    if remaining <= 0:
                        break
                    ib.waitOnUpdate(timeout=bounded_timeout(min(0.2, remaining)))
                # Native callbacks run on the reader thread under this lock.
                # ib_insync callbacks share this event loop: copy without yielding.
                with getattr(ib, "_lock", None) or nullcontext():
                    observed = _copy_snapshot_ticker(ticker)
                    completed_at = datetime.now(timezone.utc)
                raw_fields = self._snapshot_debug_fields(observed)
                returned_type = _returned_market_data_type(observed)
                flags = _market_data_type_flags(returned_type)
                timestamp = _resolve_snapshot_timestamp(observed)
                receipt = getattr(observed, "receivedAt", None) or getattr(observed, "time", None)
                if not isinstance(receipt, datetime):
                    receipt = None
                missing_fields = [name for name in required_fields if raw_fields.get(name) is None]
                attempt_debug = {
                    "attempt": attempt_index,
                    "label": attempt_label,
                    "market_data_type": returned_type,
                    "requested_market_data_type": requested_type,
                    "returned_market_data_type": returned_type,
                    "market_data_type_confirmed": returned_type != "UNKNOWN",
                    "waited_seconds": round(time.monotonic() - started_at, 3),
                    "timeout_occurred": completion_reason == "timeout",
                    "snapshot_complete": snapshot_complete,
                    "request_id": getattr(observed, "reqId", None),
                    "market_data_type_received_at_utc": (
                        observed.marketDataTypeReceivedAt.isoformat()
                        if getattr(observed, "marketDataTypeReceivedAt", None) else None
                    ),
                    "completion_reason": completion_reason,
                    "raw_fields": raw_fields,
                    "missing_fields": missing_fields,
                    **_snapshot_authority_metadata(observed, raw_fields, completed_at=completed_at, completion_reason=completion_reason),
                }
                self.last_snapshot_debug["attempts"].append(attempt_debug)
                attempt_finished = True
                if completion_reason == "timeout":
                    flags.append("MD_TIMEOUT")
                if not snapshot_complete:
                    flags.append("MD_SNAPSHOT_INCOMPLETE")
                score = (len(required_fields) - len(missing_fields), int(returned_type != "UNKNOWN"), int(snapshot_complete), sum(v is not None for v in raw_fields.values()))
                if score > best_score:
                    best_score = score
                    best_fields = dict(raw_fields)
                    best_debug = dict(attempt_debug)
                    final_flags = flags
                    snapshot_timestamp = timestamp
                    received_at = receipt
            finally:
                record_completion = getattr(ib, "record_quote_completion", None)
                if callable(record_completion):
                    # An exception/stop must not be mislabeled a measured timeout.
                    reason = completion_reason if attempt_finished else "interrupted"
                    record_completion(getattr(ticker, "reqId", None), reason)
                # Copy all result fields first; cancel may remove or mutate ticker state.
                if tracked is not None:
                    req_id = getattr(ticker, "reqId", None)
                    tracked.pop(req_id, None)
                    if ib.wrapper.reqId2Ticker.get(req_id) is ticker:
                        # ib_insync leaves this mapping after endTicker. Removing
                        # our request prevents late ticks mutating a reused Ticker.
                        ib.wrapper.reqId2Ticker.pop(req_id, None)
                if tracked is not None and self._ticker_snapshot_complete(ticker):
                    ib.wrapper.endTicker(ticker, "mktData")
                else:
                    ib.cancelMktData(contract)
            if not missing_fields and returned_type != "UNKNOWN":
                break
            print(
                f"[SNAPSHOT][RETRY] symbol={symbol} attempt={attempt_index}/{len(attempts)} "
                f"label={attempt_label} missing={missing_fields} requested_type={requested_type} returned_type={returned_type}"
            )
        if best_fields is None or best_debug is None:
            return self._empty_snapshot(symbol, base_flags + ["MD_EMPTY"])
        self.last_snapshot_debug.update(best_debug)
        reason = quote_time_rejection(snapshot_timestamp, "LAST_TRADE" if snapshot_timestamp is not None else "UNKNOWN",
                                      now=datetime.now(timezone.utc))
        if reason:
            final_flags.append(reason)
        if any(event["code"] == 10197 for attempt in self.last_snapshot_debug["attempts"] for event in attempt["broker_errors"]):
            final_flags.append("MD_CONFLICT_10197")
        if all(best_fields[name] is None for name in ("bid", "ask", "last")):
            final_flags.append("MD_EMPTY")
        for name in required_fields:
            if best_fields[name] is None:
                final_flags.append(f"MD_MISSING_{name.upper()}")
        bid, ask = best_fields["bid"], best_fields["ask"]
        timestamp_source = "LAST_TRADE" if snapshot_timestamp is not None else "UNKNOWN"
        self.last_snapshot_debug.update({
            "timestamp_source": timestamp_source,
            "timestamp_utc": snapshot_timestamp.isoformat() if snapshot_timestamp else None,
            "received_at_utc": received_at.isoformat() if received_at else None,
        })
        return MarketDataSnapshot(
            symbol=symbol,
            bid=bid,
            ask=ask,
            last=best_fields["last"],
            bid_size=best_fields["bid_size"],
            ask_size=best_fields["ask_size"],
            last_size=best_fields["last_size"],
            volume=best_fields["volume"],
            vwap=best_fields["vwap"],
            open=best_fields["open"],
            high=best_fields["high"],
            low=best_fields["low"],
            close=best_fields["close"],
            change_percent=best_fields["change_percent"],
            spread=(ask - bid) if bid is not None and ask is not None else None,
            timestamp_utc=snapshot_timestamp.isoformat() if snapshot_timestamp else None,
            data_quality_flags=list(dict.fromkeys(final_flags)),
            requested_market_data_type=best_debug["requested_market_data_type"],
            returned_market_data_type=best_debug["returned_market_data_type"],
            market_data_type_confirmed=best_debug["market_data_type_confirmed"],
            timestamp_source=timestamp_source,
            received_at_utc=received_at.isoformat() if received_at else None,
            market_data_type_received_at_utc=best_debug["market_data_type_received_at_utc"],
            request_id=best_debug["request_id"],
            snapshot_complete=best_debug["snapshot_complete"],
            **{key: best_debug[key] for key in (
                "market_data_type_confirmation_source", "request_started_at_utc",
                "request_completed_at_utc", "snapshot_completed_at_utc", "completion_reason",
                "field_availability", "field_received_at_utc", "missing_fields_observed_at_utc",
                "broker_errors",
            )},
            snapshot_attempts=list(self.last_snapshot_debug["attempts"]),
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
        fields = MarketDataClient._snapshot_debug_fields(ticker)
        return all(fields[name] is not None for name in ("bid", "ask", "last", "close", "volume"))

    @staticmethod
    def _ticker_snapshot_complete(ticker) -> bool:
        return bool(getattr(ticker, "snapshotEnd", False))

    @staticmethod
    def _snapshot_debug_fields(ticker) -> dict[str, Optional[float]]:
        fields = {
            name: _clean(getattr(ticker, name, None))
            for name in ("bid", "ask", "last", "close", "volume", "open", "high", "low", "vwap")
        }
        for name in ("bid", "ask", "last", "close", "open", "high", "low", "vwap"):
            if fields[name] is not None and fields[name] <= 0:
                fields[name] = None
        if fields["volume"] is not None and fields["volume"] < 0:
            fields["volume"] = None
        fields.update({
            name: _clean(getattr(ticker, attr, None))
            for name, attr in (("bid_size", "bidSize"), ("ask_size", "askSize"), ("last_size", "lastSize"), ("change_percent", "changePercent"))
        })
        for name in ("bid_size", "ask_size", "last_size"):
            if fields[name] is not None and fields[name] < 0:
                fields[name] = None
        return fields

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

    @history_enrichment
    def _request_daily_history_with_fallback(self, contract, *, lookback_days: int, use_rth: bool = True, end_datetime: str = ""):
        return historical_result(self._daily_history_uncached(contract,
            lookback_days=lookback_days, use_rth=use_rth, end_datetime=end_datetime))

    def _history_request(self, contract, **params):
        checkpoint()
        with historical_enrichment_attempt() as cache:
            try:
                client = self._resolve_ib_client()
            except Exception:
                return HistoricalDataResult("DISCONNECTED")
            if callable(getattr(client, "isConnected", None)) and not client.isConnected():
                return HistoricalDataResult("DISCONNECTED")
            key = (id(self), id(client), getattr(client, "_position_connection_epoch", None),
                   contract_key(contract), tuple(sorted(params.items())), False, ())
            with cache.lock:
                if cache.closed:
                    return HistoricalDataResult("ATTEMPT_CLOSED")
                if key in cache:
                    value = cache[key]
                    conflict = getattr(client, "_request_id_conflicted", None)
                    if value.request_id is not None and callable(conflict) and conflict(value.request_id):
                        value = HistoricalDataResult("REQUEST_ID_CONFLICT", request_id=value.request_id)
                        cache[key] = value
                    result = replace(value, reused=True)
                    print(f"[IBKR][HIST_REUSE] outcome={result.status} req_id={result.request_id}")
                    return result
                if len(cache) >= HISTORY_ATTEMPT_MAX_REQUESTS:
                    return HistoricalDataResult("ATTEMPT_CAPACITY")
                # Reserve before dispatch: reentrant/concurrent consumers cannot
                # create another send or renew the owner's deadline.
                cache[key] = HistoricalDataResult("IN_PROGRESS")
            try:
                if callable(getattr(client, "reqHistoricalDataAsync", None)):
                    result = self._run_async(cooperative_await(self._cancellable_insync_history(client, contract, **params)))
                else:
                    result = client.reqHistoricalData(contract, **params)
                result = historical_result(result)
            except (AcquisitionCancelled, AcquisitionDeadlineExceeded) as exc:
                with cache.lock:
                    if not cache.closed:
                        cache[key] = HistoricalDataResult("CANCELLED" if isinstance(exc, AcquisitionCancelled) else "TIMEOUT")
                raise
            except Exception:
                result = HistoricalDataResult("ERROR")
            checkpoint()
            with cache.lock:
                if cache.closed:
                    return HistoricalDataResult("ATTEMPT_CLOSED")
                cache[key] = result
            return result

    def _daily_history_uncached(self, contract, *, lookback_days: int, use_rth: bool = True, end_datetime: str = ""):
        result = self._history_request(contract, endDateTime=end_datetime,
            durationStr=f"{max(lookback_days, 3)} D", barSizeSetting="1 day",
            whatToShow="TRADES", useRTH=use_rth, formatDate=1)
        # Deliberate retry-policy change: unavailable is not confirmed absence.
        # Only an end-confirmed empty primary may request the existing fallback.
        if result.status == "COMPLETE_EMPTY" and result.completed and use_rth:
            explicit_end = end_datetime or f"{datetime.now().strftime('%Y%m%d')} 09:29:59 US/Eastern"
            result = self._history_request(contract, endDateTime=explicit_end,
                durationStr=f"{max(lookback_days, 3)} D", barSizeSetting="1 day",
                whatToShow="TRADES", useRTH=False, formatDate=1)
            result = replace(result, fallback_attempted=True)
        print(f"[IBKR][HIST_ATTEMPT_RESULT] symbol={getattr(contract, 'symbol', None)} "
              f"outcome={result.status} end_received={result.end_received} bars={len(result)}")
        return result

    @contextmanager
    def _insync_history_completion(self, wrapper, req_id, state):
        # ib_insync resolves request futures for BOTH end and error. Observe the
        # actual per-request callbacks; a resolved list/future is not an end witness.
        # All registration/restoration runs on its owning event loop without await.
        tracker = getattr(wrapper, "_ross_history_completion", None)
        if tracker is None:
            original_end = getattr(wrapper, "historicalDataEnd", None)
            original_error = getattr(wrapper, "error", None)
            if not callable(original_end) or not callable(original_error):
                yield False
                return
            tracker = {"owners": {}, "end": original_end, "error": original_error,
                       "end_instance": "historicalDataEnd" in vars(wrapper),
                       "error_instance": "error" in vars(wrapper)}
            def ended(request_id, *args):
                owner = tracker["owners"].get(request_id)
                if owner is not None and owner["status"] == "PENDING" and time.monotonic() <= owner["deadline"]:
                    owner.update(status="COMPLETE", end_received=True)
                return original_end(request_id, *args)
            def errored(request_id, error_code, *args, **kwargs):
                owner = tracker["owners"].get(request_id)
                if owner is not None and owner["status"] == "PENDING":
                    owner.update(status="ERROR", error_code=error_code)
                return original_error(request_id, error_code, *args, **kwargs)
            tracker.update(end_hook=ended, error_hook=errored)
            wrapper._ross_history_completion = tracker
            wrapper.historicalDataEnd = ended
            wrapper.error = errored
        if req_id in tracker["owners"] or len(tracker["owners"]) >= 128:
            yield False
            return
        tracker["owners"][req_id] = state
        try:
            yield True
        finally:
            if tracker["owners"].get(req_id) is state:
                tracker["owners"].pop(req_id, None)
            if not tracker["owners"]:
                if wrapper.historicalDataEnd is tracker["end_hook"]:
                    if tracker["end_instance"]:
                        wrapper.historicalDataEnd = tracker["end"]
                    else:
                        del wrapper.historicalDataEnd
                if wrapper.error is tracker["error_hook"]:
                    if tracker["error_instance"]:
                        wrapper.error = tracker["error"]
                    else:
                        del wrapper.error
                del wrapper._ross_history_completion

    async def _cancellable_insync_history(self, ib, contract, **params):
        """Own one ib_insync history request so cancellation also stops its wire work.

        Preserve the synchronous IB history defaults (including its 60s timeout).
        reqHistoricalDataAsync does not cancel wire work on CancelledError.
        """
        from ib_insync import BarDataList, util
        from src.core.acquisition import AcquisitionCancelled
        req_id = ib.client.getReqId()
        bars = BarDataList()
        bars.reqId, bars.contract = req_id, contract
        for key, value in {**params, "keepUpToDate": False, "chartOptions": []}.items():
            setattr(bars, key, value)
        state = {"status": "PENDING", "end_received": False, "error_code": None,
                 "deadline": time.monotonic() + 60}
        future = None
        sent = False
        epoch = getattr(ib.client, "_startTime", None)
        if req_id in getattr(ib.wrapper, "_futures", {}):
            return HistoricalDataResult("REQUEST_ID_CONFLICT", request_id=req_id)
        with self._insync_history_completion(ib.wrapper, req_id, state) as observed:
            if not observed:
                return HistoricalDataResult("UNVERIFIED", request_id=req_id)
            try:
                future = ib.wrapper.startReq(req_id, contract, container=bars)
                checkpoint()
                sent = True
                ib.client.reqHistoricalData(
                    req_id, contract, util.formatIBDatetime(params["endDateTime"]),
                    params["durationStr"], params["barSizeSetting"], params["whatToShow"],
                    params["useRTH"], params["formatDate"], False, [])
                await asyncio.wait_for(future, 60)
                if state["status"] == "COMPLETE":
                    state["status"] = "COMPLETE_BARS" if bars else "COMPLETE_EMPTY"
                elif state["status"] == "PENDING":
                    state["status"] = "UNVERIFIED"
            except asyncio.TimeoutError:
                state["status"] = "TIMEOUT"
            except (asyncio.CancelledError, AcquisitionCancelled):
                state["status"] = "CANCELLED"
                raise
            except AcquisitionDeadlineExceeded:
                state["status"] = "TIMEOUT"
                raise
            except Exception as exc:
                connected = getattr(ib, "isConnected", lambda: True)()
                state["status"] = "DISCONNECTED" if isinstance(exc, ConnectionError) or not connected else "ERROR"
            finally:
                # Retire the result container before SDK cancellation can deliver
                # a synchronous/late callback. Preserve the original stop/error.
                futures = getattr(ib.wrapper, "_futures", {})
                current = futures.get(req_id)
                foreign = current is not None and current is not future
                if future is not None and current is future:
                    if not future.done():
                        future.cancel()
                    ib.wrapper._endReq(req_id)
                # SDK error completion may already remove the future while
                # leaving our bars. Never remove a newer/foreign container.
                results = getattr(ib.wrapper, "_results", {})
                if results.get(req_id) is bars:
                    results.pop(req_id, None)
                contracts = getattr(ib.wrapper, "_reqId2Contract", {})
                if not foreign and contracts.get(req_id) is contract:
                    contracts.pop(req_id, None)
                if futures.get(req_id) is future:
                    futures.pop(req_id, None)
                same_epoch = epoch == getattr(ib.client, "_startTime", None)
                if sent and not state["end_received"] and state["status"] != "DISCONNECTED" and not foreign and same_epoch:
                    try:
                        ib.client.cancelHistoricalData(req_id)
                    except Exception as exc:
                        print(f"[IBKR][HIST_CANCEL_ERROR] req_id={req_id} error_type={type(exc).__name__}")
        return HistoricalDataResult(state["status"], tuple(bars), state["end_received"],
                                    req_id, state["error_code"], len(bars) if not state["end_received"] else 0)

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
            return HistoricalDataResult("UNVERIFIED")
        return self._request_daily_history_with_fallback(
            contract,
            lookback_days=lookback_days,
            use_rth=use_rth,
            end_datetime=end_datetime,
        )

    def intraday_bars_from_history(
        self,
        contract_or_symbol,
        *,
        timeframe: str = "1m",
        lookback_bars: int = 10,
        use_rth: bool = False,
        end_datetime: str = "",
    ):
        request = resolve_intraday_timeframe_request(
            timeframe=timeframe,
            requested_bars=lookback_bars,
        )
        contract = self._canonicalize_history_contract(contract_or_symbol)
        if contract is None:
            return HistoricalDataResult("UNVERIFIED")
        bars = self._history_request(contract, endDateTime=end_datetime,
            durationStr=f"{request.duration_seconds} S", barSizeSetting=request.bar_size_setting,
            whatToShow="TRADES", useRTH=use_rth, formatDate=1)
        return replace(bars, bars=tuple(bars.bars[-request.requested_bars:]))

    def average_daily_volume_from_history(self, contract_or_symbol, *, window: int = 20, use_rth: bool = True) -> tuple[Optional[int], Optional[int]]:
        bars = self.daily_bars_from_history(contract_or_symbol, lookback_days=max(window, 3), use_rth=use_rth)
        volumes = [_clean(getattr(bar, "volume", None)) for bar in bars]
        volumes = [int(v) for v in volumes if v is not None]
        if not volumes:
            return HistoricalVolumeResult(None, None, bars)
        sample = volumes[-min(window, len(volumes)):]
        return HistoricalVolumeResult(int(sum(sample) / len(sample)), len(sample), bars)

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
            timestamp_utc=None,
            data_quality_flags=list(dict.fromkeys(flags + ["MD_TIMESTAMP_UNKNOWN"])),
            requested_market_data_type=self.market_data_type,
        )

    def snapshot_for_symbol(self, symbol: str) -> MarketDataSnapshot:
        return self.snapshot_stock(symbol)
