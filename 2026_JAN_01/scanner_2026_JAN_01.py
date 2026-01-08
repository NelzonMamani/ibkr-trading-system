#!/usr/bin/env python3
"""
scanner.py (FULL VERSION)

Integrated scanner + async hot-news engine + Ross-style enrichment + watchlist

- IBKR reconnect every cycle (random client id)
- Fetch top N % gainers, enrich with:
    * last_price, open_price, prev_close
    * percent_change, gap_percent
    * relative_volume (volume / avVolume)
    * bid/ask spread %
    * float_shares (from optional local cache file)
- Async RSS fetching (aiohttp)
- Deduplication + replication + regions + velocity + spike detection
- Creates watchlist TOP 5–10 AFTER applying Ross 5 Pillars filter
- Saves descriptive, timestamped JSON outputs
- Prints 4 times per cycle:
    1) Cycle print (legacy C3 style)
    2) General printer (verbose, no filter, sorted by gap)
    3) Filtered compact/medium printer (one-line, sorted by gap)
    4) Filtered deep printer (verbose, sorted by gap)

Notes:
- Float is sourced from a local JSON cache file by default:
    floats_cache.json  -> {"INBS": 8320000, "NUAI": 27400000, ...}
  If missing, float_shares will be None and float_category becomes "UNKNOWN".
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
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

# IB
from ib_insync import IB, ScannerSubscription

# ----------------------------
# CONFIG
# ----------------------------
VERIFIED_RSS_FILE = "verified_rss.txt"   # one feed URL per line
FLOATS_CACHE_FILE = "floats_cache.json" # optional local float cache: {"SYM": int_float, ...}

CYCLE_SLEEP_SECONDS = 60
TOP_N_HEADLINES = 5
RSS_FETCH_TIMEOUT = 30
RSS_CONCURRENCY = 24
RSS_FETCH_RETRIES = 2
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
OUT_DIR_BASE = "data"

TOP_GAINERS_COUNT = 50  # IBKR top gainers list length
WATCHLIST_TOP_N = 10    # save top 5-10

# Spike detection params (news velocity spike)
ABSOLUTE_SPIKE_THRESHOLD = 5
SPIKE_RATIO = 2.0

# Age buckets (seconds)
BUCKET_5M = 5 * 60
BUCKET_10M = 10 * 60
BUCKET_60M = 60 * 60
BUCKET_24H = 24 * 3600

# Ross Pillars thresholds (v1, adjustable later)
ROSS_MIN_PRICE = 2.0
ROSS_MAX_PRICE = 20.0
ROSS_MIN_GAP = 5.0
ROSS_MIN_RVOL = 2.0
ROSS_MAX_FLOAT = 20_000_000

# Logging
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

def safe_round(x: Optional[float], nd: int = 2):
    if x is None:
        return None
    try:
        return round(float(x), nd)
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

# ============================
# Section 3: Sentiment & domain weights
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

def is_credible_source(dom: str) -> bool:
    d = dom.lower()
    return any(x in d for x in ["bloomberg", "reuters", "wsj", "ft", "nytimes", "cnn"])

# ============================
# Section 4: Load RSS list & float cache
# ============================
def load_verified_rss(file_path: str = VERIFIED_RSS_FILE) -> List[str]:
    p = Path(file_path)
    if not p.exists():
        logging.error("Verified RSS file not found: %s", file_path)
        return []
    with p.open("r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    logging.info("Loaded %d RSS feeds", len(urls))
    return urls

def load_floats_cache(file_path: str = FLOATS_CACHE_FILE) -> Dict[str, int]:
    """
    Optional local float cache.
    Format: {"SYM": 8320000, "ABC": 124000000, ...}
    """
    p = Path(file_path)
    if not p.exists():
        logging.warning("Float cache not found (%s). Float will be UNKNOWN.", file_path)
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        out = {}
        for k, v in data.items():
            if isinstance(k, str) and isinstance(v, int):
                out[k.upper()] = v
        logging.info("Loaded float cache for %d symbols", len(out))
        return out
    except Exception as e:
        logging.warning("Failed to parse float cache (%s): %s", file_path, e)
        return {}

# ============================
# Section 5: Async RSS fetcher
# ============================
async def fetch_single(session: aiohttp.ClientSession, url: str, sem: asyncio.Semaphore) -> Tuple[str, List[Dict[str,Any]]]:
    headers = {"User-Agent": USER_AGENT}
    timeout = aiohttp.ClientTimeout(total=RSS_FETCH_TIMEOUT, connect=10, sock_read=RSS_FETCH_TIMEOUT)
    backoff_base = 0.6
    async with sem:
        for attempt in range(1, RSS_FETCH_RETRIES + 1):
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
                pass
            except Exception:
                pass
            await asyncio.sleep(backoff_base * (2 ** (attempt - 1)))
    return url, []

async def fetch_all_feeds_async(rss_urls: List[str]) -> Dict[str, List[Dict[str,Any]]]:
    connector = aiohttp.TCPConnector(ssl=False, limit=RSS_CONCURRENCY, limit_per_host=10)
    sem = asyncio.Semaphore(RSS_CONCURRENCY)
    results = {}
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [asyncio.create_task(fetch_single(session, url, sem)) for url in rss_urls]
        responses = await asyncio.gather(*tasks, return_exceptions=False)
        for url, entries in responses:
            results[url] = entries or []
    return results

def fetch_all_feeds(rss_urls: List[str]) -> Dict[str, List[Dict[str,Any]]]:
    if not rss_urls:
        return {}
    try:
        prev_loop = asyncio.get_event_loop()
    except RuntimeError:
        prev_loop = None
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(fetch_all_feeds_async(rss_urls))
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

# ============================
# Section 6: IBKR scanner + enrichment
# ============================
def categorize_float(float_shares: Optional[int]) -> str:
    if float_shares is None:
        return "UNKNOWN"
    if float_shares < 20_000_000:
        return "LOW"
    if float_shares < 100_000_000:
        return "MID"
    return "HIGH"

def compute_spread_percent(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    try:
        if bid is None or ask is None:
            return None
        if bid <= 0 or ask <= 0:
            return None
        mid = (bid + ask) / 2
        if mid <= 0:
            return None
        return ((ask - bid) / mid) * 100
    except Exception:
        return None

def fetch_ibkr_symbols_and_metadata(number_of_rows: int, floats_cache: Dict[str,int]) -> Dict[str, Dict[str,Any]]:
    """
    Returns metadata dict keyed by symbol, including enriched market data.
    """
    ib = IB()
    client_id = int(time.time()) % 9999
    try:
        ib.connect('127.0.0.1', 7496, clientId=client_id, timeout=10)
    except Exception as e:
        logging.warning("IB connect failed: %s", e)
        try:
            ib.disconnect()
        except Exception:
            pass
        return {}

    metadata: Dict[str, Dict[str,Any]] = {}
    contracts = []

    try:
        scan_sub = ScannerSubscription(
            instrument='STK',
            locationCode='STK.US.MAJOR',
            scanCode='TOP_PERC_GAIN',
            numberOfRows=number_of_rows
        )

        scan_data = ib.reqScannerData(scan_sub)
        for item in scan_data:
            contract = item.contractDetails.contract
            sym = getattr(contract, "symbol", None)
            if not sym:
                continue
            sym = sym.upper()
            contracts.append(contract)
            metadata[sym] = {
                "symbol": sym,
                "contract": contract,
                "longName": getattr(item.contractDetails, "longName", sym),
                "primaryExchange": getattr(contract, "primaryExchange", "") or "",
                "currency": getattr(contract, "currency", "") or "",
            }

        # Market data enrichment
        if contracts:
            tickers = ib.reqTickers(*contracts)
            for t in tickers:
                c = getattr(t, "contract", None)
                if not c:
                    continue
                sym = getattr(c, "symbol", None)
                if not sym:
                    continue
                sym = sym.upper()
                if sym not in metadata:
                    continue

                last_price = getattr(t, "last", None)
                open_price = getattr(t, "open", None)
                prev_close = getattr(t, "prevClose", None)
                volume_today = getattr(t, "volume", None)
                av_volume = getattr(t, "avVolume", None)
                bid = getattr(t, "bid", None)
                ask = getattr(t, "ask", None)

                percent_change = None
                gap_percent = None
                if prev_close and last_price:
                    percent_change = ((last_price - prev_close) / prev_close) * 100
                if prev_close and open_price:
                    gap_percent = ((open_price - prev_close) / prev_close) * 100

                relative_volume = None
                if av_volume and volume_today:
                    try:
                        relative_volume = volume_today / av_volume
                    except Exception:
                        relative_volume = None

                spread_percent = compute_spread_percent(bid, ask)

                # Float from cache
                float_shares = floats_cache.get(sym)
                float_category = categorize_float(float_shares)

                metadata[sym].update({
                    "last_price": last_price,
                    "open_price": open_price,
                    "prev_close": prev_close,
                    "percent_change": safe_round(percent_change, 2),
                    "gap_percent": safe_round(gap_percent, 2),
                    "volume_today": volume_today,
                    "avg_volume": av_volume,
                    "relative_volume": safe_round(relative_volume, 2),
                    "bid": bid,
                    "ask": ask,
                    "bid_ask_spread_percent": safe_round(spread_percent, 2),
                    "float_shares": float_shares,
                    "float_category": float_category,
                })

    except Exception as e:
        logging.warning("IB scanner error: %s", e)
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass

    logging.info("IBKR metadata ready for %d symbols", len(metadata))
    return metadata

# ============================
# Section 7: Matching, dedupe, replicate counting
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

def normalize_hotword_list(meta: Dict[str,Any]) -> List[str]:
    candidates = [
        meta.get("symbol",""),
        meta.get("longName",""),
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

def aggregate_matches_with_links(symbols_meta: Dict[str,Dict[str,Any]],
                                 feeds_map: Dict[str,List[Dict[str,Any]]],
                                 now_ts_val: int,
                                 max_age_seconds: int = BUCKET_24H) -> Tuple[Dict[str,Any], List[Dict[str,Any]]]:
    """
    Returns:
      results_per_symbol: {SYM: {total_headlines, unique_headlines, replicated_headlines, regions, top_headlines, hotwords}}
      detailed_feed_items: flattened list of matched link_meta for velocity scoring
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

        title_to_sources = defaultdict(set)         # headline -> set(urls)
        matched_links_by_headline = defaultdict(list)
        regions_detected = set()
        total_matches = 0

        if not hotwords:
            results[symbol] = {
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

            # age check
            if published_ts:
                try:
                    age = now_ts_val - int(published_ts)
                    if age > max_age_seconds:
                        continue
                except Exception:
                    pass

            hay = f"{title} {summary}".lower()
            tokens = set(WORD_REGEX.findall(hay))

            # match: any hotword token hit
            matched = False
            for hw in hotwords:
                if hw in tokens:
                    matched = True
                    break
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
                "domain_weight": domain_weight_from_url(link),
                "domain": domain_from_url(link),
            }

            matched_links_by_headline[headline_key].append(link_meta)
            detailed_feed_items.append({
                "symbol": symbol,
                "headline": headline_key,
                "link_meta": link_meta
            })

        unique_headlines = len(title_to_sources)
        replicated = max(0, total_matches - unique_headlines)

        top_headlines = sorted(
            [{"headline": h,
              "links": matched_links_by_headline[h],
              "sources": len(title_to_sources[h])} for h in title_to_sources],
            key=lambda x: (x["sources"], max(lm["timestamp_ts"] for lm in x["links"])),
            reverse=True
        )[:TOP_N_HEADLINES]

        results[symbol] = {
            "total_headlines": total_matches,
            "unique_headlines": unique_headlines,
            "replicated_headlines": replicated,
            "top_headlines": top_headlines,
            "regions": sorted(regions_detected),
            "hotwords": hotwords
        }

    return results, detailed_feed_items

