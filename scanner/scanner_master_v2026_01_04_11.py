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

import json
import logging
import math
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ib_insync import IB, ScannerSubscription, Stock, util


# Optional float fallback: yfinance (best-effort)
try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None


logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

IB_HOST = os.environ.get("IB_HOST", "127.0.0.1")
IB_PORT = int(os.environ.get("IB_PORT", "7496"))
IB_CONNECT_TIMEOUT = float(os.environ.get("IB_CONNECT_TIMEOUT", "12"))

TOP_GAINERS_COUNT = int(os.environ.get("TOP_GAINERS_COUNT", "50"))

FLOAT_CACHE_FILE = os.environ.get("FLOAT_CACHE_FILE", "float_cache.json")


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


def load_json_file(path: str, default: Any) -> Any:
    try:
        p = Path(path)
        if not p.exists():
            return default
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json_file(path: str, obj: Any) -> None:
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
    high: Optional[float]
    low: Optional[float]
    range_pct: Optional[float]
    data_type_label: str
    truth_source_label: str
    daily_bars_count: int


def get_price_truth(ib: IB, contract: Stock) -> PriceTruth:
    """Best-effort price truth.

    Strategy:
      1) Daily bars for prev close & today's open (RTH bars).
      2) Live snapshot for last/bid/ask/high/low/vwap/volume fields (if available).
    """
    prev_close = None
    session_open = None
    daily_bars_count = 0
    try:
        bars = ib.reqHistoricalData(
            contract,
            endDateTime='',
            durationStr='2 D',
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True,
            formatDate=1,
        )
        daily_bars_count = len(bars or [])
        if daily_bars_count >= 2:
            prev_close = float(bars[-2].close)
            # today's open is in the last bar
            session_open = float(bars[-1].open)
        elif daily_bars_count == 1:
            # If only 1 bar returned, treat its close as prev close as fallback
            prev_close = float(bars[-1].close)
    except Exception:
        pass

    # Live snapshot
    last = bid = ask = high = low = vwap = None
    data_type_label = "UNKNOWN"
    truth_source_label = "SNAPSHOT"
    try:
        ticker = ib.reqMktData(contract, '', snapshot=True, regulatorySnapshot=False)
        ib.sleep(0.8)
        # ib_insync uses None for missing fields
        last = ticker.last
        if last is None:
            # Sometimes close is present when last isn't (delayed)
            last = ticker.close
        bid = ticker.bid
        ask = ticker.ask
        high = ticker.high
        low = ticker.low
        vwap = getattr(ticker, "vwap", None)
        # data type (1=real-time, 2=frozen, 3=delayed, 4=delayed-frozen)
        dt = getattr(ticker, "marketDataType", None)
        if dt == 1:
            data_type_label = "REALTIME"
        elif dt == 2:
            data_type_label = "FROZEN"
        elif dt == 3:
            data_type_label = "DELAYED"
        elif dt == 4:
            data_type_label = "DELAYED_FROZEN"
        else:
            data_type_label = "UNKNOWN"
    except Exception:
        truth_source_label = "HISTORICAL_ONLY"

    spread = None
    mid = None
    if bid is not None and ask is not None:
        try:
            spread = safe_round(float(ask) - float(bid), 4)
            mid = safe_round((float(ask) + float(bid)) / 2.0, 4)
        except Exception:
            spread = None
            mid = None

    gap_pct = compute_gap_pct(session_open, prev_close)
    pct_change = compute_pct_change(last, prev_close)
    range_pct = compute_intraday_range_pct(high, low, prev_close)

    return PriceTruth(
        prev_close=safe_round(prev_close, 4),
        session_open=safe_round(session_open, 4),
        gap_pct=gap_pct,
        last=safe_round(last, 4),
        pct_change=pct_change,
        bid=safe_round(bid, 4),
        ask=safe_round(ask, 4),
        spread=spread,
        mid=mid,
        vwap=safe_round(vwap, 4),
        high=safe_round(high, 4),
        low=safe_round(low, 4),
        range_pct=range_pct,
        data_type_label=data_type_label,
        truth_source_label=truth_source_label,
        daily_bars_count=daily_bars_count,
    )


# ============================
# Section 6: Phase 2 — Float + Volume Unification
# ============================

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


