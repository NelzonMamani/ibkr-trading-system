from __future__ import annotations

import logging
from typing import Any, Optional

import re

import requests

from src.runtime.async_runtime_bootstrap import safe_import_ib_insync

from src.config.runtime_config import get_scanner_symbols
from src.adapters.brokers.ibkr.ibkr_connection_manager import (
    IbkrConnectionConfig,
    IbkrConnectionManager,
    get_shared_ibkr_connection_manager,
)
from src.ibkr.market_data_client import MarketDataClient
from src.data.fundamentals.float_provider import FloatProvider
from src.scanner.scanner_contract import ScannerRequest
from src.scanner.candidate_identity import CandidateIdentity

from .base import IntradayStats, ProviderConnectionError, QuoteData, ScannerDataProvider


SCAN_CODES = [
    "TOP_PERC_GAIN",
    "TOP_OPEN_PERC_GAIN",
    "HOT_BY_VOLUME",
    "MOST_ACTIVE",
]

LOCATIONS = [
    "STK.US.MAJOR",
    "STK.US.SMART",
    "STK.NASDAQ",
    "STK.NYSE",
]

PRICE_RANGES = [
    (1, 20),
    (1, 50),
    (1, 100),
]


def _with_preferred(preferred: str | None, defaults: list[str]) -> list[str]:
    values: list[str] = []
    if preferred:
        values.append(preferred)
    for value in defaults:
        if value not in values:
            values.append(value)
    return values


def robust_scan(
    client: MarketDataClient,
    scanner_subscription_cls: Any,
    instrument: str,
    preferred_scan_code: str | None = None,
    preferred_location: str | None = None,
    preferred_price_range: tuple[float, float] | None = None,
) -> tuple[list, dict[str, Any]]:
    scan_codes = _with_preferred(preferred_scan_code, SCAN_CODES)
    locations = _with_preferred(preferred_location, LOCATIONS)
    price_ranges = list(PRICE_RANGES)
    if preferred_price_range is not None and preferred_price_range not in price_ranges:
        price_ranges.insert(0, preferred_price_range)

    attempts = 0
    for price_low, price_high in price_ranges:
        for scan_code in scan_codes:
            for location in locations:
                attempts += 1
                sub = scanner_subscription_cls(
                    instrument=instrument,
                    locationCode=location,
                    scanCode=scan_code,
                    numberOfRows=50,
                    abovePrice=price_low,
                    belowPrice=price_high,
                )
                results = client.request_scanner_data(sub) or []
                print(
                    f"[SCANNER][ATTEMPT] scan={scan_code} "
                    f"loc={location} price={price_low}-{price_high} "
                    f"rows={len(results)}"
                )
                if len(results) > 0:
                    print("[SCANNER][SUCCESS]")
                    return results, {
                        "scan_code": scan_code,
                        "location": location,
                        "price_low": price_low,
                        "price_high": price_high,
                        "attempts": attempts,
                    }

    return [], {"attempts": attempts}



