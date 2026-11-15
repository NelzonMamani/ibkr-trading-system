from __future__ import annotations

from typing import Sequence
from datetime import datetime, timezone
from dataclasses import replace
from copy import deepcopy
from src.ibkr.market_data_client import (HistoricalDataResult, historical_result,
    historical_request_spec, historical_binding_result)
from src.market_data.candidate_identity import CandidateIdentity

from src.adapters.brokers.ibkr.ibkr_connection_manager import get_shared_ibkr_connection_manager
from src.adapters.data.historical_bar_timeframes import resolve_intraday_timeframe_request, normalize_intraday_timeframe
from src.strategies.common.candles.candle_types import Candle


def normalize_intraday_bar_timestamp(raw_stamp):
    """Existing formatDate2 decoder; timezone-ambiguous text remains unqualified."""
    if isinstance(raw_stamp, bool):
        return None
    if isinstance(raw_stamp, (int, float)) or (isinstance(raw_stamp, str) and raw_stamp.isdigit()):
        return datetime.fromtimestamp(float(raw_stamp), timezone.utc)
    return raw_stamp


def get_intraday_bars(*, symbol: str, timeframe: str = "1m", limit: int = 50,
                      completed_opening: bool = False, expected_client=None,
                      expected_connection_epoch: int | None = None, qualified_contract=None,
                      expected_identity: CandidateIdentity | None = None) -> Sequence[Candle]:
    """Fetch normalized intraday candles for pattern evaluation.

    Legacy calls retain their empty-list failure behavior. The explicit capture
    route returns original source evidence or a typed refusal and never retries.
    """
    if completed_opening is True:
        return _completed_opening_bars(symbol=symbol, timeframe=timeframe, limit=limit,
            expected_client=expected_client, expected_connection_epoch=expected_connection_epoch,
            qualified_contract=qualified_contract, expected_identity=expected_identity)
    if (completed_opening is not False or expected_client is not None
            or expected_connection_epoch is not None or qualified_contract is not None
            or expected_identity is not None):
        return HistoricalDataResult("COMPLETED_OPENING_ARGUMENTS_UNSUPPORTED")
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
    return _normalize_intraday_history(history, contract=contract, requested_bars=request.requested_bars, fallback_symbol=symbol)


def _normalize_intraday_history(history, *, contract, requested_bars, retain_all=False, fallback_symbol=None):
    normalized: list[Candle] = []
    raw_timestamps = []
    selected = tuple(history) if retain_all else tuple(history[-requested_bars:])
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
                    volume=(float(getattr(bar, "volume", None)) if retain_all
                            else float(getattr(bar, "volume", 0) or 0)),
                    timestamp=stamp,
                )
            )
            raw_timestamps.append(raw_stamp)
        except (TypeError, ValueError, OverflowError, OSError):
            continue
    return replace(history, bars=tuple(normalized), normalized_raw_bar_timestamps=tuple(raw_timestamps),
        normalization_source_bars=raw_selected, normalization_selected_count=len(selected),
        normalization_rejected_count=len(selected)-len(normalized),
        contract_identity=(history.contract_identity if retain_all else history.contract_identity or
            CandidateIdentity.from_contract(contract, fallback_symbol=fallback_symbol)))



