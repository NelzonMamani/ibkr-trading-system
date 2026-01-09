#!/usr/bin/env python3
"""scanner_master_v2026_01_04_11.py

MASTER / GENERAL PRINTER (Checklist-Complete, Debug-First)

Implements (incrementally):
  - Phase 1A: Live Price Truth
  - Phase 2: Float + Volume Unification

Notes
  - This script is intentionally defensive: missing data must not crash the run.
  - The MASTER PRINTER must print the full canonical 1–54 fields for every symbol.
  - The compact header line is Ross-aligned: Fire → Symbol → %Chg → Gap → Price → Float → RVOL → News.

Run (from repo root):
  .venv\\Scripts\\python.exe -m src.scanner.scanner_master_v2026_01_06_07
"""

from __future__ import annotations

# ============================
# Section 0: Windows event loop fix (selector)
# ============================
import sys
if sys.platform.startswith("win"):
    import asyncio as _asyncio_tmp
    _asyncio_tmp.set_event_loop_policy(_asyncio_tmp.WindowsSelectorEventLoopPolicy())

# ============================
# Section 1: Imports & Config
# ============================

import importlib
import importlib.util
import json
import logging
import math
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ib_insync import IB, ScannerSubscription, Stock, util

from src.news.news_heat import compute_fire_indicator

from .filters import passes_catalyst_eligibility, passes_ross_5_pillars
from src.config.config_resolver import get_config

from .news_engine import NEWS_MAX_TOP_HEADLINES, get_news_truth
from .scanner_config import FLOAT_CACHE_FILE, IB_CONNECT_TIMEOUT, IB_HOST, IB_PORT, TOP_GAINERS_COUNT

# Optional float fallback: yfinance (best-effort)
if importlib.util.find_spec("yfinance"):
    yf = importlib.import_module("yfinance")  # type: ignore
else:  # pragma: no cover
    yf = None

# ============================
# Section 1B: Historical request safety + pacing
# ============================

class _HistLimiter:
    """Simple pacing + hard cap for historical requests.

    IB's historical data pacing limits can trigger error 162 (request cancelled).
    We prefer partial data over a crashed or hung scan.
    """

    def __init__(self, max_requests: int = 120, min_interval_s: float = 0.20):
        self.max_requests = max_requests
        self.min_interval_s = min_interval_s
        self._count = 0
        self._last_ts = 0.0

    @property
    def count(self) -> int:
        return self._count

    def allow(self) -> bool:
        return self._count < self.max_requests

    def tick(self) -> None:
        now = time.time()
        wait = (self._last_ts + self.min_interval_s) - now
        if wait > 0:
            time.sleep(wait)
        self._last_ts = time.time()
        self._count += 1


_HIST_LIMITER = _HistLimiter()

def _req_hist_safe(
    ib: IB,
    contract: Stock,
    *,
    endDateTime: str,
    durationStr: str,
    barSizeSetting: str,
    whatToShow: str,
    useRTH: bool,
    formatDate: int = 1,
    timeout_s: float = 6.0,
):
    """Historical data request with timeout and pacing.

    Returns a list of bars (possibly empty). Never raises.
    """
    if not _HIST_LIMITER.allow():
        return []

    _HIST_LIMITER.tick()

    try:
        import asyncio  # local import (Windows policy handled above)

        async def _coro():
            return await ib.reqHistoricalDataAsync(
                contract,
                endDateTime=endDateTime,
                durationStr=durationStr,
                barSizeSetting=barSizeSetting,
                whatToShow=whatToShow,
                useRTH=useRTH,
                formatDate=formatDate,
                keepUpToDate=False,
            )

        return ib.run(asyncio.wait_for(_coro(), timeout=timeout_s)) or []
    except Exception as e:
        logging.getLogger(__name__).warning(
            "Historical request failed for %s (%s %s %s): %s",
            getattr(contract, "symbol", "?"),
            durationStr,
            barSizeSetting,
            whatToShow,
            e,
        )
        return []



logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


# ============================
# Section 2: Canonical field order (1–54)
# ============================

