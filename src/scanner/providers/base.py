from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence


class ProviderConnectionError(RuntimeError):
    """Raised when a data provider fails to connect."""


@dataclass(frozen=True)
class QuoteData:
    symbol: str
    bid: Optional[float]
    ask: Optional[float]
    last: Optional[float]
    vwap: Optional[float]
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    change_percent: Optional[float]
    volume: Optional[float]
    timestamp_utc: Optional[str]
    data_quality_flags: Sequence[str]
    market_data_type_requested: Optional[str] = None
    market_data_type_effective: Optional[str] = None
    has_valid_bid: Optional[bool] = None
    has_valid_ask: Optional[bool] = None
    has_valid_last: Optional[bool] = None
    has_valid_close: Optional[bool] = None
    has_valid_volume: Optional[bool] = None
    quote_integrity_state: Optional[str] = None
    integrity_flags: Sequence[str] = ()
    timeout_occurred: bool = False
    source_label: Optional[str] = None


@dataclass(frozen=True)
class IntradayStats:
    current_intraday_volume: Optional[int]
    current_volume_source_label: Optional[str]
    average_daily_volume_20d: Optional[int]
    average_daily_volume_window_days: Optional[int]
    relative_volume: Optional[float]
    relative_volume_category: Optional[str]
    volume_velocity_5m: Optional[int]
    volume_velocity_15m: Optional[int]
    volume_data_quality_flag: Optional[str]


class ScannerDataProvider(Protocol):
    source_name: str

    def connect(self) -> None:
        ...

    def disconnect(self) -> None:
        ...

    def get_top_gainers(self, limit: int, request=None) -> list[str]:
        ...

    def get_quote(self, symbol: str) -> QuoteData:
        ...

    def get_prev_close(self, symbol: str) -> Optional[float]:
        ...

    def get_intraday_stats(self, symbol: str) -> IntradayStats:
        ...

    def get_float(self, symbol: str) -> Optional[int]:
        ...

    def get_previous_rth_close(self, identity) -> Optional[float]:
        ...

    def get_average_daily_volume(self, identity, window: int) -> tuple[Optional[int], Optional[int]]:
        ...

    def get_daily_bars(self, identity, lookback_days: int):
        ...
