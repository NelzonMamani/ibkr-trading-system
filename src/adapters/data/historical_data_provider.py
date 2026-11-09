from __future__ import annotations

from typing import Sequence
from datetime import datetime, timezone
from dataclasses import replace
from src.ibkr.market_data_client import HistoricalDataResult, historical_result
from src.market_data.candidate_identity import CandidateIdentity

from src.adapters.brokers.ibkr.ibkr_connection_manager import get_shared_ibkr_connection_manager
from src.adapters.data.historical_bar_timeframes import resolve_intraday_timeframe_request
from src.strategies.common.candles.candle_types import Candle


def get_intraday_bars(*, symbol: str, timeframe: str = "1m", limit: int = 50) -> Sequence[Candle]:
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
            formatDate=2, # Intraday epoch UTC; never guess the TWS local timezone.
        )
    except Exception as exc:
        print(f"[HISTORICAL_BARS] symbol={symbol} timeframe={timeframe} limit={limit} error={exc}")
        return []

    history = historical_result(bars)
    if type(getattr(contract,"conId",None)) is not int or contract.conId<=0:
        history = replace(history,status="UNVERIFIED")
    normalized: list[Candle] = []
    for bar in history[-request.requested_bars:]:
        try:
            if any(isinstance(getattr(bar,k,None), bool) for k in ("open","high","low","close","volume")):
                continue
            raw_stamp = getattr(bar, "date", None)
            if isinstance(raw_stamp, (int,float)) or (isinstance(raw_stamp,str) and raw_stamp.isdigit()):
                if isinstance(raw_stamp,bool):
                    continue
                raw_stamp = datetime.fromtimestamp(float(raw_stamp),timezone.utc)
            normalized.append(
                Candle(
                    open=float(getattr(bar, "open")),
                    high=float(getattr(bar, "high")),
                    low=float(getattr(bar, "low")),
                    close=float(getattr(bar, "close")),
                    volume=float(getattr(bar, "volume", 0) or 0),
                    timestamp=raw_stamp,
                )
            )
        except (TypeError, ValueError, OverflowError, OSError):
            continue
    return replace(history, bars=tuple(normalized),
        contract_identity=CandidateIdentity.from_contract(contract, fallback_symbol=symbol))
