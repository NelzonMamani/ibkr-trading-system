#!/usr/bin/env python3
"""
scanner_jan_04_10.py

IBKR Top Gainers + Enrichment (Gap, %Chg, RVOL, Float, Price) + RSS News Engine

Design goals (practical + robust):
- First-class objective: replicate (and improve) a Ross-style top-gainers scanner:
  1) Get top US gainers from IBKR scanner (symbols only)
  2) For each symbol: fetch IBKR market snapshot + historical daily bars
  3) Compute Gap%, %Change, RVOL (using historical volumes) defensively
  4) Float shares from cache -> Yahoo/Finviz fallback (best-effort)
  5) Run RSS engine once per cycle, then attach news per symbol
  6) Print: merged "PRIMARY" (5 pillars + market microstructure) + compact C3 block + awareness + headlines

Notes:
- Uses delayed-frozen market data by default (works off-hours/weekends if you have permissions).
- Runs in synchronous mode (simple, reliable). Async is used only for RSS fetch.
- All calculations are defensive: N/A instead of crashing.

Requirements:
  pip install ib_insync aiohttp feedparser

Optional (if present, used automatically):
  pip install beautifulsoup4 lxml  (only if you extend parsing)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import random
import re
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import aiohttp
import feedparser
from ib_insync import IB, Stock, ScannerSubscription, util

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

IB_HOST = os.getenv("IB_HOST", "127.0.0.1")
IB_PORT = int(os.getenv("IB_PORT", "7496"))

TOP_GAINERS_COUNT_DEFAULT = 50
IB_CONNECT_TIMEOUT = 10

# Use delayed-frozen by default (4). Use 1 for real-time, 3 delayed.
IB_MARKET_DATA_TYPE = int(os.getenv("IB_MARKET_DATA_TYPE", "4"))

# Market data snapshot wait (sec). Snapshot fields can lag; 1.5–3.0 works well.
MARKETDATA_SNAPSHOT_WAIT = float(os.getenv("MARKETDATA_SNAPSHOT_WAIT", "2.0"))

# Historical data settings
HIST_DAILY_LOOKBACK_DAYS = int(os.getenv("HIST_DAILY_LOOKBACK_DAYS", "15"))
HIST_USE_RTH = False  # include extended hours (helps for off-hours context)

# RVOL computation
RVOL_AVG_DAYS = int(os.getenv("RVOL_AVG_DAYS", "10"))  # average daily volume window
RVOL_MIN_AVG_VOL = int(os.getenv("RVOL_MIN_AVG_VOL", "1"))  # avoid divide-by-zero

# News engine
RSS_FETCH_TIMEOUT = int(os.getenv("RSS_FETCH_TIMEOUT", "15"))
RSS_CONCURRENCY = int(os.getenv("RSS_CONCURRENCY", "15"))
RSS_MAX_ITEMS_PER_FEED = int(os.getenv("RSS_MAX_ITEMS_PER_FEED", "35"))
NEWS_LOOKBACK_HOURS = int(os.getenv("NEWS_LOOKBACK_HOURS", "48"))
NEWS_VELOCITY_WINDOW_MIN = int(os.getenv("NEWS_VELOCITY_WINDOW_MIN", "10"))
NEWS_SPIKE_VELOCITY_THRESHOLD = int(os.getenv("NEWS_SPIKE_VELOCITY_THRESHOLD", "8"))

# Float cache (persist between runs)
FLOAT_CACHE_PATH = Path(os.getenv("FLOAT_CACHE_PATH", "scanner_float_cache.json"))

# Common RSS feed list paths (first existing is used)
RSS_FEEDLIST_CANDIDATES = [
    Path("rss_feeds.json"),
    Path("rss_feeds.txt"),
    Path("scanner/rss_feeds.json"),
    Path("scanner/rss_feeds.txt"),
    Path("config/rss_feeds.json"),
    Path("config/rss_feeds.txt"),
]

# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
                return None
            return float(x)
        s = str(x).strip()
        if s.lower() in {"nan", "none", ""}:
            return None
        v = float(s)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None

def safe_int(x: Any) -> Optional[int]:
    try:
        if x is None:
            return None
        if isinstance(x, bool):
            return int(x)
        if isinstance(x, int):
            return x
        if isinstance(x, float):
            if math.isnan(x) or math.isinf(x):
                return None
            return int(x)
        s = str(x).strip().replace(",", "")
        if s.lower() in {"nan", "none", ""}:
            return None
        return int(float(s))
    except Exception:
        return None

def fmt_pct(x: Optional[float], ndp: int = 2) -> str:
    if x is None:
        return "N/A"
    return f"{x:.{ndp}f}%"

def fmt_usd(x: Optional[float], ndp: int = 2) -> str:
    if x is None:
        return "N/A"
    return f"{x:.{ndp}f}$"

def fmt_num(x: Optional[float], ndp: int = 2) -> str:
    if x is None:
        return "N/A"
    return f"{x:.{ndp}f}"

def fmt_int(x: Optional[int]) -> str:
    if x is None:
        return "N/A"
    return f"{x}"

def format_float_display(raw_float: Any) -> str:
    """
    User-requested float display format (K/M/B).
    Accepts int-like values (shares).
    """
    v = safe_int(raw_float)
    if v is None:
        return "N/A"
    if v >= 1_000_000_000:
        return f"{v/1_000_000_000:.2f}B"
    if v >= 1_000_000:
        return f"{v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"{v/1_000:.0f}K"
    return str(v)

def float_category(float_shares: Optional[int]) -> str:
    if float_shares is None:
        return "UNKNOWN"
    if float_shares < 10_000_000:
        return "LOW"
    if float_shares < 50_000_000:
        return "MID"
    return "HIGH"

def market_session_label(now_utc: datetime) -> str:
    """
    Rough US market session labelling (no holiday calendar).
    Used only as display context, not for logic gating.
    """
    # Convert UTC to US/Eastern approximated by offset (-5 standard, -4 DST).
    # We avoid external deps; just show "OFF_HOURS" when uncertain.
    # If you want precise session classification, integrate exchange calendar.
    weekday = now_utc.weekday()  # Mon=0 ... Sun=6
    if weekday >= 5:
        return "WEEKEND"
    # Approximate regular session 14:30-21:00 UTC (EST) / 13:30-20:00 UTC (EDT).
    # Without DST, use a broad window.
    h = now_utc.hour + now_utc.minute / 60
    if 12.0 <= h < 14.5:
        return "PRE"
    if 14.5 <= h < 21.0:
        return "RTH"
    if 21.0 <= h < 23.5:
        return "AFT"
    return "OFF"

def ensure_windows_event_loop_policy() -> None:
    """
    If you run this on Windows with Python 3.8+, selector loop avoids
    certain Proactor edge cases with networking libs.
    """
    import sys
    if sys.platform.startswith("win"):
        try:
            import asyncio as _asyncio
            _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass

# -----------------------------------------------------------------------------
# IBKR connectivity helpers
# -----------------------------------------------------------------------------

def ib_connect(client_id: Optional[int] = None) -> IB:
    ib = IB()
    if client_id is None:
        client_id = int(time.time()) % 10_000 + random.randint(0, 200)
    logging.info("Connecting to %s:%s with clientId %s...", IB_HOST, IB_PORT, client_id)
    ib.connect(IB_HOST, IB_PORT, clientId=client_id, timeout=IB_CONNECT_TIMEOUT)
    return ib

def ib_disconnect_quietly(ib: IB) -> None:
    try:
        if ib.isConnected():
            ib.disconnect()
    except Exception:
        pass

# -----------------------------------------------------------------------------
# Step 1: Top gainers from IBKR scanner (symbols only)
# -----------------------------------------------------------------------------

def fetch_top_gainers_from_ibkr(number_of_rows: int) -> List[Stock]:
    """
    Returns list of Stock contracts (qualified when possible).
    """
    ib = None
    try:
        ib = ib_connect()
        logging.info("API connection ready")
        try:
            ib.reqMarketDataType(IB_MARKET_DATA_TYPE)
        except Exception:
            pass

        scan_sub = ScannerSubscription(
            instrument="STK",
            locationCode="STK.US.MAJOR",
            scanCode="TOP_PERC_GAIN",
            numberOfRows=number_of_rows,
        )
        scan_data = ib.reqScannerData(scan_sub)
        contracts: List[Stock] = []
        for item in scan_data:
            try:
                c = item.contractDetails.contract
                # Force as Stock() so downstream expectations are stable.
                contracts.append(Stock(c.symbol, c.exchange or "SMART", c.currency or "USD"))
            except Exception:
                continue

        # Qualify for conId etc. Some symbols may not qualify (halts, OTC, etc).
        try:
            qualified = ib.qualifyContracts(*contracts)
            contracts = list(qualified) if qualified else contracts
        except Exception:
            pass

        logging.info("Scanner returned %d symbols", len(contracts))
        return contracts
    finally:
        if ib:
            ib_disconnect_quietly(ib)

# -----------------------------------------------------------------------------
# Step 2: Market snapshot + historical bars (gap / %chg / rvol)
# -----------------------------------------------------------------------------

@dataclass
class MarketEnrichment:
    symbol: str
    # Snapshot
    last_price: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    open_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    volume: Optional[int] = None
    prev_close: Optional[float] = None  # from historical bars
    # Derived pillars
    gap_percent: Optional[float] = None
    change_percent: Optional[float] = None
    relative_volume: Optional[float] = None
    avg_daily_volume: Optional[float] = None
    # Extra
    vwap: Optional[float] = None
    spread: Optional[float] = None
    # Debug helpers
    daily_bars_count: int = 0

def get_market_snapshot(ib: IB, contract: Stock, sleep_seconds: float) -> Dict[str, Any]:
    """
    Requests a snapshot and returns the fields we care about.
    """
    ticker = ib.reqMktData(contract, "", snapshot=True, regulatorySnapshot=False)
    ib.sleep(sleep_seconds)
    # Cancel to release resources (even for snapshot, ib_insync recommends cancel).
    try:
        ib.cancelMktData(contract)
    except Exception:
        pass

    last_price = safe_float(getattr(ticker, "last", None))
    bid = safe_float(getattr(ticker, "bid", None))
    ask = safe_float(getattr(ticker, "ask", None))
    open_price = safe_float(getattr(ticker, "open", None))
    high_price = safe_float(getattr(ticker, "high", None))
    low_price = safe_float(getattr(ticker, "low", None))
    volume = safe_int(getattr(ticker, "volume", None))

    # Some IB accounts populate "close" as last close; we still prefer historical prev_close.
    snap_close = safe_float(getattr(ticker, "close", None))

    return {
        "last": last_price,
        "bid": bid,
        "ask": ask,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "volume": volume,
        "snap_close": snap_close,
    }

def get_daily_bars(ib: IB, contract: Stock, lookback_days: int) -> List[Any]:
    """
    Daily bars, including extended hours (useRTH=False).
    """
    duration = f"{lookback_days} D"
    try:
        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=HIST_USE_RTH,
            formatDate=1,
            keepUpToDate=False,
        )
        return list(bars) if bars else []
    except Exception as e:
        logging.debug("Historical daily bars failed for %s: %s", contract.symbol, e)
        return []

def compute_gap_percent(today_open: Optional[float], prev_close: Optional[float]) -> Optional[float]:
    if today_open is None or prev_close is None or prev_close == 0:
        return None
    return (today_open - prev_close) / prev_close * 100.0

def compute_change_percent(last_price: Optional[float], prev_close: Optional[float]) -> Optional[float]:
    if last_price is None or prev_close is None or prev_close == 0:
        return None
    return (last_price - prev_close) / prev_close * 100.0

def compute_rvol(current_volume: Optional[float], avg_volume: Optional[float]) -> Optional[float]:
    if current_volume is None or avg_volume is None or avg_volume <= 0:
        return None
    return current_volume / avg_volume

def compute_avg_daily_volume(daily_volumes: List[float], window: int) -> Optional[float]:
    vols = [v for v in daily_volumes if v is not None and v >= 0]
    if len(vols) < 2:
        return None
    # Use last `window` excluding most recent to avoid biasing avg by current spike day
    # But if we don't have enough, use whatever we have.
    historical = vols[:-1]
    if not historical:
        return None
    tail = historical[-window:] if len(historical) >= window else historical
    try:
        avg = statistics.mean(tail)
        return float(avg)
    except Exception:
        return None

def enrich_contract_with_market_data(
    ib: IB,
    contract: Stock,
    snapshot_wait: float,
    lookback_days: int,
) -> MarketEnrichment:
    symbol = contract.symbol
    enrichment = MarketEnrichment(symbol=symbol)

    snap = get_market_snapshot(ib, contract, snapshot_wait)
    enrichment.last_price = snap["last"]
    enrichment.bid = snap["bid"]
    enrichment.ask = snap["ask"]
    enrichment.open_price = snap["open"]
    enrichment.high_price = snap["high"]
    enrichment.low_price = snap["low"]
    enrichment.volume = snap["volume"]

    if enrichment.bid is not None and enrichment.ask is not None and enrichment.ask >= enrichment.bid:
        enrichment.spread = enrichment.ask - enrichment.bid

    daily_bars = get_daily_bars(ib, contract, lookback_days)
    enrichment.daily_bars_count = len(daily_bars)

    # prev close: bar[-2].close, today open: bar[-1].open (represents most recent trading day)
    if len(daily_bars) >= 2:
        prev_bar = daily_bars[-2]
        last_bar = daily_bars[-1]
        enrichment.prev_close = safe_float(getattr(prev_bar, "close", None))
        # Use last_bar.open as "session open" for most recent trading day.
        # On weekends, this is Friday's open which is still informative.
        today_open = safe_float(getattr(last_bar, "open", None))
        enrichment.gap_percent = compute_gap_percent(today_open, enrichment.prev_close)

        # Change % uses snapshot last if available; else use last_bar.close.
        last_price = enrichment.last_price
        if last_price is None:
            last_price = safe_float(getattr(last_bar, "close", None))
            enrichment.last_price = last_price
        enrichment.change_percent = compute_change_percent(last_price, enrichment.prev_close)

        # RVOL: current volume uses last_bar.volume if snapshot volume missing (often off-hours).
        daily_vols = [safe_float(getattr(b, "volume", None)) for b in daily_bars]
        avg_vol = compute_avg_daily_volume([v for v in daily_vols if v is not None], RVOL_AVG_DAYS)
        enrichment.avg_daily_volume = avg_vol
        cur_vol = enrichment.volume
        if cur_vol is None:
            cur_vol = safe_float(getattr(last_bar, "volume", None))
        enrichment.relative_volume = compute_rvol(cur_vol, avg_vol)

    return enrichment

# -----------------------------------------------------------------------------
# Step 3: Float shares (cache + best-effort scrapes)
# -----------------------------------------------------------------------------

def load_float_cache(path: Path) -> Dict[str, int]:
    if not path.exists():
        return {}
    try:
        return {k: int(v) for k, v in json.loads(path.read_text(encoding="utf-8")).items()}
    except Exception:
        return {}

def save_float_cache(path: Path, cache: Dict[str, int]) -> None:
    try:
        path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    except Exception:
        pass

def parse_finviz_float(text: str) -> Optional[int]:
    """
    Finviz 'Float' value examples: '19.50M', '1.2B', '850.6K'
    Return shares as int.
    """
    m = re.search(r"Float\s*</td>\s*<td[^>]*>\s*([0-9\.,]+)\s*([KMB])", text, re.IGNORECASE)
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    suf = m.group(2).upper()
    mult = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(suf, 1)
    return int(num * mult)

def fetch_float_from_finviz(symbol: str, timeout: int = 10) -> Optional[int]:
    """
    Best-effort: Finviz quote page scrape for Float.
    """
    import urllib.request
    url = f"https://finviz.com/quote.ashx?t={symbol}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        return parse_finviz_float(html)
    except Exception:
        return None

def fetch_float_shares(symbol: str, float_cache: Dict[str, int]) -> Tuple[Optional[int], str]:
    """
    Returns (float_shares, source_label)
    """
    sym = symbol.upper().strip()
    if sym in float_cache:
        return float_cache[sym], "cache"
    # Finviz fallback (simple, often reliable)
    finviz_val = fetch_float_from_finviz(sym)
    if finviz_val is not None:
        float_cache[sym] = finviz_val
        return finviz_val, "finviz"
    return None, "none"

# -----------------------------------------------------------------------------
# Step 4: RSS news engine (fetch once, attach per symbol)
# -----------------------------------------------------------------------------

@dataclass
class NewsHeadline:
    headline: str
    url: str
    source: str
    timestamp_ts: int

@dataclass
class NewsSummary:
    total_headlines: int = 0
    unique_headlines: int = 0
    replicated_headlines: int = 0
    regions: List[str] = None
    velocity_10m: int = 0
    avg_sentiment: float = 0.0
    keyword_score: float = 0.0
    c3_score: float = 0.0
    is_spike: bool = False
    top_headlines: List[NewsHeadline] = None

POS_WORDS = {
    "beats", "beat", "surge", "surges", "soars", "soar", "record", "records", "wins",
    "win", "upgrade", "upgrades", "raised", "raises", "strong", "growth", "profit",
    "profits", "breakthrough", "approval", "cleared", "clears", "contract", "contracts",
}
NEG_WORDS = {
    "miss", "misses", "plunge", "plunges", "drops", "drop", "downgrade", "downgrades",
    "lawsuit", "fraud", "probe", "investigation", "halt", "halts", "bankrupt", "bankruptcy",
    "warning", "warns", "recall", "recalls",
}
HOTWORDS = {
    "ai", "artificial intelligence", "fda", "phase", "contract", "merger", "acquisition",
    "earnings", "guidance", "sec", "short", "squeeze", "offering", "reverse split",
}

def guess_region_from_url(url: str) -> str:
    u = url.lower()
    if ".co.uk" in u or ".uk/" in u:
        return "EU/UK"
    if ".eu" in u:
        return "EU/UK"
    if ".cn" in u:
        return "CN"
    if ".in" in u:
        return "IN"
    if ".ca" in u:
        return "CA"
    return "INT/US"

def extract_symbol_hits(text: str, symbols: Iterable[str]) -> List[str]:
    """
    Conservative matching: symbol as whole word (case-insensitive).
    """
    hits = []
    upper = text.upper()
    for sym in symbols:
        # whole word match
        if re.search(rf"\b{re.escape(sym)}\b", upper):
            hits.append(sym)
    return hits

def sentiment_score(text: str) -> float:
    t = text.lower()
    pos = sum(1 for w in POS_WORDS if w in t)
    neg = sum(1 for w in NEG_WORDS if w in t)
    if pos == 0 and neg == 0:
        return 0.0
    return (pos - neg) / max(pos + neg, 1)

def keyword_score(text: str) -> float:
    t = text.lower()
    score = 0
    for w in HOTWORDS:
        if w in t:
            score += 1
    # scale to /10 like the earlier output
    return min(10.0, float(score))

async def fetch_one_rss(session: aiohttp.ClientSession, url: str) -> Tuple[str, bytes]:
    try:
        async with session.get(url, timeout=RSS_FETCH_TIMEOUT) as resp:
            return url, await resp.read()
    except Exception:
        return url, b""

async def fetch_all_rss(urls: List[str]) -> Dict[str, bytes]:
    connector = aiohttp.TCPConnector(limit=RSS_CONCURRENCY, ssl=False)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; scanner/1.0)"}
    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        tasks = [fetch_one_rss(session, u) for u in urls]
        results = await asyncio.gather(*tasks)
    return {u: data for (u, data) in results if data}

def load_rss_feed_urls() -> List[str]:
    for p in RSS_FEEDLIST_CANDIDATES:
        if p.exists():
            try:
                if p.suffix.lower() == ".json":
                    data = json.loads(p.read_text(encoding="utf-8"))
                    urls = []
                    if isinstance(data, list):
                        urls = [str(x).strip() for x in data]
                    elif isinstance(data, dict):
                        # allow {"feeds":[...]}
                        feeds = data.get("feeds") or data.get("rss") or []
                        urls = [str(x).strip() for x in feeds]
                    urls = [u for u in urls if u.startswith("http")]
                    logging.info("Loaded %d RSS feeds from %s", len(urls), p)
                    return urls
                else:
                    urls = [line.strip() for line in p.read_text(encoding="utf-8").splitlines()]
                    urls = [u for u in urls if u and not u.startswith("#") and u.startswith("http")]
                    logging.info("Loaded %d RSS feeds from %s", len(urls), p)
                    return urls
            except Exception:
                continue
    # Fallback minimal list (keeps script functional)
    urls = [
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US",
        "https://www.globenewswire.com/RssFeed/industry/Technology?rssFeedType=GeoRss",
        "https://www.prnewswire.com/rss/news-releases-list.rss",
    ]
    logging.warning("No RSS feed list found; using %d fallback feeds", len(urls))
    return urls

def parse_rss_items(feed_bytes: bytes, source_url: str) -> List[NewsHeadline]:
    parsed = feedparser.parse(feed_bytes)
    headlines: List[NewsHeadline] = []
    now_ts = int(time.time())
    cutoff_ts = now_ts - NEWS_LOOKBACK_HOURS * 3600

    for e in parsed.entries[:RSS_MAX_ITEMS_PER_FEED]:
        title = (getattr(e, "title", "") or "").strip()
        link = (getattr(e, "link", "") or "").strip()
        if not title or not link:
            continue

        # Try to get published timestamp
        ts = None
        if getattr(e, "published_parsed", None):
            try:
                ts = int(time.mktime(e.published_parsed))
            except Exception:
                ts = None
        if ts is None:
            ts = now_ts  # conservative: treat as recent if missing
        if ts < cutoff_ts:
            continue

        src = parsed.feed.get("title", "") or source_url
        headlines.append(NewsHeadline(headline=title, url=link, source=str(src)[:80], timestamp_ts=int(ts)))

    return headlines

def build_news_index(all_headlines: List[NewsHeadline], symbols: List[str]) -> Dict[str, List[NewsHeadline]]:
    index: Dict[str, List[NewsHeadline]] = {s: [] for s in symbols}
    for h in all_headlines:
        text = f"{h.headline} {h.url}"
        hits = extract_symbol_hits(text, symbols)
        for sym in hits:
            index[sym].append(h)
    # sort newest first per symbol
    for sym, items in index.items():
        items.sort(key=lambda x: x.timestamp_ts, reverse=True)
    return index

def summarize_news(items: List[NewsHeadline]) -> NewsSummary:
    if not items:
        return NewsSummary(
            total_headlines=0,
            unique_headlines=0,
            replicated_headlines=0,
            regions=[],
            velocity_10m=0,
            avg_sentiment=0.0,
            keyword_score=0.0,
            c3_score=0.0,
            is_spike=False,
            top_headlines=[],
        )

    total = len(items)
    title_counts: Dict[str, int] = {}
    for h in items:
        title_counts[h.headline] = title_counts.get(h.headline, 0) + 1
    unique = len(title_counts)
    replicated = total - unique

    # velocity (last N minutes)
    now_ts = int(time.time())
    window = NEWS_VELOCITY_WINDOW_MIN * 60
    vel_10m = sum(1 for h in items if now_ts - h.timestamp_ts <= window)

    # sentiment and keywords
    sentiments = [sentiment_score(h.headline) for h in items[:20]]
    avg_sent = float(statistics.mean(sentiments)) if sentiments else 0.0
    kw_scores = [keyword_score(h.headline) for h in items[:20]]
    kw = float(statistics.mean(kw_scores)) if kw_scores else 0.0

    regions = sorted({guess_region_from_url(h.url) for h in items})
    # Score: simple weighted model (tune later)
    c3 = (vel_10m * 1.6) + (total * 0.10) + (avg_sent * 6.0) + (kw * 0.6)
    spike = vel_10m >= NEWS_SPIKE_VELOCITY_THRESHOLD

    top = items[:5]
    return NewsSummary(
        total_headlines=total,
        unique_headlines=unique,
        replicated_headlines=replicated,
        regions=regions,
        velocity_10m=vel_10m,
        avg_sentiment=avg_sent,
        keyword_score=kw,
        c3_score=c3,
        is_spike=spike,
        top_headlines=top,
    )

# -----------------------------------------------------------------------------
# Step 5: Printer (merged: primary pillars + compact C3 + awareness)
# -----------------------------------------------------------------------------

def print_scanner_view(entries: List[Dict[str, Any]], top_n_headlines: int = 5) -> None:
    """
    Unified printer:
    - First line: 5 pillars + additional market fields
    - Second line: C3/News stats line (compact)
    - Then: awareness + headlines
    """
    for e in entries:
        symbol = e.get("symbol", "N/A")

        fire_icon = "🔥" if e.get("is_spike") else " "

        gap = e.get("gap_percent")
        chg = e.get("change_percent")
        rvol = e.get("relative_volume")
        float_raw = e.get("float_shares")
        float_cat = e.get("float_category", "UNKNOWN")
        price = e.get("last_price")

        bid = e.get("bid")
        ask = e.get("ask")
        spread = e.get("spread")
        volume = e.get("volume")
        avg_vol = e.get("avg_daily_volume")
        session = e.get("market_session", "N/A")

        has_news = "Y" if e.get("total_headlines", 0) > 0 else "N"

        # ---- Line 1 (merged pillars + microstructure) ----
        parts = [
            f"{symbol} | {fire_icon}",
            f"Session:{session}",
            f"Gap:{fmt_pct(gap)}",
            f"Chg:{fmt_pct(chg)}",
            f"RVOL:{(f'{rvol:.2f}×' if isinstance(rvol, (int,float)) else 'N/A')}",
            f"Float:{format_float_display(float_raw)} ({float_cat})",
            f"Price:{fmt_usd(price)}",
            f"Bid:{fmt_usd(bid)}",
            f"Ask:{fmt_usd(ask)}",
            f"Spr:{fmt_usd(spread)}",
            f"Vol:{fmt_int(safe_int(volume))}",
            f"AvgVol:{fmt_int(safe_int(avg_vol))}",
            f"News:{has_news}",
        ]
        print(" | ".join(parts))

        # ---- Line 2 (compact C3 like original) ----
        print(
            f"{symbol} | {fire_icon} | "
            f"Vel10m:{e.get('velocity_10m', 0)} | "
            f"Total:{e.get('total_headlines', 0)} | "
            f"Spike:{'YES' if e.get('is_spike') else 'NO'} | "
            f"Sent:{e.get('avg_sentiment', 0.0):+.2f} | "
            f"Score:{e.get('c3_score', 0.0):.2f} | "
            f"KW:{e.get('keyword_score', 0.0):.2f}/10"
        )

        # ---- Awareness ----
        print("\nAWARENESS")
        print(f"Total Articles: {e.get('total_headlines', 0)}")
        print(f"Unique Articles: {e.get('unique_headlines', 0)}")
        print(f"Replicated Articles: {e.get('replicated_headlines', 0)}")
        regions = e.get("regions", []) or []
        print(f"Regions: {', '.join(regions) if regions else 'N/A'}")
        print(f"Region Count: {len(regions)}")

        # ---- Trade context ----
        trade_suggestion = e.get("trade_suggestion", "Neutral ⚪")
        trade_rationale = e.get("trade_rationale", "No strong signals")
        print(f"\nTrade: {trade_suggestion} — {trade_rationale}")

        # ---- Top headlines ----
        headlines = e.get("top_headlines", []) or []
        if headlines:
            print("\nTop Headlines:")
            for idx, h in enumerate(headlines[:top_n_headlines], start=1):
                title = getattr(h, "headline", None) or (h.get("headline") if isinstance(h, dict) else "N/A")
                url = getattr(h, "url", None) or (h.get("url") if isinstance(h, dict) else None)
                print(f" {idx}. {title} — 1 source(s)")
                if url:
                    print(f"    {url}")
        else:
            print("\nTop Headlines: (none)")

        print("-" * 70)

# -----------------------------------------------------------------------------
# Trade suggestion rules (simple, tunable)
# -----------------------------------------------------------------------------

def decide_trade_context(
    gap: Optional[float],
    chg: Optional[float],
    rvol: Optional[float],
    is_spike: bool,
    avg_sentiment: float,
    total_headlines: int,
) -> Tuple[str, str]:
    rationale_bits = []
    if is_spike:
        rationale_bits.append("News velocity spike")
    if total_headlines > 0:
        rationale_bits.append("News present")
    if rvol is not None and rvol >= 2:
        rationale_bits.append("High RVOL")
    if gap is not None and abs(gap) >= 5:
        rationale_bits.append("Large gap")
    if avg_sentiment >= 0.15:
        rationale_bits.append("Positive sentiment")
    if avg_sentiment <= -0.15:
        rationale_bits.append("Negative sentiment")

    # Basic recommendation
    if (is_spike or (total_headlines >= 5)) and (avg_sentiment >= 0.15) and ((rvol or 0) >= 1.5):
        return "Consider Long 🚀", "; ".join(rationale_bits) or "Confluence"
    if (is_spike or (total_headlines >= 5)) and (avg_sentiment <= -0.15):
        return "Caution ⚠️", "; ".join(rationale_bits) or "Risk signals"
    if (is_spike or total_headlines >= 3):
        return "Watch (Long) 👀", "; ".join(rationale_bits) or "Keep on watchlist"
    if (rvol is not None and rvol >= 2):
        return "Watch (Momentum) 👀", "; ".join(rationale_bits) or "Volume anomaly"
    return "Neutral ⚪", "; ".join(rationale_bits) or "No strong signals"

# -----------------------------------------------------------------------------
# Main cycle
# -----------------------------------------------------------------------------

def build_entries(
    contracts: List[Stock],
    market_enrichments: Dict[str, MarketEnrichment],
    float_cache: Dict[str, int],
    news_index: Dict[str, List[NewsHeadline]],
) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    now = utc_now()
    session = market_session_label(now)

    for c in contracts:
        sym = c.symbol
        me = market_enrichments.get(sym) or MarketEnrichment(symbol=sym)

        float_shares, float_source = fetch_float_shares(sym, float_cache)
        fcat = float_category(float_shares)

        news_items = news_index.get(sym, [])
        ns = summarize_news(news_items)

        trade_suggestion, trade_rationale = decide_trade_context(
            gap=me.gap_percent,
            chg=me.change_percent,
            rvol=me.relative_volume,
            is_spike=ns.is_spike,
            avg_sentiment=ns.avg_sentiment,
            total_headlines=ns.total_headlines,
        )

        entry = {
            "symbol": sym,
            # 5 pillars + %chg
            "gap_percent": me.gap_percent,
            "change_percent": me.change_percent,
            "relative_volume": me.relative_volume,
            "avg_daily_volume": me.avg_daily_volume,
            "float_shares": float_shares,
            "float_category": fcat,
            "float_source": float_source,
            "last_price": me.last_price,
            # microstructure
            "bid": me.bid,
            "ask": me.ask,
            "spread": me.spread,
            "open_price": me.open_price,
            "high_price": me.high_price,
            "low_price": me.low_price,
            "volume": me.volume,
            "prev_close": me.prev_close,
            "market_session": session,
            "daily_bars_count": me.daily_bars_count,
            # news fields
            "total_headlines": ns.total_headlines,
            "unique_headlines": ns.unique_headlines,
            "replicated_headlines": ns.replicated_headlines,
            "regions": ns.regions or [],
            "velocity_10m": ns.velocity_10m,
            "avg_sentiment": ns.avg_sentiment,
            "keyword_score": ns.keyword_score,
            "c3_score": ns.c3_score,
            "is_spike": ns.is_spike,
            "top_headlines": ns.top_headlines,
            # trade
            "trade_suggestion": trade_suggestion,
            "trade_rationale": trade_rationale,
        }
        entries.append(entry)

    # Default sort: by gap desc, then change desc, then news score
    def sort_key(e: Dict[str, Any]) -> Tuple[float, float, float]:
        gap = safe_float(e.get("gap_percent")) or -1e9
        chg = safe_float(e.get("change_percent")) or -1e9
        score = safe_float(e.get("c3_score")) or 0.0
        return (gap, chg, score)

    entries.sort(key=sort_key, reverse=True)
    return entries

def run_once(args: argparse.Namespace) -> None:
    print("\n" + "=" * 70)
    print(f"STARTING SCAN CYCLE — {utc_now().isoformat()}")
    print("=" * 70)

    # 1) Scanner symbols
    contracts = fetch_top_gainers_from_ibkr(args.rows)
    if not contracts:
        logging.error("No scanner results (check TWS/IBG, permissions, or scanner parameters).")
        return

    # 2) RSS fetch once
    rss_urls = load_rss_feed_urls()
    logging.info("Fetching RSS feeds (async)...")
    try:
        feed_bytes_map = asyncio.run(fetch_all_rss(rss_urls))
    except RuntimeError:
        # If already in an event loop (rare in scripts), create new loop manually.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        feed_bytes_map = loop.run_until_complete(fetch_all_rss(rss_urls))
        loop.close()

    all_headlines: List[NewsHeadline] = []
    for url, b in feed_bytes_map.items():
        try:
            all_headlines.extend(parse_rss_items(b, url))
        except Exception:
            continue
    logging.info("RSS fetch complete. Sources=%d Items=%d", len(feed_bytes_map), len(all_headlines))

    symbols = [c.symbol for c in contracts]
    news_index = build_news_index(all_headlines, symbols)

    # 3) Market enrichment in one IB session to reduce overhead
    ib = None
    market_enrichments: Dict[str, MarketEnrichment] = {}
    try:
        ib = ib_connect()
        try:
            ib.reqMarketDataType(IB_MARKET_DATA_TYPE)
        except Exception:
            pass
        logging.info("API connection ready (market data)")

        for i, c in enumerate(contracts, start=1):
            logging.info("(%d/%d) Enriching %s", i, len(contracts), c.symbol)
            try:
                me = enrich_contract_with_market_data(
                    ib,
                    c,
                    snapshot_wait=args.snapshot_wait,
                    lookback_days=args.daily_lookback,
                )
                market_enrichments[c.symbol] = me
            except Exception as e:
                logging.warning("Enrichment failed for %s: %s", c.symbol, e)
                market_enrichments[c.symbol] = MarketEnrichment(symbol=c.symbol)

    finally:
        if ib:
            ib_disconnect_quietly(ib)

    # 4) Float cache
    float_cache = load_float_cache(FLOAT_CACHE_PATH)
    logging.info("Loaded float cache entries: %d", len(float_cache))

    # 5) Build entries + save float cache after best-effort fetches
    entries = build_entries(contracts, market_enrichments, float_cache, news_index)
    save_float_cache(FLOAT_CACHE_PATH, float_cache)

    # 6) Print
    print("\n" + "=" * 70)
    print(f"HOT NEWS (PRIMARY — merged pillars + C3 + awareness) — {utc_now().isoformat()}")
    print("=" * 70)
    print_scanner_view(entries, top_n_headlines=args.top_headlines)

def main() -> None:
    ensure_windows_event_loop_policy()

    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=TOP_GAINERS_COUNT_DEFAULT, help="Top gainers rows from IBKR scanner")
    parser.add_argument("--snapshot-wait", type=float, default=MARKETDATA_SNAPSHOT_WAIT, help="Seconds to wait for snapshot fields")
    parser.add_argument("--daily-lookback", type=int, default=HIST_DAILY_LOOKBACK_DAYS, help="Daily bars lookback days")
    parser.add_argument("--top-headlines", type=int, default=5, help="Top headlines per symbol")
    parser.add_argument("--log", type=str, default="INFO", help="Logging level (DEBUG/INFO/WARNING/ERROR)")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log.upper(), logging.INFO),
        format="[%(levelname)s] %(message)s",
    )

    run_once(args)

if __name__ == "__main__":
    main()