# IMPORTANT: This is the master lock. Re-order ONLY intentionally.
CANONICAL_FIELDS: List[str] = [
    # ---- Header / identity ----
    "momentum_fire_indicator",
    "symbol",
    "market_session_label",
    "sort_rank_by_gap_desc",

    # ---- Price truth (Phase 1 / 1A) ----
    "previous_close_price",
    "session_open_price",
    "overnight_gap_percentage",
    "last_trade_price",
    "current_percentage_change_from_prior_close",
    "bid_price",
    "ask_price",
    "bid_ask_spread",
    "mid_price",
    "vwap_price",
    "day_high_price",
    "day_low_price",
    "intraday_range_percentage",
    "price_data_type_label",
    "price_truth_source_label",
    "daily_bars_count",

    # ---- Float mechanics (Phase 2) ----
    "float_shares_raw",
    "float_shares_formatted",
    "float_category",
    "float_shares_source",
    "float_cache_hit",

    # ---- Volume (Phase 2) ----
    "current_intraday_volume",
    "current_volume_source_label",
    "average_daily_volume_20d",
    "average_daily_volume_window_days",
    "relative_volume",
    "relative_volume_category",
    "volume_velocity_5m",
    "volume_velocity_15m",
    "volume_data_quality_flag",

    # ---- News presence & attribution (Phase 3 placeholder here) ----
    "news_total_headlines",
    "news_unique_headlines",
    "news_replicated_headlines",
    "news_velocity_10m",
    "news_velocity_60m",
    "news_spike_indicator",
    "news_freshest_age_minutes",
    "news_regions_list",
    "news_region_count",
    "news_top_sources_list",
    "news_top_source_credibility_score",
    "news_average_sentiment",
    "news_keyword_relevance_score",
    "news_primary_catalyst_keywords",
    "news_top_headlines_list",

    # ---- Scoring & decision support (later phases) ----
    "composite_momentum_score",
    "score_components_breakdown",
    "attention_tier",
    "trade_suggestion_label",
    "trade_suggestion_rationale",
]
assert len(CANONICAL_FIELDS) == 54, f"Expected 54 fields, got {len(CANONICAL_FIELDS)}"


# ============================
# Section 3: Utilities
# ============================

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_round(x: Optional[float], n: int = 2) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)) and (math.isfinite(float(x))):
            return round(float(x), n)
    except Exception:
        return None
    return None


def fmt_float_human(n: Optional[int]) -> str:
    if n is None:
        return "N/A"
    try:
        v = int(n)
        if v >= 1_000_000_000:
            return f"{v/1_000_000_000:.2f}B"
        if v >= 1_000_000:
            return f"{v/1_000_000:.2f}M"
        if v >= 1_000:
            return f"{v/1_000:.0f}K"
        return str(v)
    except Exception:
        return "N/A"


def categorize_float(float_shares: Optional[int]) -> str:
    if not float_shares or float_shares <= 0:
        return "UNKNOWN"
    if float_shares < 5_000_000:
        return "MICRO_FLOAT"
    if float_shares < 20_000_000:
        return "LOW_FLOAT"
    if float_shares < 80_000_000:
        return "MID_FLOAT"
    return "HIGH_FLOAT"


def categorize_rvol(rvol: Optional[float]) -> str:
    if rvol is None:
        return "N/A"
    try:
        v = float(rvol)
        if v >= 5:
            return "EXTREME"
        if v >= 2:
            return "HIGH"
        if v >= 1.2:
            return "ELEVATED"
        if v >= 0.8:
            return "NORMAL"
        return "LOW"
    except Exception:
        return "N/A"


def compute_gap_pct(open_price: Optional[float], prev_close: Optional[float]) -> Optional[float]:
    if open_price is None or prev_close is None or prev_close == 0:
        return None
    return safe_round(((open_price - prev_close) / prev_close) * 100.0, 2)


def compute_pct_change(last_price: Optional[float], prev_close: Optional[float]) -> Optional[float]:
    if last_price is None or prev_close is None or prev_close == 0:
        return None
    return safe_round(((last_price - prev_close) / prev_close) * 100.0, 2)


def compute_intraday_range_pct(day_high: Optional[float], day_low: Optional[float], ref: Optional[float]) -> Optional[float]:
    if day_high is None or day_low is None or ref is None or ref == 0:
        return None
    return safe_round(((day_high - day_low) / ref) * 100.0, 2)


def market_session_label_utc(now: Optional[datetime] = None) -> str:
    """Coarse session label for US equities, using UTC.

    RTH is roughly 14:30–21:00 UTC (changes with DST).
    This is used only as a label; it does not gate calculations.
    """
    now = now or datetime.now(timezone.utc)
    h = now.hour + now.minute / 60.0
    # Conservative bands (covers DST shifts):
    if 12.0 <= h < 14.0:
        return "PRE"
    if 14.0 <= h < 21.5:
        return "RTH"
    if 21.5 <= h < 23.0:
        return "AFT"
    return "OVN"


def load_json_file(path: str | Path, default: Any) -> Any:
    try:
        p = Path(path)
        if not p.exists():
            return default
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json_file(path: str | Path, obj: Any) -> None:
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ============================
# Section 4: IB Connectivity
# ============================