# ============================
# Section 8: Velocity, spike, scoring & trade suggestion
# ============================
def categorize_age_seconds(age_sec: int) -> Tuple[str,str]:
    if age_sec <= BUCKET_5M:
        return "🔥","0-5m"
    if age_sec <= BUCKET_60M:
        return "🟡","5-60m"
    if age_sec <= BUCKET_24H:
        return "🟢","1-24h"
    return "⚫",">24h"

def trade_suggestion_for_symbol(avg_sent: float, is_spike: bool, heat_5m: int, keyword_score: float, top_domains: List[str]) -> Tuple[str,str]:
    credible = any(is_credible_source(d) for d in top_domains)
    parts = []
    if is_spike:
        parts.append("Volume spike")
    if credible:
        parts.append("High-cred sources")
    if avg_sent > 0.25:
        parts.append("Positive sentiment")
    if avg_sent < -0.25:
        parts.append("Negative sentiment")
    if keyword_score > 6:
        parts.append("Strong keywords")
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

def build_hot_entries(symbols_meta: Dict[str,Dict[str,Any]],
                      results_per_symbol: Dict[str,Any],
                      detailed_feed_items: List[Dict[str,Any]]) -> List[Dict[str,Any]]:
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

        if age <= BUCKET_5M:
            counts_5m[sym] += 1
            items_5m[sym].append(lm)
        if age <= BUCKET_10M:
            counts_10m[sym] += 1
            items_10m[sym].append(lm)
        if age <= BUCKET_60M:
            counts_60m[sym] += 1
            items_60m[sym].append(lm)
        if age <= BUCKET_24H:
            counts_24h[sym] += 1
            items_24h[sym].append(lm)

    # Spike detection in 5m bucket
    hot_symbols = set()
    if counts_5m:
        most = counts_5m.most_common()
        top_count = most[0][1]
        second_count = most[1][1] if len(most) > 1 else 0
        for sym, cnt in counts_5m.items():
            if cnt >= ABSOLUTE_SPIKE_THRESHOLD:
                hot_symbols.add(sym)
            elif second_count == 0 and cnt >= 2:
                hot_symbols.add(sym)
            elif second_count > 0 and cnt >= SPIKE_RATIO * second_count and cnt >= 2:
                hot_symbols.add(sym)

    entries = []
    for sym, meta in symbols_meta.items():
        news_meta = results_per_symbol.get(sym, {})
        links_60 = items_60m.get(sym, [])
        links_5 = items_5m.get(sym, [])

        if links_60:
            min_ts = min(lm["timestamp_ts"] for lm in (links_5 if links_5 else links_60))
            age_min = now - min_ts
            badge, bucket = categorize_age_seconds(age_min)

            wsum = sum(lm.get("sentiment",0.0) * lm.get("domain_weight",0.5) for lm in links_60)
            wtot = sum(lm.get("domain_weight",0.5) for lm in links_60) or 1.0
            avg_sent = wsum / wtot

            top_domains = [lm.get("domain","") for lm in items_24h.get(sym, [])]
            top_domains = list(dict.fromkeys(top_domains))[:10]

            # keyword score (simple ratio)
            hotwords = news_meta.get("hotwords", [])
            matches = 0
            checks = 0
            for lm in items_24h.get(sym, []):
                text = f"{lm.get('title','')} {lm.get('summary','')}".lower()
                for hw in hotwords:
                    checks += 1
                    if hw in text:
                        matches += 1
            keyword_score = (matches / checks * 10) if checks else 0.0

            heat_5m = counts_5m.get(sym, 0)
            velocity_10m = counts_10m.get(sym, 0)
            is_spike = sym in hot_symbols

            trade, rationale = trade_suggestion_for_symbol(avg_sent, is_spike, heat_5m, keyword_score, top_domains)
        else:
            badge, bucket = "⚫", ">24h"
            age_min = None
            avg_sent = 0.0
            top_domains = []
            keyword_score = 0.0
            heat_5m = 0
            velocity_10m = 0
            is_spike = False
            trade, rationale = "No recent news", ""

        # C3 score (kept similar to your original)
        c3_score = round((heat_5m * 2) + (avg_sent * 5) + (len(news_meta.get("regions",[])) * 0.5), 2)

        entries.append({
            # identity
            "symbol": sym,
            "company": meta.get("longName",""),

            # market data (Ross pillars)
            "last_price": meta.get("last_price"),
            "open_price": meta.get("open_price"),
            "prev_close": meta.get("prev_close"),
            "percent_change": meta.get("percent_change"),
            "gap_percent": meta.get("gap_percent"),
            "relative_volume": meta.get("relative_volume"),
            "float_shares": meta.get("float_shares"),
            "float_category": meta.get("float_category"),
            "bid_ask_spread_percent": meta.get("bid_ask_spread_percent"),

            # news awareness
            "total_headlines": news_meta.get("total_headlines",0),
            "unique_headlines": news_meta.get("unique_headlines",0),
            "replicated_headlines": news_meta.get("replicated_headlines",0),
            "regions": news_meta.get("regions",[]),
            "top_headlines": news_meta.get("top_headlines",[]),

            # news scoring / velocity
            "avg_sentiment": round(avg_sent,3),
            "keyword_score": round(keyword_score,2),
            "heat_score_5m": heat_5m,
            "velocity_10m": velocity_10m,
            "is_spike": is_spike,
            "freshness": {"badge": badge, "bucket": bucket, "seconds_old": age_min},

            # decision
            "c3_score": c3_score,
            "trade_suggestion": trade,
            "trade_rationale": rationale,
        })

    return entries

