#!/usr/bin/env python3
"""
scanner_unified.py

ONE scanner, improved architecture, keeps your working news engine.

Core goals:
- Use IBKR scanner to discover top gainers (TOP_PERC_GAIN)
- Use RSS feeds to build catalyst awareness (dedupe, replication, regions, velocity, spikes)
- Enrich with Ross 5 pillars fields:
    1) Gap % (or % change)      -> Yahoo batch quote (no key)
    2) Relative Volume (RVOL)   -> volume / avgVolume (Yahoo)
    3) Float shares             -> Finviz scrape (cached)
    4) Price range              -> Yahoo last price
    5) News catalyst            -> your RSS awareness metrics

Printing goals (4 prints per cycle):
1) Cycle print (primary) — prints full block per symbol (5 pillars header + your working block)
2) General printer (same as #1 but sorted by Gap desc explicitly)
3) Filtered compact watchlist (Ross pillars filter) — one-liners
4) Filtered detailed watchlist (Ross pillars filter) — full blocks

Notes:
- If IBKR market data is unavailable or subscriptions are limited, this still works because
  Yahoo provides prices/volume and Finviz provides float.
- If Finviz rate-limits, floats fall back to cache or UNKNOWN.
"""

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
import argparse
import asyncio
import aiohttp
import feedparser
import json
import logging
import os
import re
import time
import math
from dataclasses import dataclass
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from random import randint

import requests

# IB
from ib_insync import IB, ScannerSubscription

# ----------------------------
# Config dataclass (no globals)
# ----------------------------
@dataclass
class ScannerConfig:
    # RSS
    VERIFIED_RSS_FILE: str = "verified_rss.txt"
    RSS_FETCH_TIMEOUT: int = 30
    RSS_CONCURRENCY: int = 24
    RSS_FETCH_RETRIES: int = 2
    USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

    # Cycle
    CYCLE_SLEEP_SECONDS: int = 60
    TOP_GAINERS_COUNT: int = 50
    TOP_N_HEADLINES: int = 5
    OUT_DIR_BASE: str = "data"

    # News / spike logic
    ABSOLUTE_SPIKE_THRESHOLD: int = 5
    SPIKE_RATIO: float = 2.0

    # Age buckets (seconds)
    BUCKET_5M: int = 5 * 60
    BUCKET_10M: int = 10 * 60
    BUCKET_60M: int = 60 * 60
    BUCKET_24H: int = 24 * 3600

    # Ross pillars thresholds (you can tune later)
    PILLAR_MIN_RVOL: float = 5.0
    PILLAR_MIN_GAP_PERCENT: float = 10.0
    PILLAR_MIN_PRICE: float = 2.0
    PILLAR_MAX_PRICE: float = 20.0
    PILLAR_MAX_FLOAT: int = 10_000_000  # 10M

    # IBKR connection
    IB_HOST: str = "127.0.0.1"
    IB_PORT: int = 7496
    IB_TIMEOUT: int = 10

    # Float cache / scraping
    FLOAT_CACHE_FILE: str = "floats_cache.json"
    FINVIZ_TIMEOUT: int = 10

    # Printer toggles (your 4 prints)
    PRINT_1_CYCLE_PRIMARY: bool = True
    PRINT_2_GENERAL_SORTED: bool = True
    PRINT_3_FILTERED_COMPACT: bool = True
    PRINT_4_FILTERED_DETAILED: bool = True


CFG = ScannerConfig()

# Logging (keep your debug-friendly style)
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logging.getLogger("aiohttp").setLevel(logging.WARNING)


# ============================
# Section 2: Utilities
# ============================
WORD_REGEX = re.compile(r"\b[a-zA-Z0-9]+\b")

def now_ts() -> int:
    return int(time.time())

def ts_to_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

def iso_to_ts(iso_s: str) -> int:
    try:
        return int(datetime.fromisoformat(iso_s).replace(tzinfo=timezone.utc).timestamp())
    except Exception:
        return now_ts()

def mkdirp(path: str):
    Path(path).mkdir(parents=True, exist_ok=True)

def domain_from_url(url: str) -> str:
    m = re.search(r"https?://([^/]+)", (url or ""))
    if m:
        return m.group(1).lower()
    return (url or "").lower()

def normalize_title(title: str) -> str:
    t = re.sub(r"\s+", " ", (title or "").strip().lower())
    t = re.sub(r"[^a-z0-9 ]+", "", t)
    return t

def title_fingerprint(title: str) -> str:
    n = normalize_title(title)[:240]
    return sha1(n.encode("utf-8")).hexdigest()

def safe_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
            return None
        return float(x)
    except Exception:
        return None

