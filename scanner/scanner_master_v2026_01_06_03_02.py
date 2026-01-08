#!/usr/bin/env python3
# File: scanner_master_v2026_01_06_03.py
"""
MASTER SCANNER — v2026-01-06-03 (FULL)
- Full MASTER scanner with:
  Phase 1A: Live Price Truth (IBKR snapshot + streaming fields)
  Phase 2A: Live Volume Truth (intraday volume + velocity + quality labels)
  Phase 3D: News Truth from verified_rss.txt ONLY (presence, velocity, attribution, time distribution)
  Phase 3C: Clickable Headline Printer (prints 5 unique headlines with URLs)
  Phase 4 : Composite Momentum Scoring (transparent weights + per-symbol breakdown)
  Phase 5 : Ross 5-Pillars Printer (filtered list)
  Phase 6 : Sniper Strategy Printer (your “news-heavy” selection on top of 5 pillars)

Important:
- This script is "debug-first": it will never crash the whole run for one bad symbol.
- It is designed to print ALL canonical fields for the MASTER printer.
- News uses verified_rss.txt (one URL per line). Place it in the SAME folder as this script, unless you set VERIFIED_RSS_PATH.

Terminal clickability:
- Many terminals auto-link URLs if printed plainly.
- We print: "• Title — URL" so it becomes clickable where supported.

IBKR note:
- You must have TWS/IB Gateway running and API enabled.
- Market data permissions affect REALTIME vs DELAYED.

"""

from __future__ import annotations

import os
import re
import sys
import time
import json
import math
import logging
import asyncio
import datetime as dt
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