# ============================
# Section 9: Ross pillars filter + watchlist
# ============================
def passes_ross_five_pillars(e: Dict[str,Any]) -> bool:
    """
    Ross v1 hard filter:
    - Price $2-$20
    - Gap >= 5%
    - RVOL >= 2x
    - Float <= 20M (if unknown, fail in v1)
    - News OR RVOL >= 5 (abnormal volume can substitute)
    """
    price = e.get("last_price")
    gap = e.get("gap_percent") or 0
    rvol = e.get("relative_volume") or 0
    flt = e.get("float_shares")

    # Require float for v1 (you can relax later)
    if flt is None:
        return False

    has_news = (e.get("total_headlines", 0) > 0)

    return (
        (price is not None and ROSS_MIN_PRICE <= price <= ROSS_MAX_PRICE) and
        gap >= ROSS_MIN_GAP and
        rvol >= ROSS_MIN_RVOL and
        flt <= ROSS_MAX_FLOAT and
        (has_news or rvol >= 5.0)
    )

def sort_by_gap_then_change(e: Dict[str,Any]) -> Tuple[float,float]:
    return (-(e.get("gap_percent") or 0), -(e.get("percent_change") or 0))

def build_watchlist(entries: List[Dict[str,Any]], top_n: int = WATCHLIST_TOP_N) -> List[Dict[str,Any]]:
    qualified = [e for e in entries if passes_ross_five_pillars(e)]
    qualified_sorted = sorted(qualified, key=sort_by_gap_then_change)
    return qualified_sorted[:top_n]

