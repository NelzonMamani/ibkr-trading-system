from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from ib_insync import IB, Stock

logger = logging.getLogger(__name__)


@dataclass
class PriceTruth:
    symbol: str
    prev_close: Optional[float]
    session_open: Optional[float]
    gap_pct: Optional[float]
    last: Optional[float]
    pct_change: Optional[float]
    bid: Optional[float]
    ask: Optional[float]
    spread: Optional[float]
    mid: Optional[float]
    vwap: Optional[float]
    day_high: Optional[float]
    day_low: Optional[float]
    intraday_range_pct: Optional[float]
    data_type_label: str
    truth_source_label: str
    daily_bars_count: int


def _req_hist_safe(
    ib: IB,
    contract: Stock,
    *,
    endDateTime: str,
    durationStr: str,
    barSizeSetting: str,
    whatToShow: str,
    useRTH: bool,
    timeout_s: float = 8.0,
):
    try:
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=endDateTime,
            durationStr=durationStr,
            barSizeSetting=barSizeSetting,
            whatToShow=whatToShow,
            useRTH=useRTH,
            keepUpToDate=False,
        )
        t0 = time.time()
        while time.time() - t0 < timeout_s and bars is None:
            ib.sleep(0.1)
        return bars or []
    except Exception as exc:
        logger.warning("Historical data failed for %s: %s", contract.symbol, exc)
        return []


def get_price_truth(ib: IB, contract: Stock, session_open_price_fallback: Optional[float] = None) -> PriceTruth:
    sym = contract.symbol

    prev_close = None
    session_open = None
    last = None
    bid = None
    ask = None
    spread = None
    mid = None
    vwap = None
    day_high = None
    day_low = None
    intraday_range_pct = None
    gap_pct = None
    pct_change = None
    daily_bars_count = 0
    data_type_label = "UNKNOWN"
    truth_source = "NONE"

    try:
        ticker = ib.reqMktData(contract, "", snapshot=True, regulatorySnapshot=False)
        t0 = time.time()
        while time.time() - t0 < 2.0:
            if ticker.last is not None or ticker.close is not None or ticker.bid is not None or ticker.ask is not None:
                break
            ib.sleep(0.05)

        last_val = ticker.last
        if last_val is None:
            try:
                mp = ticker.marketPrice()
                last_val = None if mp is None else float(mp)
            except Exception:
                last_val = None

        last = float(last_val) if last_val is not None else None
        bid = float(ticker.bid) if ticker.bid is not None else None
        ask = float(ticker.ask) if ticker.ask is not None else None

        if bid is not None and ask is not None:
            spread = round(ask - bid, 6)
            mid = round((ask + bid) / 2.0, 6)

        prev_close = float(ticker.close) if ticker.close is not None else None
        session_open = float(ticker.open) if ticker.open is not None else (
            float(session_open_price_fallback) if session_open_price_fallback is not None else None
        )

        vwap = float(getattr(ticker, "vwap", None)) if getattr(ticker, "vwap", None) is not None else None
        day_high = float(ticker.high) if ticker.high is not None else None
        day_low = float(ticker.low) if ticker.low is not None else None
        if day_high is not None and day_low is not None and last:
            intraday_range_pct = round((day_high - day_low) / last * 100.0, 2)

        if prev_close is not None and last is not None and prev_close != 0:
            pct_change = round((last - prev_close) / prev_close * 100.0, 2)

        if prev_close is not None and session_open is not None and prev_close != 0:
            gap_pct = round((session_open - prev_close) / prev_close * 100.0, 2)

        mdt = getattr(ticker, "marketDataType", None)
        if mdt == 1:
            data_type_label = "REALTIME"
        elif mdt == 3:
            data_type_label = "DELAYED"
        elif mdt == 4:
            data_type_label = "DELAYED_FROZEN"
        elif mdt == 2:
            data_type_label = "FROZEN"
        else:
            data_type_label = "UNKNOWN"

        truth_source = "SNAPSHOT"
    except Exception as exc:
        logger.warning("Snapshot price failed for %s: %s", sym, exc)

    try:
        ib.cancelMktData(contract)
    except Exception:
        pass

    if prev_close is None or session_open is None:
        bars = _req_hist_safe(
            ib,
            contract,
            endDateTime="",
            durationStr="2 D",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
        )
        daily_bars_count = len(bars)
        if bars:
            bar_prev = bars[-2] if len(bars) >= 2 else bars[-1]
            prev_close = prev_close or float(bar_prev.close)
            session_open = session_open or float(bar_prev.open)

    return PriceTruth(
        symbol=sym,
        prev_close=prev_close,
        session_open=session_open,
        gap_pct=gap_pct,
        last=last,
        pct_change=pct_change,
        bid=bid,
        ask=ask,
        spread=spread,
        mid=mid,
        vwap=vwap,
        day_high=day_high,
        day_low=day_low,
        intraday_range_pct=intraday_range_pct,
        data_type_label=data_type_label,
        truth_source_label=truth_source,
        daily_bars_count=daily_bars_count,
    )