def ib_connect() -> IB:
    ib = IB()
    ib.RaiseRequestErrors = False  # prefer empty results over hard failures on pacing/cancellations
    client_id = int(get_config("IBKR_CLIENT_ID") or 0)
    if client_id <= 0:
        client_id = random.randint(1000, 9999)
    logging.info("Connecting to %s:%s with clientId %s...", IB_HOST, IB_PORT, client_id)
    ib.connect(IB_HOST, IB_PORT, clientId=client_id, timeout=IB_CONNECT_TIMEOUT)
    return ib


def fetch_top_gainers(ib: IB, n: int = TOP_GAINERS_COUNT) -> List[Stock]:
    sub = ScannerSubscription(
        instrument='STK',
        locationCode='STK.US.MAJOR',
        scanCode='TOP_PERC_GAIN',
        numberOfRows=n,
    )
    scan_data = ib.reqScannerData(sub)
    contracts: List[Stock] = []
    for item in scan_data:
        c = item.contractDetails.contract
        # Ensure SMART for data; keep symbol
        contracts.append(Stock(c.symbol, 'SMART', 'USD'))
    return contracts


# ============================
# Section 5: Phase 1A — Live Price Truth
# ============================

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
def get_price_truth(ib: IB, contract: Stock, session_open_price_fallback: Optional[float] = None) -> PriceTruth:
    """Phase 1A — Live Price Truth.

    Uses snapshot market data first (avoids historical pacing cancellations),
    with minimal historical fallback only when required.
    """
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

    # --- Snapshot market data (preferred) ---
    try:
        ticker = ib.reqMktData(contract, "", snapshot=True, regulatorySnapshot=False)
        t0 = time.time()
        while time.time() - t0 < 2.0:
            if ticker.last is not None or ticker.close is not None or ticker.bid is not None or ticker.ask is not None:
                break
            ib.sleep(0.05)

        # Note: marketPrice() can be NaN if empty; guard with None checks above
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

        vwap = float(ticker.vwap) if getattr(ticker, "vwap", None) is not None else None
        day_high = float(ticker.high) if ticker.high is not None else None
        day_low = float(ticker.low) if ticker.low is not None else None
        if day_high is not None and day_low is not None and last is not None and last != 0:
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
    except Exception as e:
        logging.getLogger(__name__).warning("Snapshot price failed for %s: %s", sym, e)

    # Ensure no lingering subscription
    try:
        ib.cancelMktData(contract)
    except Exception:
        pass

    # --- Minimal historical fallback (only fill missing open/close) ---
    if prev_close is None or session_open is None:
        bars = _req_hist_safe(
            ib,
            contract,
            endDateTime="",
            durationStr="2 D",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
            timeout_s=8.0,
        )
        daily_bars_count = len(bars)
        if bars:
            b = bars[-1]
            if prev_close is None and getattr(b, "close", None) is not None:
                prev_close = float(b.close)
            if session_open is None and getattr(b, "open", None) is not None:
                session_open = float(b.open)

            if prev_close is not None and last is not None and prev_close != 0:
                pct_change = round((last - prev_close) / prev_close * 100.0, 2)
            if prev_close is not None and session_open is not None and prev_close != 0:
                gap_pct = round((session_open - prev_close) / prev_close * 100.0, 2)

            if truth_source == "NONE":
                truth_source = "HISTORICAL_FALLBACK"

    return PriceTruth(
        symbol=contract.symbol,
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

def get_float_shares(ib: IB, contract: Stock, float_cache: Dict[str, Any]) -> Tuple[Optional[int], str, bool]:
    """Return (float_shares_raw, source_label, cache_hit)."""
    sym = contract.symbol.upper()
    # 1) Cache
    if sym in float_cache:
        try:
            v = int(float_cache[sym]["float_shares_raw"])
            if v > 0:
                return v, str(float_cache[sym].get("float_shares_source", "CACHE")), True
        except Exception:
            pass

    # 2) IB Fundamentals (best-effort; often unavailable for many small caps)
    try:
        # reqFundamentalData returns XML string; parsing is non-trivial and often not consistent.
        # We do not parse it here; keep hook for later.
        _ = ib.reqFundamentalData(contract, reportType='ReportSnapshot')
    except Exception:
        pass

    # 3) yfinance fallback
    if yf is not None:
        try:
            info = yf.Ticker(sym).info
            v = info.get("floatShares")
            if v is not None:
                v_int = int(v)
                if v_int > 0:
                    float_cache[sym] = {
                        "float_shares_raw": v_int,
                        "float_shares_source": "Yahoo",
                        "ts": utc_now_iso(),
                    }
                    return v_int, "Yahoo", False
        except Exception:
            pass

    return None, "Unavailable", False


@dataclass
class VolumeTruth:
    current_intraday_volume: Optional[int]
    current_volume_source_label: str
    average_daily_volume_20d: Optional[int]
    average_daily_volume_window_days: int
    relative_volume: Optional[float]
    relative_volume_category: str
    volume_velocity_5m: Optional[int]
    volume_velocity_15m: Optional[int]
    volume_data_quality_flag: str


def _try_live_intraday_volume(ib: IB, contract: Stock, wait_seconds: float = 1.25) -> Tuple[Optional[int], str]:
    """Attempt to obtain a *current* intraday cumulative volume.

    IBKR sources can be inconsistent depending on permissions and market data type.
    This function is defensive and does not raise.

    Returns: (volume, source_label)
      - source_label in {"LIVE_STREAM", "SNAPSHOT", "HIST_DAILY_TODAY", "UNAVAILABLE"}
    """
    # 1) Streaming (best). We request non-snapshot market data, wait briefly, then cancel.
    try:
        t = ib.reqMktData(contract, "", False, False)
        deadline = time.time() + max(0.25, float(wait_seconds))
        vol = None
        while time.time() < deadline:
            ib.sleep(0.1)
            v = getattr(t, "volume", None)
            if isinstance(v, (int, float)) and v > 0:
                vol = int(v)
                break
        try:
            ib.cancelMktData(contract)
        except Exception:
            pass
        if vol is not None:
            return vol, "LIVE_STREAM"
    except Exception:
        pass

    # 2) Snapshot (good fallback)
    try:
        t = ib.reqMktData(contract, "", True, False)
        ib.sleep(0.8)
        v = getattr(t, "volume", None)
        if isinstance(v, (int, float)) and v > 0:
            return int(v), "SNAPSHOT"
    except Exception:
        pass

    # 3) Historical daily bar for "today" (often returns volume-to-date for current session)
    try:
        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr="2 D",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
        )
        if bars and len(bars) >= 1:
            v = getattr(bars[-1], "volume", None)
            if isinstance(v, (int, float)) and v > 0:
                return int(v), "HIST_DAILY_TODAY"
    except Exception:
        pass

    return None, "UNAVAILABLE"