def _completed_opening_bars(*, symbol, timeframe, limit, expected_client,
                            expected_connection_epoch, qualified_contract, expected_identity):
    """Explicit capture-only bound request; never qualify/connect or trim facts."""
    from ibapi.contract import Contract
    from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
    from src.core.acquisition import AcquisitionCancelled, AcquisitionDeadlineExceeded, checkpoint
    from src.market_data.session_pct_change import covered_opening_window

    def refused(reason, source=None):
        # A planned/no-op request has no transmitted request_spec or dispatch
        # clock. After dispatch, retain the actual source witness and all raw rows.
        return replace(source, status=reason) if source is not None else HistoricalDataResult(reason)

    try:
        if (type(symbol) is not str or symbol != symbol.strip().upper() or not symbol
                or type(limit) is not int or limit <= 0
                or normalize_intraday_timeframe(timeframe) != "1m"
                or type(expected_connection_epoch) is not int or expected_connection_epoch < 0
                or type(expected_client) is not IbkrClient or type(qualified_contract) is not Contract
                or type(expected_identity) is not CandidateIdentity
                or type(expected_identity.con_id) is not int or expected_identity.con_id <= 0
                or expected_identity.symbol != symbol or expected_identity.sec_type != "STK"
                or expected_identity.currency != "USD"
                or CandidateIdentity.from_contract(qualified_contract) != expected_identity):
            return refused("COMPLETED_OPENING_ARGUMENTS_UNSUPPORTED")
    except (TypeError, ValueError, AttributeError):
        return refused("COMPLETED_OPENING_ARGUMENTS_UNSUPPORTED")
    initial = covered_opening_window(datetime.now(timezone.utc))
    if initial is None or initial.phase != "RTH_OPEN":
        return refused("COMPLETED_OPENING_WINDOW_UNAVAILABLE")
    def source_valid():
        return (manager.existing_client is expected_client
            and type(expected_client.client_id) is int and expected_client.client_id == 71
            and type(expected_client.clientId) is int and expected_client.clientId == 71
            and type(expected_client._position_connection_epoch) is int
            and expected_client._position_connection_epoch == expected_connection_epoch
            and expected_client.readonly_enabled is True and expected_client.isConnected()
            and not expected_client._stop_event.is_set()
            and CandidateIdentity.from_contract(qualified_contract) == expected_identity)

    source = None
    try:
        checkpoint()
        manager = get_shared_ibkr_connection_manager(readonly_enabled=True)
        if not source_valid():
            return refused("COMPLETED_OPENING_SOURCE_UNAVAILABLE")
        now = datetime.now(timezone.utc)
        window = covered_opening_window(now)
        if (window is None or window.phase != "RTH_OPEN" or window.fingerprint != initial.fingerprint):
            return refused("COMPLETED_OPENING_WINDOW_CHANGED")
        end = now.replace(second=0, microsecond=0)
        seconds = int((end - window.current_open).total_seconds())
        # The adopted capture admission reuses the completed-context's 16-bar
        # requirement. The covered opening window supplies the upper boundary;
        # limit never expands the wire window or truncates returned evidence.
        if (seconds < 16 * 60 or seconds % 60 or not window.current_open < end < window.opening_end):
            return refused("COMPLETED_OPENING_WINDOW_UNAVAILABLE")
        params = dict(endDateTime=end.strftime("%Y%m%d-%H:%M:%S"), durationStr=f"{seconds} S",
            barSizeSetting="1 min", whatToShow="TRADES", useRTH=1, formatDate=2,
            keepUpToDate=False, chartOptions=[])
        checkpoint()
        if not source_valid():
            return refused("COMPLETED_OPENING_SOURCE_CHANGED")
        wire_now = datetime.now(timezone.utc)
        wire_window = covered_opening_window(wire_now)
        if (wire_window is None or wire_window.phase != "RTH_OPEN"
                or wire_window.fingerprint != window.fingerprint or wire_now < now
                or wire_now.replace(second=0, microsecond=0) != end):
            return refused("COMPLETED_OPENING_WINDOW_CHANGED")
        source = historical_result(expected_client.reqHistoricalData(qualified_contract, **params))
        if not source_valid():
            return refused("COMPLETED_OPENING_SOURCE_CHANGED", source)
        returned_at = datetime.now(timezone.utc)
        after = covered_opening_window(returned_at)
        if after is None or after.phase != "RTH_OPEN" or after.fingerprint != window.fingerprint:
            return refused("COMPLETED_OPENING_WINDOW_CHANGED", source)
        expected_spec = historical_request_spec(end_date_time=params["endDateTime"],
            duration_str=params["durationStr"], bar_size_setting="1 min", what_to_show="TRADES",
            use_rth=1, format_date=2, keep_up_to_date=False, chart_options=[])
        bound = historical_binding_result(source, qualified_contract, expected_spec)
        if (bound.status != source.status or source.contract_identity != expected_identity
                or source.dispatched_contract_identity != expected_identity or source.request_spec != expected_spec):
            return refused("COMPLETED_OPENING_SOURCE_UNVERIFIED", source)
        if not source.completed:
            return source  # Original timeout/error/partial facts, including raw rows.
        # Only the native owner's original dispatch/completion and detached raw
        # rows establish this frame. Never construct missing authority from the
        # normalized rows or the profile's later return clock.
        if (type(source.request_id) is not int or source.request_id <= 0
                or type(source.request_dispatched_at_utc) is not str
                or type(source.completed_at_utc) is not str
                or type(source.callback_start) is not str or type(source.callback_end) is not str
                or type(source.source_bar_count) is not int or source.source_bar_count != len(source)
                or source.raw_source_bars is None or len(source.raw_source_bars) != len(source)
                or len(source.raw_bar_timestamps) != len(source)):
            return refused("COMPLETED_OPENING_SOURCE_UNVERIFIED", source)
        try:
            dispatched = datetime.fromisoformat(source.request_dispatched_at_utc)
            completed = datetime.fromisoformat(source.completed_at_utc)
            if (dispatched.tzinfo is None or dispatched.utcoffset() is None
                    or completed.tzinfo is None or completed.utcoffset() is None
                    or not now <= dispatched <= completed <= returned_at
                    or dispatched.astimezone(timezone.utc).replace(second=0, microsecond=0) != end):
                return refused("COMPLETED_OPENING_SOURCE_CLOCK_CONFLICT", source)
        except (TypeError, ValueError, OverflowError):
            return refused("COMPLETED_OPENING_SOURCE_UNVERIFIED", source)
        return _normalize_intraday_history(source, contract=qualified_contract,
            requested_bars=limit, retain_all=True)
    except (AcquisitionCancelled, AcquisitionDeadlineExceeded):
        raise
    except Exception:
        # Profile-private logs/receipts own exception diagnostics. Do not expose
        # provider payloads or replace a failure with another request.
        return refused("COMPLETED_OPENING_SOURCE_ERROR", source)
