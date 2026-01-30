from __future__ import annotations

from typing import Optional

import re

import requests

from ib_insync import ScannerSubscription

from src.config.runtime_config import get_ibkr_max_symbols_per_cycle, get_scanner_symbols
from src.ibkr.market_data_client import MarketDataClient
from src.scanner.scanner_contract import ScannerRequest

from .base import IntradayStats, ProviderConnectionError, QuoteData, ScannerDataProvider


class IbkrScannerProvider(ScannerDataProvider):
    source_name = "IBKR"

    def __init__(self, market_data_client: Optional[MarketDataClient] = None) -> None:
        self.market_data_client = market_data_client or MarketDataClient()
        self.last_scan_details: dict[str, dict[str, Optional[str]]] = {}

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
        location_code = (
            request.location_code if request and request.location_code else "STK.US.MAJOR"
        )
        scan_code = request.ibkr_scan_code if request and request.ibkr_scan_code else "TOP_PERC_GAIN"
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
            f"instrument={instrument} location={location_code} "
            f"scanCode={scan_code} numberOfRows={resolved_requested_top_n} "
            f"abovePrice={above_price} belowPrice={below_price}"
        )

        scan_data = self.market_data_client.ib.reqScannerData(subscription)
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

        symbols = get_scanner_symbols(default=[])
        if not symbols:
            symbols = ["AAPL", "MSFT", "NVDA", "AMD", "TSLA"]
        symbols = [symbol.upper() for symbol in symbols][:limit]
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
        float_shares = self._fetch_yahoo_float(symbol)
        if float_shares:
            return float_shares
        return self._fetch_finviz_float(symbol)

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
        url = (
            "https://query1.finance.yahoo.com/v10/finance/quoteSummary/"
            f"{symbol}?modules=defaultKeyStatistics"
        )
        try:
            response = requests.get(
                url,
                timeout=5,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return None
        result = payload.get("quoteSummary", {}).get("result") or []
        if not result:
            return None
        stats = result[0].get("defaultKeyStatistics") or {}
        float_field = stats.get("floatShares") or {}
        raw_value = float_field.get("raw")
        if raw_value in {None, 0}:
            return None
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _fetch_finviz_float(symbol: str) -> Optional[int]:
        url = f"https://finviz.com/quote.ashx?t={symbol}"
        try:
            response = requests.get(
                url,
                timeout=5,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()
            text = response.text
        except Exception:
            return None
        match = re.search(r"Float</td>\s*<td[^>]*>\s*([^<]+)</td>", text, re.IGNORECASE)
        if not match:
            return None
        return _parse_finviz_float(match.group(1).strip())


def _parse_finviz_float(value: str) -> Optional[int]:
    match = re.match(r"^\s*([\d\.]+)\s*([KMB])?\s*$", value, re.IGNORECASE)
    if not match:
        return None
    number = float(match.group(1))
    suffix = match.group(2)
    multiplier = 1
    if suffix:
        suffix = suffix.upper()
        multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(suffix, 1)
    return int(number * multiplier)