def get_volume_truth(ib: IB, contract: Stock, *, session_label: str) -> VolumeTruth:
    """Phase 1B — Volume + RVOL + Velocity (best-effort)."""
    cur_vol, cur_vol_src = _try_live_intraday_volume(ib, contract)

    avg20 = None
    rvol = None
    vel_5m = None
    vel_15m = None
    vol_truth_source = "NONE"
    window_days = 20

    # --- Daily bars for Avg20 volume (single request) ---
    daily = _req_hist_safe(
        ib,
        contract,
        endDateTime="",
        durationStr="25 D",
        barSizeSetting="1 day",
        whatToShow="TRADES",
        useRTH=True,
        timeout_s=8.0,
    )
    if daily:
        vols = []
        for b in daily[-21:]:
            v = getattr(b, "volume", None)
            if v is None:
                continue
            vols.append(float(v))
        if len(vols) >= 5:
            tail = vols[-20:] if len(vols) >= 20 else vols
            avg20 = int(sum(tail) / len(tail))
            vol_truth_source = "HIST_DAILY_25D"

    if cur_vol is not None and avg20 and avg20 > 0:
        rvol = round(cur_vol / avg20, 2)

    # --- Intraday 5m bars for velocity (single request) ---
    intraday = _req_hist_safe(
        ib,
        contract,
        endDateTime="",
        durationStr="1 D",
        barSizeSetting="5 mins",
        whatToShow="TRADES",
        useRTH=(session_label == "RTH"),
        timeout_s=8.0,
    )
    if intraday:
        def _sum_last_n(minutes: int) -> Optional[int]:
            bars_needed = max(1, int(minutes / 5))
            tail = intraday[-bars_needed:]
            s = 0
            for b in tail:
                v = getattr(b, "volume", None)
                if v is None:
                    continue
                s += int(v)
            return s if s > 0 else None

        vel_5m = _sum_last_n(5)
        vel_15m = _sum_last_n(15)
        if vol_truth_source == "NONE":
            vol_truth_source = "HIST_INTRADAY_5M"

    has_cur = cur_vol is not None
    has_avg = avg20 is not None
    has_v5 = vel_5m is not None
    has_v15 = vel_15m is not None
    src_bucket = (
        "LIVE" if cur_vol_src == "LIVE_STREAM" else
        "SNAPSHOT" if cur_vol_src == "SNAPSHOT" else
        "HIST" if cur_vol_src == "HIST_DAILY_TODAY" else
        "UNAVAILABLE"
    )

    if has_cur and has_avg and has_v5 and has_v15:
        quality = "OK_LIVE" if src_bucket == "LIVE" else "OK_DELAYED"
    elif has_cur and has_avg:
        quality = f"PARTIAL_NO_VELOCITY_{src_bucket}"
    elif has_cur and not has_avg:
        quality = f"PARTIAL_NO_AVG_{src_bucket}"
    elif has_cur:
        quality = f"PARTIAL_CUR_ONLY_{src_bucket}"
    else:
        quality = "MISSING_VOLUME"

    return VolumeTruth(
        current_intraday_volume=cur_vol,
        current_volume_source_label=cur_vol_src,
        average_daily_volume_20d=avg20,
        average_daily_volume_window_days=window_days,
        relative_volume=rvol,
        relative_volume_category=categorize_rvol(rvol),
        volume_velocity_5m=vel_5m,
        volume_velocity_15m=vel_15m,
        volume_data_quality_flag=quality,
    )

