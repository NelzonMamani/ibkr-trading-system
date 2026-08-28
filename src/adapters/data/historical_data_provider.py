from __future__ import annotations

from typing import List

from src.adapters.brokers.ibkr.ibkr_connection_manager import get_shared_ibkr_connection_manager
from src.adapters.data.historical_bar_timeframes import resolve_intraday_timeframe_request
from src.strategies.common.candles.candle_types import Candle


def get_intraday_bars(*, symbol: str, timeframe: str = "1m", limit: int = 50) -> List[Candle]:
    """Fetch normalized intraday candles for pattern evaluation.

    Returns an empty list on any failure so callers can safely fall back to snapshots.
    """
    if limit <= 0:
        return []
    request = resolve_intraday_timeframe_request(timeframe=timeframe, requested_bars=limit)

    try:
        manager = get_shared_ibkr_connection_manager(readonly_enabled=True)
        client = manager.get_client()
        contract_details = client.resolve_contract(symbol)
        contract = getattr(contract_details, "contract", contract_details)
        # IBKR expects durationStr in seconds (S) or days (D), NOT minutes (M)
        bars = client.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=f"{request.duration_seconds} S",
            barSizeSetting=request.bar_size_setting,
            whatToShow="TRADES",
            useRTH=False,
            formatDate=1,
        ) or []
    except Exception as exc:
        print(f"[HISTORICAL_BARS] symbol={symbol} timeframe={timeframe} limit={limit} error={exc}")
        return []

    normalized: list[Candle] = []
    for bar in bars[-request.requested_bars:]:
        try:
            normalized.append(
                Candle(
                    open=float(getattr(bar, "open")),
                    high=float(getattr(bar, "high")),
                    low=float(getattr(bar, "low")),
                    close=float(getattr(bar, "close")),
                    volume=float(getattr(bar, "volume", 0) or 0),
                    timestamp=getattr(bar, "date", None),
                )
            )
        except (TypeError, ValueError):
            continue
    return normalized
