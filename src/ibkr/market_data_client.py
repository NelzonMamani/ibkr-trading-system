from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
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
        qualified = qualify_contracts_resilient(
            self._resolve_ib_client(),
            contract,
            timeout_seconds=self.snapshot_timeout_seconds,
            log_prefix="[EXECUTION][QUALIFY]",
        )
        if qualified:
            return qualified[0]
        raise RuntimeError(
            f"CONTRACT_QUALIFY_FAILED symbol={contract.symbol} error=NO_QUALIFIED_CONTRACT"
        )

    def qualifyContracts(self, *contracts):
        """
        Compatibility wrapper for ib_insync-style APIs used by the
        snapshot enrichment layer.
        """
        ib = self._resolve_ib_client()
        return qualify_contracts_resilient(
            ib,
            *contracts,
            timeout_seconds=self.snapshot_timeout_seconds,
            log_prefix="[EXECUTION][QUALIFY]",
        )

    def snapshot_stock(self, contract_or_symbol) -> MarketDataSnapshot:
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
            req_market_data_type = getattr(ib, "reqMarketDataType", None)
            if callable(req_market_data_type):
                req_market_data_type(_market_data_type_code(requested_type))
            tracked = _track_insync_snapshot_callbacks(ib)
            request_started_at = datetime.now(timezone.utc)
            ticker = ib.reqMktData(contract, genericTickList="", snapshot=True, regulatorySnapshot=False)
            _prepare_snapshot_ticker(ib, ticker, requested_type, tracked, request_started_at)
            started_at = time.monotonic()
            snapshot_complete = False
            completion_reason = "timeout"
            try:
                while True:
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
                    ib.waitOnUpdate(timeout=min(0.2, remaining))
                completed_at = datetime.now(timezone.utc)
                raw_fields = self._snapshot_debug_fields(ticker)
                returned_type = _returned_market_data_type(ticker)
                flags = _market_data_type_flags(returned_type)
                timestamp = _resolve_snapshot_timestamp(ticker)
                receipt = getattr(ticker, "receivedAt", None) or getattr(ticker, "time", None)
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
                    "request_id": getattr(ticker, "reqId", None),
                    "market_data_type_received_at_utc": (
                        ticker.marketDataTypeReceivedAt.isoformat()
                        if getattr(ticker, "marketDataTypeReceivedAt", None) else None
                    ),
                    "completion_reason": completion_reason,
                    "raw_fields": raw_fields,
                    "missing_fields": missing_fields,
                    **_snapshot_authority_metadata(ticker, raw_fields, completed_at=completed_at, completion_reason=completion_reason),
                }
                self.last_snapshot_debug["attempts"].append(attempt_debug)
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
        if snapshot_timestamp is None:
            final_flags.append("MD_TIMESTAMP_UNKNOWN")
        elif (datetime.now(timezone.utc) - snapshot_timestamp).total_seconds() > int(get_config("IBKR_SNAPSHOT_MAX_AGE_SECONDS")):
            final_flags.append("MD_STALE")
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
                f"symbol={getattr(contract, 'symbol', None)} conId={getattr(contract, 'conId', None)} "
                f"secType={getattr(contract, 'secType', None)} exchange={getattr(contract, 'exchange', None)} "
                f"primaryExchange={getattr(contract, 'primaryExchange', None)} tradingClass={getattr(contract, 'tradingClass', None)} "
                f"localSymbol={getattr(contract, 'localSymbol', None)} currency={getattr(contract, 'currency', None)} "
                f"label={attempt['label']} useRTH={attempt['useRTH']} endDateTime='{attempt['endDateTime']}' durationStr={attempt['durationStr']} whatToShow=TRADES"
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
                    f"symbol={getattr(contract, 'symbol', None)} conId={getattr(contract, 'conId', None)} label={attempt['label']} error={exc}"
                )
                bars = []
            print(
                "[IBKR][HIST_ATTEMPT_RESULT] "
                f"symbol={getattr(contract, 'symbol', None)} conId={getattr(contract, 'conId', None)} label={attempt['label']} raw_bar_count={len(bars)}"
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
            return []
        try:
            bars = self._resolve_ib_client().reqHistoricalData(
                contract,
                endDateTime=end_datetime,
                durationStr=f"{request.duration_seconds} S",
                barSizeSetting=request.bar_size_setting,
                whatToShow="TRADES",
                useRTH=use_rth,
                formatDate=1,
            ) or []
        except Exception as exc:
            print(
                "[IBKR][INTRADAY_HIST_FAIL] "
                f"symbol={getattr(contract, 'symbol', None)} timeframe={timeframe} "
                f"lookback_bars={request.requested_bars} error={exc}"
            )
            return []
        return list(bars[-request.requested_bars:])

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
            timestamp_utc=None,
            data_quality_flags=list(dict.fromkeys(flags + ["MD_TIMESTAMP_UNKNOWN"])),
            requested_market_data_type=self.market_data_type,
        )

    def snapshot_for_symbol(self, symbol: str) -> MarketDataSnapshot:
        return self.snapshot_stock(symbol)
