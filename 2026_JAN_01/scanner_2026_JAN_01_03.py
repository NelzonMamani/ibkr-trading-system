#!/usr/bin/env python3
"""
scanner.py — Ross Cameron (Warrior Trading) style scanner module (standalone + importable)

GOALS (your requirements)
-------------------------
1) Standalone script that runs anywhere (like your original):
   - IBKR scanner for top movers (with fallback scan codes)
   - News engine (RSS from verified_rss.txt)
   - Enrichment for Ross 5 pillars:
       Gap% / %Change, Relative Volume, Float, Price, News
   - Prints 4 times per cycle:
       (1) Cycle legacy C3 (spike/velocity based)
       (2) General verbose (NO Ross filter; sorted by gap/%change)
       (3) Filtered compact watchlist (Ross filter; sorted by gap/%change)
       (4) Filtered deep watchlist (Ross filter; sorted by gap/%change)
   - Saves timestamped files, including Ross watchlist (top 5–10)

2) Works as a module inside a bigger trading system:
   - core engine function run_scan(cfg) returns structured data without sleeping.
   - printing/sleeping only in standalone mode.

3) Data sourcing strategy (important!):
   - IBKR is primary for symbols + prices when available.
   - If IBKR does not provide float/RVOL inputs due to subscription/fields:
       We fall back to Yahoo Finance (JSON endpoints) and/or Finviz (HTML scrape).
   - We cache floats locally to avoid repeated lookups:
       floats_cache.json is auto-created/updated.

NOTE ABOUT "GAP CAN NEVER BE EMPTY"
----------------------------------
For TOP_PERC_GAIN symbols, there is always a % move vs prior close by definition.
Outside RTH, IBKR may not populate open/prevClose fields, so we must compute
gap_percent robustly:
  1) Use percent_change (last vs prevClose) if available
  2) Else use open vs prevClose
  3) Else use last vs prevClose
  4) Else fallback to scanner's implied move (0 if truly unavailable)

This preserves your expectation: gap_percent is never None for top gainers.
"""

# ============================
# Section 0: Windows asyncio event loop fix
# ============================
import sys
if sys.platform.startswith("win"):
    import asyncio as _asyncio_tmp
    _asyncio_tmp.set_event_loop_policy(_asyncio_tmp.WindowsSelectorEventLoopPolicy())

# ============================
# Section 1: Imports
# ============================
import argparse
import asyncio
import json
import logging
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import feedparser

# IBKR
from ib_insync import IB, ScannerSubscription

# HTTP fallbacks (Yahoo / Finviz)
try:
    import requests  # preferred
except Exception:
    requests = None  # fallback to urllib if requests isn't available

from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# ============================
# Section 2: Logging
# ============================
LOGGER = logging.getLogger("scanner")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logging.getLogger("aiohttp").setLevel(logging.WARNING)

# ============================
# Section 3: Config
# ============================
@dataclass(frozen=True)
class RossPillarsConfig:
    """
    Ross Cameron "5 Pillars" (v1 defaults). You can tune later.

    1) Relative Volume ≥ X  (Ross often uses 5x; we default 2x so you see candidates)
    2) Gap% / %Change ≥ Y   (strong mover; premarket gappers)
    3) News catalyst present (or at least some news awareness)
    4) Price range: $2–$20  (Ross avoids sub-$2 and >$20)
    5) Low float            (Ross likes <10M; we start with <20M until your data is solid)
    """
    min_price: float = 2.0
    max_price: float = 20.0
    min_gap_percent: float = 5.0
    min_rvol: float = 2.0
    max_float: int = 20_000_000

@dataclass(frozen=True)
class ScannerConfig:
    verified_rss_file: str = "verified_rss.txt"    # RSS list file
    floats_cache_file: str = "floats_cache.json"   # auto-updated cache

    use_ibkr: bool = True
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 7496
    ibkr_top_rows: int = 50
    ibkr_scan_codes: Tuple[str, ...] = ("TOP_PERC_GAIN", "HOT_BY_VOLUME", "MOST_ACTIVE")

    # RSS
    rss_fetch_timeout: int = 30
    rss_concurrency: int = 24
    rss_fetch_retries: int = 2
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

    # News age buckets
    bucket_5m: int = 5 * 60
    bucket_10m: int = 10 * 60
    bucket_60m: int = 60 * 60
    bucket_24h: int = 24 * 3600

    # Spike detection
    absolute_spike_threshold: int = 5
    spike_ratio: float = 2.0

    # Output
    out_dir_base: str = "data"
    top_n_headlines: int = 5
    watchlist_top_n: int = 10
    cycle_sleep_seconds: int = 60

    ross: RossPillarsConfig = RossPillarsConfig()

# ============================
# Section 4: Utilities
# ============================
WORD_REGEX = re.compile(r"\b[a-zA-Z0-9]+\b")

def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def now_ts() -> int:
    return int(time.time())

def ts_to_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

def mkdirp(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)

def domain_from_url(url: str) -> str:
    m = re.search(r"https?://([^/]+)", (url or ""))
    return m.group(1).lower() if m else (url or "").lower()

def normalize_title(title: str) -> str:
    t = re.sub(r"\s+", " ", (title or "").strip().lower())
    t = re.sub(r"[^a-z0-9 ]+", "", t)
    return t

def title_fingerprint(title: str) -> str:
    n = normalize_title(title)[:240]
    return sha1(n.encode("utf-8")).hexdigest()

def safe_round(x: Optional[float], nd: int = 2) -> Optional[float]:
    try:
        return None if x is None else round(float(x), nd)
    except Exception:
        return None

def format_float_shares(raw_float):
    """Formats large integer floats to human-readable K/M/B."""
    if isinstance(raw_float, int):
        if raw_float >= 1_000_000_000:
            return f"{raw_float/1_000_000_000:.2f}B"
        elif raw_float >= 1_000_000:
            return f"{raw_float/1_000_000:.2f}M"
        elif raw_float >= 1_000:
            return f"{raw_float/1_000:.0f}K"
        else:
            return str(raw_float)
    return raw_float

