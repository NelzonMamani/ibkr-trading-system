from __future__ import annotations

from typing import Sequence
from datetime import datetime, timezone
from dataclasses import replace
from copy import deepcopy
from src.ibkr.market_data_client import (HistoricalDataResult, historical_result,
    historical_request_spec, historical_binding_result)
from src.market_data.candidate_identity import CandidateIdentity

from src.adapters.brokers.ibkr.ibkr_connection_manager import get_shared_ibkr_connection_manager
from src.adapters.data.historical_bar_timeframes import resolve_intraday_timeframe_request
from src.strategies.common.candles.candle_types import Candle


def normalize_intraday_bar_timestamp(raw_stamp):
    """Existing formatDate2 decoder; timezone-ambiguous text remains unqualified."""
    if isinstance(raw_stamp, bool):
        return None
    if isinstance(raw_stamp, (int, float)) or (isinstance(raw_stamp, str) and raw_stamp.isdigit()):
        return datetime.fromtimestamp(float(raw_stamp), timezone.utc)
    return raw_stamp


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
    history = historical_binding_result(history, contract, historical_request_spec(
        end_date_time="", duration_str=f"{request.duration_seconds} S",
        bar_size_setting=request.bar_size_setting, what_to_show="TRADES",
        use_rth=0, format_date=2, keep_up_to_date=False, chart_options=[]))
    if type(getattr(contract,"conId",None)) is not int or contract.conId<=0:
        history = replace(history,status="UNVERIFIED")
    if not history.completed:
        # Retain the existing qualified-identity compatibility projection, but
        # never replace a conflicting source identity or fabricate its frame.
        return replace(history, contract_identity=history.contract_identity or
            CandidateIdentity.from_contract(contract, fallback_symbol=symbol))
    normalized: list[Candle] = []
    raw_timestamps = []
    selected = tuple(history[-request.requested_bars:])
    raw_selected = tuple({key: deepcopy(getattr(bar, key, None))
        for key in ("date", "open", "high", "low", "close", "volume")} for bar in selected)
    for bar in selected:
        try:
            if any(isinstance(getattr(bar,k,None), bool) for k in ("open","high","low","close","volume")):
                continue
            raw_stamp = getattr(bar, "date", None)
            stamp = normalize_intraday_bar_timestamp(raw_stamp)
            if isinstance(raw_stamp, bool):
                continue
            normalized.append(
                Candle(
                    open=float(getattr(bar, "open")),
                    high=float(getattr(bar, "high")),
                    low=float(getattr(bar, "low")),
                    close=float(getattr(bar, "close")),
                    volume=float(getattr(bar, "volume", 0) or 0),
                    timestamp=stamp,
                )
            )
            raw_timestamps.append(raw_stamp)
        except (TypeError, ValueError, OverflowError, OSError):
            continue
    return replace(history, bars=tuple(normalized), normalized_raw_bar_timestamps=tuple(raw_timestamps),
        normalization_source_bars=raw_selected, normalization_selected_count=len(selected),
        normalization_rejected_count=len(selected)-len(normalized),
        contract_identity=history.contract_identity or CandidateIdentity.from_contract(contract, fallback_symbol=symbol))
