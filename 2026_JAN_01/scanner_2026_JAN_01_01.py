#!/usr/bin/env python3
"""
scanner.py — Ross Cameron (Warrior Trading) inspired scanner module + standalone script

GOALS (what this script is designed to do)
------------------------------------------
✅ Works as a MODULE in a bigger trading system:
   - import and call run_scan(config) to get structured results (no printing, no sleeping)

✅ Works as a STANDALONE script:
   - runs a loop (or --once)
   - prints 4 times per cycle (debug-friendly, like your original)
   - saves descriptive, timestamped JSON outputs

✅ Educational comments + deliberate redundancy in printing:
   - printing is a “live audit trail” for trading decisions

IMPORTANT NOTE ABOUT FLOAT
--------------------------
IBKR market data does not reliably provide free float. This script supports a local float cache:
  floats_cache.json  -> {"INBS": 8320000, "NUAI": 27400000, ...}

If float is missing, float_category becomes "UNKNOWN".
In Ross 5 Pillars filter v1 below, UNKNOWN float FAILS by default (conservative).
You can relax it later if you want.

PRINTERS (printed 4 times per cycle)
------------------------------------
PRINT #1: Cycle legacy print (feels like your original; sorted by news heat/spike)
PRINT #2: General verbose view (NO 5 pillars filter; sorted by gap desc)
PRINT #3: Filtered compact/medium watchlist (5 pillars filter; sorted by gap desc; one line each)
PRINT #4: Filtered deep verbose view (5 pillars filter; sorted by gap desc; full blocks)

Files saved per cycle (timestamped)
-----------------------------------
- scan_full_entries_<TS>.json
- scan_news_results_per_symbol_<TS>.json
- scan_detailed_feed_dump_<TS>.json
- watchlist_ross_top<N>_<TS>.json
"""

# ============================
# Section 0: Windows asyncio event loop policy fix
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
import aiohttp
import feedparser
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
from typing import Dict, List, Any, Tuple, Optional

# IBKR (ib_insync)
from ib_insync import IB, ScannerSubscription

# ============================
# Section 2: Logging (debug-friendly)
# ============================
LOGGER = logging.getLogger("scanner")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logging.getLogger("aiohttp").setLevel(logging.WARNING)

# ============================
# Section 3: Configuration (data-only)
# ============================
@dataclass(frozen=True)
class RossPillarsConfig:
    """
    Ross Cameron "5 Pillars" thresholds (Version 1).
    Adjust later without touching core logic.
    """
    min_price: float = 2.0          # Ross: prefers >= $2 (avoid ultra-low quality)
    max_price: float = 20.0         # Ross: avoids > $20 (harder to move, less explosive)
    min_gap_percent: float = 5.0    # Ross: wants gappers / strong premarket interest
    min_rvol: float = 2.0           # Ross: wants unusual volume (v1 relaxed; many use 5x)
    max_float: int = 20_000_000     # Ross: prefers low float (supply constraint)

@dataclass(frozen=True)
class ScannerConfig:
    """
    Everything configurable lives here.
    This makes the scanner:
      - reusable as a module
      - stable in a larger trading system
      - easy to test / iterate
    """
    # Inputs
    verified_rss_file: str = "verified_rss.txt"   # one RSS URL per line
    floats_cache_file: str = "floats_cache.json"  # {"SYM": int_float, ...}

    # Execution
    use_ibkr: bool = True
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 7496
    ibkr_top_gainers_count: int = 50

    # RSS
    rss_fetch_timeout: int = 30
    rss_concurrency: int = 24
    rss_fetch_retries: int = 2
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

    # News age windows (seconds)
    bucket_5m: int = 5 * 60
    bucket_10m: int = 10 * 60
    bucket_60m: int = 60 * 60
    bucket_24h: int = 24 * 3600

    # Spike detection (news velocity)
    absolute_spike_threshold: int = 5
    spike_ratio: float = 2.0

    # Output
    out_dir_base: str = "data"
    top_n_headlines: int = 5
    watchlist_top_n: int = 10

    # Ross filter
    ross: RossPillarsConfig = RossPillarsConfig()

    # Cycle behavior (standalone)
    cycle_sleep_seconds: int = 60