def get_volume_truth(ib: IB, contract: Stock) -> VolumeTruth:
    """Unify current volume, avg volume, RVOL, and velocity buckets."""
    # Phase 2A: Live Volume Truth
    # - Prefer streaming live volume (reqMktData snapshot=False)
    # - Fall back to snapshot volume
    # - Fall back to daily bars (volume-to-date) if needed
    cur_vol, cur_vol_src = _try_live_intraday_volume(ib, contract, wait_seconds=1.25)

    # Avg daily volume 20D from historical daily bars
    avg_vol_20d: Optional[int] = None
    window_days = 20
    try:
        bars = ib.reqHistoricalData(
            contract,
            endDateTime='',
            durationStr='20 D',
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True,
            formatDate=1,
        )
        vols = [int(b.volume) for b in (bars or []) if getattr(b, "volume", 0) is not None]
        if vols:
            avg_vol_20d = int(sum(vols) / len(vols))
    except Exception:
        pass

    rvol: Optional[float] = None
    if cur_vol is not None and avg_vol_20d and avg_vol_20d > 0:
        rvol = safe_round(cur_vol / avg_vol_20d, 2)

    # Velocity volumes via intraday bars (5m bars, last 1–3 bars)
    v5: Optional[int] = None
    v15: Optional[int] = None
    try:
        ib_bars = ib.reqHistoricalData(
            contract,
            endDateTime='',
            durationStr='1 D',
            barSizeSetting='5 mins',
            whatToShow='TRADES',
            useRTH=False,
            formatDate=1,
        )
        vols5 = [int(b.volume) for b in (ib_bars or [])]
        if vols5:
            v5 = int(vols5[-1])
            v15 = int(sum(vols5[-3:])) if len(vols5) >= 3 else int(sum(vols5))
    except Exception:
        pass

    # Quality labels: explicit and diagnostic
    has_cur = cur_vol is not None
    has_avg = avg_vol_20d is not None
    has_v5 = v5 is not None
    has_v15 = v15 is not None
    src_bucket = (
        "LIVE" if cur_vol_src == "LIVE" else
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
        average_daily_volume_20d=avg_vol_20d,
        average_daily_volume_window_days=window_days,
        relative_volume=rvol,
        relative_volume_category=categorize_rvol(rvol),
        volume_velocity_5m=v5,
        volume_velocity_15m=v15,
        volume_data_quality_flag=quality,
    )


# ============================
# Section 7: News placeholders (Phase 3 will wire real attribution)
# ============================

def empty_news_block() -> Dict[str, Any]:
    return {
        "news_total_headlines": 0,
        "news_unique_headlines": 0,
        "news_replicated_headlines": 0,
        "news_velocity_10m": 0,
        "news_velocity_60m": 0,
        "news_spike_indicator": False,
        "news_freshest_age_minutes": None,
        "news_regions_list": [],
        "news_region_count": 0,
        "news_top_sources_list": [],
        "news_top_source_credibility_score": 0.0,
        "news_average_sentiment": 0.0,
        "news_keyword_relevance_score": 0.0,
        "news_primary_catalyst_keywords": [],
        "news_top_headlines_list": [],
    }


# ============================
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

    vt = get_volume_truth(ib, contract)

    # Fire indicator (simple, trader-friendly; adjustable later)
    fire = ""
    if (pt.pct_change is not None and pt.pct_change >= 10) and (vt.relative_volume is not None and vt.relative_volume >= 2):
        fire = "🔥"

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
        "day_high_price": pt.high,
        "day_low_price": pt.low,
        "intraday_range_percentage": pt.range_pct,
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
    }

    # News placeholders (Phase 3 will overwrite)
    entry.update(empty_news_block())

    # Scoring placeholders
    entry.update({
        "composite_momentum_score": None,
        "score_components_breakdown": None,
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
# Section 9: MASTER PRINTER
# ============================

def print_master(entries: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 90)
    print("MASTER SCANNER PRINTER —", utc_now_iso())
    print("=" * 90)

    for e in entries:
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
            print(f"  - {k}: {e.get(k)}")
        print("-" * 90)


# ============================
# Section 10: Orchestrator
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
            logging.info("(%d/%d) Enriching %s", idx, len(contracts), c.symbol)
            raw_entries.append(build_entry(ib, c, float_cache, session_label, sort_rank=idx))

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
        print_master(sorted_entries)

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