def safe_int(x) -> Optional[int]:
    try:
        if x is None:
            return None
        if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
            return None
        return int(float(x))
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
    return "N/A" if raw_float in (None, "", "N/A") else str(raw_float)

def float_category(float_shares: Optional[int]) -> str:
    # Ross-style: low float is a major driver
    if float_shares is None:
        return "UNKNOWN"
    if float_shares < 10_000_000:
        return "LOW"
    if float_shares < 50_000_000:
        return "MID"
    return "HIGH"


# ============================
# Section 3: Sentiment & domain weights (keep yours)
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


# ============================
# Section 4: RSS loader
# ============================
def load_verified_rss(file_path: str) -> List[str]:
    p = Path(file_path)
    if not p.exists():
        logging.error("Verified RSS file not found: %s", file_path)
        return []
    with p.open("r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    logging.info("Loaded %d RSS feeds", len(urls))
    return urls


# ============================
# Section 5: Async RSS fetching (your style)
# ============================
async def fetch_single(session: aiohttp.ClientSession, url: str, sem: asyncio.Semaphore, cfg: ScannerConfig) -> Tuple[str, List[Dict[str,Any]]]:
    headers = {"User-Agent": cfg.USER_AGENT}
    timeout = aiohttp.ClientTimeout(total=cfg.RSS_FETCH_TIMEOUT, connect=10, sock_read=cfg.RSS_FETCH_TIMEOUT)
    backoff_base = 0.6
    async with sem:
        for attempt in range(1, cfg.RSS_FETCH_RETRIES + 1):
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
            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                logging.debug("Fetch attempt %d/%d failed for %s: %s", attempt, cfg.RSS_FETCH_RETRIES, url, repr(e))
            except Exception as e:
                logging.debug("Fetch unexpected error %s: %s", url, repr(e))
            await asyncio.sleep(backoff_base * (2 ** (attempt - 1)))
    return url, []

async def fetch_all_feeds_async(rss_urls: List[str], cfg: ScannerConfig) -> Dict[str, List[Dict[str,Any]]]:
    connector = aiohttp.TCPConnector(ssl=False, limit=cfg.RSS_CONCURRENCY, limit_per_host=10)
    sem = asyncio.Semaphore(cfg.RSS_CONCURRENCY)
    results = {}
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [asyncio.create_task(fetch_single(session, url, sem, cfg)) for url in rss_urls]
        responses = await asyncio.gather(*tasks, return_exceptions=False)
        for url, entries in responses:
            results[url] = entries or []
    return results

def fetch_all_feeds(rss_urls: List[str], cfg: ScannerConfig) -> Dict[str, List[Dict[str,Any]]]:
    if not rss_urls:
        return {}
    try:
        prev_loop = asyncio.get_event_loop()
    except RuntimeError:
        prev_loop = None
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(fetch_all_feeds_async(rss_urls, cfg))
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        try:
            loop.close()
        except Exception:
            pass
        if prev_loop is not None:
            try:
                asyncio.set_event_loop(prev_loop)
            except Exception:
                asyncio.set_event_loop(asyncio.new_event_loop())
        else:
            asyncio.set_event_loop(asyncio.new_event_loop())
    return results


# ============================
# Section 6: IBKR symbol discovery (keep it simple & reliable)
# ============================
def ibkr_fetch_top_gainers(cfg: ScannerConfig) -> Dict[str, Dict[str, Any]]:
    """
    Uses IBKR scanner ONLY to discover symbols + contract metadata.
    (Keeps your original approach; does not depend on IB market data.)
    """
    ib = IB()
    client_id = randint(1000, 9999)
    try:
        logging.info("Connecting to IBKR host=%s port=%s clientId=%s", cfg.IB_HOST, cfg.IB_PORT, client_id)
        ib.connect(cfg.IB_HOST, cfg.IB_PORT, clientId=client_id, timeout=cfg.IB_TIMEOUT)
    except Exception as e:
        logging.error("IB connect failed: %s", e)
        try:
            ib.disconnect()
        except Exception:
            pass
        return {}

    out: Dict[str, Dict[str, Any]] = {}
    try:
        scan_sub = ScannerSubscription(
            instrument="STK",
            locationCode="STK.US.MAJOR",
            scanCode="TOP_PERC_GAIN",
            numberOfRows=cfg.TOP_GAINERS_COUNT
        )
        scan_data = ib.reqScannerData(scan_sub)
        contracts = [item.contractDetails.contract for item in scan_data]
        logging.info("Scanner OK (TOP_PERC_GAIN). Symbols=%d", len(contracts))

        # Contract details give name/industry where available
        for c in contracts:
            sym = getattr(c, "symbol", None)
            if not sym:
                continue
            cd = None
            try:
                details = ib.reqContractDetails(c)
                if details:
                    cd = details[0]
            except Exception:
                cd = None

            out[sym] = {
                "symbol": sym,
                "contract": c,
                "longName": getattr(cd, "longName", "") or getattr(c, "localSymbol", sym),
                "industry": getattr(cd, "industry", "") or "",
                "category": getattr(cd, "category", "") or "",
                "subcategory": getattr(cd, "subcategory", "") or "",
                "primaryExchange": getattr(c, "primaryExchange", "") or "",
                "currency": getattr(c, "currency", "") or "",
            }

    except Exception as e:
        logging.error("IB scanner error: %s", e)
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass
    return out


# ============================
# Section 7: Enrichment — Yahoo (batch, no key)
# ============================
def yahoo_batch_quote(symbols: List[str], cfg: ScannerConfig) -> Dict[str, Dict[str, Any]]:
    """
    Batch quote from Yahoo endpoint:
    https://query1.finance.yahoo.com/v7/finance/quote?symbols=...

    Returns dict keyed by symbol with:
    - last_price
    - prev_close
    - percent_change (regularMarketChangePercent)
    - volume
    - avg_volume (averageDailyVolume3Month)
    """
    if not symbols:
        return {}

    # Yahoo can handle a lot, but keep it reasonable
    chunk_size = 50
    out: Dict[str, Dict[str, Any]] = {}
    headers = {"User-Agent": cfg.USER_AGENT}

    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i:i+chunk_size]
        url = "https://query1.finance.yahoo.com/v7/finance/quote"
        params = {"symbols": ",".join(chunk)}
        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
            r.raise_for_status()
            data = r.json()
            results = data.get("quoteResponse", {}).get("result", []) or []
            for row in results:
                sym = row.get("symbol")
                if not sym:
                    continue
                last_price = safe_float(row.get("regularMarketPrice"))
                prev_close = safe_float(row.get("regularMarketPreviousClose"))
                pct_change = safe_float(row.get("regularMarketChangePercent"))
                volume = safe_int(row.get("regularMarketVolume"))
                avg_vol = safe_int(row.get("averageDailyVolume3Month"))

                gap_percent = None
                # Gap definition here: (last - prev_close) / prev_close
                if last_price is not None and prev_close not in (None, 0.0):
                    gap_percent = (last_price - prev_close) / prev_close * 100.0

                rvol = None
                if volume is not None and avg_vol not in (None, 0):
                    rvol = volume / float(avg_vol)

                out[sym] = {
                    "last_price": last_price,
                    "prev_close": prev_close,
                    "percent_change": pct_change,
                    "gap_percent": gap_percent,
                    "volume": volume,
                    "avg_volume": avg_vol,
                    "relative_volume": rvol,
                }
        except Exception as e:
            logging.warning("Yahoo quote failed for chunk %s..: %s", chunk[0], e)

    return out