# ============================
# Section 4: Utilities (pure helpers)
# ============================
WORD_REGEX = re.compile(r"\b[a-zA-Z0-9]+\b")

def now_ts() -> int:
    return int(time.time())

def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def ts_to_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

def safe_round(x: Optional[float], nd: int = 2) -> Optional[float]:
    try:
        return None if x is None else round(float(x), nd)
    except Exception:
        return None

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

def format_float_shares(raw_float):
    """Formats large integer floats to human-readable K/M/B."""
    if isinstance(raw_float, int):
        if raw_float >= 1_000_000_000:
            return f"{raw_float/1_000_000_000:.2f}B"
        if raw_float >= 1_000_000:
            return f"{raw_float/1_000_000:.2f}M"
        if raw_float >= 1_000:
            return f"{raw_float/1_000:.0f}K"
        return str(raw_float)
    return raw_float

def compute_spread_percent(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    """Bid/ask spread in % terms (helps with tradability / slippage)."""
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
# Section 5: Sentiment + domain weights (simple + educational)
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
    """
    Simple word-count sentiment (educational, not “AI sentiment”).
    Use only as a tie-breaker / context, NOT as a primary trading signal.
    """
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
# Section 6: Local inputs (RSS list, float cache)
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

def load_floats_cache(file_path: str) -> Dict[str, int]:
    """
    Optional float cache: {"SYM": 8320000, ...}
    Float is vital to Ross-style low-float momentum selection.
    """
    p = Path(file_path)
    if not p.exists():
        LOGGER.warning("Float cache not found (%s). Float will be UNKNOWN.", file_path)
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

# ============================
# Section 7: RSS fetching (async) — same style as your original
# ============================
async def fetch_single_feed(
    session: aiohttp.ClientSession,
    url: str,
    sem: asyncio.Semaphore,
    timeout_total: int,
    retries: int,
    user_agent: str
) -> Tuple[str, List[Dict[str, Any]]]:

    headers = {"User-Agent": user_agent}
    timeout = aiohttp.ClientTimeout(total=timeout_total, connect=10, sock_read=timeout_total)
    backoff_base = 0.6

    async with sem:
        for attempt in range(1, retries + 1):
            try:
                async with session.get(url, headers=headers, timeout=timeout) as resp:
                    resp.raise_for_status()
                    raw = await resp.read()
                    parsed = feedparser.parse(raw)
                    entries = parsed.entries or []
                    normalized: List[Dict[str, Any]] = []
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
                LOGGER.debug("Fetch fail attempt %d/%d: %s", attempt, retries, url)
            except Exception:
                LOGGER.debug("Fetch unexpected error: %s", url)

            await asyncio.sleep(backoff_base * (2 ** (attempt - 1)))

    return url, []

async def fetch_all_feeds_async(cfg: ScannerConfig, rss_urls: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    connector = aiohttp.TCPConnector(ssl=False, limit=cfg.rss_concurrency, limit_per_host=10)
    sem = asyncio.Semaphore(cfg.rss_concurrency)
    results: Dict[str, List[Dict[str, Any]]] = {}

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            asyncio.create_task(
                fetch_single_feed(
                    session=session,
                    url=u,
                    sem=sem,
                    timeout_total=cfg.rss_fetch_timeout,
                    retries=cfg.rss_fetch_retries,
                    user_agent=cfg.user_agent
                )
            )
            for u in rss_urls
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=False)
        for url, entries in responses:
            results[url] = entries or []
    return results

def fetch_all_feeds(cfg: ScannerConfig, rss_urls: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Runs the async RSS fetcher in a safe event loop wrapper.
    This matches your original “standalone” style.
    """
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

        if prev_loop is not None:
            try:
                asyncio.set_event_loop(prev_loop)
            except Exception:
                asyncio.set_event_loop(asyncio.new_event_loop())
        else:
            asyncio.set_event_loop(asyncio.new_event_loop())

# ============================
# Section 8: IBKR scanner + enrichment (gap, % change, rvol, spread)
# ============================
def categorize_float(float_shares: Optional[int]) -> str:
    if float_shares is None:
        return "UNKNOWN"
    if float_shares < 20_000_000:
        return "LOW"
    if float_shares < 100_000_000:
        return "MID"
    return "HIGH"

def fetch_ibkr_top_gainers_enriched(
    cfg: ScannerConfig,
    floats_cache: Dict[str, int]
) -> Dict[str, Dict[str, Any]]:
    """
    Fetch top % gainers from IBKR + enrich with market metrics used by Ross-style selection.
    Returns dict keyed by symbol.
    """
    ib = IB()
    client_id = int(time.time()) % 9999  # simple unique-ish id per run

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

    symbols_meta: Dict[str, Dict[str, Any]] = {}
    contracts = []

    try:
        scan_sub = ScannerSubscription(
            instrument="STK",
            locationCode="STK.US.MAJOR",
            scanCode="TOP_PERC_GAIN",
            numberOfRows=cfg.ibkr_top_gainers_count
        )

        LOGGER.info("Requesting IBKR scanner TOP_PERC_GAIN rows=%d", cfg.ibkr_top_gainers_count)
        scan_data = ib.reqScannerData(scan_sub)

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
                "primaryExchange": getattr(contract, "primaryExchange", "") or "",
                "currency": getattr(contract, "currency", "") or "",
            }

        # Request tick data for enrichment
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
                if sym not in symbols_meta:
                    continue

                last_price = getattr(t, "last", None)
                open_price = getattr(t, "open", None)
                prev_close = getattr(t, "prevClose", None)
                volume_today = getattr(t, "volume", None)
                av_volume = getattr(t, "avVolume", None)
                bid = getattr(t, "bid", None)
                ask = getattr(t, "ask", None)

                # % change vs prev close
                percent_change = None
                if prev_close and last_price:
                    percent_change = ((last_price - prev_close) / prev_close) * 100

                # gap % vs prev close
                gap_percent = None
                if prev_close and open_price:
                    gap_percent = ((open_price - prev_close) / prev_close) * 100

                # relative volume (very useful as a “how real is this move?” metric)
                relative_volume = None
                if av_volume and volume_today:
                    try:
                        relative_volume = volume_today / av_volume
                    except Exception:
                        relative_volume = None

                spread_percent = compute_spread_percent(bid, ask)

                # float from cache (optional but crucial to Ross logic)
                float_shares = floats_cache.get(sym)
                float_category = categorize_float(float_shares)

                symbols_meta[sym].update({
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

        LOGGER.info("IBKR enrichment complete. Symbols=%d", len(symbols_meta))
        return symbols_meta

    except Exception as e:
        LOGGER.warning("IB scanner error: %s", e)
        return symbols_meta
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass

# ============================
# Section 9: News aggregation (dedupe, replication, regions, top headlines)
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
    """
    Educational note:
    - This is a very simple matcher.
    - It can be improved later (tickers, synonyms, entity resolution).
    """
    candidates = [
        meta.get("symbol", ""),
        meta.get("longName", ""),
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
    cfg: ScannerConfig,
    symbols_meta: Dict[str, Dict[str, Any]],
    feeds_map: Dict[str, List[Dict[str, Any]]],
    now_ts_val: int
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Returns:
      results_per_symbol: summary news metrics per symbol
      detailed_feed_items: flattened matched link_meta (used for velocity/spike)
    """
    results_per_symbol: Dict[str, Any] = {}
    detailed_feed_items: List[Dict[str, Any]] = []

    # Flatten feed items (makes scanning faster / simpler)
    feed_items = []
    for feed_url, entries in feeds_map.items():
        for e in entries:
            feed_items.append({
                "feed_url": feed_url,
                "title": e.get("title", ""),
                "summary": e.get("summary", ""),
                "link": e.get("link", "") or feed_url,
                "published_ts": e.get("published_ts"),
            })

    for sym, meta in symbols_meta.items():
        hotwords = normalize_hotword_list(meta)

        title_to_sources = defaultdict(set)         # headline -> set(urls)
        matched_links_by_headline = defaultdict(list)
        regions_detected = set()
        total_matches = 0

        if not hotwords:
            results_per_symbol[sym] = {
                "total_headlines": 0,
                "unique_headlines": 0,
                "replicated_headlines": 0,
                "top_headlines": [],
                "regions": [],
                "hotwords": [],
            }
            continue

        for item in feed_items:
            title = (item["title"] or "").strip()
            summary = (item["summary"] or "").strip()
            link = (item["link"] or "").strip()
            published_ts = item.get("published_ts")

            # Age filter — we care about last 24h for momentum context
            if published_ts:
                try:
                    age = now_ts_val - int(published_ts)
                    if age > cfg.bucket_24h:
                        continue
                except Exception:
                    pass

            hay = f"{title} {summary}".lower()
            tokens = set(WORD_REGEX.findall(hay))

            # Simple match: any hotword token appears
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
                "domain_weight": domain_weight_from_url(link),
                "domain": domain_from_url(link),
            }

            matched_links_by_headline[headline_key].append(link_meta)
            detailed_feed_items.append({"symbol": sym, "headline": headline_key, "link_meta": link_meta})

        unique_headlines = len(title_to_sources)
        replicated = max(0, total_matches - unique_headlines)

        # Top headlines ranked by (replication) and recency
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
# Section 10: Velocity / spike / scoring
# ============================
def categorize_age_seconds(cfg: ScannerConfig, age_sec: int) -> Tuple[str, str]:
    if age_sec <= cfg.bucket_5m:
        return "🔥", "0-5m"
    if age_sec <= cfg.bucket_60m:
        return "🟡", "5-60m"
    if age_sec <= cfg.bucket_24h:
        return "🟢", "1-24h"
    return "⚫", ">24h"

def trade_suggestion_for_symbol(avg_sent: float, is_spike: bool, heat_5m: int, keyword_score: float, top_domains: List[str]) -> Tuple[str, str]:
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

    # This is NOT a trading bot — just a human-readable hint
    if is_spike and avg_sent >= 0.25:
        return "Consider Long 🚀", rationale
    if is_spike and avg_sent <= -0.25:
        return "Consider Short 🛑", rationale
    if heat_5m >= 2 and avg_sent > 0.1:
        return "Watch (Long) 👀", rationale
    if heat_5m >= 2 and avg_sent < -0.1:
        return "Watch (Short) 👀", rationale
    return "Neutral ⚪", rationale

def build_entries(
    cfg: ScannerConfig,
    symbols_meta: Dict[str, Dict[str, Any]],
    results_per_symbol: Dict[str, Any],
    detailed_feed_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Build one unified 'entry' dict per symbol, combining:
    - market enrichment (gap, rvol, float, price)
    - news awareness (unique, replicated, regions)
    - velocity and spike flags
    """
    now = now_ts()

    # Count news items by time window
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
        ts = lm.get("timestamp_ts") or now
        age = now - int(ts)

        if age <= cfg.bucket_5m:
            counts_5m[sym] += 1
            items_5m[sym].append(lm)
        if age <= cfg.bucket_10m:
            counts_10m[sym] += 1
            items_10m[sym].append(lm)
        if age <= cfg.bucket_60m:
            counts_60m[sym] += 1
            items_60m[sym].append(lm)
        if age <= cfg.bucket_24h:
            counts_24h[sym] += 1
            items_24h[sym].append(lm)

    # Spike detection (5-minute window)
    hot_symbols = set()
    if counts_5m:
        most = counts_5m.most_common()
        second_count = most[1][1] if len(most) > 1 else 0

        for sym, cnt in counts_5m.items():
            if cnt >= cfg.absolute_spike_threshold:
                hot_symbols.add(sym)
            elif second_count == 0 and cnt >= 2:
                hot_symbols.add(sym)
            elif second_count > 0 and cnt >= cfg.spike_ratio * second_count and cnt >= 2:
                hot_symbols.add(sym)

    entries: List[Dict[str, Any]] = []

    for sym, meta in symbols_meta.items():
        news = results_per_symbol.get(sym, {})
        links_60 = items_60m.get(sym, [])
        links_5 = items_5m.get(sym, [])

        if links_60:
            min_ts = min(lm["timestamp_ts"] for lm in (links_5 if links_5 else links_60))
            age_min = now - min_ts
            badge, bucket = categorize_age_seconds(cfg, age_min)

            wsum = sum(lm.get("sentiment", 0.0) * lm.get("domain_weight", 0.5) for lm in links_60)
            wtot = sum(lm.get("domain_weight", 0.5) for lm in links_60) or 1.0
            avg_sent = wsum / wtot

            top_domains = [lm.get("domain", "") for lm in items_24h.get(sym, [])]
            top_domains = list(dict.fromkeys(top_domains))[:10]

            # Keyword score (simple)
            hotwords = news.get("hotwords", [])
            matches, checks = 0, 0
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
            keyword_score = 0.0
            heat_5m = 0
            velocity_10m = 0
            is_spike = False
            trade, rationale = "No recent news", ""

        # C3 score (kept close to your original style)
        c3_score = round((heat_5m * 2) + (avg_sent * 5) + (len(news.get("regions", [])) * 0.5), 2)

        entries.append({
            # identity
            "symbol": sym,
            "company": meta.get("longName", ""),

            # market data (Ross pillars core data)
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
            "total_headlines": news.get("total_headlines", 0),
            "unique_headlines": news.get("unique_headlines", 0),
            "replicated_headlines": news.get("replicated_headlines", 0),
            "regions": news.get("regions", []),
            "top_headlines": news.get("top_headlines", []),

            # news velocity/scoring
            "avg_sentiment": round(avg_sent, 3),
            "keyword_score": round(keyword_score, 2),
            "heat_score_5m": heat_5m,
            "velocity_10m": velocity_10m,
            "is_spike": is_spike,
            "freshness": {"badge": badge, "bucket": bucket, "seconds_old": age_min},

            # human hint
            "trade_suggestion": trade,
            "trade_rationale": rationale,

            # your existing score concept
            "c3_score": c3_score,
        })

    return entries

# ============================
# Section 11: Ross filter + watchlist builder
# ============================
def passes_ross_five_pillars(cfg: ScannerConfig, e: Dict[str, Any]) -> bool:
    """
    Ross v1 hard filter (conservative).
    You can relax it later once the system is stable.

    Pillars (and how we print/compute them):
    1) RVOL threshold        -> e["relative_volume"]
    2) Daily % change / gap  -> e["gap_percent"] (primary for gappers)
    3) News catalyst         -> e["total_headlines"] > 0  (proxy for news presence)
    4) Price range $2-$20    -> e["last_price"]
    5) Low float             -> e["float_shares"] <= max_float
    """
    ross = cfg.ross
    price = e.get("last_price")
    gap = e.get("gap_percent") or 0.0
    rvol = e.get("relative_volume") or 0.0
    flt = e.get("float_shares")

    # Conservative v1: missing float => FAIL
    if flt is None:
        return False

    has_news = (e.get("total_headlines", 0) > 0)

    return (
        price is not None and ross.min_price <= price <= ross.max_price and
        gap >= ross.min_gap_percent and
        rvol >= ross.min_rvol and
        flt <= ross.max_float and
        (has_news or rvol >= 5.0)  # allow very abnormal RVOL to substitute for news in v1
    )

def sort_by_gap_then_change(e: Dict[str, Any]) -> Tuple[float, float]:
    """
    Sorting contract (as agreed):
    1) Gap % (desc)
    2) Daily % change (desc)
    """
    return (-(e.get("gap_percent") or 0), -(e.get("percent_change") or 0))

def build_watchlist(cfg: ScannerConfig, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    qualified = [e for e in entries if passes_ross_five_pillars(cfg, e)]
    qualified_sorted = sorted(qualified, key=sort_by_gap_then_change)
    return qualified_sorted[:cfg.watchlist_top_n]

# ============================
# Section 12: PRINTERS (print-only; deliberately redundant for debugging)
# ============================
def print_cycle_legacy(entries: List[Dict[str, Any]]):
    """
    PRINT #1 — cycle legacy print “as it was”
    - No Ross filter
    - Sorted by: spike -> heat -> velocity -> unique headlines
    """
    print("\n" + "=" * 70)
    print("HOT NEWS (cycle legacy C3) —", utc_iso_now())
    print("=" * 70)

    entries_sorted = sorted(
        entries,
        key=lambda x: (
            not x.get("is_spike", False),
            -x.get("heat_score_5m", 0),
            -x.get("velocity_10m", 0),
            -x.get("unique_headlines", 0),
        )
    )

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
            for i, th in enumerate(e.get("top_headlines", [])[:5], start=1):
                headline = th.get("headline", "")
                links = th.get("links", [])[:5]
                print(f" {i}. {headline} — {len(links)} source(s)")
                if links:
                    best = sorted(links, key=lambda x: x.get("timestamp_ts", 0), reverse=True)[0]
                    print(f"    {best.get('url')}")
        else:
            print("Top Headlines: (none)")
        print("-" * 70)

def print_ross_line(e: Dict[str, Any]):
    """
    Your agreed Ross “one-line” display (includes awareness):
    INBS | 🔥 | Gap... | RVOL... | Float... | Price... | Total Articles... | Unique... | Vel10m... | Sent... | Score... | Region Count...
    """
    sym = e.get("symbol", "")
    fire = "🔥" if e.get("is_spike", False) else " "
    float_fmt = format_float_shares(e.get("float_shares"))
    regions = e.get("regions", [])
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
        f"Region Count: {len(regions)}"
    )

def print_general_verbose(cfg: ScannerConfig, entries: List[Dict[str, Any]]):
    """
    PRINT #2 — General verbose view
    - NO Ross filter
    - Sorted by gap desc then % change desc
    - Prints full blocks (easy debugging)
    """
    print("\n" + "=" * 70)
    print("GENERAL VIEW (no filter) — sorted by GAP desc —", utc_iso_now())
    print("=" * 70)

    entries_sorted = sorted(entries, key=sort_by_gap_then_change)

    for e in entries_sorted:
        print_ross_line(e)

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
            for i, th in enumerate(e.get("top_headlines", [])[:cfg.top_n_headlines], start=1):
                headline = th.get("headline", "")
                links = th.get("links", [])
                print(f" {i}. {headline} — {len(links)} source(s)")
                if links:
                    best = sorted(links, key=lambda x: x.get("timestamp_ts", 0), reverse=True)[0]
                    print(f"    {best.get('url')}")
        else:
            print("\nTop Headlines: (none)")

        print("-" * 70)

def print_filtered_compact(cfg: ScannerConfig, entries: List[Dict[str, Any]]):
    """
    PRINT #3 — Filtered compact watchlist (Ross 5 Pillars applied)
    - Sorted by gap desc then % change desc
    - One line per symbol (your Ross line)
    """
    filtered = [e for e in entries if passes_ross_five_pillars(cfg, e)]
    filtered_sorted = sorted(filtered, key=sort_by_gap_then_change)[:cfg.watchlist_top_n]

    print("\n" + "=" * 70)
    print(f"ROSS WATCHLIST (filtered) — TOP {cfg.watchlist_top_n} — sorted by GAP desc —", utc_iso_now())
    print("=" * 70)

    if not filtered_sorted:
        print("No symbols passed Ross 5 pillars (v1).")
        print("=" * 70)
        return

    for e in filtered_sorted:
        print_ross_line(e)

    print("=" * 70)

def print_filtered_deep(cfg: ScannerConfig, entries: List[Dict[str, Any]]):
    """
    PRINT #4 — Filtered deep view (Ross 5 Pillars applied)
    - Sorted by gap desc then % change desc
    - Full verbose blocks for top N
    """
    filtered = [e for e in entries if passes_ross_five_pillars(cfg, e)]
    filtered_sorted = sorted(filtered, key=sort_by_gap_then_change)[:cfg.watchlist_top_n]

    print("\n" + "=" * 70)
    print(f"DEEP VIEW (filtered) — TOP {cfg.watchlist_top_n} —", utc_iso_now())
    print("=" * 70)

    if not filtered_sorted:
        print("No symbols passed Ross 5 pillars (v1).")
        print("=" * 70)
        return

    for e in filtered_sorted:
        print_ross_line(e)

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
            for i, th in enumerate(e.get("top_headlines", [])[:cfg.top_n_headlines], start=1):
                headline = th.get("headline", "")
                links = th.get("links", [])
                print(f" {i}. {headline} — {len(links)} source(s)")
                if links:
                    best = sorted(links, key=lambda x: x.get("timestamp_ts", 0), reverse=True)[0]
                    print(f"    {best.get('url')}")
        else:
            print("\nTop Headlines: (none)")

        print("-" * 70)

# ============================
# Section 13: Saving outputs (descriptive + timestamped)
# ============================
def save_outputs(cfg: ScannerConfig, results: Dict[str, Any]) -> str:
    ts_label = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(cfg.out_dir_base, ts_label)
    mkdirp(out_dir)

    entries = results["entries"]
    watchlist = results["watchlist"]
    results_per_symbol = results["news_results_per_symbol"]
    detailed_feed_items = results["detailed_feed_items"]

    # Full scan entries
    path_entries = os.path.join(out_dir, f"scan_full_entries_{ts_label}.json")
    with open(path_entries, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    # News per symbol (debugging)
    path_news = os.path.join(out_dir, f"scan_news_results_per_symbol_{ts_label}.json")
    with open(path_news, "w", encoding="utf-8") as f:
        json.dump(results_per_symbol, f, indent=2, ensure_ascii=False)

    # Detailed feed dump (debugging velocity/spike)
    path_dump = os.path.join(out_dir, f"scan_detailed_feed_dump_{ts_label}.json")
    with open(path_dump, "w", encoding="utf-8") as f:
        json.dump(detailed_feed_items, f, indent=2, ensure_ascii=False)

    # Watchlist
    path_watch = os.path.join(out_dir, f"watchlist_ross_top{len(watchlist)}_{ts_label}.json")
    with open(path_watch, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, indent=2, ensure_ascii=False)

    LOGGER.info("Saved outputs to %s", out_dir)
    LOGGER.info(" - %s", path_entries)
    LOGGER.info(" - %s", path_news)
    LOGGER.info(" - %s", path_dump)
    LOGGER.info(" - %s", path_watch)

    return out_dir

# ============================
# Section 14: SCANNER ENGINE (module-friendly; NO prints; NO sleep)
# ============================
def run_scan(cfg: ScannerConfig) -> Dict[str, Any]:
    """
    Core scanner engine.
    This is what your larger trading system should call.

    RETURNS a structured dict with everything needed:
      - entries (all symbols)
      - watchlist (Ross filtered top N)
      - raw news structures (debugging, future scoring)
    """
    # Load inputs (RSS list and float cache)
    rss_urls = load_verified_rss(cfg.verified_rss_file)
    floats_cache = load_floats_cache(cfg.floats_cache_file)

    if not rss_urls:
        raise RuntimeError("No RSS feeds loaded. Check verified_rss.txt path.")

    if not cfg.use_ibkr:
        raise RuntimeError("IBKR disabled (use_ibkr=False).")

    # 1) IBKR scan + market enrichment
    symbols_meta = fetch_ibkr_top_gainers_enriched(cfg, floats_cache)
    if not symbols_meta:
        raise RuntimeError("No symbols returned from IBKR scanner.")

    # 2) RSS fetch
    feeds_map = fetch_all_feeds(cfg, rss_urls)

    # 3) Aggregate news matches
    now_val = now_ts()
    results_per_symbol, detailed_feed_items = aggregate_matches_with_links(cfg, symbols_meta, feeds_map, now_val)

    # 4) Build unified entries
    entries = build_entries(cfg, symbols_meta, results_per_symbol, detailed_feed_items)

    # 5) Build watchlist (Ross filtered)
    watchlist = build_watchlist(cfg, entries)

    return {
        "timestamp": utc_iso_now(),
        "entries": entries,
        "watchlist": watchlist,
        "news_results_per_symbol": results_per_symbol,
        "detailed_feed_items": detailed_feed_items,
    }

# ============================
# Section 15: ORCHESTRATOR (one cycle; prints 4 times; saves files)
# ============================
def run_cycle(cfg: ScannerConfig) -> None:
    """
    Runs exactly ONE cycle in standalone mode:
    - calls run_scan (engine)
    - prints 4 times
    - saves outputs
    """
    print("\n" + "=" * 70)
    print("STARTING SCAN CYCLE —", utc_iso_now())
    print("=" * 70)

    try:
        results = run_scan(cfg)
    except Exception as e:
        LOGGER.error("Cycle failed: %s", e)
        return

    entries = results["entries"]

    # PRINT 1 — cycle legacy style
    print_cycle_legacy(entries)

    # PRINT 2 — general verbose (no filter)
    print_general_verbose(cfg, entries)

    # PRINT 3 — filtered compact watchlist
    print_filtered_compact(cfg, entries)

    # PRINT 4 — filtered deep view
    print_filtered_deep(cfg, entries)

    # Save
    out_dir = save_outputs(cfg, results)
    print("\n" + "=" * 70)
    print("CYCLE COMPLETE — saved to:", out_dir)
    print("=" * 70)

# ============================
# Section 16: CLI / main loop (standalone)
# ============================
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ross-style scanner (module + standalone).")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--no-ib", action="store_true", help="Disable IBKR (will error if you try to run)")
    parser.add_argument("--top", type=int, default=50, help="IBKR top gainers count (default 50)")
    parser.add_argument("--watch", type=int, default=10, help="Watchlist size (default 10)")
    parser.add_argument("--sleep", type=int, default=60, help="Seconds between cycles (default 60)")

    parser.add_argument("--rss-file", type=str, default="verified_rss.txt", help="RSS list file path")
    parser.add_argument("--float-cache", type=str, default="floats_cache.json", help="Float cache JSON path")
    parser.add_argument("--out-dir", type=str, default="data", help="Output directory base")

    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Build config safely (no globals)
    cfg = ScannerConfig(
        verified_rss_file=args.rss_file,
        floats_cache_file=args.float_cache,
        out_dir_base=args.out_dir,
        use_ibkr=(not args.no_ib),
        ibkr_top_gainers_count=max(5, int(args.top)),
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