# ============================
# Section 10: Printers (4 prints per cycle)
# ============================
def print_cycle_legacy_c3(entries: List[Dict[str,Any]]):
    """
    PRINT #1: Cycle print "as it was" (legacy C3 style feel).
    This does NOT apply the 5 pillars filter.
    It prints a compact block per ticker (like your original).
    """
    print("\n" + "="*70)
    print("HOT NEWS (cycle legacy C3) —", datetime.now(timezone.utc).isoformat())
    print("="*70)

    # Keep your legacy sorting logic: spike/heat/velocity/unique
    entries_sorted = sorted(entries, key=lambda x: (not x.get("is_spike",False),
                                                   -x.get("heat_score_5m",0),
                                                   -x.get("velocity_10m",0),
                                                   -x.get("unique_headlines",0)))

    for e in entries_sorted:
        sym = e["symbol"]
        badge = e.get("freshness",{}).get("badge","⚫")
        print(
            f"{sym} | {badge} | Vel10m:{e.get('velocity_10m',0)} | "
            f"Total:{e.get('total_headlines',0)} | Spike:{'YES' if e.get('is_spike') else 'No'} | "
            f"Sent:{e.get('avg_sentiment',0.0):+.2f} | Score:{e.get('c3_score')} | KW:{e.get('keyword_score',0.0):.2f}/10"
        )

        print(f"Trade: {e.get('trade_suggestion','Neutral ⚪')} — {e.get('trade_rationale','')}")
        if e.get("top_headlines"):
            print("Top Headlines:")
            for i, th in enumerate(e.get("top_headlines",[])[:TOP_N_HEADLINES], start=1):
                headline = th.get("headline","")
                links = th.get("links",[])[:5]
                print(f" {i}. {headline} — {len(links)} source(s)")
                if links:
                    best = sorted(links, key=lambda x: x.get("timestamp_ts",0), reverse=True)[0]
                    print(f"    {best.get('url')}")
        else:
            print("Top Headlines: (none)")
        print("-"*70)