class IbkrScannerProvider(ScannerDataProvider):
    source_name = "IBKR"
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
        connection_manager: Optional[IbkrConnectionManager] = None,
        market_data_client: Optional[MarketDataClient] = None,
    ) -> None:
        if connection_manager is None and any(
            value is not None for value in (host, port, client_id)
        ):
            shared_manager = get_shared_ibkr_connection_manager(readonly_enabled=True)
            manager_config = shared_manager.config
            self.connection_manager = IbkrConnectionManager(
                IbkrConnectionConfig(
                    host=host or manager_config.host,
                    port=port or manager_config.port,
                    base_client_id=client_id or manager_config.base_client_id,
                    run_mode=manager_config.run_mode,
                    snapshot_timeout_seconds=manager_config.snapshot_timeout_seconds,
                    market_data_type=manager_config.market_data_type,
                    readonly_enabled=True,
                    max_client_id_retries=manager_config.max_client_id_retries,
                )
            )
        else:
            self.connection_manager = connection_manager or get_shared_ibkr_connection_manager(
                readonly_enabled=True
            )
        self.market_data_client = market_data_client or self.connection_manager.get_market_data_client()
        if getattr(self.market_data_client, "connection_manager", None) is None:
            raise RuntimeError(
                "IBKR connections must be created only by IBKRConnectionManager"
            )
        self.last_scan_details: dict[str, Any] = {}
        self.last_float_source: Optional[str] = None
        self.last_float_failures: list[tuple[str, str]] = []

    def connect(self) -> None:
        try:
            self.market_data_client.connect()
        except Exception as exc:
            print("STATE=DEGRADED")
            raise ProviderConnectionError(str(exc)) from exc

    def disconnect(self) -> None:
        self.market_data_client.disconnect()

    def get_top_gainers(
        self,
        limit: int,
        request: ScannerRequest | None = None,
    ) -> list[str]:
        resolved_requested_top_n = 50

        instrument = request.instrument if request and request.instrument else "STK"
        instrument_source = "scanner_request" if request and request.instrument else "adapter_default"
        location_code = request.location_code if request and request.location_code else "STK.US.MAJOR"
        scan_code = request.ibkr_scan_code if request and request.ibkr_scan_code else "TOP_PERC_GAIN"
        _, _, ScannerSubscription = safe_import_ib_insync()

        logger = logging.getLogger(__name__)

        print(
            "[SCANNER][IBKR][SUBSCRIPTION] "
            f"instrument={instrument} instrument_source={instrument_source} "
            f"location={location_code} scanCode={scan_code} "
            f"numberOfRows={resolved_requested_top_n}"
        )

        scan_items, scan_context = robust_scan(
            self.market_data_client,
            ScannerSubscription,
            instrument,
            preferred_scan_code=scan_code,
            preferred_location=location_code,
            preferred_price_range=(
                request.above_price if request and request.above_price is not None else 1,
                request.below_price if request and request.below_price is not None else 20,
            ),
        )
        retry_attempts = int(scan_context.get("attempts") or 0)
        retry_exhausted = len(scan_items) == 0
        if not retry_exhausted:
            logger.info(
                "[SCANNER][IBKR][SUCCESS] "
                f"using_location={scan_context.get('location')} symbols={len(scan_items)}"
            )

        symbol_details: dict[str, dict[str, Optional[str]]] = {}
        returned_rows = len(scan_items)
        print(
            "[SCANNER][IBKR] "
            f"requested_rows={resolved_requested_top_n} returned_rows={returned_rows}"
        )
        if returned_rows < resolved_requested_top_n:
            print(
                "[SCANNER][IBKR][WARN] "
                f"requested_rows={resolved_requested_top_n} returned_rows={returned_rows}"
            )

        symbols = []
        for item in scan_items:
            if not item.contractDetails or not item.contractDetails.contract:
                continue
            contract = item.contractDetails.contract
            symbol = contract.symbol.upper()
            symbols.append(symbol)
            details = getattr(item, "contractDetails", None)
            symbol_details[symbol] = {
                "conId": getattr(contract, "conId", None),
                "tradingClass": getattr(contract, "tradingClass", None),
                "primaryExchange": getattr(contract, "primaryExchange", None),
                "longName": getattr(details, "longName", None),
                "description": getattr(contract, "description", None),
            }
        self.last_scan_details = {
            "requested_location_code": location_code,
            "requested_scan_code": scan_code,
            "selected_location_code": scan_context.get("location"),
            "selected_scan_code": scan_context.get("scan_code"),
            "retry_attempts": retry_attempts,
            "retry_exhausted": retry_exhausted,
            "returned_rows": returned_rows,
            "symbols": symbols,
            "symbol_details": symbol_details,
        }
        if symbols:
            print(f"RAW_SCAN_SYMBOLS (N={len(symbols)}): {symbols}")
            for idx, item in enumerate(scan_items, start=1):
                details = getattr(item, "contractDetails", None)
                contract = details.contract if details else None
                symbol = contract.symbol.upper() if contract and contract.symbol else "NA"
                con_id = getattr(contract, "conId", None) if contract else None
                primary_exchange = (
                    getattr(contract, "primaryExchange", None) if contract else None
                )
                trading_class = getattr(contract, "tradingClass", None) if contract else None
                rank = getattr(item, "rank", None) or idx
                print(
                    "[SCANNER][IBKR][ROW] "
                    f"rank={rank} symbol={symbol} conId={con_id} "
                    f"primaryExchange={primary_exchange} tradingClass={trading_class}"
                )
            return symbols

        logger.error(
            "[SCANNER][FATAL] broker returned zero rows across all fallback locations"
        )
        logger.error(
            "[SCANNER][BROKER_EMPTY] IBKR returned zero symbols "
            "(scanCode=ALL_FALLBACKS, location=ALL_FALLBACKS, price_range=ALL_FALLBACKS)"
        )
        symbols = get_scanner_symbols(default=[])
        fallback_source = "config_scanner_symbols"
        if not symbols:
            symbols = ["AAPL", "MSFT", "NVDA", "AMD", "TSLA"]
            fallback_source = "hardcoded_teaching_fallback"
        symbols = [symbol.upper() for symbol in symbols][:limit]
        print(
            "[SCANNER][IBKR][RAW_ZERO] "
            f"local_fallback_source={fallback_source} fallback_symbol_count={len(symbols)}"
        )
        print(f"RAW_SCAN_SYMBOLS (N={len(symbols)}): {symbols}")
        return symbols

    def get_quote(self, symbol: str) -> QuoteData:
        contract = self._qualified_contract_for_symbol(symbol)
        print(
            "[IBKR][PROVIDER][QUOTE] "
            f"symbol={symbol} contract_symbol={getattr(contract, 'symbol', None) if contract is not None else None} "
            f"conId={getattr(contract, 'conId', None) if contract is not None else None} "
            f"exchange={getattr(contract, 'exchange', None) if contract is not None else None} "
            f"primaryExchange={getattr(contract, 'primaryExchange', None) if contract is not None else None}"
        )
        snapshot = self.market_data_client.snapshot_stock(contract if contract is not None else symbol)
        debug = getattr(self.market_data_client, "last_snapshot_debug", {}) or {}
        raw_fields = debug.get("raw_fields", {})
        waited_seconds = debug.get("waited_seconds", 0.0)
        timeout_occurred = bool(debug.get("timeout_occurred"))
        print(
            "[IBKR][PROVIDER][QUOTE][SNAPSHOT] "
            f"symbol={symbol} raw_fields={raw_fields} waited_seconds={waited_seconds} timeout_occurred={timeout_occurred}"
        )
        flags = list(snapshot.data_quality_flags)
        if "MD_TIMEOUT" in flags:
            flags = ["SNAPSHOT_TIMEOUT" if flag == "MD_TIMEOUT" else flag for flag in flags]
        return QuoteData(
            symbol=snapshot.symbol,
            bid=snapshot.bid,
            ask=snapshot.ask,
            last=snapshot.last,
            vwap=snapshot.vwap,
            open=snapshot.open,
            high=snapshot.high,
            low=snapshot.low,
            close=snapshot.close,
            change_percent=snapshot.change_percent,
            volume=snapshot.volume,
            timestamp_utc=snapshot.timestamp_utc,
            data_quality_flags=tuple(flags),
        )

    def qualifyContracts(self, *contracts):
        return self.market_data_client.qualifyContracts(*contracts)

    def get_prev_close(self, symbol: str) -> Optional[float]:
        prev_close = self.market_data_client.prev_close_from_history(symbol, use_rth=True)
        if prev_close is not None:
            return prev_close
        snapshot = self.market_data_client.snapshot_stock(symbol)
        return snapshot.close

    def _qualify_identity_contract(self, identity):
        candidate = self._candidate_identity(identity)
        contract = self._contract_from_candidate_identity(candidate)
        qualified = self.market_data_client.qualifyContracts(contract)
        if qualified:
            return qualified[0]
        if getattr(contract, "conId", None) not in {None, 0}:
            return contract
        return self.market_data_client.qualify_contract(getattr(candidate, "symbol", getattr(identity, "symbol", identity)))

    def _candidate_identity(self, identity) -> CandidateIdentity:
        if isinstance(identity, CandidateIdentity):
            return identity
        if hasattr(identity, "__dict__") or hasattr(identity, "con_id"):
            return CandidateIdentity(
                symbol=str(getattr(identity, "symbol", identity)).upper(),
                con_id=getattr(identity, "con_id", None) or getattr(identity, "conId", None),
                sec_type=getattr(identity, "sec_type", None) or getattr(identity, "secType", None) or "STK",
                exchange=getattr(identity, "exchange", None),
                primary_exchange=getattr(identity, "primary_exchange", None) or getattr(identity, "primaryExchange", None),
                trading_class=getattr(identity, "trading_class", None) or getattr(identity, "tradingClass", None),
                currency=getattr(identity, "currency", None) or "USD",
                local_symbol=getattr(identity, "local_symbol", None) or getattr(identity, "localSymbol", None),
            )
        return CandidateIdentity(symbol=str(identity).upper())

    def _contract_from_candidate_identity(self, identity: CandidateIdentity):
        _, Stock, Contract = safe_import_ib_insync()
        exchange = identity.exchange or "SMART"
        currency = identity.currency or "USD"
        symbol = identity.symbol or identity.local_symbol or identity.trading_class or ""
        contract = Stock(symbol, exchange, currency) if identity.sec_type in {None, "", "STK"} else Contract()
        contract.symbol = symbol
        contract.secType = identity.sec_type or "STK"
        contract.exchange = exchange
        contract.currency = currency
        if identity.con_id not in {None, 0}:
            contract.conId = int(identity.con_id)
        if identity.primary_exchange:
            contract.primaryExchange = identity.primary_exchange
        if identity.trading_class:
            contract.tradingClass = identity.trading_class
        if identity.local_symbol:
            contract.localSymbol = identity.local_symbol
        return contract

    def _qualified_contract_for_symbol(self, symbol: str):
        detail = ((self.last_scan_details or {}).get("symbol_details") or {}).get(symbol.upper(), {})
        identity = CandidateIdentity.from_mapping({"symbol": symbol.upper(), **detail})
        return self._qualify_identity_contract(identity)

    def get_previous_rth_close(self, identity) -> Optional[float]:
        contract = self._qualify_identity_contract(identity)
        return self.market_data_client.prev_close_from_history(contract if contract is not None else getattr(identity, "symbol", identity), use_rth=True)

    def get_average_daily_volume(self, identity, window: int) -> tuple[Optional[int], Optional[int]]:
        contract = self._qualify_identity_contract(identity)
        return self.market_data_client.average_daily_volume_from_history(contract if contract is not None else getattr(identity, "symbol", identity), window=window, use_rth=True)

    def get_daily_bars(self, identity, lookback_days: int, *, use_rth: bool = True, end_datetime: str = ""):
        candidate = self._candidate_identity(identity)
        print(
            "[IBKR][PROVIDER][HISTORY] "
            f"identity_key={candidate.key} symbol={candidate.symbol} conId={candidate.con_id} "
            f"exchange={candidate.exchange} primaryExchange={candidate.primary_exchange} "
            f"tradingClass={candidate.trading_class} localSymbol={candidate.local_symbol}"
        )
        contract = self._qualify_identity_contract(identity)
        print(
            "[IBKR][PROVIDER][HISTORY][CONTRACT] "
            f"symbol={getattr(contract, 'symbol', None) if contract is not None else None} "
            f"conId={getattr(contract, 'conId', None) if contract is not None else None} "
            f"exchange={getattr(contract, 'exchange', None) if contract is not None else None} "
            f"primaryExchange={getattr(contract, 'primaryExchange', None) if contract is not None else None}"
        )
        bars = self.market_data_client.daily_bars_from_history(
            contract if contract is not None else getattr(identity, "symbol", identity),
            lookback_days=lookback_days,
            use_rth=use_rth,
            end_datetime=end_datetime,
        )
        print(
            "[IBKR][PROVIDER][HISTORY][RESULT] "
            f"symbol={candidate.symbol} raw_bars={len(bars)} normalized_bars={len(bars)}"
        )
        return bars

    def get_intraday_stats(self, symbol: str) -> IntradayStats:
        snapshot = self.market_data_client.snapshot_stock(symbol)
        volume = int(snapshot.volume) if snapshot.volume is not None else None
        avg_volume = None
        window_days = None
        try:
            avg_volume, window_days = self._average_daily_volume(symbol)
        except Exception:
            avg_volume, window_days = None, None
        return IntradayStats(
            current_intraday_volume=volume,
            current_volume_source_label="IBKR_SNAPSHOT",
            average_daily_volume_20d=avg_volume,
            average_daily_volume_window_days=window_days,
            relative_volume=None,
            relative_volume_category=None,
            volume_velocity_5m=None,
            volume_velocity_15m=None,
            volume_data_quality_flag="IBKR_SNAPSHOT",
        )

    def get_float(self, symbol: str) -> Optional[int]:
        symbol = str(symbol or "").upper().strip()
        self.last_float_failures = []
        self.last_float_source = None
        fallback_applied = False
        cache_provider = FloatProvider(ttl_days=7)

        for provider_name, fetcher in (
            ("YAHOO", self._fetch_yahoo_float_detailed),
            ("FINVIZ", self._fetch_finviz_float_detailed),
        ):
            for attempt in range(1, 3):
                print(f"[FLOAT][FETCH_START] symbol={symbol} provider={provider_name} attempt={attempt}")
                value, reason = fetcher(symbol)
                if value is not None and value > 0:
                    cache_provider.record_discovery(symbol=symbol, value=int(value), source=provider_name)
                    self.last_float_source = provider_name
                    print(f"[FLOAT][SOURCE] symbol={symbol} source={provider_name}")
                    print(f"[FLOAT][CACHE_USED] symbol={symbol} used=False")
                    print(f"[FLOAT][FALLBACK_USED] symbol={symbol} used={fallback_applied}")
                    print(
                        f"[FLOAT][FETCH_OK] symbol={symbol} provider={provider_name} value={int(value)}"
                    )
                    return int(value)
                fail_reason = reason or "UNKNOWN"
                self.last_float_failures.append((provider_name, fail_reason))
                print(
                    f"[FLOAT][FAIL_REASON] symbol={symbol} provider={provider_name} "
                    f"attempt={attempt} reason={fail_reason}"
                )
                if fail_reason in {"FIELD_NOT_FOUND", "PARSE_ERROR"}:
                    break

        cached_value, cached_source = cache_provider.get_float(symbol)
        self.last_float_failures.extend(list(getattr(cache_provider, "last_float_failures", [])))
        self.last_float_source = cached_source
        cache_used = bool(getattr(cache_provider, "last_cache_used", cached_value is not None))
        fallback_applied = bool(getattr(cache_provider, "last_fallback_used", False)) or fallback_applied
        print(f"[FLOAT][SOURCE] symbol={symbol} source={cached_source}")
        print(f"[FLOAT][CACHE_USED] symbol={symbol} used={cache_used}")
        print(f"[FLOAT][FALLBACK_USED] symbol={symbol} used={fallback_applied}")
        return cached_value

    def _average_daily_volume(self, symbol: str) -> tuple[Optional[int], Optional[int]]:
        contract = self.market_data_client.qualify_contract(symbol)
        if contract is None:
            return None, None
        return self.market_data_client.average_daily_volume_from_history(contract, window=20, use_rth=True)

    @staticmethod
    def _fetch_yahoo_float(symbol: str) -> Optional[int]:
        value, _ = IbkrScannerProvider._fetch_yahoo_float_detailed(symbol)
        return value

    @staticmethod
    def _fetch_yahoo_float_detailed(symbol: str) -> tuple[Optional[int], str]:
        headers = {"User-Agent": "Mozilla/5.0"}
        urls = [
            (
                "QUOTE_SUMMARY_V10",
                "https://query1.finance.yahoo.com/v10/finance/quoteSummary/"
                f"{symbol}?modules=defaultKeyStatistics",
            ),
            (
                "QUOTE_SUMMARY_V11",
                "https://query2.finance.yahoo.com/v11/finance/quoteSummary/"
                f"{symbol}?modules=defaultKeyStatistics",
            ),
        ]
        request_failures = 0
        parse_failures = 0
        for _, url in urls:
            try:
                response = requests.get(url, timeout=5, headers=headers)
                response.raise_for_status()
                payload = response.json()
            except requests.RequestException:
                request_failures += 1
                continue
            except ValueError:
                parse_failures += 1
                continue
            parsed = _extract_yahoo_float(payload)
            if parsed is not None and parsed > 0:
                return parsed, "OK"
        if request_failures == len(urls):
            return None, "REQUEST_ERROR"
        if parse_failures == len(urls):
            return None, "PARSE_ERROR"
        return None, "FIELD_NOT_FOUND"

    @staticmethod
    def _fetch_finviz_float(symbol: str) -> Optional[int]:
        value, _ = IbkrScannerProvider._fetch_finviz_float_detailed(symbol)
        return value

    def _fetch_ibkr_float_detailed(self, symbol: str) -> tuple[Optional[int], str]:
        try:
            contract = self._qualified_contract_for_symbol(symbol)
            snapshot = self.market_data_client.snapshot_stock(contract if contract is not None else symbol)
        except Exception:
            return None, "REQUEST_ERROR"
        for field_name in ("sharesOutstanding", "floatShares", "float_shares"):
            parsed = _parse_shares_value(getattr(snapshot, field_name, None))
            if parsed is not None and parsed > 0:
                return parsed, "OK"
        return None, "FIELD_NOT_FOUND"

    @staticmethod
    def _fetch_finviz_float_detailed(symbol: str) -> tuple[Optional[int], str]:
        url = f"https://finviz.com/quote.ashx?t={symbol}"
        try:
            response = requests.get(
                url,
                timeout=5,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()
            text = response.text
        except requests.RequestException:
            return None, "REQUEST_ERROR"
        parsed = _extract_finviz_float(text)
        if parsed is None:
            return None, "FIELD_NOT_FOUND"
        return parsed, "OK"


def _parse_finviz_float(value: str) -> Optional[int]:
    return _parse_shares_value(value)


def _extract_finviz_float(html: str) -> Optional[int]:
    patterns = [
        r">\s*(?:Shs\s*)?Float\s*</td>\s*<td[^>]*>\s*([^<]+)</td>",
        r"\b(?:Shs\s*)?Float\b\s*</[^>]+>\s*<[^>]+>\s*([^<]+)",
        r'"(?:Shs\s*)?Float"\s*:\s*"([^\"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if not match:
            continue
        parsed = _parse_shares_value(match.group(1).strip())
        if parsed is not None and parsed > 0:
            return parsed
    return None


def _extract_yahoo_float(payload: dict) -> Optional[int]:
    quote_summary = payload.get("quoteSummary", {}) if isinstance(payload, dict) else {}
    result = quote_summary.get("result") if isinstance(quote_summary, dict) else None
    if not isinstance(result, list) or not result:
        return None
    root = result[0] if isinstance(result[0], dict) else {}
    stats = root.get("defaultKeyStatistics") if isinstance(root, dict) else None
    if isinstance(stats, dict):
        float_field = stats.get("floatShares")
        if isinstance(float_field, dict):
            parsed = _parse_shares_value(float_field.get("raw"))
            if parsed is None:
                parsed = _parse_shares_value(float_field.get("fmt"))
        else:
            parsed = _parse_shares_value(float_field)
        if parsed is not None and parsed > 0:
            return parsed
    summary_detail = root.get("summaryDetail") if isinstance(root, dict) else None
    if isinstance(summary_detail, dict):
        fallback_field = summary_detail.get("sharesOutstanding")
        if isinstance(fallback_field, dict):
            parsed = _parse_shares_value(fallback_field.get("raw"))
            if parsed is None:
                parsed = _parse_shares_value(fallback_field.get("fmt"))
        else:
            parsed = _parse_shares_value(fallback_field)
        if parsed is not None and parsed > 0:
            return parsed
    return None


def _parse_shares_value(value: object) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if float(value) > 0 else None
    text = str(value).strip()
    if not text:
        return None
    normalized = (
        text.replace("\u00a0", " ")
        .replace("\u202f", " ")
        .replace(",", "")
        .replace("shares", "")
        .replace("SHARES", "")
        .strip()
    )
    if normalized.upper() in {"N/A", "NA", "-", "--", "NONE", "NULL"}:
        return None
    match = re.match(r"^\s*([\d]*\.?[\d]+)\s*([KMB])?\s*$", normalized, re.IGNORECASE)
    if not match:
        return None
    try:
        number = float(match.group(1))
    except ValueError:
        return None
    suffix = match.group(2)
    multiplier = 1
    if suffix:
        suffix = suffix.upper()
        multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(suffix, 1)
    return int(number * multiplier) if number > 0 else None
