from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    bid: Optional[float]
    ask: Optional[float]
    last: Optional[float]
    asof_utc: datetime
    volume: Optional[float] = None
    source: str = "IBKR"
    market_data_type: str = "UNKNOWN"
    requested_market_data_type: str = "UNKNOWN"
    returned_market_data_type: str = "UNKNOWN"
    market_data_type_confirmed: bool = False
    # asof_utc retains its acquisition-time contract; only this field is a
    # broker-provided market timestamp.
    market_timestamp_utc: Optional[datetime] = None
    timestamp_source: str = "UNKNOWN"
    received_at_utc: Optional[datetime] = None
    market_data_type_received_at_utc: Optional[datetime] = None
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
    close: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    bid_size: Optional[float] = None
    ask_size: Optional[float] = None
    last_size: Optional[float] = None
    data_quality_flags: tuple[str, ...] = field(default_factory=tuple)