# Section 8: Entry builder (1 symbol → 54 fields)
# ============================

def build_entry(
    ib: IB,
    contract: Stock,
    float_cache: Dict[str, Any],
    session_label: str,
    sort_rank: int,
) -> Dict[str, Any]:
    sym = contract.symbol.upper()

    # Phase 1A
    pt = get_price_truth(ib, contract)

    # Phase 2
    float_raw, float_src, cache_hit = get_float_shares(ib, contract, float_cache)
    float_fmt = fmt_float_human(float_raw)
    float_cat = categorize_float(float_raw)

    vt = get_volume_truth(ib, contract, session_label=session_label)

    # Phase 3A/3B: News truth (RSS-based best-effort)
    news = get_news_truth(sym)
    news_total = news.get("news_total_headlines") or 0

    # Fire indicator (news-derived only)
    fire = "🔥" if compute_fire_indicator(news) else ""

    entry: Dict[str, Any] = {
        # Header / identity
        "momentum_fire_indicator": fire,
        "symbol": sym,
        "market_session_label": session_label,
        "sort_rank_by_gap_desc": sort_rank,

        # Price truth
        "previous_close_price": pt.prev_close,
        "session_open_price": pt.session_open,
        "overnight_gap_percentage": pt.gap_pct,
        "last_trade_price": pt.last,
        "current_percentage_change_from_prior_close": pt.pct_change,
        "bid_price": pt.bid,
        "ask_price": pt.ask,
        "bid_ask_spread": pt.spread,
        "mid_price": pt.mid,
        "vwap_price": pt.vwap,
        "day_high_price": pt.day_high,
        "day_low_price": pt.day_low,
        "intraday_range_percentage": pt.intraday_range_pct,
        "price_data_type_label": pt.data_type_label,
        "price_truth_source_label": pt.truth_source_label,
        "daily_bars_count": pt.daily_bars_count,

        # Float mechanics
        "float_shares_raw": float_raw,
        "float_shares_formatted": float_fmt,
        "float_category": float_cat,
        "float_shares_source": float_src,
        "float_cache_hit": cache_hit,

        # Volume
        "current_intraday_volume": vt.current_intraday_volume,
        "current_volume_source_label": vt.current_volume_source_label,
        "average_daily_volume_20d": vt.average_daily_volume_20d,
        "average_daily_volume_window_days": vt.average_daily_volume_window_days,
        "relative_volume": vt.relative_volume,
        "relative_volume_category": vt.relative_volume_category,
        "volume_velocity_5m": vt.volume_velocity_5m,
        "volume_velocity_15m": vt.volume_velocity_15m,
        "volume_data_quality_flag": vt.volume_data_quality_flag,

        # News Truth (Phase 3A)
        "news_total_headlines": news.get("news_total_headlines"),
        "news_unique_headlines": news.get("news_unique_headlines"),
        "news_replicated_headlines": news.get("news_replicated_headlines"),
        "news_velocity_10m": news.get("news_velocity_10m"),
        "news_velocity_60m": news.get("news_velocity_60m"),
        "news_spike_indicator": news.get("news_spike_indicator"),
        "news_freshest_age_minutes": news.get("news_freshest_age_minutes"),
        "news_regions_list": news.get("news_regions_list"),
        "news_region_count": news.get("news_region_count"),
        "news_top_sources_list": news.get("news_top_sources_list"),
        "news_top_source_credibility_score": news.get("news_top_source_credibility_score"),
        "news_average_sentiment": news.get("news_average_sentiment"),
        "news_keyword_relevance_score": news.get("news_keyword_relevance_score"),
        "news_primary_catalyst_keywords": news.get("news_primary_catalyst_keywords"),
        "news_top_headlines_list": news.get("news_top_headlines_list"),
    }

    entry["score_components_breakdown"] = {}

    # Scoring placeholders (Phase 4 will fill)
    entry.update({
        "composite_momentum_score": None,
        "attention_tier": None,
        "trade_suggestion_label": None,
        "trade_suggestion_rationale": None,
    })

    # Ensure canonical completeness
    for k in CANONICAL_FIELDS:
        if k not in entry:
            entry[k] = None
    return entry


