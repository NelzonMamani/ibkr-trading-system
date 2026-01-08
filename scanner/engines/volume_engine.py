from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from ib_insync import IB, Stock

logger = logging.getLogger(__name__)


@dataclass
class VolumeTruth:
    current_intraday_volume: Optional[int]
    current_volume_source_label: str
    average_daily_volume_20d: Optional[int]
    average_daily_volume_window_days: int
    relative_volume: Optional[float]
    relative_volume_category: Optional[str]
    volume_velocity_5m: Optional[float]
    volume_velocity_15m: Optional[float]
    volume_data_quality_flag: str


def _req_hist_safe(
    ib: IB,
    contract: Stock,
    *,
    durationStr: str,
    barSizeSetting: str,
    whatToShow: str,
    useRTH: bool,
    timeout_s: float = 8.0,
):
    try:
        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",
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
        logger.warning("Historical volume failed for %s: %s", contract.symbol, exc)
        return []


def get_volume_truth(ib: IB, contract: Stock) -> VolumeTruth:
    current_volume = None
    volume_source = "NONE"
    avg20 = None
    rel_vol = None
    rel_category = None
    vel_5m = None
    vel_15m = None
    quality = "PARTIAL"

    try:
        ticker = ib.reqMktData(contract, "", snapshot=True, regulatorySnapshot=False)
        t0 = time.time()
        while time.time() - t0 < 2.0:
            if ticker.volume is not None:
                break
            ib.sleep(0.05)
        if ticker.volume is not None:
            current_volume = int(ticker.volume)
            volume_source = "SNAPSHOT"
    except Exception:
        pass

    try:
        ib.cancelMktData(contract)
    except Exception:
        pass

    bars = _req_hist_safe(
        ib,
        contract,
        durationStr="20 D",
        barSizeSetting="1 day",
        whatToShow="TRADES",
        useRTH=True,
    )
    if bars:
        volumes = [bar.volume for bar in bars if bar.volume is not None]
        if volumes:
            avg20 = int(sum(volumes) / len(volumes))

    if current_volume and avg20:
        rel_vol = round(current_volume / avg20, 2) if avg20 else None
        if rel_vol is not None:
            if rel_vol >= 5:
                rel_category = "HIGH"
            elif rel_vol >= 2:
                rel_category = "MED"
            else:
                rel_category = "LOW"

    intraday = _req_hist_safe(
        ib,
        contract,
        durationStr="1 D",
        barSizeSetting="5 mins",
        whatToShow="TRADES",
        useRTH=False,
    )
    if intraday:
        last_5 = intraday[-1].volume if intraday[-1].volume is not None else None
        last_3 = intraday[-3:].copy()
        sum_15 = sum(bar.volume or 0 for bar in last_3)
        if last_5 is not None:
            vel_5m = float(last_5)
        if sum_15:
            vel_15m = float(sum_15)

    if current_volume is None and avg20 is None and not intraday:
        quality = "EMPTY"

    return VolumeTruth(
        current_intraday_volume=current_volume,
        current_volume_source_label=volume_source,
        average_daily_volume_20d=avg20,
        average_daily_volume_window_days=20,
        relative_volume=rel_vol,
        relative_volume_category=rel_category,
        volume_velocity_5m=vel_5m,
        volume_velocity_15m=vel_15m,
        volume_data_quality_flag=quality,
    )
