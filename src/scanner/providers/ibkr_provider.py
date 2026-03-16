from __future__ import annotations

from typing import Optional

import re

import requests

from src.runtime.async_runtime_bootstrap import safe_import_ib_insync

from src.config.runtime_config import get_ibkr_max_symbols_per_cycle, get_scanner_symbols
from src.adapters.brokers.ibkr.ibkr_connection_manager import (
    IbkrConnectionManager,
    get_shared_ibkr_connection_manager,
)
from src.ibkr.market_data_client import MarketDataClient
from src.data.fundamentals.float_provider import FloatProvider
from src.scanner.scanner_contract import ScannerRequest

from .base import IntradayStats, ProviderConnectionError, QuoteData, ScannerDataProvider


class IbkrScannerProvider(ScannerDataProvider):
    source_name = "IBKR"

    def __init__(
        self,
        connection_manager: Optional[IbkrConnectionManager] = None,
        market_data_client: Optional[MarketDataClient] = None,
    ) -> None:
        self.connection_manager = connection_manager or get_shared_ibkr_connection_manager(
            readonly_enabled=True
        )
        self.market_data_client = market_data_client or MarketDataClient(
            connection_manager=self.connection_manager,
            allow_direct_connection=False,
        )
        if getattr(self.market_data_client, "connection_manager", None) is None:
            raise RuntimeError(
                "IBKR connections must be created only by IBKRConnectionManager"
            )
        self.last_scan_details: dict[str, dict[str, Optional[str]]] = {}
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
        resolved_requested_top_n = min(limit, get_ibkr_max_symbols_per_cycle())

        instrument = request.instrument if request and request.instrument else "STK"
        instrument_source = "scanner_request" if request and request.instrument else "adapter_default"
        location_from_request = bool(request and request.location_code)
        location_code = (
            request.location_code if location_from_request else "STK.US"
        )
        location_source = "scanner_request" if location_from_request else "adapter_default"
        scan_code = request.ibkr_scan_code if request and request.ibkr_scan_code else "TOP_PERC_GAIN"
        scan_code_source = "scanner_request" if request and request.ibkr_scan_code else "adapter_default"
        above_price = (
            request.above_price
            if request and request.above_price is not None
            else 1
        )
        below_price = (
            request.below_price
            if request and request.below_price is not None
            else 20
        )
        _, _, ScannerSubscription = safe_import_ib_insync()
        subscription = ScannerSubscription(
            instrument=instrument,
            locationCode=location_code,
            scanCode=scan_code,
            numberOfRows=resolved_requested_top_n,
            abovePrice=above_price,
            belowPrice=below_price,
        )

        print(
            "[SCANNER][IBKR][SUBSCRIPTION] "
            f"instrument={instrument} instrument_source={instrument_source} "
            f"location={location_code} location_source={location_source} "
            f"scanCode={scan_code} scan_code_source={scan_code_source} "
            f"numberOfRows={resolved_requested_top_n} "
            f"abovePrice={above_price} belowPrice={below_price}"
        )

        scan_data = self.market_data_client.request_scanner_data(subscription)
        scan_items = scan_data or []
        self.last_scan_details = {}
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
            self.last_scan_details[symbol] = {
                "conId": getattr(contract, "conId", None),
                "tradingClass": getattr(contract, "tradingClass", None),
                "primaryExchange": getattr(contract, "primaryExchange", None),
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

        print(
            "[SCANNER][IBKR][RAW_ZERO] reason=BROKER_RETURNED_ZERO_CANDIDATES "
            f"requested_rows={resolved_requested_top_n} location={location_code} scanCode={scan_code}"
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
        snapshot = self.market_data_client.snapshot_stock(symbol)
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
            data_quality_flags=tuple(snapshot.data_quality_flags),
        )

    def get_prev_close(self, symbol: str) -> Optional[float]:
        prev_close = self.market_data_client.prev_close_from_history(symbol, use_rth=True)
        if prev_close is not None:
            return prev_close
        snapshot = self.market_data_client.snapshot_stock(symbol)
        return snapshot.close

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

        for provider_name, fetcher in (
            ("FINVIZ", self._fetch_finviz_float_detailed),
            ("YAHOO_FINANCE", self._fetch_yahoo_float_detailed),
        ):
            print(f"[FLOAT][FETCH_START] symbol={symbol} provider={provider_name}")
            value, reason = fetcher(symbol)
            if value is not None and value > 0:
                self.last_float_source = provider_name
                print(
                    f"[FLOAT][FETCH_OK] symbol={symbol} provider={provider_name} value={int(value)}"
                )
                return int(value)
            fail_reason = reason or "UNKNOWN"
            self.last_float_failures.append((provider_name, fail_reason))
            print(
                f"[FLOAT][FETCH_FAIL] symbol={symbol} provider={provider_name} reason={fail_reason}"
            )

        cache_provider = FloatProvider()
        cached_value, cached_source = cache_provider.get_float(symbol)
        self.last_float_failures.extend(list(cache_provider.last_float_failures))
        self.last_float_source = cached_source
        return cached_value

    def _average_daily_volume(self, symbol: str) -> tuple[Optional[int], Optional[int]]:
        contract = self.market_data_client.qualify_contract(symbol)
        if contract is None:
            return None, None
        try:
            bars = self.market_data_client.ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr="20 D",
                barSizeSetting="1 day",
                whatToShow="TRADES",
                useRTH=True,
                formatDate=1,
            )
        except Exception:
            return None, None
        if not bars:
            return None, None
        volumes = [getattr(bar, "volume", None) for bar in bars if getattr(bar, "volume", None)]
        if not volumes:
            return None, None
        avg_volume = int(sum(volumes) / len(volumes))
        return avg_volume, len(volumes)

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