# ============================
# Section 8: Enrichment — Float via Finviz (cached)
# ============================
_FLOAT_RE = re.compile(r"Float\s*([0-9\.\,]+)\s*([KMB])", re.IGNORECASE)

def load_float_cache(path: str) -> Dict[str, int]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_float_cache(path: str, cache: Dict[str, int]):
    try:
        Path(path).write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception:
        pass

def parse_finviz_float(html: str) -> Optional[int]:
    """
    Finviz quote page has a table including Float. We do a resilient regex-based parse.
    """
    if not html:
        return None
    # A very common pattern: "Float" in table cells. Regex fallback:
    m = re.search(r">Float</td>\s*<td[^>]*>\s*([0-9\.,]+)\s*([KMB])", html, re.IGNORECASE)
    if not m:
        m = _FLOAT_RE.search(html)
    if not m:
        return None

    num_s = m.group(1).replace(",", "")
    unit = m.group(2).upper()
    try:
        val = float(num_s)
        mult = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(unit, 1)
        return int(val * mult)
    except Exception:
        return None

def finviz_fetch_float(symbol: str, cfg: ScannerConfig) -> Optional[int]:
    url = f"https://finviz.com/quote.ashx?t={symbol}"
    headers = {"User-Agent": cfg.USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    try:
        r = requests.get(url, headers=headers, timeout=cfg.FINVIZ_TIMEOUT)
        r.raise_for_status()
        return parse_finviz_float(r.text)
    except Exception:
        return None

def enrich_floats(symbols: List[str], cfg: ScannerConfig) -> Dict[str, int]:
    """
    Returns float_shares for symbols, using cache first, then Finviz.
    """
    cache = load_float_cache(cfg.FLOAT_CACHE_FILE)
    out: Dict[str, int] = {}

    # First fill from cache
    for s in symbols:
        if s in cache and isinstance(cache[s], int):
            out[s] = cache[s]

    # Fetch missing floats (limited)
    missing = [s for s in symbols if s not in out]
    if missing:
        logging.info("Float: fetching %d missing floats from Finviz (cached)", len(missing))
    for s in missing:
        val = finviz_fetch_float(s, cfg)
        if isinstance(val, int) and val > 0:
            out[s] = val
            cache[s] = val

        # small polite delay to reduce rate-limit risk
        time.sleep(0.15)

    save_float_cache(cfg.FLOAT_CACHE_FILE, cache)
    return out


# ============================
# Section 9: Region detection (your logic)
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


# ============================
# Section 10: Matching, dedupe, replication counting (your engine)
# ============================
def normalize_hotword_list(meta: Dict[str, Any]) -> List[str]:
    candidates = [
        meta.get("symbol",""),
        meta.get("longName",""),
        meta.get("industry",""),
        meta.get("category",""),
        meta.get("subcategory","")
    ]
    words = []
    for c in candidates:
        if not c:
            continue
        for token in re.split(r"[^A-Za-z0-9]+", str(c)):
            token = token.strip()
            if len(token) >= 2:
                words.append(token)
    return list({w.lower() for w in words})

def aggregate_matches_with_links(
    symbols_meta: Dict[str, Dict[str, Any]],
    feeds_map: Dict[str, List[Dict[str, Any]]],
    now_ts_val: int,
    cfg: ScannerConfig
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    For each symbol, find RSS items matching hotwords.
    Produces per-symbol news awareness metrics and a detailed feed item list for velocity/spikes.
    """
    results = {}
    detailed_feed_items = []

    # Flatten feed items
    feed_items = []
    for feed_url, entries in feeds_map.items():
        for e in entries:
            feed_items.append({
                "feed_url": feed_url,
                "title": e.get("title",""),
                "summary": e.get("summary",""),
                "link": e.get("link","") or feed_url,
                "published_ts": e.get("published_ts")
            })

    for symbol, meta in symbols_meta.items():
        hotwords = normalize_hotword_list(meta)
        title_to_sources = defaultdict(set)
        matched_links_by_headline = defaultdict(list)
        regions_detected = set()
        total_matches = 0

        if not hotwords:
            results[symbol] = {
                "metadata": meta,
                "total_headlines": 0,
                "unique_headlines": 0,
                "replicated_headlines": 0,
                "top_headlines": [],
                "regions": [],
                "hotwords": []
            }
            continue

        for item in feed_items:
            title = (item["title"] or "").strip()
            summary = (item["summary"] or "").strip()
            link = (item["link"] or "").strip()
            published_ts = item.get("published_ts")

            # Age filter (24h)
            if published_ts:
                try:
                    age = now_ts_val - int(published_ts)
                    if age > cfg.BUCKET_24H:
                        continue
                except Exception:
                    pass

            hay = f"{title} {summary}".lower()
            tokens = set(WORD_REGEX.findall(hay))
            matched = any(hw in tokens for hw in hotwords)
            if not matched:
                continue

            total_matches += 1
            regions_detected.add(region_from_url(item["feed_url"]))

            headline_key = title if title else (summary[:120] or link)
            title_to_sources[headline_key].add(link)

            published_ts_use = int(published_ts) if published_ts else now_ts_val
            link_meta = {
                "title": title,
                "summary": summary,
                "url": link,
                "region": region_from_url(item["feed_url"]),
                "timestamp": ts_to_iso(published_ts_use),
                "timestamp_ts": published_ts_use,
                "sentiment": sentiment_score_text(f"{title} {summary}"),
                "domain_weight": domain_weight_from_url(link)
            }
            matched_links_by_headline[headline_key].append(link_meta)
            detailed_feed_items.append({"symbol": symbol, "headline": headline_key, "link_meta": link_meta})

        unique_headlines = len(title_to_sources)
        replicated = total_matches - unique_headlines

        top_headlines = sorted(
            [{"headline": h, "links": matched_links_by_headline[h], "sources": len(title_to_sources[h])} for h in title_to_sources],
            key=lambda x: (x["sources"], max(link["timestamp_ts"] for link in x["links"])),
            reverse=True
        )[:cfg.TOP_N_HEADLINES]

        results[symbol] = {
            "metadata": meta,
            "total_headlines": total_matches,
            "unique_headlines": unique_headlines,
            "replicated_headlines": replicated,
            "top_headlines": top_headlines,
            "regions": sorted(regions_detected),
            "hotwords": hotwords
        }

    return results, detailed_feed_items


# ============================
# Section 11: Velocity, spikes, scoring (your engine)
# ============================
def categorize_age_seconds(age_sec: int, cfg: ScannerConfig) -> Tuple[str, str]:
    if age_sec <= cfg.BUCKET_5M:
        return "🔥", "0-5m"
    if age_sec <= cfg.BUCKET_60M:
        return "🟡", "5-60m"
    if age_sec <= cfg.BUCKET_24H:
        return "🟢", "1-24h"
    return "⚫", ">24h"

def trade_suggestion_for_symbol(avg_sent: float, is_spike: bool, heat_5m: int, keyword_score: float, top_sources: List[str]) -> Tuple[str, str]:
    credible = any(d in " ".join(top_sources) for d in ["bloomberg","reuters","wsj","ft","nytimes","cnn"])
    rationale_parts = []
    if is_spike:
        rationale_parts.append("Volume spike")
    if credible:
        rationale_parts.append("High-cred sources")
    if avg_sent > 0.25:
        rationale_parts.append("Positive sentiment")
    if avg_sent < -0.25:
        rationale_parts.append("Negative sentiment")
    if keyword_score > 6:
        rationale_parts.append("Strong keywords")
    rationale = "; ".join(rationale_parts) if rationale_parts else "No strong signals"
    if is_spike and avg_sent >= 0.25:
        return "Consider Long 🚀", rationale
    if is_spike and avg_sent <= -0.25:
        return "Consider Short 🛑", rationale
    if heat_5m >= 2 and avg_sent > 0.1:
        return "Watch (Long) 👀", rationale
    if heat_5m >= 2 and avg_sent < -0.1:
        return "Watch (Short) 👀", rationale
    return "Neutral ⚪", rationale

def build_hot_news(
    results_per_symbol: Dict[str, Any],
    detailed_feed_items: List[Dict[str, Any]],
    cfg: ScannerConfig
) -> List[Dict[str, Any]]:
    """
    Builds list of symbol entries with spike/velocity/sentiment/keyword scoring + headlines.
    """
    now = now_ts()

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
        ts = lm.get("timestamp_ts") or iso_to_ts(lm.get("timestamp"))
        age = now - int(ts)
        if age <= cfg.BUCKET_5M:
            counts_5m[sym] += 1
            items_5m[sym].append(lm)
        if age <= cfg.BUCKET_10M:
            counts_10m[sym] += 1
            items_10m[sym].append(lm)
        if age <= cfg.BUCKET_60M:
            counts_60m[sym] += 1
            items_60m[sym].append(lm)
        if age <= cfg.BUCKET_24H:
            counts_24h[sym] += 1
            items_24h[sym].append(lm)

    # Determine spikes
    hot_symbols = set()
    if counts_5m:
        most = counts_5m.most_common()
        second_count = most[1][1] if len(most) > 1 else 0
        for sym, cnt in counts_5m.items():
            if cnt >= cfg.ABSOLUTE_SPIKE_THRESHOLD:
                hot_symbols.add(sym)
            elif second_count == 0 and cnt >= 2:
                hot_symbols.add(sym)
            elif second_count > 0 and cnt >= cfg.SPIKE_RATIO * second_count and cnt >= 2:
                hot_symbols.add(sym)

    hot_news = []
    for sym, meta in results_per_symbol.items():
        links_60 = items_60m.get(sym, [])
        links_5 = items_5m.get(sym, [])

        if not links_60:
            avg_sent = 0.0
            top_sources = []
            keyword_score = 0.0
            heat_score = 0
            velocity_10m = counts_10m.get(sym, 0)
            is_spike = False
            badge = "⚫"
            bucket = ">24h"
            age_min = None
        else:
            min_ts = min(lm["timestamp_ts"] for lm in (links_5 if links_5 else links_60))
            age_min = now - min_ts
            badge, bucket = categorize_age_seconds(age_min, cfg)

            wsum = sum(lm.get("sentiment", 0.0) * lm.get("domain_weight", 0.5) for lm in links_60)
            wtot = sum(lm.get("domain_weight", 0.5) for lm in links_60) or 1.0
            avg_sent = (wsum / wtot)

            top_sources = [domain_from_url(lm.get("url","")) for lm in items_24h.get(sym, [])]

            # Keyword score vs hotwords
            hotwords = meta.get("hotwords", [])
            matches = 0
            checks = 0
            for lm in items_24h.get(sym, []):
                text = f"{lm.get('title','')} {lm.get('summary','')}".lower()
                for hw in hotwords:
                    checks += 1
                    if hw in text:
                        matches += 1
            keyword_score = (matches / checks * 10) if checks else 0.0

            heat_score = counts_5m.get(sym, 0)
            velocity_10m = counts_10m.get(sym, 0)
            is_spike = sym in hot_symbols

        trade, rationale = trade_suggestion_for_symbol(avg_sent, is_spike, heat_score, keyword_score, top_sources)

        entry = {
            # Identity
            "symbol": sym,
            "company": meta.get("metadata",{}).get("longName",""),
            # News awareness
            "total_headlines": meta.get("total_headlines", 0),
            "unique_headlines": meta.get("unique_headlines", 0),
            "replicated_headlines": meta.get("replicated_headlines", 0),
            "regions": meta.get("regions", []),
            "region_count": len(meta.get("regions", [])),
            # Sentiment / scoring
            "avg_sentiment": round(avg_sent, 3),
            "top_sources": list(dict.fromkeys(top_sources))[:5],
            "keyword_score": round(keyword_score, 2),
            "heat_score_5m": heat_score,
            "velocity_10m": velocity_10m,
            "is_spike": is_spike,
            "freshness": {"badge": badge, "bucket": bucket, "seconds_old": age_min},
            # Links
            "top_headlines": meta.get("top_headlines", []),
            "links_5m": sorted(links_5, key=lambda x: x.get("timestamp_ts",0), reverse=True)[:20],
            "links_60m": sorted(links_60, key=lambda x: x.get("timestamp_ts",0), reverse=True)[:50],
            # Trade hint
            "trade_suggestion": trade,
            "trade_rationale": rationale,
        }

        # Your original C3 score style
        entry["c3_score"] = round((heat_score * 2) + (entry["avg_sentiment"] * 5) + (entry["region_count"] * 0.5), 2)

        hot_news.append(entry)

    # Default sort (your original): spikes, heat, velocity, unique headlines
    hot_news.sort(key=lambda x: (not x["is_spike"], -x["heat_score_5m"], -x["velocity_10m"], -x["unique_headlines"]))
    return hot_news


# ============================
# Section 12: Merge enrichment (Yahoo + Float) into entries
# ============================
def merge_market_fields(entries: List[Dict[str, Any]], yahoo_map: Dict[str, Dict[str, Any]], floats_map: Dict[str, int]):
    for e in entries:
        sym = e.get("symbol")
        y = yahoo_map.get(sym, {})
        e["last_price"] = y.get("last_price")
        e["prev_close"] = y.get("prev_close")
        e["percent_change"] = y.get("percent_change")
        e["gap_percent"] = y.get("gap_percent")
        e["volume"] = y.get("volume")
        e["avg_volume"] = y.get("avg_volume")
        e["relative_volume"] = y.get("relative_volume")

        fs = floats_map.get(sym)
        e["float_shares"] = fs
        e["float_category"] = float_category(fs)


# ============================
# Section 13: Printers (4 prints)
# ============================
def _pillars_header_line(e: Dict[str, Any]) -> str:
    symbol = e.get("symbol", "N/A")
    fire_icon = "🔥" if e.get("is_spike") else " "
    gap = e.get("gap_percent")
    rvol = e.get("relative_volume")
    fs = e.get("float_shares")
    fcat = e.get("float_category", "UNKNOWN")
    price = e.get("last_price")
    has_news = "Y" if e.get("total_headlines", 0) > 0 else "N"

    gap_s = f"{gap:.2f}%" if gap is not None else "N/A"
    rvol_s = f"{rvol:.2f}×" if rvol is not None else "N/A"
    float_s = f"{format_float_shares(fs)} ({fcat})" if fs is not None else "N/A (UNKNOWN)"
    price_s = f"${price:.2f}" if price is not None else "N/A"

    return f"{symbol} | {fire_icon} | Gap:{gap_s} | RVOL:{rvol_s} | Float:{float_s} | Price:{price_s} | News:{has_news}"

def print_primary_block(entries: List[Dict[str, Any]], cfg: ScannerConfig, title: str):
    print("\n" + "="*70)
    print(f"{title} —", datetime.now(timezone.utc).isoformat())
    print("="*70)

    for e in entries:
        sym = e["symbol"]
        badge = e.get("freshness", {}).get("badge", "⚫")
        vel = e.get("velocity_10m", 0)
        total = e.get("total_headlines", 0)
        spike = "YES" if e.get("is_spike") else "No"
        sent = e.get("avg_sentiment", 0.0)
        score = e.get("c3_score", 0.0)
        kw = e.get("keyword_score", 0.0)
        trade = e.get("trade_suggestion", "Neutral ⚪")

        # --- 5 pillars header first (as agreed)
        print(_pillars_header_line(e))

        # --- your original working C3 line
        print(f"{sym} | {badge} | Vel10m:{vel} | Total:{total} | Spike:{spike} | Sent:{sent:+.2f} | Score:{score} | KW:{kw:.2f}/10")

        # Awareness block (you asked to keep complete)
        print("\nAWARENESS")
        print(f"Total Articles: {e.get('total_headlines', 0)}")
        print(f"Unique Articles: {e.get('unique_headlines', 0)}")
        print(f"Replicated Articles: {e.get('replicated_headlines', 0)}")
        regions = e.get("regions", [])
        print(f"Regions: {', '.join(regions) if regions else 'N/A'}")
        print(f"Region Count: {len(regions)}")

        print(f"\nTrade: {trade} — {e.get('trade_rationale','')}")

        # Top headlines
        if e.get("top_headlines"):
            print("\nTop Headlines:")
            for i, th in enumerate(e.get("top_headlines", [])[:cfg.TOP_N_HEADLINES], start=1):
                headline = th.get("headline", "")
                links = th.get("links", [])[:5]
                print(f" {i}. {headline} — {len(links)} source(s)")
                if links:
                    best = sorted(links, key=lambda x: x.get("timestamp_ts", 0), reverse=True)[0]
                    print(f"    {best.get('url')}")
        else:
            print("\nTop Headlines: (none)")

        print("-"*70)

def sorted_by_gap_desc(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def key_fn(e):
        g = e.get("gap_percent")
        g = -1e18 if g is None else g
        return g
    return sorted(entries, key=key_fn, reverse=True)

def passes_ross_pillars(e: Dict[str, Any], cfg: ScannerConfig) -> bool:
    """
    Ross 5 pillars filter:
    1) RVOL >= 5
    2) Gap% >= 10 (or %change if you want to adjust later)
    3) News present (we treat as yes if total_headlines > 0)
    4) Price between 2 and 20
    5) Float < 10M
    """
    rvol = e.get("relative_volume")
    gap = e.get("gap_percent")
    price = e.get("last_price")
    fs = e.get("float_shares")
    news_ok = e.get("total_headlines", 0) > 0

    if rvol is None or rvol < cfg.PILLAR_MIN_RVOL:
        return False
    if gap is None or gap < cfg.PILLAR_MIN_GAP_PERCENT:
        return False
    if price is None or not (cfg.PILLAR_MIN_PRICE <= price <= cfg.PILLAR_MAX_PRICE):
        return False
    if fs is None or fs >= cfg.PILLAR_MAX_FLOAT:
        return False
    if not news_ok:
        return False
    return True

def print_filtered_compact(entries: List[Dict[str, Any]], cfg: ScannerConfig, top_n: int = 10):
    """
    One-line watchlist output after Ross pillars filter.
    Sorted by gap desc.
    """
    filtered = [e for e in entries if passes_ross_pillars(e, cfg)]
    filtered = sorted_by_gap_desc(filtered)[:top_n]

    print("\n" + "="*70)
    print("WATCHLIST (FILTERED COMPACT — Ross 5 pillars) —", datetime.now(timezone.utc).isoformat())
    print("="*70)
    if not filtered:
        print("No symbols passed the 5 pillars filter (this can happen on weekends/quiet sessions).")
        return

    for e in filtered:
        sym = e["symbol"]
        fire_icon = "🔥" if e.get("is_spike") else " "
        gap = e.get("gap_percent")
        rvol = e.get("relative_volume")
        fs = e.get("float_shares")
        fcat = e.get("float_category", "UNKNOWN")
        price = e.get("last_price")
        total = e.get("total_headlines", 0)
        uniq = e.get("unique_headlines", 0)
        vel = e.get("velocity_10m", 0)
        sent = e.get("avg_sentiment", 0.0)
        score = e.get("c3_score", 0.0)
        rc = e.get("region_count", 0)

        print(
            f"{sym} | {fire_icon} | "
            f"Gap:{gap:.2f}% | RVOL:{rvol:.2f}× | Float:{format_float_shares(fs)} ({fcat}) | "
            f"Price:${price:.2f} | Total Articles:{total} | Unique:{uniq} | "
            f"Vel10m:{vel} | Sent:{sent:+.2f} | Score:{score} | Region Count:{rc}"
        )

def print_filtered_detailed(entries: List[Dict[str, Any]], cfg: ScannerConfig, top_n: int = 10):
    filtered = [e for e in entries if passes_ross_pillars(e, cfg)]
    filtered = sorted_by_gap_desc(filtered)[:top_n]
    if not filtered:
        print("\n(No symbols passed the 5 pillars filter; skipping detailed watchlist.)")
        return
    print_primary_block(filtered, cfg, "WATCHLIST (FILTERED DETAILED — Ross 5 pillars)")


# ============================
# Section 14: Save outputs (timestamped, descriptive)
# ============================
def save_outputs(entries: List[Dict[str, Any]], cfg: ScannerConfig) -> str:
    ts_label = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(cfg.OUT_DIR_BASE, ts_label)
    mkdirp(out_dir)

    with open(os.path.join(out_dir, f"scanner_entries_{ts_label}.json"), "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    # Also save filtered watchlist
    filtered = [e for e in entries if passes_ross_pillars(e, cfg)]
    filtered = sorted_by_gap_desc(filtered)[:10]
    with open(os.path.join(out_dir, f"watchlist_top10_{ts_label}.json"), "w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2, ensure_ascii=False)

    logging.info("Saved outputs to %s", out_dir)
    return out_dir


# ============================
# Section 15: Orchestrator (single cycle)
# ============================
def run_cycle(cfg: ScannerConfig, use_ib: bool = True):
    print("\n" + "="*70)
    print("STARTING SCAN CYCLE —", datetime.now(timezone.utc).isoformat())
    print("="*70)

    # Step 1: Discover symbols via IBKR scanner
    symbols_meta = {}
    if use_ib:
        symbols_meta = ibkr_fetch_top_gainers(cfg)
    if not symbols_meta:
        logging.warning("No symbols returned from IBKR scanner. Aborting cycle.")
        return

    symbols = list(symbols_meta.keys())

    # Step 2: Fetch RSS feeds (async)
    rss_urls = load_verified_rss(cfg.VERIFIED_RSS_FILE)
    if not rss_urls:
        logging.error("No RSS feeds loaded; verify %s", cfg.VERIFIED_RSS_FILE)
        return
    feeds_map = fetch_all_feeds(rss_urls, cfg)

    # Step 3: Match news against hotwords (your engine)
    now = now_ts()
    results_per_symbol, detailed_feed_items = aggregate_matches_with_links(symbols_meta, feeds_map, now, cfg)

    # Step 4: Build hot news list (your engine)
    entries = build_hot_news(results_per_symbol, detailed_feed_items, cfg)

    # Step 5: Enrich market fields (Yahoo) and float (Finviz cached)
    yahoo_map = yahoo_batch_quote([e["symbol"] for e in entries], cfg)
    floats_map = enrich_floats([e["symbol"] for e in entries], cfg)
    merge_market_fields(entries, yahoo_map, floats_map)

    # Step 6: Sort for printing by GAP DESC (as you requested for all printers)
    entries_sorted_by_gap = sorted_by_gap_desc(entries)

    # PRINT 1: Cycle primary print (full blocks)
    if cfg.PRINT_1_CYCLE_PRIMARY:
        print_primary_block(entries_sorted_by_gap, cfg, "HOT NEWS (PRIMARY — 5 pillars + full block)")

    # PRINT 2: General sorted print (same blocks; explicit)
    if cfg.PRINT_2_GENERAL_SORTED:
        print_primary_block(entries_sorted_by_gap, cfg, "HOT NEWS (GENERAL SORTED BY GAP DESC)")

    # PRINT 3: Filtered compact watchlist (one-liners)
    if cfg.PRINT_3_FILTERED_COMPACT:
        print_filtered_compact(entries_sorted_by_gap, cfg, top_n=10)

    # PRINT 4: Filtered detailed watchlist (full blocks)
    if cfg.PRINT_4_FILTERED_DETAILED:
        print_filtered_detailed(entries_sorted_by_gap, cfg, top_n=10)

    # Save
    save_outputs(entries_sorted_by_gap, cfg)


# ============================
# Section 16: CLI entrypoint
# ============================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--no-ib", action="store_true", help="Do not query IBKR (testing)")
    parser.add_argument("--quiet", action="store_true", help="Reduce logging verbosity")
    args = parser.parse_args()

    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    if args.once:
        run_cycle(CFG, use_ib=(not args.no_ib))
        return

    try:
        while True:
            run_cycle(CFG, use_ib=(not args.no_ib))
            logging.info("Sleeping %d seconds until next cycle...", CFG.CYCLE_SLEEP_SECONDS)
            time.sleep(CFG.CYCLE_SLEEP_SECONDS)
    except KeyboardInterrupt:
        logging.info("Interrupted by user — exiting.")

if __name__ == "__main__":
    main()