# Windows event loop fix (selector) for aiohttp / asyncio
if sys.platform.startswith("win"):
    try:
        import asyncio as _asyncio_tmp
        _asyncio_tmp.set_event_loop_policy(_asyncio_tmp.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

from ib_insync import IB, Stock, util  # type: ignore

# Optional deps for RSS
try:
    import aiohttp  # type: ignore
except Exception:
    aiohttp = None  # type: ignore

try:
    import feedparser  # type: ignore
except Exception as e:
    raise RuntimeError("feedparser is required. pip install feedparser") from e

# Optional float fallback
try:
    import yfinance as yf  # type: ignore
except Exception:
    yf = None  # type: ignore

# ----------------------------
# Config
# ----------------------------

LOG_LEVEL = os.getenv("SCANNER_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger("scanner")

IB_HOST = os.getenv("IB_HOST", "127.0.0.1")
IB_PORT = int(os.getenv("IB_PORT", "7496"))  # paper: 7497 typically
IB_CLIENT_ID = int(os.getenv("IB_CLIENT_ID", "0"))  # 0 => random

# How many symbols from IB scanner
SCANNER_SYMBOL_LIMIT = int(os.getenv("SCANNER_SYMBOL_LIMIT", "50"))

# Historical windows
AVG_VOL_WINDOW_DAYS = 20

# News settings
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VERIFIED_RSS_PATH = os.getenv("VERIFIED_RSS_PATH", os.path.join(SCRIPT_DIR, "verified_rss.txt"))

NEWS_HTTP_TIMEOUT_S = int(os.getenv("NEWS_HTTP_TIMEOUT_S", "10"))
NEWS_MAX_FEEDS = int(os.getenv("NEWS_MAX_FEEDS", "500"))  # safety cap
NEWS_MAX_ENTRIES_PER_FEED = int(os.getenv("NEWS_MAX_ENTRIES_PER_FEED", "200"))
NEWS_TOP_HEADLINES_N = 5

# Debug toggles
NEWS_DEBUG = bool(int(os.getenv("NEWS_DEBUG", "0")))
PRICE_DEBUG = bool(int(os.getenv("PRICE_DEBUG", "0")))
VOLUME_DEBUG = bool(int(os.getenv("VOLUME_DEBUG", "0")))
SCORING_DEBUG = bool(int(os.getenv("SCORING_DEBUG", "0")))

# Canonical time buckets for news freshness distribution
NEWS_TIME_BUCKETS = [
    ("0–1m", 0, 1),
    ("1–5m", 1, 5),
    ("5–10m", 5, 10),
    ("10–20m", 10, 20),
    ("20–30m", 20, 30),
    ("30–60m", 30, 60),
    ("1–5h", 60, 300),
    ("5–10h", 300, 600),
    ("10–24h", 600, 1440),
    ("24–48h", 1440, 2880),
    ("48h+", 2880, 10**9),
]

# ----------------------------
# Utilities
# ----------------------------

def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)

def safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None

def safe_int(x: Any) -> Optional[int]:
    try:
        if x is None:
            return None
        return int(float(x))
    except Exception:
        return None

def round2(x: Optional[float]) -> Optional[float]:
    if x is None:
        return None
    try:
        return round(float(x), 2)
    except Exception:
        return None

def format_compact_number(n: Optional[int]) -> str:
    if n is None:
        return "N/A"
    try:
        if n >= 1_000_000_000:
            return f"{n/1_000_000_000:.2f}B"
        if n >= 1_000_000:
            return f"{n/1_000_000:.2f}M"
        if n >= 1_000:
            return f"{n/1_000:.0f}K"
        return str(n)
    except Exception:
        return "N/A"

def compute_category_float(float_shares: Optional[int]) -> str:
    if float_shares is None:
        return "UNKNOWN"
    if float_shares < 10_000_000:
        return "MICRO_FLOAT"
    if float_shares < 50_000_000:
        return "LOW_FLOAT"
    if float_shares < 150_000_000:
        return "MID_FLOAT"
    return "HIGH_FLOAT"

def compute_rvol_category(rvol: Optional[float]) -> str:
    if rvol is None:
        return "N/A"
    if rvol >= 5:
        return "EXTREME"
    if rvol >= 2:
        return "HIGH"
    if rvol >= 1:
        return "NORMAL"
    return "LOW"

def parse_hostname_region(url: str) -> str:
    """
    Heuristic region label from domain/TLD. Not perfect, but useful for distribution and "unique regions".
    """
    try:
        host = urlparse(url).hostname or ""
        host = host.lower()
        # common multi-part TLDs (approx)
        if host.endswith(".co.uk") or host.endswith(".uk"):
            return "UK"
        if host.endswith(".com"):
            return "US/Global"
        if host.endswith(".ca"):
            return "Canada"
        if host.endswith(".au"):
            return "Australia"
        if host.endswith(".de"):
            return "Germany"
        if host.endswith(".fr"):
            return "France"
        if host.endswith(".es"):
            return "Spain"
        if host.endswith(".it"):
            return "Italy"
        if host.endswith(".nl"):
            return "Netherlands"
        if host.endswith(".eu"):
            return "EU"
        if host.endswith(".jp"):
            return "Japan"
        if host.endswith(".cn"):
            return "China"
        if host.endswith(".in"):
            return "India"
        if host.endswith(".br"):
            return "Brazil"
        # fallback
        return "Other"
    except Exception:
        return "Other"

def hyperlink_osc8(title: str, url: str) -> str:
    """
    OSC 8 hyperlink (some terminals support clickable links).
    If unsupported, the printed text still includes the URL elsewhere.
    """
    return f"\033]8;;{url}\033\\{title}\033]8;;\033\\"

# ----------------------------
# Float Cache (simple JSON file)
# ----------------------------

FLOAT_CACHE_PATH = os.getenv("FLOAT_CACHE_PATH", os.path.join(SCRIPT_DIR, "float_cache.json"))

def load_float_cache() -> Dict[str, Dict[str, Any]]:
    if not os.path.exists(FLOAT_CACHE_PATH):
        return {}
    try:
        with open(FLOAT_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                logger.info(f"Loaded float cache entries: {len(data)}")
                return data
    except Exception as e:
        logger.warning(f"Could not load float cache: {e}")
    return {}

def save_float_cache(cache: Dict[str, Dict[str, Any]]) -> None:
    try:
        with open(FLOAT_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, sort_keys=True)
    except Exception as e:
        logger.warning(f"Could not save float cache: {e}")

# ----------------------------
# IBKR Connection + Scanner
# ----------------------------

def connect_ib() -> IB:
    ib = IB()
    client_id = IB_CLIENT_ID if IB_CLIENT_ID != 0 else int(time.time()) % 10000 + 1000
    logger.info(f"Connecting to {IB_HOST}:{IB_PORT} with clientId {client_id}...")
    ib.connect(IB_HOST, IB_PORT, clientId=client_id)
    if not ib.isConnected():
        raise RuntimeError("IB connection failed.")
    logger.info("Connected")
    return ib

def get_top_gainers_contracts(ib: IB, limit: int = SCANNER_SYMBOL_LIMIT) -> List[Stock]:
    """
    Uses IBKR market scanner to retrieve top % gainers.
    This is the canonical “unfiltered universe” for the MASTER printer.
    """
    from ib_insync import ScannerSubscription  # type: ignore

    sub = ScannerSubscription(
        instrument="STK",
        locationCode="STK.US.MAJOR",
        scanCode="TOP_PERC_GAIN",
    )
    try:
        scan = ib.reqScannerData(sub)
        symbols: List[str] = []
        for row in scan:
            try:
                c = row.contractDetails.contract
                if getattr(c, "symbol", None):
                    symbols.append(c.symbol)
            except Exception:
                continue
        symbols = symbols[:limit]
        logger.info(f"Scanner returned {len(symbols)} symbols")
        return [Stock(sym, "SMART", "USD") for sym in symbols]
    except Exception as e:
        logger.error(f"Scanner failed: {e}")
        return []

# ----------------------------
# Phase 1A: Price Truth
# ----------------------------

def get_price_truth(ib: IB, contract: Stock) -> Dict[str, Any]:
    """
    Live price truth: previous close, open, last, bid, ask, spread, mid, session labels, data type.
    """
    out: Dict[str, Any] = {
        "previous_close_price": None,
        "session_open_price": None,
        "overnight_gap_percentage": None,
        "last_trade_price": None,
        "current_percentage_change_from_prior_close": None,
        "bid_price": None,
        "ask_price": None,
        "bid_ask_spread": None,
        "mid_price": None,
        "vwap_price": None,  # optional; IB provides ticker.vwap sometimes
        "day_high_price": None,
        "day_low_price": None,
        "intraday_range_percentage": None,
        "price_data_type_label": "UNKNOWN",
        "price_truth_source_label": "SNAPSHOT",
        "daily_bars_count": 0,
        "market_session_label": "RTH",  # best-effort
    }

    # Daily bars for prev close + open
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
        out["daily_bars_count"] = len(bars)
        if len(bars) >= 2:
            prev_close = safe_float(bars[-2].close)
            open_px = safe_float(bars[-1].open)
            out["previous_close_price"] = round2(prev_close)
            out["session_open_price"] = round2(open_px)
            if prev_close is not None and open_px is not None and prev_close != 0:
                out["overnight_gap_percentage"] = round2(((open_px - prev_close) / prev_close) * 100)
    except Exception as e:
        if PRICE_DEBUG:
            logger.warning(f"Price daily bars failed {contract.symbol}: {e}")

    # Snapshot + brief stream settle
    try:
        t = ib.reqMktData(contract, "", False, False)
        ib.sleep(0.35)

        last = safe_float(getattr(t, "last", None))
        bid = safe_float(getattr(t, "bid", None))
        ask = safe_float(getattr(t, "ask", None))
        close = safe_float(getattr(t, "close", None))
        open_ = safe_float(getattr(t, "open", None))
        high = safe_float(getattr(t, "high", None))
        low = safe_float(getattr(t, "low", None))
        vwap = safe_float(getattr(t, "vwap", None))
        md_type = getattr(t, "marketDataType", None)

        out["last_trade_price"] = round2(last)
        out["bid_price"] = round2(bid)
        out["ask_price"] = round2(ask)
        out["vwap_price"] = round2(vwap)
        out["day_high_price"] = round2(high)
        out["day_low_price"] = round2(low)

        if bid is not None and ask is not None:
            out["bid_ask_spread"] = round2(ask - bid)
            out["mid_price"] = round2((ask + bid) / 2)

        # Prefer IB close/open if historical missing
        if out["previous_close_price"] is None and close is not None:
            out["previous_close_price"] = round2(close)
        if out["session_open_price"] is None and open_ is not None:
            out["session_open_price"] = round2(open_)

        # % change from prior close (dynamic intraday)
        prev_close = safe_float(out["previous_close_price"])
        if prev_close is not None and prev_close != 0 and last is not None:
            out["current_percentage_change_from_prior_close"] = round2(((last - prev_close) / prev_close) * 100)

        # Intraday range %
        if high is not None and low is not None and prev_close is not None and prev_close != 0:
            out["intraday_range_percentage"] = round2(((high - low) / prev_close) * 100)

        # Market data type labels (IB: 1=REALTIME, 2=FROZEN, 3=DELAYED, 4=DELAYED_FROZEN)
        if md_type == 1:
            out["price_data_type_label"] = "REALTIME"
        elif md_type == 2:
            out["price_data_type_label"] = "FROZEN"
        elif md_type == 3:
            out["price_data_type_label"] = "DELAYED"
        elif md_type == 4:
            out["price_data_type_label"] = "DELAYED_FROZEN"
        else:
            out["price_data_type_label"] = "UNKNOWN"

        # Clean up subscription
        ib.cancelMktData(contract)

    except Exception as e:
        if PRICE_DEBUG:
            logger.warning(f"Price snapshot failed {contract.symbol}: {e}")

    return out

# ----------------------------
# Phase 2: Float + Volume Unification
# ----------------------------

def get_float_truth(ib: IB, contract: Stock, float_cache: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    sym = contract.symbol
    now_iso = utc_now().isoformat()

    out: Dict[str, Any] = {
        "float_shares_raw": None,
        "float_shares_formatted": "N/A",
        "float_category": "UNKNOWN",
        "float_shares_source": "Unavailable",
        "float_cache_hit": False,
    }

    # Cache first
    if sym in float_cache and isinstance(float_cache[sym], dict):
        cached = float_cache[sym]
        fs = safe_int(cached.get("float_shares_raw"))
        if fs is not None and fs > 0:
            out["float_shares_raw"] = fs
            out["float_shares_formatted"] = format_compact_number(fs)
            out["float_category"] = compute_category_float(fs)
            out["float_shares_source"] = cached.get("float_shares_source", "Cache")
            out["float_cache_hit"] = True
            return out

    # IB fundamentals (may be unavailable)
    try:
        # Many accounts do NOT have fundamentals entitlements; keep best-effort.
        # reqFundamentalData returns XML usually. We do NOT parse it here; we rely on other sources.
        _ = ib.reqFundamentalData(contract, reportType="ReportSnapshot")
        # If we ever add XML parse, do it here.
    except Exception:
        pass

    # Yahoo fallback
    if yf is not None:
        try:
            t = yf.Ticker(sym)
            info = getattr(t, "info", {}) or {}
            fs = safe_int(info.get("floatShares"))
            if fs is not None and fs > 0:
                out["float_shares_raw"] = fs
                out["float_shares_formatted"] = format_compact_number(fs)
                out["float_category"] = compute_category_float(fs)
                out["float_shares_source"] = "Yahoo"
        except Exception:
            pass

    # Save to cache if found
    if out["float_shares_raw"] is not None:
        float_cache[sym] = {
            "float_shares_raw": out["float_shares_raw"],
            "float_shares_source": out["float_shares_source"],
            "updated_utc": now_iso,
        }

    return out

def get_volume_truth(ib: IB, contract: Stock) -> Dict[str, Any]:
    """
    Live volume truth:
    - current_intraday_volume from live ticker.volume (best-effort)
    - average_daily_volume_20d from historical daily bars
    - RVOL = current_intraday_volume / avg_daily_volume_20d (note: not time-normalised)
    - velocity 5m / 15m from 1-min bars
    - quality flags
    """
    out: Dict[str, Any] = {
        "current_intraday_volume": None,
        "current_volume_source_label": "N/A",
        "average_daily_volume_20d": None,
        "average_daily_volume_window_days": AVG_VOL_WINDOW_DAYS,
        "relative_volume": None,
        "relative_volume_category": "N/A",
        "volume_velocity_5m": None,
        "volume_velocity_15m": None,
        "volume_data_quality_flag": "PARTIAL",
    }

    # Historical avg daily volume
    try:
        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=f"{AVG_VOL_WINDOW_DAYS} D",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
        )
        vols = [safe_int(b.volume) for b in bars if safe_int(b.volume) is not None]
        if vols:
            out["average_daily_volume_20d"] = int(sum(vols) / len(vols))
    except Exception as e:
        if VOLUME_DEBUG:
            logger.warning(f"Avg daily vol failed {contract.symbol}: {e}")

    # Live ticker volume + 1-min velocity
    try:
        t = ib.reqMktData(contract, "", False, False)
        ib.sleep(0.35)

        vol = safe_int(getattr(t, "volume", None))
        md_type = getattr(t, "marketDataType", None)

        if vol is not None:
            out["current_intraday_volume"] = vol
            out["current_volume_source_label"] = "LIVE_STREAM"

        # Quality flag: label REALTIME vs DELAYED
        if md_type == 1:
            out["volume_data_quality_flag"] = "OK_REALTIME"
        elif md_type in (3, 4):
            out["volume_data_quality_flag"] = "OK_DELAYED"
        else:
            out["volume_data_quality_flag"] = "PARTIAL"

        ib.cancelMktData(contract)
    except Exception as e:
        if VOLUME_DEBUG:
            logger.warning(f"Live volume failed {contract.symbol}: {e}")

    # RVOL (simple)
    avg = out["average_daily_volume_20d"]
    cur = out["current_intraday_volume"]
    if avg is not None and avg > 0 and cur is not None:
        out["relative_volume"] = round2(cur / avg)
        out["relative_volume_category"] = compute_rvol_category(out["relative_volume"])

    # Velocity from 1-min bars
    try:
        bars_1m = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr="30 M",
            barSizeSetting="1 min",
            whatToShow="TRADES",
            useRTH=False,
            formatDate=1,
        )
        vols_1m = [safe_int(b.volume) for b in bars_1m if safe_int(b.volume) is not None]
        if len(vols_1m) >= 15:
            out["volume_velocity_5m"] = int(sum(vols_1m[-5:]))
            out["volume_velocity_15m"] = int(sum(vols_1m[-15:]))
        elif len(vols_1m) >= 5:
            out["volume_velocity_5m"] = int(sum(vols_1m[-5:]))
            out["volume_velocity_15m"] = int(sum(vols_1m))
    except Exception as e:
        if VOLUME_DEBUG:
            logger.warning(f"Velocity failed {contract.symbol}: {e}")

    return out

# ----------------------------
# Phase 3: News Truth (verified_rss.txt only)
# ----------------------------

@dataclass
class NewsItem:
    title: str
    url: str
    published_utc: Optional[dt.datetime]
    source_host: str
    region: str

def load_verified_rss_urls(path: str) -> List[str]:
    if not os.path.exists(path):
        logger.warning(f"verified_rss.txt not found at: {path}")
        return []
    urls: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(line)
    urls = urls[:NEWS_MAX_FEEDS]
    if NEWS_DEBUG:
        logger.info(f"Loaded {len(urls)} RSS feeds from verified_rss.txt")
    return urls

def parse_entry_time_utc(entry: Any) -> Optional[dt.datetime]:
    """
    Best-effort parse of feedparser entry published time.
    """
    try:
        # feedparser gives struct_time in entry.published_parsed
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            ts = time.mktime(entry.published_parsed)
            return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)
        if hasattr(entry, "updated_parsed") and entry.updated_parsed:
            ts = time.mktime(entry.updated_parsed)
            return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)
    except Exception:
        pass
    return None