# ============================

# ============================
# Phase 4: Composite Momentum Scoring
# ============================

# Scoring is intentionally simple and debuggable. You can tune weights safely.
SCORING_WEIGHTS = {
    "pct_change": 0.30,
    "relative_volume": 0.25,
    "float": 0.15,
    "news": 0.25,
    "spread_penalty": 0.05,
}

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def _safe_float(x, default=None):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default

def _score_float(float_shares_raw: int | None) -> float:
    if float_shares_raw is None or float_shares_raw <= 0:
        return 0.0
    # Momentum bias: lower float gets higher score.
    if float_shares_raw <= 5_000_000:
        return 1.0
    if float_shares_raw <= 20_000_000:
        return 0.75
    if float_shares_raw <= 50_000_000:
        return 0.45
    if float_shares_raw <= 100_000_000:
        return 0.25
    return 0.15

def _score_news(entry: dict) -> float:
    total = _safe_float(entry.get("news_total_headlines"), 0.0) or 0.0
    unique = _safe_float(entry.get("news_unique_headlines"), 0.0) or 0.0
    vel10 = _safe_float(entry.get("news_velocity_10m"), 0.0) or 0.0
    regions = _safe_float(entry.get("news_region_count"), 0.0) or 0.0
    cred = _safe_float(entry.get("news_top_source_credibility_score"), 0.0) or 0.0

    # Normalisations (bounded, forgiving).
    total_n = _clamp(total / 50.0, 0.0, 1.0)
    unique_n = _clamp(unique / 10.0, 0.0, 1.0)
    vel10_n = _clamp(vel10 / 10.0, 0.0, 1.0)
    regions_n = _clamp(regions / 6.0, 0.0, 1.0)
    cred_n = _clamp(cred, 0.0, 1.0)

    # Weighted internal mix.
    return (
        0.30 * total_n
        + 0.25 * unique_n
        + 0.25 * vel10_n
        + 0.10 * regions_n
        + 0.10 * cred_n
    )

def compute_composite_momentum(entry: dict) -> tuple[float | None, dict | None, str | None, str | None, str | None]:
    pct = _safe_float(entry.get("current_percentage_change_from_prior_close"), None)
    rvol = _safe_float(entry.get("relative_volume"), None)
    float_raw = entry.get("float_shares_raw")

    # If we lack core fields, do not manufacture a score.
    if pct is None or rvol is None:
        return None, None, None, None, None

    pct_n = _clamp(pct / 100.0, -1.0, 2.0)  # allow negative, and >100% blowoffs
    pct_n = _clamp((pct_n + 1.0) / 3.0, 0.0, 1.0)  # map [-1..2] -> [0..1]

    rvol_n = _clamp(rvol / 10.0, 0.0, 1.0)
    float_n = _score_float(float_raw)
    news_n = _score_news(entry)

    spread = _safe_float(entry.get("bid_ask_spread"), None)
    last_price = _safe_float(entry.get("last_trade_price"), None)
    if spread is None or last_price is None or last_price == 0:
        spread_pen = 0.0
    else:
        spread_pct = spread / last_price
        # Penalise very wide spreads (microcaps). Cap penalty at 1.
        spread_pen = _clamp(float(spread_pct) / 0.05, 0.0, 1.0)  # 5% spread => full penalty

    raw = (
        SCORING_WEIGHTS["pct_change"] * pct_n
        + SCORING_WEIGHTS["relative_volume"] * rvol_n
        + SCORING_WEIGHTS["float"] * float_n
        + SCORING_WEIGHTS["news"] * news_n
        - SCORING_WEIGHTS["spread_penalty"] * spread_pen
    )
    score_0_100 = _clamp(raw, 0.0, 1.0) * 100.0

    components = {
        "pct_change_norm": round(pct_n, 4),
        "rvol_norm": round(rvol_n, 4),
        "float_norm": round(float_n, 4),
        "news_norm": round(news_n, 4),
        "spread_penalty_norm": round(spread_pen, 4),
        "weights": SCORING_WEIGHTS,
    }

    if score_0_100 >= 75:
        tier = "A"
        label = "HOT"
        rationale = "High % change + strong relative volume; supportive float/news context."
    elif score_0_100 >= 55:
        tier = "B"
        label = "WATCH"
        rationale = "Decent momentum; monitor price action and liquidity."
    else:
        tier = "C"
        label = "PASS"
        rationale = "Insufficient composite strength versus risk/liquidity."
    return round(score_0_100, 2), components, tier, label, rationale


