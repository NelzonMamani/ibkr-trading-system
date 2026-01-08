#!/usr/bin/env python3
"""
scanner.py
Integrated scanner + async hot-news engine
- IBKR reconnect every cycle (random client id)
- Fetch top 50 gainers, metadata, hotwords
- Async RSS fetching with aiohttp (safe exception handling)
- Deduplication, replication, velocity, spike detection
- Compact console print (C3) + detailed JSON outputs
- Full debug prints for tracing
- UTC timestamps
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
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Dict, List, Any, Tuple
from random import randint

# IB
from ib_insync import IB, ScannerSubscription, Stock

# CONFIG
VERIFIED_RSS_FILE = "verified_rss.txt"   # one feed URL per line
CYCLE_SLEEP_SECONDS = 60
TOP_N_HEADLINES = 5
RSS_FETCH_TIMEOUT = 30
RSS_CONCURRENCY = 24
RSS_FETCH_RETRIES = 2
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
OUT_DIR_BASE = "data"
TOP_GAINERS_COUNT = 50  # you chose 50

# Spike detection params
ABSOLUTE_SPIKE_THRESHOLD = 5
SPIKE_RATIO = 2.0

# Age buckets (seconds)
BUCKET_5M = 5 * 60
BUCKET_10M = 10 * 60
BUCKET_60M = 60 * 60
BUCKET_24H = 24 * 3600

# Logging
logging.basicConfig(level=logging.DEBUG, format="[%(levelname)s] %(message)s")
logging.getLogger("aiohttp").setLevel(logging.WARNING)

# ============================
# Section 2: Utilities
# ============================
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

WORD_REGEX = re.compile(r"\b[a-zA-Z0-9]+\b")

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
# Section 4: Load RSS list
# ============================
def load_verified_rss(file_path: str = VERIFIED_RSS_FILE) -> List[str]:
    logging.debug("load_verified_rss() start: %s", file_path)
    p = Path(file_path)
    if not p.exists():
        logging.error("Verified RSS file not found: %s", file_path)
        return []
    with p.open("r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    logging.info("Loaded %d RSS feeds", len(urls))
    logging.debug("load_verified_rss() done")
    return urls

# ============================
# Section 5: Async fetcher (aiohttp) - fixed exceptions & retries
# ============================
async def fetch_single(session: aiohttp.ClientSession, url: str, sem: asyncio.Semaphore) -> Tuple[str, List[Dict[str,Any]]]:
    logging.debug("fetch_single() start: %s", url)
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
                    logging.debug("fetch_single() fetched %d entries from %s", len(normalized), url)
                    return url, normalized
            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                logging.debug("Fetch attempt %d/%d failed for %s: %s", attempt, RSS_FETCH_RETRIES, url, repr(e))
            except Exception as e:
                logging.debug("Fetch unexpected error %s: %s", url, repr(e))
            await asyncio.sleep(backoff_base * (2 ** (attempt - 1)))
    logging.debug("fetch_single() done (no entries): %s", url)
    return url, []

async def fetch_all_feeds_async(rss_urls: List[str]) -> Dict[str, List[Dict[str,Any]]]:
    logging.debug("fetch_all_feeds_async() start: %d urls", len(rss_urls))
    connector = aiohttp.TCPConnector(ssl=False, limit=RSS_CONCURRENCY, limit_per_host=10)
    sem = asyncio.Semaphore(RSS_CONCURRENCY)
    results = {}
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [asyncio.create_task(fetch_single(session, url, sem)) for url in rss_urls]
        responses = await asyncio.gather(*tasks, return_exceptions=False)
        for url, entries in responses:
            results[url] = entries or []
    logging.debug("fetch_all_feeds_async() done")
    return results

def fetch_all_feeds(rss_urls: List[str]) -> Dict[str, List[Dict[str,Any]]]:
    logging.debug("fetch_all_feeds() start")
    if not rss_urls:
        return {}
    try:
        prev_loop = asyncio.get_event_loop()
    except RuntimeError:
        prev_loop = None
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(fetch_all_feeds_async(rss_urls))
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
    logging.debug("fetch_all_feeds() done")
    return results

# ============================
# Section 6: IBKR scanner & metadata (reconnect each cycle)
# ============================
def fetch_ibkr_symbols_and_metadata(number_of_rows: int = TOP_GAINERS_COUNT) -> Dict[str, Dict[str,Any]]:
    logging.debug("fetch_ibkr_symbols_and_metadata() start")
    ib = IB()
    client_id = int(time.time()) % 9999
    try:
        logging.info("Connecting to IBKR with clientId %s", client_id)
        ib.connect('127.0.0.1', 7496, clientId=client_id, timeout=10)
    except Exception as e:
        logging.warning("IB connect failed: %s", e)
        try:
            ib.disconnect()
        except Exception:
            pass
        logging.debug("fetch_ibkr_symbols_and_metadata() failed - returning empty")
        return {}

    metadata = {}
    try:
        scan_sub = ScannerSubscription(
            instrument='STK',
            locationCode='STK.US.MAJOR',
            scanCode='TOP_PERC_GAIN',
            numberOfRows=number_of_rows
        )
        logging.debug("Requesting scanner data for %d rows", number_of_rows)
        scan_data = ib.reqScannerData(scan_sub)
        contracts = [item.contractDetails.contract for item in scan_data]
        logging.debug("IBKR scanner returned %d contracts", len(contracts))
        for contract in contracts:
            sym = getattr(contract, "symbol", None)
            if not sym:
                continue
            # small retry for contract details
            cd = None
            for attempt in range(1, 3):
                try:
                    details = ib.reqContractDetails(contract)
                    if details:
                        cd = details[0]
                        break
                except Exception:
                    time.sleep(0.2)
            metadata[sym] = {
                "symbol": sym,
                "contract": contract,
                "longName": getattr(cd, "longName", "") or getattr(contract, "localSymbol", sym),
                "industry": getattr(cd, "industry", "") or "",
                "category": getattr(cd, "category", "") or "",
                "subcategory": getattr(cd, "subcategory", "") or "",
                "primaryExchange": getattr(contract, "primaryExchange", "") or "",
                "currency": getattr(contract, "currency", "") or "",
            }
    except Exception as e:
        logging.warning("IB scanner error: %s", e)
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass
    logging.debug("fetch_ibkr_symbols_and_metadata() done: %d symbols", len(metadata))
    return metadata

# ============================
# Section 7: Matching, dedupe, replicate counting
# ============================
def normalize_hotword_list(metadata: Dict[str,Any]) -> List[str]:
    candidates = [metadata.get("symbol",""), metadata.get("longName",""), metadata.get("industry",""), metadata.get("category",""), metadata.get("subcategory","")]
    words = []
    for c in candidates:
        if not c:
            continue
        for token in re.split(r"[^A-Za-z0-9]+", str(c)):
            token = token.strip()
            if len(token) >= 2:
                words.append(token)
    return list({w.lower() for w in words})

def aggregate_matches_with_links(hotwords_dict: Dict[str,Dict[str,Any]],
                                 feeds_map: Dict[str,List[Dict[str,Any]]],
                                 now_ts_val: int,
                                 max_age_seconds: int = BUCKET_24H) -> Tuple[Dict[str,Any], List[Dict[str,Any]]]:
    logging.debug("aggregate_matches_with_links() start")
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

    for symbol, meta in hotwords_dict.items():
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
                "regions": []
            }
            continue

        for item in feed_items:
            title = (item["title"] or "").strip()
            summary = (item["summary"] or "").strip()
            link = (item["link"] or "").strip()
            published_ts = item.get("published_ts")
            # age check
            age_ok = True
            if published_ts:
                try:
                    age = now_ts_val - int(published_ts)
                    if age > max_age_seconds:
                        age_ok = False
                except Exception:
                    pass
            if not age_ok:
                continue

            hay = f"{title} {summary}".lower()
            tokens = set(WORD_REGEX.findall(hay))
            matched = False
            for hw in hotwords:
                if hw.lower() in tokens:
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
                "domain_weight": domain_weight_from_url(link)
            }
            matched_links_by_headline[headline_key].append(link_meta)
            detailed_feed_items.append({
                "symbol": symbol,
                "headline": headline_key,
                "link_meta": link_meta
            })

        unique_headlines = len(title_to_sources)
        replicated = total_matches - unique_headlines
        top_headlines = sorted(
            [{"headline": h, "links": matched_links_by_headline[h], "sources": len(title_to_sources[h])} for h in title_to_sources],
            key=lambda x: (x["sources"], max(link["timestamp_ts"] for link in x["links"])),
            reverse=True
        )[:TOP_N_HEADLINES]

        results[symbol] = {
            "metadata": meta,
            "total_headlines": total_matches,
            "unique_headlines": unique_headlines,
            "replicated_headlines": replicated,
            "top_headlines": top_headlines,
            "regions": sorted(regions_detected),
            "hotwords": hotwords
        }
    logging.debug("aggregate_matches_with_links() done")
    return results, detailed_feed_items

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
# Section 8: Build hot list, velocity, spike, scoring & trade suggestion
# ============================
def categorize_age_seconds(age_sec: int) -> Tuple[str,str]:
    if age_sec <= BUCKET_5M:
        return "🔥","0-5m"
    if age_sec <= BUCKET_60M:
        return "🟡","5-60m"
    if age_sec <= BUCKET_24H:
        return "🟢","1-24h"
    return "⚫",">24h"

def trade_suggestion_for_symbol(avg_sent: float, is_spike: bool, heat_5m: int, keyword_score: float, top_sources: List[str]) -> Tuple[str,str]:
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

def build_hot_and_tomorrow(results_per_symbol: Dict[str,Any], detailed_feed_items: List[Dict[str,Any]]) -> Tuple[List[Dict[str,Any]], List[Dict[str,Any]]]:
    logging.debug("build_hot_and_tomorrow() start")
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

    # determine spikes
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

    hot_news = []
    for sym, meta in results_per_symbol.items():
        links_60 = items_60m.get(sym, [])
        links_5 = items_5m.get(sym, [])
        if not links_60:
            # quiet symbol
            avg_sent = 0.0
            top_sources = []
            keyword_score = 0.0
            heat_score = 0
            velocity_10m = counts_10m.get(sym, 0)
            is_spike = False
            badge = "⚫"; bucket = ">24h"; age_min = None
        else:
            min_ts = min(lm["timestamp_ts"] for lm in (links_5 if links_5 else links_60))
            age_min = now - min_ts
            badge, bucket = categorize_age_seconds(age_min)
            wsum = sum(lm.get("sentiment",0.0) * lm.get("domain_weight",0.5) for lm in links_60)
            wtot = sum(lm.get("domain_weight",0.5) for lm in links_60) or 1.0
            avg_sent = (wsum / wtot)
            top_sources = [domain_from_url(lm.get("url","")) for lm in items_24h.get(sym, [])]
            # simple keyword score
            hotwords = meta.get("hotwords", [])
            matches = 0; checks = 0
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
            "symbol": sym,
            "company": meta.get("metadata",{}).get("longName","") if isinstance(meta, dict) else meta.get("longName",""),
            "total_headlines": meta.get("total_headlines",0),
            "unique_headlines": meta.get("unique_headlines",0),
            "replicated_headlines": meta.get("replicated_headlines",0),
            "regions": meta.get("regions",[]),
            "avg_sentiment": round(avg_sent,3),
            "top_sources": list(dict.fromkeys(top_sources))[:5],
            "keyword_score": round(keyword_score,2),
            "heat_score_5m": heat_score,
            "velocity_10m": velocity_10m,
            "is_spike": is_spike,
            "freshness": {"badge": badge, "bucket": bucket, "seconds_old": age_min},
            "top_headlines": meta.get("top_headlines",[]),
            "links_5m": sorted(links_5, key=lambda x: x.get("timestamp_ts",0), reverse=True)[:20],
            "links_60m": sorted(links_60, key=lambda x: x.get("timestamp_ts",0), reverse=True)[:50],
            "trade_suggestion": trade,
            "trade_rationale": rationale
        }
        hot_news.append(entry)

    # sort by spike, heat, velocity, unique headlines
    hot_news.sort(key=lambda x: (not x["is_spike"], -x["heat_score_5m"], -x["velocity_10m"], -x["unique_headlines"]))

    # tomorrow watchlist (24h)
    tomorrow = []
    for sym, meta in results_per_symbol.items():
        total_24 = counts_24h.get(sym, 0)
        if total_24 == 0:
            continue
        regions = meta.get("regions", [])
        sig_score = total_24 + len(regions)*2
        tomorrow.append({
            "symbol": sym,
            "company": meta.get("metadata",{}).get("longName",""),
            "total_headlines_24h": total_24,
            "regions": regions,
            "significance_score": sig_score,
            "top_headlines": meta.get("top_headlines",[]),
            "links_24h": items_24h.get(sym, [])[:50]
        })
    tomorrow.sort(key=lambda x: (-x["significance_score"], -x["total_headlines_24h"]))
    logging.debug("build_hot_and_tomorrow() done")
    return hot_news, tomorrow

# ============================
# Section 9: Console formatter (C3 one-line + top 5 headlines)
# ============================
def print_compact_c3(entries: List[Dict[str,Any]], show_n: int = 50):
    print("\n" + "="*70)
    print("HOT NEWS (compact C3) —", datetime.now(timezone.utc).isoformat())
    print("="*70)
    for e in entries[:show_n]:
        sym = e["symbol"]
        comp = e.get("company","")
        total = e.get("total_headlines",0)
        uniq = e.get("unique_headlines",0)
        dupes = e.get("replicated_headlines",0)
        regions = ", ".join(e.get("regions",[])) if e.get("regions") else "N/A"
        vel = e.get("velocity_10m",0)
        spike = "YES" if e.get("is_spike") else "No"
        sent = e.get("avg_sentiment",0.0)
        kw = e.get("keyword_score",0.0)
        badge = e.get("freshness",{}).get("badge","⚫")
        heat = e.get("heat_score_5m",0)
        score = round((heat * 2) + (e.get("avg_sentiment",0.0) * 5) + (len(e.get("regions",[])) * 0.5), 2)
        trade = e.get("trade_suggestion","Neutral ⚪")
        # one-line C3 block
        print(f"{sym} | {badge} | Vel10m:{vel} | Total:{total} | Spike:{spike} | Sent:{sent:+.2f} | Score:{score} | KW:{kw:.2f}/10")
        print(f"Trade: {trade} — {e.get('trade_rationale')}")
        # top headlines (show up to 5; show best link for each headline)
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
    print("\nTomorrow Watchlist (top 10):")
    print("="*70 + "\n")

# ============================
# Section 10: Save outputs
# ============================
def save_outputs(hot_news: List[Dict[str,Any]], tomorrow_watch: List[Dict[str,Any]], detailed_feed_items: List[Dict[str,Any]], hotwords_dict: Dict[str,Any]):
    ts_label = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(OUT_DIR_BASE, ts_label)
    mkdirp(out_dir)
    with open(os.path.join(out_dir, "hot_news.json"), "w", encoding="utf-8") as f:
        json.dump(hot_news, f, indent=2, ensure_ascii=False)
    with open(os.path.join(out_dir, "tomorrow_watch.json"), "w", encoding="utf-8") as f:
        json.dump(tomorrow_watch, f, indent=2, ensure_ascii=False)
    with open(os.path.join(out_dir, "detailed_feed_dump.json"), "w", encoding="utf-8") as f:
        json.dump(detailed_feed_items, f, indent=2, ensure_ascii=False)
    with open(os.path.join(out_dir, "hotwords.json"), "w", encoding="utf-8") as f:
        json.dump(hotwords_dict, f, indent=2, ensure_ascii=False)
    logging.info("Saved outputs to %s", out_dir)
    return out_dir

# ============================
# Section 11: Orchestrator (single cycle) + CLI
# ============================
def run_cycle(rss_urls: List[str], use_ib: bool = True):
    logging.debug("run_cycle() start")
    start_ts = now_ts()
    logging.info("Starting cycle at %s", datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat())

    # Step 1: IBKR symbols+metadata (reconnect every cycle)
    hotwords_dict = {}
    if use_ib:
        logging.debug("Attempting to fetch IBKR symbols and metadata")
        hotwords_dict = fetch_ibkr_symbols_and_metadata(number_of_rows=TOP_GAINERS_COUNT)
        logging.debug("Fetched %d symbols from IBKR", len(hotwords_dict))
    if not hotwords_dict:
        logging.warning("No symbols metadata returned from IBKR (or IB disabled). Aborting cycle.")
        return

    # Step 2: async fetch all feeds
    try:
        logging.debug("fetch_all_feeds() start")
        feeds_map = fetch_all_feeds(rss_urls)
        logging.debug("fetch_all_feeds() returned feeds for %d sources", len(feeds_map))
    except Exception as e:
        logging.exception("Failed to fetch RSS feeds: %s", e)
        feeds_map = {u: [] for u in rss_urls}

    # Step 3: aggregate matches + detailed items
    now = now_ts()
    results_per_symbol, detailed_feed_items = aggregate_matches_with_links(hotwords_dict, feeds_map, now, max_age_seconds=BUCKET_24H)

    # Step 4: build hot news and tomorrow watchlist
    hot_news, tomorrow_watch = build_hot_and_tomorrow(results_per_symbol, detailed_feed_items)

    # Step 5: print compact C3 for all symbols — include quiet ones
    all_symbols = list(hotwords_dict.keys())
    hot_map = {e["symbol"]: e for e in hot_news}
    full_entries = []
    for sym in all_symbols:
        if sym in hot_map:
            full_entries.append(hot_map[sym])
        else:
            md = results_per_symbol.get(sym, {"metadata":{"longName": sym}, "total_headlines":0, "unique_headlines":0, "replicated_headlines":0, "regions":[]})
            full_entries.append({
                "symbol": sym,
                "company": md.get("metadata",{}).get("longName", sym),
                "total_headlines": md.get("total_headlines",0),
                "unique_headlines": md.get("unique_headlines",0),
                "replicated_headlines": md.get("replicated_headlines",0),
                "regions": md.get("regions",[]),
                "avg_sentiment": 0.0,
                "top_sources": [],
                "keyword_score": 0.0,
                "heat_score_5m": 0,
                "velocity_10m": 0,
                "is_spike": False,
                "freshness": {"badge": "⚫", "bucket": ">24h", "seconds_old": None},
                "top_headlines": [],
                "links_5m": [],
                "links_60m": [],
                "trade_suggestion": "No recent news",
                "trade_rationale": ""
            })
    # sort full_entries by same logic: spike/heat/velocity/unique headlines
    full_entries.sort(key=lambda x: (not x.get("is_spike",False), -x.get("heat_score_5m",0), -x.get("velocity_10m",0), -x.get("unique_headlines",0)))
    print_compact_c3(full_entries, show_n=len(full_entries))

    # Print Tomorrow watchlist summary
    print("Tomorrow Watchlist (top 10):")
    for w in tomorrow_watch[:10]:
        print(f"{w['symbol']} — {w['company']} | {w['total_headlines_24h']} headlines | regions: {', '.join(w['regions'])}")
    logging.debug("Saving outputs")
    out_dir = save_outputs(hot_news, tomorrow_watch, detailed_feed_items, results_per_symbol)
    logging.info("Cycle complete (saved to %s).", out_dir)
    logging.debug("run_cycle() done")

def main():
    logging.debug("Script started")
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--no-ib", action="store_true", help="Do not query IBKR (useful for testing)")
    args = parser.parse_args()

    rss_urls = load_verified_rss()
    if not rss_urls:
        logging.error("No RSS feeds loaded; create verified_rss.txt with feed URLs (one per line).")
        return

    if args.once:
        run_cycle(rss_urls, use_ib=(not args.no_ib))
        return

    try:
        while True:
            run_cycle(rss_urls, use_ib=(not args.no_ib))
            logging.info("Sleeping %d seconds until next cycle...", CYCLE_SLEEP_SECONDS)
            time.sleep(CYCLE_SLEEP_SECONDS)
    except KeyboardInterrupt:
        logging.info("Interrupted by user — exiting.")

if __name__ == "__main__":
    main()