def print_ross_pillars_awareness_line(e: Dict[str,Any]):
    """
    This is your agreed Ross line:
    INBS | 🔥 | Gap... | RVOL... | Float... | Price... | Total Articles... | Unique... | Vel10m... | Sent... | Score... | Region Count...
    """
    sym = e.get("symbol","")
    fire = "🔥" if e.get("is_spike", False) else " "
    float_fmt = format_float_shares(e.get("float_shares"))

    print(
        f"{sym} | {fire} | "
        f"Gap:{e.get('gap_percent','N/A')}% | "
        f"RVOL:{e.get('relative_volume','N/A')}× | "
        f"Float:{float_fmt} ({e.get('float_category','N/A')}) | "
        f"Price:${e.get('last_price','N/A')} | "
        f"Total Articles: {e.get('total_headlines',0)} | "
        f"Unique Articles: {e.get('unique_headlines',0)} | "
        f"Vel10m:{e.get('velocity_10m',0)} | "
        f"Sent:{e.get('avg_sentiment',0.0):+.2f} | "
        f"Score:{e.get('c3_score','N/A')} | "
        f"Region Count: {len(e.get('regions',[]))}"
    )

def print_general_verbose_sorted_by_gap(entries: List[Dict[str,Any]]):
    """
    PRINT #2: General printer
    - No 5 pillars filtering
    - Sorted by Gap desc then % Change desc
    - Prints full block per ticker:
        * Ross pillars awareness line
        * C3 line
        * Awareness block (includes replicated + regions)
        * Trade line
        * Top 5 unique headlines w/ one best link each
    """
    print("\n" + "="*70)
    print("GENERAL VIEW (no filter) — sorted by GAP desc —", datetime.now(timezone.utc).isoformat())
    print("="*70)

    entries_sorted = sorted(entries, key=sort_by_gap_then_change)

    for e in entries_sorted:
        # 1) Ross line
        print_ross_pillars_awareness_line(e)

        # 2) C3 line (kept)
        sym = e["symbol"]
        print(
            f"{sym} | 🔥 | Vel10m:{e.get('velocity_10m',0)} | Total:{e.get('total_headlines',0)} | "
            f"Spike:{'YES' if e.get('is_spike') else 'No'} | Sent:{e.get('avg_sentiment',0.0):+.2f} | "
            f"Score:{e.get('c3_score')} | KW:{e.get('keyword_score',0.0):.2f}/10"
        )

        # 3) Awareness block
        print("\nAWARENESS")
        print(f"Total Articles: {e.get('total_headlines',0)}")
        print(f"Unique Articles: {e.get('unique_headlines',0)}")
        print(f"Replicated Articles: {e.get('replicated_headlines',0)}")
        regs = e.get("regions", [])
        print(f"Regions: {', '.join(regs) if regs else 'N/A'}")
        print(f"Region Count: {len(regs)}")

        # 4) Trade line
        print(f"\nTrade: {e.get('trade_suggestion','Neutral ⚪')} — {e.get('trade_rationale','')}")

        # 5) Top headlines (top 5 unique)
        if e.get("top_headlines"):
            print("\nTop Headlines:")
            for i, th in enumerate(e.get("top_headlines",[])[:TOP_N_HEADLINES], start=1):
                headline = th.get("headline","")
                links = th.get("links", [])
                print(f" {i}. {headline} — {len(links)} source(s)")
                if links:
                    best = sorted(links, key=lambda x: x.get("timestamp_ts",0), reverse=True)[0]
                    print(f"    {best.get('url')}")
        else:
            print("\nTop Headlines: (none)")

        print("-"*70)