def apply_composite_scoring(entries: List[Dict[str, Any]]) -> None:
    for entry in entries:
        score, components, tier, label, rationale = compute_composite_momentum(entry)
        entry["composite_momentum_score"] = score
        if components is not None:
            existing = entry.get("score_components_breakdown") or {}
            existing.update(components)
            entry["score_components_breakdown"] = existing
        entry["attention_tier"] = tier
        entry["trade_suggestion_label"] = label
        entry["trade_suggestion_rationale"] = rationale


# Section 9: MASTER PRINTER
# ============================

def format_clickable(label: str, url: str) -> str:
    """Format headline text, preferring terminal-clickable OSC8 hyperlinks.

    Compatibility:
    - Many terminals support OSC8 hyperlinks.
    - Some IDE consoles do not. To ensure you always see the destination,
      we also append the raw URL by default.

    Env:
      DISABLE_OSC8=1   -> never emit OSC8
      SHOW_URLS=0      -> do not append the raw URL
    """
    if not url:
        return label

    show_urls = bool(get_config("SHOW_URLS"))
    disable_osc8 = bool(get_config("DISABLE_OSC8"))

    if disable_osc8:
        return f"{label} ({url})" if show_urls else label

    # OSC 8 hyperlink: ESC ] 8 ;; URL ESC \ LABEL ESC ] 8 ;; ESC \
    clickable = f"\033]8;;{url}\033\\{label}\033]8;;\033\\"
    return f"{clickable} ({url})" if show_urls else clickable


def validate_entry(entry: dict) -> tuple[bool, list[str]]:
    missing = [k for k in CANONICAL_FIELDS if k not in entry]
    return len(missing) == 0, missing


def _print_headlines_block(headlines: list) -> None:
    for h in headlines[:NEWS_MAX_TOP_HEADLINES]:
        if isinstance(h, dict):
            title = str(h.get("title", ""))
            url = str(h.get("url", ""))
            age = h.get("age_minutes")
            age_s = "N/A" if age is None else f"{age}m"
            src = h.get("source", "")
            label = f"{title} [{src}] ({age_s})" if src else f"{title} ({age_s})"
            print(f"    - {format_clickable(label, url)}")
        else:
            print(f"    - {h}")


def print_master(entries: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 90)
    print("MASTER SCANNER PRINTER —", utc_now_iso())
    print("=" * 90)

    for e in entries:
        _, missing = validate_entry(e)
        if missing:
            print(f"[WARN] Missing canonical fields: {missing}")
        fire = e.get("momentum_fire_indicator", "") or ""
        sym = e.get("symbol", "")
        pct = e.get("current_percentage_change_from_prior_close")
        gap = e.get("overnight_gap_percentage")
        px = e.get("last_trade_price")
        flt = e.get("float_shares_formatted")
        rvol = e.get("relative_volume")
        news_total = e.get("news_total_headlines", 0)

        pct_s = "N/A" if pct is None else f"{pct:.1f}"
        gap_s = "N/A" if gap is None else f"{gap:.1f}"
        px_s = "N/A" if px is None else f"{px:.4g}"
        rvol_s = "N/A" if rvol is None else f"{rvol:.2f}"
        flt_s = flt if flt is not None else "N/A"

        print(f"{fire} {sym} | %Chg:{pct_s} | Gap:{gap_s} | Px:{px_s} | Float:{flt_s} | RVOL:{rvol_s} | News:{news_total}")

        # Debug-first full dump in canonical order
        for k in CANONICAL_FIELDS:
            if k == "news_top_headlines_list":
                headlines = e.get(k) or []
                print(f"  - {k}:")
                if isinstance(headlines, list):
                    _print_headlines_block(headlines)
                else:
                    print(f"    - {headlines}")
                continue

            print(f"  - {k}: {e.get(k)}")
        print("-" * 90)


# ============================
# Section 10: Filtered Watchlists
# ============================

