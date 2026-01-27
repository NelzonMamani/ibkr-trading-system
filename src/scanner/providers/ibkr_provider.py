from __future__ import annotations

from typing import Optional

from ib_insync import ScannerSubscription

from src.config.runtime_config import get_ibkr_max_symbols_per_cycle, get_scanner_symbols
from src.ibkr.market_data_client import MarketDataClient

from .base import IntradayStats, ProviderConnectionError, QuoteData, ScannerDataProvider


class IbkrScannerProvider(ScannerDataProvider):
    source_name = "IBKR"

    def __init__(self, market_data_client: Optional[MarketDataClient] = None) -> None:
        self.market_data_client = market_data_client or MarketDataClient()

    def connect(self) -> None:
        try:
            self.market_data_client.connect()
        except Exception as exc:
            raise ProviderConnectionError(str(exc)) from exc

    def disconnect(self) -> None:
        self.market_data_client.disconnect()

    def get_top_gainers(self, limit: int) -> list[str]:
        resolved_requested_top_n = min(limit, get_ibkr_max_symbols_per_cycle())

        subscription = ScannerSubscription(
            instrument="STK",
            locationCode="STK.US",
            scanCode="TOP_PERC_GAIN",
            numberOfRows=resolved_requested_top_n,
        )

        print(
            "[SCANNER][IBKR][SUBSCRIPTION] "
            f"instrument=STK location=STK.US "
            f"scanCode=TOP_PERC_GAIN numberOfRows={resolved_requested_top_n}"
        )

        scan_data = self.market_data_client.ib.reqScannerData(subscription)
        returned_rows = len(scan_data or [])
        print(
            "[SCANNER][IBKR] "
            f"requested_rows={resolved_requested_top_n} returned_rows={returned_rows}"
        )
        if returned_rows < resolved_requested_top_n:
            print(
                "[SCANNER][IBKR][WARN] "
                f"requested_rows={resolved_requested_top_n} returned_rows={returned_rows}"
            )

        symbols = [
            item.contractDetails.contract.symbol.upper()
            for item in (scan_data or [])
            if item.contractDetails and item.contractDetails.contract
        ]
        if symbols:
            return symbols

        symbols = get_scanner_symbols(default=[])
        if not symbols:
            symbols = ["AAPL", "MSFT", "NVDA", "AMD", "TSLA"]
        return [symbol.upper() for symbol in symbols][:limit]

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
        return None