def print_filtered_compact_watchlist(entries: List[Dict[str,Any]], top_n: int = WATCHLIST_TOP_N):
    """
    PRINT #3: Compact/medium watchlist printer
    - Applies Ross 5 pillars filter
    - Sorted by GAP desc then % Change desc
    - Prints ONE LINE per symbol (your Ross line)
    """
    filtered = [e for e in entries if passes_ross_five_pillars(e)]
    filtered_sorted = sorted(filtered, key=sort_by_gap_then_change)[:top_n]

    print("\n" + "="*70)
    print(f"ROSS WATCHLIST (filtered) — TOP {top_n} — sorted by GAP desc —", datetime.now(timezone.utc).isoformat())
    print("="*70)

    if not filtered_sorted:
        print("No symbols passed Ross 5 pillars (v1).")
        print("="*70)
        return

    for e in filtered_sorted:
        print_ross_pillars_awareness_line(e)

    print("="*70)

def print_filtered_deep_verbose(entries: List[Dict[str,Any]], top_n: int = WATCHLIST_TOP_N):
    """
    PRINT #4: Deep printer (filtered)
    - Applies Ross 5 pillars
    - Sorted by GAP desc then % Change desc
    - Prints full verbose blocks for top N (same structure as general printer, but filtered)
    """
    filtered = [e for e in entries if passes_ross_five_pillars(e)]
    filtered_sorted = sorted(filtered, key=sort_by_gap_then_change)[:top_n]

    print("\n" + "="*70)
    print(f"DEEP VIEW (filtered) — TOP {top_n} —", datetime.now(timezone.utc).isoformat())
    print("="*70)

    if not filtered_sorted:
        print("No symbols passed Ross 5 pillars (v1).")
        print("="*70)
        return

    for e in filtered_sorted:
        print_ross_pillars_awareness_line(e)

        sym = e["symbol"]
        print(
            f"{sym} | 🔥 | Vel10m:{e.get('velocity_10m',0)} | Total:{e.get('total_headlines',0)} | "
            f"Spike:{'YES' if e.get('is_spike') else 'No'} | Sent:{e.get('avg_sentiment',0.0):+.2f} | "
            f"Score:{e.get('c3_score')} | KW:{e.get('keyword_score',0.0):.2f}/10"
        )

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
            for i, th in enumerate(e.get("top_headlines",[])[:TOP_N_HEADLINES], start=1):
                headline = th.get("headline","")
                links = th.get("links", [])
                print(f" {i}. {headline} — {len(links)} source(s)")
                if links:
                    best = sorted(links, key=lambda x: x.get("timestamp_ts",0), reverse=True)[0]
                    print(f"    {best.get('url')}")
        else:
            print("\nTop Headlines: (none)")

        print("-"*70)