def _format_watchlist_line(entry: Dict[str, Any]) -> str:
    fire = entry.get("momentum_fire_indicator", "") or ""
    sym = entry.get("symbol", "")
    pct = entry.get("current_percentage_change_from_prior_close")
    gap = entry.get("overnight_gap_percentage")
    px = entry.get("last_trade_price")
    flt = entry.get("float_shares_formatted")
    rvol = entry.get("relative_volume")
    news_total = entry.get("news_total_headlines", 0)
    vel10 = entry.get("news_velocity_10m")
    freshest = entry.get("news_freshest_age_minutes")
    regions = entry.get("news_regions_list")

    pct_s = "N/A" if pct is None else f"{pct:.1f}"
    gap_s = "N/A" if gap is None else f"{gap:.1f}"
    px_s = "N/A" if px is None else f"{px:.4g}"
    rvol_s = "N/A" if rvol is None else f"{rvol:.2f}"
    flt_s = flt if flt is not None else "N/A"
    freshest_s = "N/A" if freshest is None else f"{freshest}m"

    return (
        f"{fire} {sym} | %Chg:{pct_s} | Gap:{gap_s} | Px:{px_s} | Float:{flt_s} | "
        f"RVOL:{rvol_s} | News:{news_total} | Vel10:{vel10} | Freshest:{freshest_s} | Regions:{regions}"
    )


def build_filtered_watchlist(entries: List[Dict[str, Any]], limit: int = 15) -> List[Dict[str, Any]]:
    filtered = [
        entry
        for entry in entries
        if passes_ross_5_pillars(entry) and passes_catalyst_eligibility(entry)
    ]
    filtered = sorted(
        filtered,
        key=lambda x: (
            x.get("current_percentage_change_from_prior_close") is None,
            -(x.get("current_percentage_change_from_prior_close") or -10**9),
        ),
    )
    return filtered[:limit]


def print_filtered_watchlist(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    filtered = build_filtered_watchlist(entries, limit=15)
    print("\n" + "=" * 90)
    print("FILTERED WATCHLIST (ROSS+CATALYST) — TOP 15 —", utc_now_iso())
    print("=" * 90)
    for entry in filtered:
        print(_format_watchlist_line(entry))
    print("=" * 90)

    focus = filtered[:3]
    print("\n" + "=" * 90)
    print("FOCUS TOP 3 —", utc_now_iso())
    print("=" * 90)
    for entry in focus:
        print(_format_watchlist_line(entry))
    print("=" * 90)
    return filtered


# ============================
# Section 11: Orchestrator
# ============================

def run_once() -> None:
    session_label = market_session_label_utc()
    float_cache: Dict[str, Any] = load_json_file(FLOAT_CACHE_FILE, {})
    if not isinstance(float_cache, dict):
        float_cache = {}
    logging.info("Loaded float cache entries: %d", len(float_cache))

    ib = None
    try:
        ib = ib_connect()
        contracts = fetch_top_gainers(ib, TOP_GAINERS_COUNT)
        logging.info("Scanner returned %d symbols", len(contracts))

        # Build entries
        raw_entries: List[Dict[str, Any]] = []
        for idx, c in enumerate(contracts, start=1):
            sym = getattr(c, "symbol", "UNKNOWN")
            logging.info("(%d/%d) Enriching %s", idx, len(contracts), sym)
            try:
                entry = build_entry(ib, c, float_cache, session_label, sort_rank=idx)
                raw_entries.append(entry)
            except Exception as e:
                # Critical: do not let a single IBKR request failure (e.g., HMDS 162) abort the entire scan.
                logging.exception("[ENRICH] Failed for %s: %s", sym, e)
                raw_entries.append({
                    "momentum_fire_indicator": "",
                    "symbol": sym,
                    "market_session_label": session_label,
                    "sort_rank_by_gap_desc": idx,
                    # preserve canonical keys with N/A elsewhere; printer expects complete schema
                    **{k: None for k in CANONICAL_FIELDS if k not in {"momentum_fire_indicator","symbol","market_session_label","sort_rank_by_gap_desc"}}
                })

        # Sort by % change desc (Ross/IB style), while keeping a deterministic rank label for printing
        sorted_entries = sorted(
            raw_entries,
            key=lambda x: (x.get("current_percentage_change_from_prior_close") is None,
                           -(x.get("current_percentage_change_from_prior_close") or -10**9)),
        )
        # Re-assign rank by %Chg desc (naming kept for legacy)
        for i, e in enumerate(sorted_entries, start=1):
            e["sort_rank_by_gap_desc"] = i

        save_json_file(FLOAT_CACHE_FILE, float_cache)
        apply_composite_scoring(sorted_entries)
        print_master(sorted_entries)
        print_filtered_watchlist(sorted_entries)

    finally:
        try:
            if ib is not None and ib.isConnected():
                ib.disconnect()
        except Exception:
            pass


def main() -> None:
    # Ensure ib_insync has a loop
    util.patchAsyncio()
    run_once()


if __name__ == "__main__":
    main()