async def fetch_feed(session: Any, url: str) -> Tuple[str, Optional[bytes]]:
    try:
        async with session.get(url, timeout=NEWS_HTTP_TIMEOUT_S, headers={"User-Agent": "Mozilla/5.0"}) as resp:
            if resp.status != 200:
                return url, None
            data = await resp.read()
            return url, data
    except Exception:
        return url, None

async def fetch_all_feeds_async(urls: List[str]) -> Dict[str, bytes]:
    if not urls:
        return {}
    if aiohttp is None:
        return {}

    out: Dict[str, bytes] = {}
    timeout = aiohttp.ClientTimeout(total=NEWS_HTTP_TIMEOUT_S)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [fetch_feed(session, u) for u in urls]
        for coro in asyncio.as_completed(tasks):
            url, data = await coro
            if data:
                out[url] = data
    return out

def fetch_all_feeds_sync(urls: List[str]) -> Dict[str, bytes]:
    import requests  # local import to avoid hard dependency if unused
    out: Dict[str, bytes] = {}
    for u in urls:
        try:
            r = requests.get(u, timeout=NEWS_HTTP_TIMEOUT_S, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200 and r.content:
                out[u] = r.content
        except Exception:
            continue
    return out

def build_news_index(verified_urls: List[str]) -> List[NewsItem]:
    """
    Builds a global list of NewsItem from RSS feeds.
    Later, per-symbol we filter by symbol match.
    """
    now = utc_now()
    items: List[NewsItem] = []

    # Fetch
    feed_blobs: Dict[str, bytes] = {}
    if aiohttp is not None:
        try:
            feed_blobs = asyncio.run(fetch_all_feeds_async(verified_urls))
        except Exception:
            feed_blobs = {}
    if not feed_blobs:
        feed_blobs = fetch_all_feeds_sync(verified_urls)

    for feed_url, blob in feed_blobs.items():
        parsed = feedparser.parse(blob)
        for e in (parsed.entries or [])[:NEWS_MAX_ENTRIES_PER_FEED]:
            title = (getattr(e, "title", "") or "").strip()
            link = (getattr(e, "link", "") or "").strip()
            if not title or not link:
                continue
            published = parse_entry_time_utc(e)
            host = urlparse(link).hostname or urlparse(feed_url).hostname or ""
            region = parse_hostname_region(link or feed_url)

            # Discard extremely old items beyond 7 days to reduce noise
            if published is not None:
                age_min = (now - published).total_seconds() / 60.0
                if age_min > 7 * 24 * 60:
                    continue

            items.append(NewsItem(
                title=title,
                url=link,
                published_utc=published,
                source_host=host,
                region=region
            ))

    if NEWS_DEBUG:
        logger.info(f"Built news index: {len(items)} items")
    return items

def symbol_regex(sym: str) -> re.Pattern:
    """
    Strict-ish symbol matching:
    - Word boundary match
    - Uppercase
    Avoids matching inside other words where possible.
    """
    s = re.escape(sym.upper())
    # boundaries: start/end or non-alnum around
    return re.compile(rf"(?<![A-Z0-9]){s}(?![A-Z0-9])", re.IGNORECASE)

def compute_news_truth_for_symbol(sym: str, news_index: List[NewsItem]) -> Dict[str, Any]:
    now = utc_now()
    rx = symbol_regex(sym)

    matched: List[NewsItem] = []
    for it in news_index:
        # match in title
        if rx.search(it.title.upper()):
            matched.append(it)

    # sort by recency (published desc, None last)
    def key(it: NewsItem):
        return it.published_utc or dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    matched.sort(key=key, reverse=True)

    # total + unique/replicated based on normalised titles
    norm_titles: List[str] = []
    unique_items: List[NewsItem] = []
    replicated = 0

    for it in matched:
        norm = re.sub(r"\s+", " ", it.title.strip().lower())
        if norm in norm_titles:
            replicated += 1
            continue
        norm_titles.append(norm)
        unique_items.append(it)

    # Velocities (counts of *items* within lookback windows)
    vel10 = 0
    vel60 = 0
    freshest_age_min: Optional[float] = None

    for it in matched:
        if it.published_utc is None:
            continue
        age_min = (now - it.published_utc).total_seconds() / 60.0
        if freshest_age_min is None or age_min < freshest_age_min:
            freshest_age_min = age_min
        if age_min <= 10:
            vel10 += 1
        if age_min <= 60:
            vel60 += 1

    # Spike indicator: simple heuristic
    spike = (vel10 >= 3) or (vel60 >= 10)

    # Region + source breakdown from unique items (more meaningful)
    regions = []
    sources = []
    for it in unique_items:
        if it.region and it.region not in regions:
            regions.append(it.region)
        if it.source_host and it.source_host not in sources:
            sources.append(it.source_host)

    # Time bucket distribution (counts of unique items)
    bucket_counts = {name: 0 for name, _, _ in NEWS_TIME_BUCKETS}
    for it in unique_items:
        if it.published_utc is None:
            continue
        age_min = (now - it.published_utc).total_seconds() / 60.0
        for name, lo, hi in NEWS_TIME_BUCKETS:
            if lo <= age_min < hi:
                bucket_counts[name] += 1
                break

    # Placeholder sentiment/relevance fields (kept, but 0 until NLP stage)
    out: Dict[str, Any] = {
        "news_total_headlines": len(matched),
        "news_unique_headlines": len(unique_items),
        "news_replicated_headlines": replicated,
        "news_velocity_10m": vel10,
        "news_velocity_60m": vel60,
        "news_spike_indicator": bool(spike),
        "news_freshest_age_minutes": round2(freshest_age_min),
        "news_regions_list": regions,
        "news_region_count": len(regions),
        "news_top_sources_list": sources[:5],
        "news_top_source_credibility_score": 0.0,  # not implemented yet
        "news_average_sentiment": 0.0,              # not implemented yet
        "news_keyword_relevance_score": 0.0,        # not implemented yet
        "news_primary_catalyst_keywords": [],       # not implemented yet
        "news_top_headlines_list": [
            {"title": it.title, "url": it.url, "published_utc": (it.published_utc.isoformat() if it.published_utc else None), "region": it.region, "source": it.source_host}
            for it in unique_items[:NEWS_TOP_HEADLINES_N]
        ],
        # Phase 3B time distribution fields
        "news_time_bucket_counts": bucket_counts,
    }
    return out

# ----------------------------
# Fire Indicator (keep stable, simple, explainable)
# ----------------------------

def compute_fire_indicator(entry: Dict[str, Any]) -> str:
    """
    Keep a consistent, defensible "🔥" rule:
    - Percent change >= 20%
    - AND (RVOL >= 2 OR volume_velocity_5m >= 100k)
    - AND (news_total_headlines >= 1 OR news_velocity_60m >= 1)
    """
    pct = safe_float(entry.get("current_percentage_change_from_prior_close"))
    rvol = safe_float(entry.get("relative_volume"))
    v5 = safe_int(entry.get("volume_velocity_5m"))
    news_total = safe_int(entry.get("news_total_headlines"))
    news_vel60 = safe_int(entry.get("news_velocity_60m"))

    if pct is None:
        return ""
    hot_vol = (rvol is not None and rvol >= 2.0) or (v5 is not None and v5 >= 100_000)
    has_news = (news_total is not None and news_total >= 1) or (news_vel60 is not None and news_vel60 >= 1)

    if pct >= 20.0 and hot_vol and has_news:
        return "🔥"
    return ""

# ----------------------------
# Phase 4: Composite Momentum Scoring (transparent weights)
# ----------------------------

SCORING_MODEL = {
    "pct_change_weight": 0.35,
    "rvol_weight": 0.25,
    "news_velocity_10m_weight": 0.20,
    "news_region_diversity_weight": 0.10,
    "float_tightness_weight": 0.10,
}

def score_float_tightness(float_shares: Optional[int]) -> float:
    """
    Tight float => higher score.
    """
    if float_shares is None or float_shares <= 0:
        return 0.0
    # piecewise: <10M best, then degrade
    if float_shares <= 10_000_000:
        return 1.0
    if float_shares <= 50_000_000:
        return 0.7
    if float_shares <= 150_000_000:
        return 0.4
    return 0.2

def normalise_pct_change(pct: Optional[float]) -> float:
    if pct is None:
        return 0.0
    # cap at 100% for scoring stability
    return max(0.0, min(1.0, pct / 100.0))

def normalise_rvol(rvol: Optional[float]) -> float:
    if rvol is None:
        return 0.0
    # cap at 10x
    return max(0.0, min(1.0, rvol / 10.0))

def normalise_news_vel10(v: Optional[int]) -> float:
    if v is None:
        return 0.0
    # cap at 20 items/10m
    return max(0.0, min(1.0, v / 20.0))

def normalise_region_count(n: Optional[int]) -> float:
    if n is None:
        return 0.0
    # cap at 10 regions
    return max(0.0, min(1.0, n / 10.0))

def compute_composite_score(entry: Dict[str, Any]) -> Tuple[Optional[float], Dict[str, Any]]:
    pct = safe_float(entry.get("current_percentage_change_from_prior_close"))
    rvol = safe_float(entry.get("relative_volume"))
    vel10 = safe_int(entry.get("news_velocity_10m"))
    regions = safe_int(entry.get("news_region_count"))
    fs = safe_int(entry.get("float_shares_raw"))

    c_pct = normalise_pct_change(pct)
    c_rvol = normalise_rvol(rvol)
    c_vel10 = normalise_news_vel10(vel10)
    c_regions = normalise_region_count(regions)
    c_float = score_float_tightness(fs)

    w = SCORING_MODEL
    score = (
        c_pct * w["pct_change_weight"] +
        c_rvol * w["rvol_weight"] +
        c_vel10 * w["news_velocity_10m_weight"] +
        c_regions * w["news_region_diversity_weight"] +
        c_float * w["float_tightness_weight"]
    )

    breakdown = {
        "components": {
            "pct_change_norm": round2(c_pct),
            "rvol_norm": round2(c_rvol),
            "news_vel10_norm": round2(c_vel10),
            "regions_norm": round2(c_regions),
            "float_tightness_norm": round2(c_float),
        },
        "weights": w,
        "raw_inputs": {
            "pct_change": pct,
            "rvol": rvol,
            "news_velocity_10m": vel10,
            "news_region_count": regions,
            "float_shares_raw": fs,
        }
    }
    return round2(score), breakdown

def attention_tier(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    if score >= 0.75:
        return "A+"
    if score >= 0.55:
        return "A"
    if score >= 0.40:
        return "B"
    if score >= 0.25:
        return "C"
    return "D"

# ----------------------------
# Canonical Field Order (54)
# ----------------------------

CANONICAL_FIELDS: List[Tuple[str, str, bool]] = [
    # (field_name, description, allowed_NA)
    ("momentum_fire_indicator", "Fire indicator based on % change + volume + news", True),
    ("symbol", "Ticker symbol", False),
    ("market_session_label", "Market session label (best-effort)", True),
    ("sort_rank_by_pct_change_desc", "Sort rank by % change (desc)", True),

    ("previous_close_price", "Previous close price", True),
    ("session_open_price", "Session open price (RTH)", True),
    ("overnight_gap_percentage", "Overnight gap % (open vs prior close)", True),
    ("last_trade_price", "Last trade price (live)", True),
    ("current_percentage_change_from_prior_close", "Current % change vs prior close (dynamic)", True),

    ("bid_price", "Bid price (live)", True),
    ("ask_price", "Ask price (live)", True),
    ("bid_ask_spread", "Bid/ask spread", True),
    ("mid_price", "Mid price", True),

    ("vwap_price", "VWAP (if available)", True),
    ("day_high_price", "Day high price", True),
    ("day_low_price", "Day low price", True),
    ("intraday_range_percentage", "Intraday range % (high-low vs prior close)", True),

    ("price_data_type_label", "IBKR market data type label", True),
    ("price_truth_source_label", "Price truth source label", True),
    ("daily_bars_count", "Count of daily bars fetched", True),

    ("float_shares_raw", "Float shares (raw integer)", True),
    ("float_shares_formatted", "Float shares formatted (K/M/B)", True),
    ("float_category", "Float category (micro/low/mid/high)", True),
    ("float_shares_source", "Float source (Yahoo/Cache/etc)", True),
    ("float_cache_hit", "Float cache hit", True),

    ("current_intraday_volume", "Current intraday volume (live ticker)", True),
    ("current_volume_source_label", "Volume source label", True),
    ("average_daily_volume_20d", "Average daily volume (20d)", True),
    ("average_daily_volume_window_days", "Average volume window days", True),
    ("relative_volume", "Relative volume (current / avg daily)", True),
    ("relative_volume_category", "Relative volume category", True),

    ("volume_velocity_5m", "Volume velocity (sum last 5 x 1-min bars)", True),
    ("volume_velocity_15m", "Volume velocity (sum last 15 x 1-min bars)", True),
    ("volume_data_quality_flag", "Volume data quality flag", True),

    ("news_total_headlines", "Total matched headlines (incl duplicates)", True),
    ("news_unique_headlines", "Unique headlines count", True),
    ("news_replicated_headlines", "Replicated headlines count", True),
    ("news_velocity_10m", "News velocity in last 10 minutes (count of items)", True),
    ("news_velocity_60m", "News velocity in last 60 minutes (count of items)", True),
    ("news_spike_indicator", "News spike indicator (heuristic)", True),
    ("news_freshest_age_minutes", "Freshest headline age in minutes", True),
    ("news_regions_list", "Regions list (heuristic from domains)", True),
    ("news_region_count", "Unique region count", True),
    ("news_top_sources_list", "Top sources list", True),
    ("news_top_source_credibility_score", "Top source credibility score (placeholder)", True),
    ("news_average_sentiment", "Average sentiment (placeholder)", True),
    ("news_keyword_relevance_score", "Keyword relevance score (placeholder)", True),
    ("news_primary_catalyst_keywords", "Primary catalyst keywords (placeholder)", True),
    ("news_top_headlines_list", "Top 5 unique headlines (title+url)", True),
    ("news_time_bucket_counts", "News time distribution buckets", True),

    ("composite_momentum_score", "Composite momentum score (0..1)", True),
    ("score_components_breakdown", "Scoring components breakdown", True),
    ("attention_tier", "Attention tier derived from score", True),
    ("trade_suggestion_label", "Trade suggestion label (placeholder)", True),
    ("trade_suggestion_rationale", "Trade suggestion rationale (placeholder)", True),
]

# ----------------------------
# Printers
# ----------------------------

def print_master_header() -> None:
    print("=" * 98)
    print(f"MASTER SCANNER PRINTER — {utc_now().isoformat()}")
    print("=" * 98)

def compact_master_line(entry: Dict[str, Any]) -> str:
    fire = entry.get("momentum_fire_indicator", "")
    sym = entry.get("symbol", "N/A")
    pct = entry.get("current_percentage_change_from_prior_close", None)
    gap = entry.get("overnight_gap_percentage", None)
    px = entry.get("last_trade_price", None)
    flt = entry.get("float_shares_formatted", "N/A")
    rvol = entry.get("relative_volume", None)
    news = entry.get("news_total_headlines", 0)
    vel10 = entry.get("news_velocity_10m", 0)

    def fmt(x):
        return "N/A" if x is None else str(x)

    return f"{fire} {sym} | %Chg:{fmt(pct)} | Gap:{fmt(gap)} | Px:{fmt(px)} | Float:{flt} | RVOL:{fmt(rvol)} | News:{news} | Vel10m:{vel10}"

def print_master_entry_debug(entry: Dict[str, Any]) -> None:
    print(compact_master_line(entry))
    for field, desc, _allowed_na in CANONICAL_FIELDS:
        print(f"  - {field}: {entry.get(field)}")

    # Clickable headlines section (always show if present)
    headlines = entry.get("news_top_headlines_list") or []
    if isinstance(headlines, list) and headlines:
        print("  - top_headlines_clickable:")
        for i, h in enumerate(headlines[:NEWS_TOP_HEADLINES_N], start=1):
            title = str(h.get("title", "")).strip()
            url = str(h.get("url", "")).strip()
            if not title or not url:
                continue
            # Print both OSC8 link and plain URL (safe)
            clickable = hyperlink_osc8(title, url)
            print(f"      {i}. {clickable} — {url}")
    print("-" * 90)

def print_scoring_model() -> None:
    print("\nSCORING MODEL (Phase 4) — weights (sum=1.00)")
    for k, v in SCORING_MODEL.items():
        print(f"  - {k}: {v}")

def passes_ross_5_pillars(entry: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Ross-style “5 pillars” approximated with available fields.
    You can refine thresholds later; this is structured to be easy to tune.
    """
    reasons: List[str] = []

    px = safe_float(entry.get("last_trade_price"))
    pct = safe_float(entry.get("current_percentage_change_from_prior_close"))
    rvol = safe_float(entry.get("relative_volume"))
    fs = safe_int(entry.get("float_shares_raw"))
    news_total = safe_int(entry.get("news_total_headlines"))

    # Pillar 1: Price range (example: $1 to $20)
    if px is None or not (1.0 <= px <= 20.0):
        reasons.append("Price not in [1, 20]")

    # Pillar 2: % change (example: >= 10%)
    if pct is None or pct < 10.0:
        reasons.append("%Chg < 10")

    # Pillar 3: RVOL (example: >= 1.5)
    if rvol is None or rvol < 1.5:
        reasons.append("RVOL < 1.5")

    # Pillar 4: Float (example: <= 50M)
    if fs is None or fs > 50_000_000:
        reasons.append("Float > 50M or unknown")

    # Pillar 5: News presence
    if news_total is None or news_total < 1:
        reasons.append("No news")

    return (len(reasons) == 0), reasons

def print_ross_5_pillars(entries_sorted: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 98)
    print("ROSS 5-PILLARS PRINTER (Phase 5) — Filtered Watchlist")
    print("=" * 98)
    kept = []
    for e in entries_sorted:
        ok, _ = passes_ross_5_pillars(e)
        if ok:
            kept.append(e)
    if not kept:
        print("No symbols passed the 5-pillar filter (with current thresholds).")
        return

    for e in kept[:25]:
        print(compact_master_line(e))

def sniper_select(entry: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Your sniper strategy (Phase 6) on top of Ross list:
    - Must pass Ross 5 pillars
    - Rank preference: higher news_total + higher region diversity + higher news velocity
    """
    ok, reasons = passes_ross_5_pillars(entry)
    if not ok:
        return False, reasons
    # Additional sniper constraints can be added here (kept minimal now)
    return True, []

def sniper_rank_key(entry: Dict[str, Any]) -> Tuple[int, int, int, float]:
    news_total = safe_int(entry.get("news_total_headlines")) or 0
    regions = safe_int(entry.get("news_region_count")) or 0
    vel10 = safe_int(entry.get("news_velocity_10m")) or 0
    score = safe_float(entry.get("composite_momentum_score")) or 0.0
    return (news_total, regions, vel10, score)

def print_sniper(entries_sorted: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 98)
    print("SNIPER STRATEGY PRINTER (Phase 6) — News-Heavy Selection")
    print("=" * 98)

    candidates = []
    for e in entries_sorted:
        ok, _ = sniper_select(e)
        if ok:
            candidates.append(e)

    candidates.sort(key=sniper_rank_key, reverse=True)

    if not candidates:
        print("No symbols qualified for Sniper Strategy (after Ross filter).")
        return

    # Target: top 10 for “blind buy trial list” (as you described)
    top = candidates[:10]
    for e in top:
        sym = e.get("symbol")
        nt = e.get("news_total_headlines")
        rc = e.get("news_region_count")
        v10 = e.get("news_velocity_10m")
        sc = e.get("composite_momentum_score")
        print(f"{e.get('momentum_fire_indicator','')} {sym} | News:{nt} | Regions:{rc} | Vel10m:{v10} | Score:{sc}")

        # Show 5 unique headlines
        headlines = e.get("news_top_headlines_list") or []
        for i, h in enumerate(headlines[:NEWS_TOP_HEADLINES_N], start=1):
            title = str(h.get("title", "")).strip()
            url = str(h.get("url", "")).strip()
            if not title or not url:
                continue
            print(f"    {i}. {hyperlink_osc8(title, url)} — {url}")
        print("-" * 90)

# ----------------------------
# Entry builder (wires Phases 1A/2A/3D/4)
# ----------------------------

def build_entry(
    ib: IB,
    contract: Stock,
    float_cache: Dict[str, Dict[str, Any]],
    news_index: List[NewsItem],
    sort_rank_by_pct: int,
) -> Dict[str, Any]:
    sym = contract.symbol

    entry: Dict[str, Any] = {}

    # Identify
    entry["symbol"] = sym
    entry["market_session_label"] = "RTH"
    entry["sort_rank_by_pct_change_desc"] = sort_rank_by_pct

    # Phase 1A
    price = get_price_truth(ib, contract)
    entry.update(price)

    # Phase 2 (float)
    flt = get_float_truth(ib, contract, float_cache)
    entry.update(flt)

    # Phase 2A (volume)
    vol = get_volume_truth(ib, contract)
    entry.update(vol)

    # Phase 3D (news)
    news = compute_news_truth_for_symbol(sym, news_index)
    entry.update(news)

    # Fire indicator (after we have pct/rvol/news)
    entry["momentum_fire_indicator"] = compute_fire_indicator(entry)

    # Phase 4 scoring
    score, breakdown = compute_composite_score(entry)
    entry["composite_momentum_score"] = score
    entry["score_components_breakdown"] = breakdown
    entry["attention_tier"] = attention_tier(score)

    # Placeholders for later
    entry["trade_suggestion_label"] = None
    entry["trade_suggestion_rationale"] = None

    # Ensure all canonical fields exist (even if None) to prevent “missing fields”
    for f, _desc, _allow_na in CANONICAL_FIELDS:
        if f not in entry:
            entry[f] = None

    return entry

# ----------------------------
# Main run
# ----------------------------

def run_once() -> None:
    ib: Optional[IB] = None
    float_cache = load_float_cache()

    try:
        ib = connect_ib()

        # Build RSS index once per run
        verified_urls = load_verified_rss_urls(VERIFIED_RSS_PATH)
        news_index = build_news_index(verified_urls)

        # Universe from IB scanner
        contracts = get_top_gainers_contracts(ib, limit=SCANNER_SYMBOL_LIMIT)
        if not contracts:
            print("No symbols returned by scanner.")
            return

        # Enrich contracts with full truth (do not crash on one symbol)
        enriched: List[Dict[str, Any]] = []
        for i, c in enumerate(contracts, start=1):
            try:
                logger.info(f"({i}/{len(contracts)}) Enriching {c.symbol}")
                e = build_entry(
                    ib=ib,
                    contract=c,
                    float_cache=float_cache,
                    news_index=news_index,
                    sort_rank_by_pct=i,  # provisional; corrected after sorting
                )
                enriched.append(e)
            except Exception as e:
                logger.error(f"Failed symbol {c.symbol}: {e}")
                continue

        # Sort by percentage change DESC (your confirmed canonical ordering for printing)
        enriched.sort(
            key=lambda x: safe_float(x.get("current_percentage_change_from_prior_close")) if safe_float(x.get("current_percentage_change_from_prior_close")) is not None else -1e9,
            reverse=True,
        )

        # Re-rank after sort
        for idx, e in enumerate(enriched, start=1):
            e["sort_rank_by_pct_change_desc"] = idx

        # Print
        print_master_header()
        print_scoring_model()

        for e in enriched:
            print_master_entry_debug(e)

        # Secondary printers
        print_ross_5_pillars(enriched)
        print_sniper(enriched)

        # Persist float cache
        save_float_cache(float_cache)

    finally:
        try:
            if ib is not None and ib.isConnected():
                logger.info("Disconnecting")
                ib.disconnect()
        except Exception:
            pass

def main() -> None:
    run_once()

if __name__ == "__main__":
    main()