# ============================
# Section 11: Save outputs (descriptive, timestamped)
# ============================
def save_outputs(entries: List[Dict[str,Any]], watchlist: List[Dict[str,Any]]) -> str:
    ts_label = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(OUT_DIR_BASE, ts_label)
    mkdirp(out_dir)

    # Full scan entries
    full_scan_path = os.path.join(out_dir, f"scan_full_entries_{ts_label}.json")
    with open(full_scan_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    # Watchlist (Ross filtered)
    watchlist_path = os.path.join(out_dir, f"watchlist_ross_top{len(watchlist)}_{ts_label}.json")
    with open(watchlist_path, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, indent=2, ensure_ascii=False)

    logging.info("Saved scan: %s", full_scan_path)
    logging.info("Saved watchlist: %s", watchlist_path)
    return out_dir

# ============================
# Section 12: Orchestrator (single cycle) + CLI
# ============================
def run_cycle(rss_urls: List[str], floats_cache: Dict[str,int], use_ib: bool = True):
    start_ts = now_ts()
    logging.info("Starting cycle at %s", datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat())

    # Step 1: IBKR symbols+metadata (reconnect each cycle)
    if not use_ib:
        logging.warning("IB disabled. Aborting cycle.")
        return

    symbols_meta = fetch_ibkr_symbols_and_metadata(TOP_GAINERS_COUNT, floats_cache)
    if not symbols_meta:
        logging.warning("No symbols returned from IBKR. Aborting cycle.")
        return

    # Step 2: fetch all feeds
    try:
        feeds_map = fetch_all_feeds(rss_urls)
    except Exception as e:
        logging.warning("RSS fetch failed: %s", e)
        feeds_map = {u: [] for u in rss_urls}

    # Step 3: aggregate matches
    now_val = now_ts()
    results_per_symbol, detailed_feed_items = aggregate_matches_with_links(symbols_meta, feeds_map, now_val, max_age_seconds=BUCKET_24H)

    # Step 4: build entries (per symbol)
    entries = build_hot_entries(symbols_meta, results_per_symbol, detailed_feed_items)

    # Step 5: Build watchlist AFTER applying Ross pillars
    watchlist = build_watchlist(entries, top_n=WATCHLIST_TOP_N)

    # =========================
    # PRINT 4 TIMES PER CYCLE
    # =========================
    # 1) Cycle print (legacy style)
    print_cycle_legacy_c3(entries)

    # 2) General printer (no filter, sorted by gap)
    print_general_verbose_sorted_by_gap(entries)

    # 3) Compact/medium printer (filtered top N)
    print_filtered_compact_watchlist(entries, top_n=WATCHLIST_TOP_N)

    # 4) Deep printer (filtered top N, verbose)
    print_filtered_deep_verbose(entries, top_n=WATCHLIST_TOP_N)

    # Step 6: Save outputs (descriptive + timestamped)
    out_dir = save_outputs(entries, watchlist)
    logging.info("Cycle complete. Outputs saved to %s", out_dir)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--no-ib", action="store_true", help="Do not query IBKR (test mode)")
    parser.add_argument("--top", type=int, default=TOP_GAINERS_COUNT, help="IBKR top gainers count (default 50)")
    parser.add_argument("--watch", type=int, default=WATCHLIST_TOP_N, help="Watchlist size (default 10)")
    args = parser.parse_args()

    global TOP_GAINERS_COUNT
    global WATCHLIST_TOP_N
    TOP_GAINERS_COUNT = max(5, int(args.top))
    WATCHLIST_TOP_N = max(5, min(20, int(args.watch)))

    rss_urls = load_verified_rss()
    if not rss_urls:
        logging.error("No RSS feeds loaded; create verified_rss.txt with feed URLs (one per line).")
        return

    floats_cache = load_floats_cache(FLOATS_CACHE_FILE)

    if args.once:
        run_cycle(rss_urls, floats_cache, use_ib=(not args.no_ib))
        return

    try:
        while True:
            run_cycle(rss_urls, floats_cache, use_ib=(not args.no_ib))
            logging.info("Sleeping %d seconds until next cycle...", CYCLE_SLEEP_SECONDS)
            time.sleep(CYCLE_SLEEP_SECONDS)
    except KeyboardInterrupt:
        logging.info("Interrupted by user — exiting.")

if __name__ == "__main__":
    main()
