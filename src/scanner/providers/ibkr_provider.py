from __future__ import annotations

import re
from typing import Optional

import requests

from src.config.runtime_config import get_scanner_symbols
from src.ibkr.market_data_client import MarketDataClient

from .base import IntradayStats, ProviderConnectionError, QuoteData, ScannerDataProvider


class IbkrScannerProvider(ScannerDataProvider):
    source_name = "IBKR"

    def __init__(self, market_data_client: Optional[MarketDataClient] = None) -> None:
        self.market_data_client = market_data_client or MarketDataClient()
        self.last_scan_contracts: list[dict[str, Optional[object]]] = []

    def connect(self) -> None:
        try:
            self.market_data_client.connect()
        except Exception as exc:
            raise ProviderConnectionError(str(exc)) from exc

    def disconnect(self) -> None:
        self.market_data_client.disconnect()

    def get_top_gainers(
        self,
        limit: int,
        *,
        scan_code: str | None = None,
        region: str | None = None,
        instrument: str | None = None,
        exchanges: list[str] | None = None,
    ) -> list[dict[str, Optional[object]]]:
        scan_code_value = scan_code or "TOP_PERC_GAIN"
        contracts = self.market_data_client.scan_top_gainers(
            scan_code=scan_code_value,
            limit=limit,
            region=region,
            instrument=instrument,
            exchanges=exchanges,
        )
        if contracts:
            self.last_scan_contracts = contracts
            return contracts
        symbols = get_scanner_symbols(default=[])
        if not symbols:
            symbols = ["AAPL", "MSFT", "NVDA", "AMD", "TSLA"]
        self.last_scan_contracts = [
            {"symbol": symbol.upper(), "conId": None, "exchange": None}
            for symbol in symbols
        ]
        return self.last_scan_contracts[:limit]

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
            volume=snapshot.volume,
            timestamp_utc=snapshot.timestamp_utc,
            data_quality_flags=tuple(snapshot.data_quality_flags),
        )

    def get_prev_close(self, symbol: str) -> Optional[float]:
        snapshot = self.market_data_client.snapshot_stock(symbol)
        return snapshot.close

    def get_intraday_stats(self, symbol: str) -> IntradayStats:
        snapshot = self.market_data_client.snapshot_stock(symbol)
        volume = int(snapshot.volume) if snapshot.volume is not None else None
        return IntradayStats(
            current_intraday_volume=volume,
            current_volume_source_label="IBKR_SNAPSHOT",
            average_daily_volume_20d=None,
            average_daily_volume_window_days=None,
            relative_volume=None,
            relative_volume_category=None,
            volume_velocity_5m=None,
            volume_velocity_15m=None,
            volume_data_quality_flag="IBKR_SNAPSHOT",
        )

    def get_float(self, symbol: str) -> Optional[int]:
        symbol = symbol.upper()
        yahoo_float = self._fetch_float_yahoo(symbol)
        if yahoo_float is not None:
            return yahoo_float
        return self._fetch_float_finviz(symbol)

    @staticmethod
    def _fetch_float_yahoo(symbol: str) -> Optional[int]:
        url = (
            "https://query1.finance.yahoo.com/v10/finance/quoteSummary/"
            f"{symbol}?modules=defaultKeyStatistics"
        )
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=6,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return None
        try:
            stats = payload["quoteSummary"]["result"][0]["defaultKeyStatistics"]
            raw = stats.get("floatShares", {}).get("raw")
            return int(raw) if raw is not None else None
        except Exception:
            return None

    @staticmethod
    def _fetch_float_finviz(symbol: str) -> Optional[int]:
        url = f"https://finviz.com/quote.ashx?t={symbol}"
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=6,
            )
            response.raise_for_status()
            html = response.text
        except Exception:
            return None
        match = re.search(r">Float</td>\s*<td[^>]*>([^<]+)</td>", html)
        if not match:
            return None
        value = match.group(1).strip()
        return IbkrScannerProvider._parse_float_value(value)

    @staticmethod
    def _parse_float_value(value: str) -> Optional[int]:
        cleaned = value.replace(",", "").strip().upper()
        match = re.match(r"^([0-9]*\.?[0-9]+)([KMB]?)$", cleaned)
        if not match:
            return None
        amount = float(match.group(1))
        suffix = match.group(2)
        multiplier = 1.0
        if suffix == "K":
            multiplier = 1_000.0
        elif suffix == "M":
            multiplier = 1_000_000.0
        elif suffix == "B":
            multiplier = 1_000_000_000.0
        return int(amount * multiplier)