def compute_spread_percent(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    try:
        if bid is None or ask is None or bid <= 0 or ask <= 0:
            return None
        mid = (bid + ask) / 2
        if mid <= 0:
            return None
        return ((ask - bid) / mid) * 100
    except Exception:
        return None

# ============================
# Section 5: Sentiment & domain weights (simple)
# ============================
POS_WORDS = {"gain","gains","beats","beat","rise","rises","up","upgrade","record","profit","positive","approve","approval","win","wins","benefit","surge"}
NEG_WORDS = {"down","drop","drops","loss","losses","miss","missed","downgrade","accuse","lawsuit","investigation","fall","fell","negative","recall","bankruptcy","cut","decline","plummet"}

DOMAIN_WEIGHTS = {
    "bloomberg.com": 2.0,
    "reuters.com": 2.0,
    "wsj.com": 1.8,
    "ft.com": 1.8,
    "cnn.com": 1.6,
    "nytimes.com": 1.6,
    "marketwatch.com": 1.4,
    "investing.com": 1.0,
    "seekingalpha.com": 0.8
}

def sentiment_score_text(text: str) -> float:
    if not text:
        return 0.0
    tokens = WORD_REGEX.findall(text.lower())
    if not tokens:
        return 0.0
    pos = sum(1 for t in tokens if t in POS_WORDS)
    neg = sum(1 for t in tokens if t in NEG_WORDS)
    if pos == 0 and neg == 0:
        return 0.0
    score = (pos - neg) / max(1, pos + neg)
    return max(-1.0, min(1.0, score))

def domain_weight_from_url(url: str) -> float:
    dom = domain_from_url(url)
    parts = dom.split(".")
    root = ".".join(parts[-2:]) if len(parts) >= 2 else dom
    return DOMAIN_WEIGHTS.get(root, 0.5)

def is_credible_source(domain: str) -> bool:
    d = (domain or "").lower()
    return any(k in d for k in ["bloomberg", "reuters", "wsj", "ft", "nytimes", "cnn"])

# ============================
# Section 6: Inputs (RSS list + float cache)
# ============================
def load_verified_rss(file_path: str) -> List[str]:
    p = Path(file_path)
    if not p.exists():
        LOGGER.error("Verified RSS file not found: %s", file_path)
        return []
    urls = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            u = line.strip()
            if u and not u.startswith("#"):
                urls.append(u)
    LOGGER.info("Loaded %d RSS feeds", len(urls))
    return urls

def load_float_cache(file_path: str) -> Dict[str, int]:
    p = Path(file_path)
    if not p.exists():
        LOGGER.warning("Float cache not found (%s). Float will be fetched from web fallbacks.", file_path)
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        out: Dict[str, int] = {}
        for k, v in raw.items():
            if isinstance(k, str) and isinstance(v, int):
                out[k.upper()] = v
        LOGGER.info("Loaded float cache for %d symbols", len(out))
        return out
    except Exception as e:
        LOGGER.warning("Failed to parse float cache (%s): %s", file_path, e)
        return {}

def save_float_cache(file_path: str, cache: Dict[str, int]) -> None:
    try:
        Path(file_path).write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception as e:
        LOGGER.warning("Failed to save float cache (%s): %s", file_path, e)

# ============================
# Section 7: RSS fetching (async)
# ============================
async def fetch_single_feed(session: aiohttp.ClientSession, url: str, sem: asyncio.Semaphore, cfg: ScannerConfig) -> Tuple[str, List[Dict[str, Any]]]:
    headers = {"User-Agent": cfg.user_agent}
    timeout = aiohttp.ClientTimeout(total=cfg.rss_fetch_timeout, connect=10, sock_read=cfg.rss_fetch_timeout)
    backoff_base = 0.6

    async with sem:
        for attempt in range(1, cfg.rss_fetch_retries + 1):
            try:
                async with session.get(url, headers=headers, timeout=timeout) as resp:
                    resp.raise_for_status()
                    raw = await resp.read()
                    parsed = feedparser.parse(raw)
                    entries = parsed.entries or []
                    normalized = []
                    for e in entries:
                        title = (e.get("title") or "").strip()
                        summary = (e.get("summary") or e.get("description") or "").strip()
                        link = (e.get("link") or "").strip()
                        published_ts = None
                        try:
                            if e.get("published_parsed"):
                                published_ts = int(time.mktime(e.published_parsed))
                            elif e.get("updated_parsed"):
                                published_ts = int(time.mktime(e.updated_parsed))
                        except Exception:
                            published_ts = None

                        normalized.append({
                            "title": title,
                            "summary": summary,
                            "link": link,
                            "published_ts": published_ts,
                            "feed_url": url
                        })
                    return url, normalized
            except (asyncio.TimeoutError, aiohttp.ClientError):
                LOGGER.debug("RSS fetch failed attempt %d/%d: %s", attempt, cfg.rss_fetch_retries, url)
            except Exception:
                LOGGER.debug("RSS fetch unexpected error: %s", url)
            await asyncio.sleep(backoff_base * (2 ** (attempt - 1)))

    return url, []

async def fetch_all_feeds_async(cfg: ScannerConfig, rss_urls: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    connector = aiohttp.TCPConnector(ssl=False, limit=cfg.rss_concurrency, limit_per_host=10)
    sem = asyncio.Semaphore(cfg.rss_concurrency)
    results: Dict[str, List[Dict[str, Any]]] = {}
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [asyncio.create_task(fetch_single_feed(session, u, sem, cfg)) for u in rss_urls]
        responses = await asyncio.gather(*tasks, return_exceptions=False)
        for url, entries in responses:
            results[url] = entries or []
    return results

def fetch_all_feeds(cfg: ScannerConfig, rss_urls: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    if not rss_urls:
        return {}
    try:
        prev_loop = asyncio.get_event_loop()
    except RuntimeError:
        prev_loop = None
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(fetch_all_feeds_async(cfg, rss_urls))
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        try:
            loop.close()
        except Exception:
            pass
        asyncio.set_event_loop(prev_loop if prev_loop is not None else asyncio.new_event_loop())

# ============================
# Section 8: Web fallbacks (Yahoo + Finviz)
# ============================
def _http_get_text(url: str, user_agent: str, timeout: int = 15) -> str:
    """HTTP GET that works even without requests installed."""
    headers = {"User-Agent": user_agent}
    if requests is not None:
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.text
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def _http_get_json(url: str, user_agent: str, timeout: int = 15) -> Dict[str, Any]:
    txt = _http_get_text(url, user_agent=user_agent, timeout=timeout)
    return json.loads(txt)

def fetch_yahoo_quote(symbol: str, user_agent: str) -> Dict[str, Any]:
    """
    Yahoo endpoints:
      - Quote (price, prevClose, open, regularMarketVolume, avg volume)
      - QuoteSummary defaultKeyStatistics (floatShares)

    Returns dict with optional keys:
      price, prev_close, open_price, volume_today, avg_volume, float_shares
    """
    sym = symbol.upper()
    out: Dict[str, Any] = {}
    try:
        # v7 quote: fast
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={sym}"
        data = _http_get_json(url, user_agent=user_agent, timeout=15)
        res = (((data or {}).get("quoteResponse") or {}).get("result") or [])
        if res:
            q = res[0]
            out["last_price"] = q.get("regularMarketPrice") or q.get("postMarketPrice") or q.get("preMarketPrice")
            out["prev_close"] = q.get("regularMarketPreviousClose")
            out["open_price"] = q.get("regularMarketOpen")
            out["volume_today"] = q.get("regularMarketVolume")
            out["avg_volume"] = q.get("averageDailyVolume3Month") or q.get("averageDailyVolume10Day")
    except Exception as e:
        LOGGER.debug("Yahoo quote failed for %s: %s", sym, e)

    try:
        # quoteSummary: floatShares lives in defaultKeyStatistics
        url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{sym}?modules=defaultKeyStatistics"
        data = _http_get_json(url, user_agent=user_agent, timeout=15)
        qs = (((data or {}).get("quoteSummary") or {}).get("result") or [])
        if qs:
            stats = (qs[0].get("defaultKeyStatistics") or {})
            fs = stats.get("floatShares")
            if isinstance(fs, dict):
                fs = fs.get("raw")
            if isinstance(fs, (int, float)):
                out["float_shares"] = int(fs)
    except Exception as e:
        LOGGER.debug("Yahoo quoteSummary failed for %s: %s", sym, e)

    return out

def _parse_finviz_float_to_int(s: str) -> Optional[int]:
    """
    Finviz formats like: '8.32M', '1.2B', '450K'
    """
    if not s:
        return None
    s = s.strip().upper()
    m = re.match(r"^([0-9.]+)\s*([KMB])$", s)
    if not m:
        # sometimes just a number
        try:
            return int(float(s.replace(",", "")))
        except Exception:
            return None
    val = float(m.group(1))
    suf = m.group(2)
    mult = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[suf]
    return int(val * mult)

def fetch_finviz_symbol(symbol: str, user_agent: str) -> Dict[str, Any]:
    """
    Scrape Finviz for Float and Avg Volume when Yahoo fails.
    This is a lightweight regex parse (no extra deps).
    """
    sym = symbol.upper()
    out: Dict[str, Any] = {}
    try:
        url = f"https://finviz.com/quote.ashx?t={sym}"
        html = _http_get_text(url, user_agent=user_agent, timeout=15)

        # Finviz key/value cells include things like:
        # <td ...>Float</td><td ...>8.32M</td>
        def find_value(key: str) -> Optional[str]:
            # try a couple patterns
            patterns = [
                rf">{re.escape(key)}<.*?>\s*([^<]+)\s*<",
                rf">{re.escape(key)}</td>\s*<td[^>]*>\s*([^<]+)\s*<"
            ]
            for pat in patterns:
                m = re.search(pat, html, flags=re.IGNORECASE | re.DOTALL)
                if m:
                    return m.group(1).strip()
            return None

        f = find_value("Float")
        if f:
            fi = _parse_finviz_float_to_int(f.replace(",", ""))
            if fi:
                out["float_shares"] = fi

        av = find_value("Avg Volume")
        if av:
            avi = _parse_finviz_float_to_int(av.replace(",", ""))
            if avi:
                out["avg_volume"] = avi

        # Sometimes Finviz has Price and Change too
        price = find_value("Price")
        if price:
            try:
                out["last_price"] = float(price.replace("$", "").replace(",", ""))
            except Exception:
                pass

    except Exception as e:
        LOGGER.debug("Finviz scrape failed for %s: %s", sym, e)

    return out

# ============================
# Section 9: IBKR scanner (with fallback scan codes) + enrichment
# ============================
def _ibkr_request_scanner_with_fallback(ib: IB, cfg: ScannerConfig) -> Tuple[List[Any], str]:
    last_exc = None
    for code in cfg.ibkr_scan_codes:
        try:
            LOGGER.info("Requesting IBKR scanner: %s (rows=%d)", code, cfg.ibkr_top_rows)
            sub = ScannerSubscription(
                instrument="STK",
                locationCode="STK.US.MAJOR",
                scanCode=code,
                numberOfRows=cfg.ibkr_top_rows
            )
            data = ib.reqScannerData(sub)
            if data:
                LOGGER.info("Scanner %s returned %d rows", code, len(data))
                return data, code
            LOGGER.warning("Scanner %s returned 0 rows, trying next.", code)
        except Exception as e:
            LOGGER.warning("Scanner %s failed (non-fatal): %s", code, e)
            last_exc = e
    if last_exc:
        LOGGER.error("All scanners failed. Last error: %s", last_exc)
    return [], "NONE"

def resolve_gap_percent(
    scan_code_used: str,
    open_price: Optional[float],
    prev_close: Optional[float],
    last_price: Optional[float],
    percent_change: Optional[float],
) -> float:
    """
    Guarantees gap_percent is not None for TOP_PERC_GAIN symbols.

    Priority:
    1) if TOP_PERC_GAIN: use percent_change if available
    2) open vs prev_close
    3) last vs prev_close
    4) fallback 0.0 (should be rare)
    """
    if scan_code_used == "TOP_PERC_GAIN" and percent_change is not None:
        return float(percent_change)
    if open_price and prev_close and prev_close > 0:
        return ((open_price - prev_close) / prev_close) * 100
    if last_price and prev_close and prev_close > 0:
        return ((last_price - prev_close) / prev_close) * 100
    return 0.0

def enrich_symbols_from_ibkr(cfg: ScannerConfig, float_cache: Dict[str, int]) -> Dict[str, Dict[str, Any]]:
    """
    Returns meta per symbol. Includes:
      - last_price, prev_close, open_price
      - percent_change, gap_percent (robust)
      - volume_today, avg_volume, relative_volume
      - float_shares (cache + web fallback)
    """
    ib = IB()
    client_id = int(time.time()) % 9999
    try:
        LOGGER.info("Connecting to IBKR host=%s port=%d clientId=%d", cfg.ibkr_host, cfg.ibkr_port, client_id)
        ib.connect(cfg.ibkr_host, cfg.ibkr_port, clientId=client_id, timeout=10)
    except Exception as e:
        LOGGER.warning("IB connect failed: %s", e)
        try:
            ib.disconnect()
        except Exception:
            pass
        return {}

    try:
        scan_data, scan_code_used = _ibkr_request_scanner_with_fallback(ib, cfg)
        if not scan_data:
            return {}

        symbols_meta: Dict[str, Dict[str, Any]] = {}
        contracts = []
        for item in scan_data:
            contract = item.contractDetails.contract
            sym = getattr(contract, "symbol", None)
            if not sym:
                continue
            sym = sym.upper()
            contracts.append(contract)
            symbols_meta[sym] = {
                "symbol": sym,
                "contract": contract,
                "longName": getattr(item.contractDetails, "longName", sym),
                "ibkr_scan_code_used": scan_code_used,
            }

        # tickers
        tickers = ib.reqTickers(*contracts) if contracts else []
        for t in tickers:
            c = getattr(t, "contract", None)
            if not c:
                continue
            sym = getattr(c, "symbol", None)
            if not sym:
                continue
            sym = sym.upper()
            if sym not in symbols_meta:
                continue

            last_price = getattr(t, "last", None)
            open_price = getattr(t, "open", None)
            prev_close = getattr(t, "prevClose", None)

            volume_today = getattr(t, "volume", None)
            avg_volume = getattr(t, "avVolume", None)

            bid = getattr(t, "bid", None)
            ask = getattr(t, "ask", None)

            percent_change = None
            if prev_close and last_price:
                percent_change = ((last_price - prev_close) / prev_close) * 100

            gap_percent = resolve_gap_percent(
                scan_code_used=scan_code_used,
                open_price=open_price,
                prev_close=prev_close,
                last_price=last_price,
                percent_change=percent_change
            )

            relative_volume = None
            if avg_volume and volume_today:
                try:
                    relative_volume = volume_today / avg_volume
                except Exception:
                    relative_volume = None

            symbols_meta[sym].update({
                "last_price": last_price,
                "open_price": open_price,
                "prev_close": prev_close,
                "percent_change": safe_round(percent_change, 2),
                "gap_percent": safe_round(gap_percent, 2),
                "volume_today": volume_today,
                "avg_volume": avg_volume,
                "relative_volume": safe_round(relative_volume, 2),
                "bid": bid,
                "ask": ask,
                "bid_ask_spread_percent": safe_round(compute_spread_percent(bid, ask), 2),
            })

            # float: cache first
            if sym in float_cache:
                symbols_meta[sym]["float_shares"] = float_cache[sym]
            else:
                symbols_meta[sym]["float_shares"] = None

        LOGGER.info("IBKR enrichment complete. Symbols=%d (scan=%s)", len(symbols_meta), scan_code_used)
        return symbols_meta

    finally:
        try:
            ib.disconnect()
        except Exception:
            pass

def categorize_float(float_shares: Optional[int]) -> str:
    if float_shares is None:
        return "UNKNOWN"
    if float_shares < 20_000_000:
        return "LOW"
    if float_shares < 100_000_000:
        return "MID"
    return "HIGH"

def enrich_missing_fields_from_web(cfg: ScannerConfig, symbols_meta: Dict[str, Dict[str, Any]], float_cache: Dict[str, int]) -> None:
    """
    Fill missing float_shares / avg_volume / prev_close / open/price if needed.
    This restores the behavior you described from your original script (Yahoo/Finviz fallback).
    """
    updated_cache = False
    for sym, meta in symbols_meta.items():
        need_float = meta.get("float_shares") is None
        need_avg = meta.get("avg_volume") is None
        need_prev = meta.get("prev_close") is None
        need_open = meta.get("open_price") is None
        need_price = meta.get("last_price") is None

        if not (need_float or need_avg or need_prev or need_open or need_price):
            continue

        # Yahoo first (best structured)
        y = fetch_yahoo_quote(sym, user_agent=cfg.user_agent)

        # Map yahoo keys into our meta names
        if need_price and y.get("last_price") is not None:
            meta["last_price"] = y.get("last_price")
        if need_prev and y.get("prev_close") is not None:
            meta["prev_close"] = y.get("prev_close")
        if need_open and y.get("open_price") is not None:
            meta["open_price"] = y.get("open_price")
        if need_avg and y.get("avg_volume") is not None:
            meta["avg_volume"] = y.get("avg_volume")
        if need_float and y.get("float_shares") is not None:
            meta["float_shares"] = int(y.get("float_shares"))

        # If still missing float/avg, try Finviz
        if meta.get("float_shares") is None or meta.get("avg_volume") is None:
            fz = fetch_finviz_symbol(sym, user_agent=cfg.user_agent)
            if meta.get("float_shares") is None and fz.get("float_shares") is not None:
                meta["float_shares"] = int(fz.get("float_shares"))
            if meta.get("avg_volume") is None and fz.get("avg_volume") is not None:
                meta["avg_volume"] = int(fz.get("avg_volume"))
            if meta.get("last_price") is None and fz.get("last_price") is not None:
                meta["last_price"] = fz.get("last_price")

        # If we got float, update cache
        if meta.get("float_shares") is not None and sym not in float_cache:
            float_cache[sym] = int(meta["float_shares"])
            updated_cache = True

        # Recompute percent_change/gap/rvol after filling
        last_price = meta.get("last_price")
        prev_close = meta.get("prev_close")
        open_price = meta.get("open_price")
        if prev_close and last_price:
            meta["percent_change"] = safe_round(((last_price - prev_close) / prev_close) * 100, 2)
        meta["gap_percent"] = safe_round(resolve_gap_percent(
            scan_code_used=meta.get("ibkr_scan_code_used", ""),
            open_price=open_price,
            prev_close=prev_close,
            last_price=last_price,
            percent_change=meta.get("percent_change")
        ), 2)

        # RVOL
        vol = meta.get("volume_today")
        av = meta.get("avg_volume")
        if av and vol:
            try:
                meta["relative_volume"] = safe_round(vol / av, 2)
            except Exception:
                pass

        meta["float_category"] = categorize_float(meta.get("float_shares"))

    if updated_cache:
        save_float_cache(cfg.floats_cache_file, float_cache)
        LOGGER.info("Float cache updated: %s", cfg.floats_cache_file)

# ============================
# Section 10: News matching & awareness
# ============================
def region_from_url(url: str) -> str:
    u = (url or "").lower()
    if ".co.uk" in u or ".uk" in u:
        return "EU/UK"
    if ".cn" in u or "scmp" in u or "globaltimes" in u:
        return "CN"
    if ".au" in u or ".com.au" in u:
        return "AU"
    if ".ca" in u:
        return "CA"
    if ".de" in u or "spiegel" in u:
        return "EU"
    if ".in" in u or "economictimes" in u:
        return "IN"
    if ".za" in u:
        return "ZA"
    if ".jp" in u or "nikkei" in u:
        return "JP"
    if ".ru" in u:
        return "RU"
    return "INT/US"

def normalize_hotword_list(meta: Dict[str, Any]) -> List[str]:
    candidates = [meta.get("symbol",""), meta.get("longName","")]
    words = []
    for c in candidates:
        if not c:
            continue
        for token in re.split(r"[^A-Za-z0-9]+", str(c)):
            token = token.strip()
            if len(token) >= 2:
                words.append(token.lower())
    return list(set(words))

def aggregate_matches_with_links(
    cfg: ScannerConfig,
    symbols_meta: Dict[str, Dict[str, Any]],
    feeds_map: Dict[str, List[Dict[str, Any]]],
    now_val: int
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    results_per_symbol: Dict[str, Any] = {}
    detailed_feed_items: List[Dict[str, Any]] = []

    feed_items = []
    for feed_url, entries in feeds_map.items():
        for e in entries:
            feed_items.append({
                "feed_url": feed_url,
                "title": e.get("title",""),
                "summary": e.get("summary",""),
                "link": e.get("link","") or feed_url,
                "published_ts": e.get("published_ts"),
            })

    for sym, meta in symbols_meta.items():
        hotwords = normalize_hotword_list(meta)
        title_to_sources = defaultdict(set)
        matched_links_by_headline = defaultdict(list)
        regions_detected = set()
        total_matches = 0

        for item in feed_items:
            title = (item["title"] or "").strip()
            summary = (item["summary"] or "").strip()
            link = (item["link"] or "").strip()
            published_ts = item.get("published_ts")

            # age filter
            if published_ts:
                try:
                    if now_val - int(published_ts) > cfg.bucket_24h:
                        continue
                except Exception:
                    pass

            hay = f"{title} {summary}".lower()
            tokens = set(WORD_REGEX.findall(hay))
            if not any(hw in tokens for hw in hotwords):
                continue

            total_matches += 1
            regions_detected.add(region_from_url(item["feed_url"]))
            headline_key = title if title else (summary[:120] or link)
            title_to_sources[headline_key].add(link)

            published_ts_use = int(published_ts) if published_ts else now_val
            link_meta = {
                "title": title,
                "summary": summary,
                "url": link,
                "region": region_from_url(item["feed_url"]),
                "timestamp": ts_to_iso(published_ts_use),
                "timestamp_ts": published_ts_use,
                "sentiment": sentiment_score_text(f"{title} {summary}"),
                "domain_weight": domain_weight_from_url(link),
                "domain": domain_from_url(link),
            }
            matched_links_by_headline[headline_key].append(link_meta)
            detailed_feed_items.append({"symbol": sym, "headline": headline_key, "link_meta": link_meta})

        unique_headlines = len(title_to_sources)
        replicated = max(0, total_matches - unique_headlines)

        top_headlines = sorted(
            [
                {"headline": h, "links": matched_links_by_headline[h], "sources": len(title_to_sources[h])}
                for h in title_to_sources
            ],
            key=lambda x: (x["sources"], max(lm["timestamp_ts"] for lm in x["links"])),
            reverse=True
        )[:cfg.top_n_headlines]

        results_per_symbol[sym] = {
            "total_headlines": total_matches,
            "unique_headlines": unique_headlines,
            "replicated_headlines": replicated,
            "top_headlines": top_headlines,
            "regions": sorted(regions_detected),
            "hotwords": hotwords,
        }

    return results_per_symbol, detailed_feed_items

# ============================
# Section 11: Build entries (velocity/spike scoring + unified fields)
# ============================
def categorize_age_seconds(cfg: ScannerConfig, age_sec: int) -> Tuple[str, str]:
    if age_sec <= cfg.bucket_5m:
        return "🔥","0-5m"
    if age_sec <= cfg.bucket_60m:
        return "🟡","5-60m"
    if age_sec <= cfg.bucket_24h:
        return "🟢","1-24h"
    return "⚫",">24h"

def trade_suggestion_for_symbol(avg_sent: float, is_spike: bool, heat_5m: int, keyword_score: float, top_domains: List[str]) -> Tuple[str, str]:
    credible = any(is_credible_source(d) for d in top_domains)
    parts = []
    if is_spike: parts.append("Volume spike")
    if credible: parts.append("High-cred sources")
    if avg_sent > 0.25: parts.append("Positive sentiment")
    if avg_sent < -0.25: parts.append("Negative sentiment")
    if keyword_score > 6: parts.append("Strong keywords")
    rationale = "; ".join(parts) if parts else "No strong signals"
    if is_spike and avg_sent >= 0.25:
        return "Consider Long 🚀", rationale
    if is_spike and avg_sent <= -0.25:
        return "Consider Short 🛑", rationale
    if heat_5m >= 2 and avg_sent > 0.1:
        return "Watch (Long) 👀", rationale
    if heat_5m >= 2 and avg_sent < -0.1:
        return "Watch (Short) 👀", rationale
    return "Neutral ⚪", rationale

def build_entries(cfg: ScannerConfig, symbols_meta: Dict[str, Dict[str, Any]], news_per_symbol: Dict[str, Any], detailed_feed_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    nowv = now_ts()

    counts_5m = Counter()
    counts_10m = Counter()
    counts_60m = Counter()
    counts_24h = Counter()

    items_5m = defaultdict(list)
    items_10m = defaultdict(list)
    items_60m = defaultdict(list)
    items_24h = defaultdict(list)

    for it in detailed_feed_items:
        sym = it["symbol"]
        lm = it["link_meta"]
        ts = lm.get("timestamp_ts") or nowv
        age = nowv - int(ts)
        if age <= cfg.bucket_5m:
            counts_5m[sym] += 1; items_5m[sym].append(lm)
        if age <= cfg.bucket_10m:
            counts_10m[sym] += 1; items_10m[sym].append(lm)
        if age <= cfg.bucket_60m:
            counts_60m[sym] += 1; items_60m[sym].append(lm)
        if age <= cfg.bucket_24h:
            counts_24h[sym] += 1; items_24h[sym].append(lm)

    # spikes
    hot_symbols = set()
    if counts_5m:
        most = counts_5m.most_common()
        second = most[1][1] if len(most) > 1 else 0
        for sym, cnt in counts_5m.items():
            if cnt >= cfg.absolute_spike_threshold:
                hot_symbols.add(sym)
            elif second == 0 and cnt >= 2:
                hot_symbols.add(sym)
            elif second > 0 and cnt >= cfg.spike_ratio * second and cnt >= 2:
                hot_symbols.add(sym)

    entries: List[Dict[str, Any]] = []
    for sym, meta in symbols_meta.items():
        news = news_per_symbol.get(sym, {})
        links_60 = items_60m.get(sym, [])
        links_5 = items_5m.get(sym, [])

        if links_60:
            min_ts = min(lm["timestamp_ts"] for lm in (links_5 if links_5 else links_60))
            age_min = nowv - min_ts
            badge, bucket = categorize_age_seconds(cfg, age_min)

            wsum = sum(lm.get("sentiment",0.0) * lm.get("domain_weight",0.5) for lm in links_60)
            wtot = sum(lm.get("domain_weight",0.5) for lm in links_60) or 1.0
            avg_sent = wsum / wtot

            top_domains = [lm.get("domain","") for lm in items_24h.get(sym, [])]
            top_domains = list(dict.fromkeys(top_domains))[:10]

            hotwords = news.get("hotwords", [])
            matches, checks = 0, 0
            for lm in items_24h.get(sym, []):
                text = f"{lm.get('title','')} {lm.get('summary','')}".lower()
                for hw in hotwords:
                    checks += 1
                    if hw in text:
                        matches += 1
            keyword_score = (matches / checks * 10) if checks else 0.0

            heat_5m = counts_5m.get(sym,0)
            vel_10m = counts_10m.get(sym,0)
            is_spike = sym in hot_symbols
            trade, rationale = trade_suggestion_for_symbol(avg_sent, is_spike, heat_5m, keyword_score, top_domains)
        else:
            badge, bucket = "⚫", ">24h"
            age_min = None
            avg_sent = 0.0
            keyword_score = 0.0
            heat_5m = 0
            vel_10m = 0
            is_spike = False
            trade, rationale = "No recent news", ""

        c3_score = round((heat_5m * 2) + (avg_sent * 5) + (len(news.get("regions",[])) * 0.5), 2)

        entries.append({
            "symbol": sym,
            "company": meta.get("longName",""),

            # Market data / pillars
            "last_price": meta.get("last_price"),
            "open_price": meta.get("open_price"),
            "prev_close": meta.get("prev_close"),
            "percent_change": meta.get("percent_change"),
            "gap_percent": meta.get("gap_percent"),
            "volume_today": meta.get("volume_today"),
            "avg_volume": meta.get("avg_volume"),
            "relative_volume": meta.get("relative_volume"),
            "float_shares": meta.get("float_shares"),
            "float_category": meta.get("float_category", categorize_float(meta.get("float_shares"))),
            "bid_ask_spread_percent": meta.get("bid_ask_spread_percent"),
            "ibkr_scan_code_used": meta.get("ibkr_scan_code_used",""),

            # News awareness
            "total_headlines": news.get("total_headlines",0),
            "unique_headlines": news.get("unique_headlines",0),
            "replicated_headlines": news.get("replicated_headlines",0),
            "regions": news.get("regions",[]),
            "top_headlines": news.get("top_headlines",[]),

            # Velocity/scoring
            "avg_sentiment": round(avg_sent,3),
            "keyword_score": round(keyword_score,2),
            "heat_score_5m": heat_5m,
            "velocity_10m": vel_10m,
            "is_spike": is_spike,
            "freshness": {"badge": badge, "bucket": bucket, "seconds_old": age_min},

            # Human hint
            "trade_suggestion": trade,
            "trade_rationale": rationale,
            "c3_score": c3_score,
        })

    return entries

# ============================
# Section 12: Ross filter + sorting
# ============================
def passes_ross_five_pillars(cfg: ScannerConfig, e: Dict[str, Any]) -> bool:
    """
    Ross pillars mapping (with comments so you can adjust later):

    (We PRINT) vs (Ross asks) vs (We FILTER)

    1) RVOL — Ross asks: "Is there unusual volume?"
       - variable: relative_volume  # calculated volume_today / avg_volume
       - print: RVOL:{relative_volume}×
       - filter: >= cfg.ross.min_rvol

    2) GAP — Ross asks: "Is it a gapper / strong mover?"
       - variable: gap_percent  # robust, never None for top gainers
       - print: Gap:{gap_percent}%
       - filter: >= cfg.ross.min_gap_percent

    3) FLOAT — Ross asks: "Is the float low?"
       - variable: float_shares  # from cache/Yahoo/Finviz
       - print: Float:{formatted} ({LOW/MID/HIGH})
       - filter: <= cfg.ross.max_float

    4) PRICE — Ross asks: "Is the price in range ($2-$20)?"
       - variable: last_price
       - print: Price:${last_price}
       - filter: cfg.ross.min_price <= price <= cfg.ross.max_price

    5) NEWS — Ross asks: "Is there a catalyst?"
       - variable: total_headlines / unique_headlines / regions
       - print: Total Articles, Unique Articles, Region Count
       - filter v1: require total_headlines > 0 (you can relax later)
    """
    ross = cfg.ross

    price = e.get("last_price")
    gap = e.get("gap_percent") or 0.0
    rvol = e.get("relative_volume") or 0.0
    flt = e.get("float_shares")
    has_news = (e.get("total_headlines",0) > 0)

    if price is None:
        return False
    if flt is None:
        return False  # conservative until your float sourcing is stable

    return (
        ross.min_price <= price <= ross.max_price and
        gap >= ross.min_gap_percent and
        rvol >= ross.min_rvol and
        flt <= ross.max_float and
        has_news
    )

def sort_by_gap_then_change(e: Dict[str, Any]) -> Tuple[float, float]:
    return (-(e.get("gap_percent") or 0), -(e.get("percent_change") or 0))

def build_watchlist(cfg: ScannerConfig, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    filt = [e for e in entries if passes_ross_five_pillars(cfg, e)]
    return sorted(filt, key=sort_by_gap_then_change)[:cfg.watchlist_top_n]

# ============================
# Section 13: Printers (your 3+1 style)
# ============================
def print_ross_line(e: Dict[str, Any]) -> None:
    sym = e.get("symbol","")
    fire = "🔥" if e.get("is_spike", False) else " "
    gap = e.get("gap_percent")
    rvol = e.get("relative_volume")
    flt = e.get("float_shares")
    price = e.get("last_price")
    news_flag = "Y" if (e.get("total_headlines",0) > 0) else "N"
    regions = e.get("regions", [])
    print(
        f"{sym} | {fire} | "
        f"Gap:{gap if gap is not None else 'N/A'}% | "
        f"RVOL:{rvol if rvol is not None else 'N/A'}× | "
        f"Float:{format_float_shares(flt)} ({e.get('float_category','UNKNOWN')}) | "
        f"Price:${price if price is not None else 'N/A'} | "
        f"News:{news_flag} | "
        f"Total Articles: {e.get('total_headlines',0)} | "
        f"Unique Articles: {e.get('unique_headlines',0)} | "
        f"Vel10m:{e.get('velocity_10m',0)} | "
        f"Sent:{e.get('avg_sentiment',0.0):+.2f} | "
        f"Score:{e.get('c3_score','N/A')} | "
        f"Region Count: {len(regions)}"
    )

def print_cycle_legacy(entries: List[Dict[str, Any]], cfg: ScannerConfig) -> None:
    print("\n" + "="*70)
    print("HOT NEWS (cycle legacy C3) —", utc_iso_now())
    print("="*70)

    entries_sorted = sorted(entries, key=lambda x: (
        not x.get("is_spike", False),
        -x.get("heat_score_5m", 0),
        -x.get("velocity_10m", 0),
        -x.get("unique_headlines", 0),
    ))

    for e in entries_sorted:
        sym = e["symbol"]
        badge = e.get("freshness", {}).get("badge", "⚫")
        print(
            f"{sym} | {badge} | Vel10m:{e.get('velocity_10m',0)} | "
            f"Total:{e.get('total_headlines',0)} | Spike:{'YES' if e.get('is_spike') else 'No'} | "
            f"Sent:{e.get('avg_sentiment',0.0):+.2f} | Score:{e.get('c3_score')} | KW:{e.get('keyword_score',0.0):.2f}/10"
        )
        print(f"Trade: {e.get('trade_suggestion','Neutral ⚪')} — {e.get('trade_rationale','')}")
        if e.get("top_headlines"):
            print("Top Headlines:")
            for i, th in enumerate(e.get("top_headlines",[])[:cfg.top_n_headlines], start=1):
                headline = th.get("headline","")
                links = th.get("links",[])[:5]
                print(f" {i}. {headline} — {len(links)} source(s)")
                if links:
                    best = sorted(links, key=lambda x: x.get("timestamp_ts",0), reverse=True)[0]
                    print(f"    {best.get('url')}")
        else:
            print("Top Headlines: (none)")
        print("-"*70)

def print_general_verbose(entries: List[Dict[str, Any]], cfg: ScannerConfig) -> None:
    print("\n" + "="*70)
    print("GENERAL VIEW (no filter) — sorted by GAP desc —", utc_iso_now())
    print("="*70)

    for e in sorted(entries, key=sort_by_gap_then_change):
        print_ross_line(e)

        sym = e["symbol"]
        print(f"{sym} | 🔥 | Vel10m:{e.get('velocity_10m',0)} | Total:{e.get('total_headlines',0)} | "
              f"Spike:{'YES' if e.get('is_spike') else 'No'} | Sent:{e.get('avg_sentiment',0.0):+.2f} | "
              f"Score:{e.get('c3_score')} | KW:{e.get('keyword_score',0.0):.2f}/10 | IBScan:{e.get('ibkr_scan_code_used','')}")
        print("\nAWARENESS")
        print(f"Total Articles: {e.get('total_headlines',0)}")
        print(f"Unique Articles: {e.get('unique_headlines',0)}")
        print(f"Replicated Articles: {e.get('replicated_headlines',0)}")
        regs = e.get("regions", [])
        print(f"Regions: {', '.join(regs) if regs else 'N/A'}")
        print(f"Region Count: {len(regs)}")
        print(f"\nTrade: {e.get('trade_suggestion','Neutral ⚪')} — {e.get('trade_rationale','')}")
        if e.get("top_headlines"):
            print("\nTop Headlines:")
            for i, th in enumerate(e.get("top_headlines",[])[:cfg.top_n_headlines], start=1):
                headline = th.get("headline","")
                links = th.get("links",[])
                print(f" {i}. {headline} — {len(links)} source(s)")
                if links:
                    best = sorted(links, key=lambda x: x.get("timestamp_ts",0), reverse=True)[0]
                    print(f"    {best.get('url')}")
        else:
            print("\nTop Headlines: (none)")
        print("-"*70)

def print_filtered_compact(entries: List[Dict[str, Any]], cfg: ScannerConfig) -> None:
    print("\n" + "="*70)
    print(f"ROSS WATCHLIST (filtered) — TOP {cfg.watchlist_top_n} — sorted by GAP desc —", utc_iso_now())
    print("="*70)

    filt = [e for e in entries if passes_ross_five_pillars(cfg, e)]
    filt = sorted(filt, key=sort_by_gap_then_change)[:cfg.watchlist_top_n]

    if not filt:
        print("No symbols passed Ross 5 pillars (v1). (Check float sourcing/news matching thresholds.)")
        print("="*70)
        return

    for e in filt:
        print_ross_line(e)
    print("="*70)

def print_filtered_deep(entries: List[Dict[str, Any]], cfg: ScannerConfig) -> None:
    print("\n" + "="*70)
    print(f"DEEP VIEW (filtered) — TOP {cfg.watchlist_top_n} —", utc_iso_now())
    print("="*70)

    filt = [e for e in entries if passes_ross_five_pillars(cfg, e)]
    filt = sorted(filt, key=sort_by_gap_then_change)[:cfg.watchlist_top_n]

    if not filt:
        print("No symbols passed Ross 5 pillars (v1).")
        print("="*70)
        return

    for e in filt:
        print_ross_line(e)
        sym = e["symbol"]
        print(f"\nAWARENESS for {sym}")
        print(f"Total Articles: {e.get('total_headlines',0)}")
        print(f"Unique Articles: {e.get('unique_headlines',0)}")
        print(f"Replicated Articles: {e.get('replicated_headlines',0)}")
        regs = e.get("regions", [])
        print(f"Regions: {', '.join(regs) if regs else 'N/A'} | Region Count: {len(regs)}")
        print(f"Trade: {e.get('trade_suggestion','Neutral ⚪')} — {e.get('trade_rationale','')}")
        if e.get("top_headlines"):
            print("\nTop Headlines:")
            for i, th in enumerate(e.get("top_headlines",[])[:cfg.top_n_headlines], start=1):
                headline = th.get("headline","")
                links = th.get("links",[])
                print(f" {i}. {headline} — {len(links)} source(s)")
                if links:
                    best = sorted(links, key=lambda x: x.get("timestamp_ts",0), reverse=True)[0]
                    print(f"    {best.get('url')}")
        print("-"*70)

# ============================
# Section 14: Save outputs (timestamped)
# ============================
def save_outputs(cfg: ScannerConfig, results: Dict[str, Any]) -> str:
    ts_label = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(cfg.out_dir_base, ts_label)
    mkdirp(out_dir)

    entries = results["entries"]
    watchlist = results["watchlist"]
    news = results["news_results_per_symbol"]
    dump = results["detailed_feed_items"]

    def _write(name: str, obj: Any) -> str:
        p = os.path.join(out_dir, f"{name}_{ts_label}.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
        return p

    p1 = _write("scan_full_entries", entries)
    p2 = _write("scan_news_results_per_symbol", news)
    p3 = _write("scan_detailed_feed_dump", dump)
    p4 = _write(f"watchlist_ross_top{len(watchlist)}", watchlist)

    LOGGER.info("Saved outputs to %s", out_dir)
    LOGGER.info(" - %s", p1)
    LOGGER.info(" - %s", p2)
    LOGGER.info(" - %s", p3)
    LOGGER.info(" - %s", p4)
    return out_dir

# ============================
# Section 15: Core engine (module-friendly) — returns data, no sleep
# ============================
def run_scan(cfg: ScannerConfig) -> Dict[str, Any]:
    rss_urls = load_verified_rss(cfg.verified_rss_file)
    if not rss_urls:
        raise RuntimeError("No RSS feeds loaded (verified_rss.txt missing/empty).")

    float_cache = load_float_cache(cfg.floats_cache_file)

    if not cfg.use_ibkr:
        raise RuntimeError("IBKR disabled, but this build expects IBKR for symbols.")

    symbols_meta = enrich_symbols_from_ibkr(cfg, float_cache)
    if not symbols_meta:
        raise RuntimeError("No symbols returned from IBKR scanners.")

    # Web fallback enrichment to restore original behavior
    enrich_missing_fields_from_web(cfg, symbols_meta, float_cache)

    # RSS fetch + match
    feeds_map = fetch_all_feeds(cfg, rss_urls)
    nowv = now_ts()
    news_per_symbol, detailed_feed_items = aggregate_matches_with_links(cfg, symbols_meta, feeds_map, nowv)

    entries = build_entries(cfg, symbols_meta, news_per_symbol, detailed_feed_items)
    watchlist = build_watchlist(cfg, entries)

    return {
        "timestamp": utc_iso_now(),
        "entries": entries,
        "watchlist": watchlist,
        "news_results_per_symbol": news_per_symbol,
        "detailed_feed_items": detailed_feed_items,
    }

# ============================
# Section 16: One cycle orchestrator — prints 4 times + saves
# ============================
def run_cycle(cfg: ScannerConfig) -> None:
    print("\n" + "="*70)
    print("STARTING SCAN CYCLE —", utc_iso_now())
    print("="*70)

    try:
        results = run_scan(cfg)
    except Exception as e:
        LOGGER.error("Cycle failed: %s", e)
        return

    entries = results["entries"]

    # PRINT 1
    print_cycle_legacy(entries, cfg)

    # PRINT 2
    print_general_verbose(entries, cfg)

    # PRINT 3
    print_filtered_compact(entries, cfg)

    # PRINT 4
    print_filtered_deep(entries, cfg)

    out_dir = save_outputs(cfg, results)

    print("\n" + "="*70)
    print("CYCLE COMPLETE — saved to:", out_dir)
    print("="*70)

# ============================
# Section 17: CLI
# ============================
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ross-style scanner (IBKR + RSS + Yahoo/Finviz fallback)")
    p.add_argument("--once", action="store_true", help="Run one cycle and exit")
    p.add_argument("--debug", action="store_true", help="Enable debug logs")
    p.add_argument("--top", type=int, default=50, help="IBKR scanner rows (default 50)")
    p.add_argument("--watch", type=int, default=10, help="Watchlist size (default 10)")
    p.add_argument("--sleep", type=int, default=60, help="Seconds between cycles (default 60)")
    p.add_argument("--rss-file", type=str, default="verified_rss.txt", help="RSS list file")
    p.add_argument("--float-cache", type=str, default="floats_cache.json", help="Float cache JSON (auto-updated)")
    p.add_argument("--out-dir", type=str, default="data", help="Output directory base")
    return p.parse_args()

def main() -> None:
    args = parse_args()
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    cfg = ScannerConfig(
        verified_rss_file=args.rss_file,
        floats_cache_file=args.float_cache,
        out_dir_base=args.out_dir,
        ibkr_top_rows=max(5, int(args.top)),
        watchlist_top_n=max(5, min(20, int(args.watch))),
        cycle_sleep_seconds=max(5, int(args.sleep)),
    )

    if args.once:
        run_cycle(cfg)
        return

    try:
        while True:
            run_cycle(cfg)
            LOGGER.info("Sleeping %d seconds until next cycle...", cfg.cycle_sleep_seconds)
            time.sleep(cfg.cycle_sleep_seconds)
    except KeyboardInterrupt:
        LOGGER.info("Interrupted by user — exiting.")

if __name__ == "__main__":
    main()
