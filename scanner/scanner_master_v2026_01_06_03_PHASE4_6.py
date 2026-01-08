#!/usr/bin/env python3
"""
MASTER SCANNER — General / Canonical Printer + Scoring + Ross Pillars + Sniper Printer
Version: v2026-01-06-03 (Phase 4–6)

What you get:
- MASTER PRINTER: prints all canonical fields per symbol (debug-first)
- Phase 4: Composite momentum scoring (transparent weights + breakdown)
- Phase 5: Ross 5-Pillars Printer (watchlist)
- Phase 6: Sniper Printer (Ross filters + news-dominant selection, top 10)

Sorting:
- MASTER PRINTER: sorted by % change from prior close (descending)
- Ross & Sniper printers: sorted by composite score (descending) by default, but can be changed

Notes:
- News truth is currently a safe stub. Wire your async RSS engine later inside get_news_truth().
- Terminal "clickable" links depend on terminal; we print Title + URL.
"""

from ib_insync import *
from datetime import datetime, timezone
import time
import math
from typing import Dict, Any, List, Optional

# ============================================================
# Canonical Field Order (freeze)
# ============================================================

CANONICAL_FIELDS_54 = [
    # --- Header / identity ---
    "momentum_fire_indicator",
    "symbol",
    "market_session_label",
    "sort_rank_by_gap_desc",

    # --- Price truth ---
    "previous_close_price",
    "session_open_price",
    "overnight_gap_percentage",
    "last_trade_price",
    "current_percentage_change_from_prior_close",

    # --- L1 / microstructure ---
    "bid_price",
    "ask_price",
    "bid_ask_spread",
    "mid_price",

    # --- Reference intraday ---
    "vwap_price",
    "day_high_price",
    "day_low_price",
    "intraday_range_percentage",

    # --- Price metadata ---
    "price_data_type_label",
    "price_truth_source_label",
    "daily_bars_count",

    # --- Float truth ---
    "float_shares_raw",
    "float_shares_formatted",
    "float_category",
    "float_shares_source",
    "float_cache_hit",

    # --- Volume truth ---
    "current_intraday_volume",
    "current_volume_source_label",
    "average_daily_volume_20d",
    "average_daily_volume_window_days",
    "relative_volume",
    "relative_volume_category",
    "volume_velocity_5m",
    "volume_velocity_15m",
    "volume_data_quality_flag",

    # --- News truth ---
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
    "news_top_headlines_list",  # list of {title,url,source,age_min,region}

    # --- Composite scoring / triage ---
    "composite_momentum_score",
    "score_components_breakdown",
    "attention_tier",
    "trade_suggestion_label",
    "trade_suggestion_rationale",
]

# ============================================================
# Helpers
# ============================================================

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()

def safe_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None

def safe_round(x, n=2) -> Optional[float]:
    f = safe_float(x)
    if f is None:
        return None
    return round(f, n)

def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))

def format_float_shares(n) -> str:
    if not isinstance(n, (int, float)) or n is None:
        return "N/A"
    n = float(n)
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(int(n))

def float_category_from_shares(float_shares: Optional[int]) -> str:
    if not isinstance(float_shares, int) or float_shares <= 0:
        return "UNKNOWN"
    if float_shares < 10_000_000:
        return "MICRO_FLOAT"
    if float_shares < 50_000_000:
        return "LOW_FLOAT"
    if float_shares < 150_000_000:
        return "MID_FLOAT"
    return "HIGH_FLOAT"

def rvol_category(rvol: Optional[float]) -> str:
    if rvol is None:
        return "N/A"
    if rvol >= 5:
        return "EXTREME"
    if rvol >= 2:
        return "HIGH"
    if rvol >= 1:
        return "NORMAL"
    return "LOW"

def compute_bid_ask_fields(bid: Optional[float], ask: Optional[float]):
    if bid is None or ask is None:
        return None, None, None
    spread = ask - bid
    mid = (ask + bid) / 2.0
    return safe_round(spread, 6), safe_round(mid, 6), spread

# ============================================================
# Phase 1A — Live Price Truth (IBKR)
# ============================================================

def get_price_truth(ib: IB, contract: Contract) -> Dict[str, Any]:
    out = {
        "previous_close_price": None,
        "session_open_price": None,
        "overnight_gap_percentage": None,
        "last_trade_price": None,
        "current_percentage_change_from_prior_close": None,

        "bid_price": None,
        "ask_price": None,
        "bid_ask_spread": None,
        "mid_price": None,

        "vwap_price": None,
        "day_high_price": None,
        "day_low_price": None,
        "intraday_range_percentage": None,

        "price_data_type_label": "DELAYED",
        "price_truth_source_label": "SNAPSHOT",
        "daily_bars_count": 0,
    }

    # Daily bars (prev close + open)
    try:
        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr="2 D",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1
        )
        out["daily_bars_count"] = len(bars)
        if len(bars) >= 2:
            prev_close = bars[-2].close
            open_px = bars[-1].open
            out["previous_close_price"] = prev_close
            out["session_open_price"] = open_px
            if prev_close and prev_close != 0:
                out["overnight_gap_percentage"] = safe_round(((open_px - prev_close) / prev_close) * 100, 2)
    except Exception:
        pass

    # Live snapshot (last/bid/ask)
    try:
        t = ib.reqMktData(contract, "", False, False)
        ib.sleep(0.45)

        last_px = t.last
        bid = t.bid
        ask = t.ask

        out["last_trade_price"] = last_px
        out["bid_price"] = bid
        out["ask_price"] = ask

        spread_rounded, mid_rounded, spread_raw = compute_bid_ask_fields(bid, ask)
        out["bid_ask_spread"] = spread_rounded
        out["mid_price"] = mid_rounded

        # Derived % change (the one you want as primary)
        prev_close = out["previous_close_price"]
        if prev_close and prev_close != 0 and last_px is not None:
            out["current_percentage_change_from_prior_close"] = safe_round(((last_px - prev_close) / prev_close) * 100, 2)

        # Data type label
        # In IBKR, 1=REALTIME, 2=FROZEN, 3=DELAYED, 4=DELAYED_FROZEN (general concept)
        # ib_insync exposes ticker.marketDataType sometimes; if missing, keep default.
        try:
            mdt = getattr(t, "marketDataType", None)
            if mdt == 1:
                out["price_data_type_label"] = "REALTIME"
            elif mdt == 2:
                out["price_data_type_label"] = "FROZEN"
            elif mdt == 3:
                out["price_data_type_label"] = "DELAYED"
            elif mdt == 4:
                out["price_data_type_label"] = "DELAYED_FROZEN"
        except Exception:
            pass

    except Exception:
        pass

    return out

# ============================================================
# Phase 2 — Float Truth (placeholder wiring point)
# ============================================================

def get_float_truth(contract: Contract) -> Dict[str, Any]:
    """
    This is intentionally a minimal stub.
    Wire your real float unification (IBKR/Yahoo/Finviz + cache) here if needed.
    """
    # If you already have your float cache logic in another file, transplant it here.
    return {
        "float_shares_raw": None,
        "float_shares_formatted": "N/A",
        "float_category": "UNKNOWN",
        "float_shares_source": "Unavailable",
        "float_cache_hit": False
    }

# ============================================================
# Phase 2A — Live Volume Truth (intraday vol + velocities)
# ============================================================

def get_volume_truth(ib: IB, contract: Contract) -> Dict[str, Any]:
    out = {
        "current_intraday_volume": None,
        "current_volume_source_label": "N/A",
        "average_daily_volume_20d": None,
        "average_daily_volume_window_days": 20,
        "relative_volume": None,
        "relative_volume_category": "N/A",
        "volume_velocity_5m": None,
        "volume_velocity_15m": None,
        "volume_data_quality_flag": "PARTIAL",
    }

    # Live volume from ticker
    try:
        t = ib.reqMktData(contract, "", False, False)
        ib.sleep(0.45)
        vol = getattr(t, "volume", None)
        if vol is not None:
            out["current_intraday_volume"] = int(vol)
            out["current_volume_source_label"] = "LIVE_STREAM"
    except Exception:
        pass

    # Average daily volume 20d + velocities using 5m bars (best-effort)
    try:
        daily = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr="20 D",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1
        )
        if daily:
            avg20 = sum(b.volume for b in daily) / len(daily)
            out["average_daily_volume_20d"] = int(avg20) if avg20 is not None else None
    except Exception:
        pass

    # RVOL = current volume / avg 20d volume (simple, day-level approximation)
    try:
        if out["current_intraday_volume"] is not None and out["average_daily_volume_20d"] not in (None, 0):
            out["relative_volume"] = safe_round(out["current_intraday_volume"] / out["average_daily_volume_20d"], 2)
            out["relative_volume_category"] = rvol_category(out["relative_volume"])
    except Exception:
        pass

    # Velocities: sum last N 1-min or 5-min bars (we use 5-min bars for reliability)
    try:
        bars_5m = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr="1 D",
            barSizeSetting="5 mins",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1
        )
        if bars_5m:
            last_1 = bars_5m[-1:]
            last_3 = bars_5m[-3:]  # ~15 min
            out["volume_velocity_5m"] = int(sum(b.volume for b in last_1))
            out["volume_velocity_15m"] = int(sum(b.volume for b in last_3))
            out["volume_data_quality_flag"] = "OK_DELAYED"
    except Exception:
        # Keep PARTIAL if fails
        pass

    return out

# ============================================================
# Phase 3A/3B/3C — News Truth (safe stub + time distribution fields)
# ============================================================

NEWS_TIME_BUCKETS = [
    ("news_bucket_0_1m", 0, 1),
    ("news_bucket_1_5m", 1, 5),
    ("news_bucket_5_10m", 5, 10),
    ("news_bucket_10_20m", 10, 20),
    ("news_bucket_20_30m", 20, 30),
    ("news_bucket_30_60m", 30, 60),
    ("news_bucket_1_5h", 60, 300),
    ("news_bucket_5_10h", 300, 600),
    ("news_bucket_10_24h", 600, 1440),
    ("news_bucket_24_48h", 1440, 2880),
    ("news_bucket_over_48h", 2880, 10**9),
]

def blank_news_distribution() -> Dict[str, int]:
    return {k: 0 for (k, _, __) in NEWS_TIME_BUCKETS}

def get_news_truth(symbol: str) -> Dict[str, Any]:
    """
    Safe placeholder news truth.
    Replace this body with your real hot-news engine integration later.

    Required contract:
      - news_top_headlines_list: list of dicts with keys:
          title, url, source, age_min, region
    """
    dist = blank_news_distribution()
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

        # Phase 3B fields (time distribution)
        **dist,
    }

# ============================================================
# Phase 4 — Composite Momentum Scoring (transparent model)
# ============================================================

SCORING_WEIGHTS = {
    # Price strength (you explicitly prefer % change vs prior close)
    "pct_change": 0.35,

    # RVOL / volume confirmation
    "rvol": 0.20,
    "vol_velocity": 0.10,

    # Float (lower float tends to move faster; Ross-style)
    "float": 0.10,

    # News presence (for now stub -> score will be 0 until wired)
    "news": 0.25,
}

def score_pct_change(pct: Optional[float]) -> float:
    """
    Map % change into 0..1 using a saturating curve.
    - 0% => 0.00
    - 10% => ~0.33
    - 20% => ~0.55
    - 40% => ~0.80
    - 60%+ => approaches 1.00
    """
    if pct is None:
        return 0.0
    x = max(0.0, pct)
    return clamp01(1.0 - math.exp(-x / 25.0))

def score_rvol(rvol: Optional[float]) -> float:
    """
    RVOL score:
    - 1.0 => ~0.30
    - 2.0 => ~0.55
    - 5.0 => ~0.85
    - 8.0+ => ~0.95
    """
    if rvol is None:
        return 0.0
    x = max(0.0, rvol)
    return clamp01(1.0 - math.exp(-x / 2.5))

def score_velocity(v5: Optional[int], v15: Optional[int], avg20: Optional[int]) -> float:
    """
    A simple “pressure” proxy: compare recent 15m volume vs average daily volume.
    This is crude but stable, and we keep it in 0..1.
    """
    if v15 is None or avg20 in (None, 0):
        return 0.0
    ratio = v15 / float(avg20)  # fraction of a full average day traded in 15m
    # 0.5% of ADV in 15m => modest; 2%+ => strong
    return clamp01(1.0 - math.exp(-ratio / 0.02))

def score_float(float_shares_raw: Optional[int]) -> float:
    """
    Lower float => higher score.
    MICRO (<10M): 1.00
    LOW (10–50M): 0.70
    MID (50–150M): 0.40
    HIGH (150M+): 0.20
    UNKNOWN: 0.25 (neutral-low)
    """
    if not isinstance(float_shares_raw, int) or float_shares_raw <= 0:
        return 0.25
    c = float_category_from_shares(float_shares_raw)
    return {
        "MICRO_FLOAT": 1.00,
        "LOW_FLOAT": 0.70,
        "MID_FLOAT": 0.40,
        "HIGH_FLOAT": 0.20
    }.get(c, 0.25)

def score_news(news_total: int, vel10: int, vel60: int, region_count: int, freshest_age: Optional[float]) -> float:
    """
    News score focuses on:
    - total count (log-scaled)
    - velocity in 10m / 60m (log-scaled)
    - region diversity
    - freshness bonus

    NOTE: With stub news, this returns 0.
    """
    if not news_total and not vel10 and not vel60 and not region_count:
        return 0.0

    # Log scalers
    def log_norm(v, k):
        return clamp01(math.log(1 + max(0, v)) / math.log(1 + k))

    total_s = log_norm(news_total, 50)   # saturate ~50
    v10_s   = log_norm(vel10, 20)       # saturate ~20
    v60_s   = log_norm(vel60, 60)       # saturate ~60
    reg_s   = clamp01(region_count / 8.0)

    fresh_bonus = 0.0
    if freshest_age is not None:
        # 0 min => +0.20, 60 min => ~+0.05, 6h => ~+0.0
        fresh_bonus = clamp01(0.20 * math.exp(-freshest_age / 60.0))

    base = (0.35 * total_s) + (0.30 * v10_s) + (0.20 * v60_s) + (0.15 * reg_s)
    return clamp01(base + fresh_bonus)

def compute_composite_score(entry: Dict[str, Any]) -> Dict[str, Any]:
    pct = safe_float(entry.get("current_percentage_change_from_prior_close"))
    rvol = safe_float(entry.get("relative_volume"))
    v5 = entry.get("volume_velocity_5m")
    v15 = entry.get("volume_velocity_15m")
    avg20 = entry.get("average_daily_volume_20d")
    float_raw = entry.get("float_shares_raw")

    news_total = int(entry.get("news_total_headlines") or 0)
    vel10 = int(entry.get("news_velocity_10m") or 0)
    vel60 = int(entry.get("news_velocity_60m") or 0)
    region_count = int(entry.get("news_region_count") or 0)
    freshest_age = safe_float(entry.get("news_freshest_age_minutes"))

    s_pct = score_pct_change(pct)
    s_rvol = score_rvol(rvol)
    s_vel = score_velocity(v5, v15, avg20)
    s_float = score_float(float_raw)
    s_news = score_news(news_total, vel10, vel60, region_count, freshest_age)

    total = (
        SCORING_WEIGHTS["pct_change"] * s_pct +
        SCORING_WEIGHTS["rvol"] * s_rvol +
        SCORING_WEIGHTS["vol_velocity"] * s_vel +
        SCORING_WEIGHTS["float"] * s_float +
        SCORING_WEIGHTS["news"] * s_news
    )

    breakdown = {
        "scores_0to1": {
            "pct_change": round(s_pct, 4),
            "rvol": round(s_rvol, 4),
            "vol_velocity": round(s_vel, 4),
            "float": round(s_float, 4),
            "news": round(s_news, 4),
        },
        "weights": SCORING_WEIGHTS,
        "weighted_total_0to1": round(total, 4),
    }

    # Convert to 0..100 for human readability
    score_100 = round(total * 100.0, 2)

    # Tiers
    if score_100 >= 75:
        tier = "A+"
    elif score_100 >= 60:
        tier = "A"
    elif score_100 >= 45:
        tier = "B"
    elif score_100 >= 30:
        tier = "C"
    else:
        tier = "D"

    return {
        "composite_momentum_score": score_100,
        "score_components_breakdown": breakdown,
        "attention_tier": tier,
        "trade_suggestion_label": None,
        "trade_suggestion_rationale": None,
    }

# ============================================================
# Phase 5 — Ross 5 Pillars Filters (practical proxy)
# ============================================================

def ross_5_pillars_pass(entry: Dict[str, Any]) -> (bool, List[str]):
    """
    Ross Cameron style screen (practical proxy, adjustable):
      1) Price between 2 and 20
      2) Float <= 50M (low float)
      3) % change >= 10% (momentum)
      4) RVOL >= 2
      5) Has news presence (total > 0) [placeholder until news is wired]

    Returns: (pass, reasons_failed)
    """
    reasons = []

    px = safe_float(entry.get("last_trade_price"))
    if px is None or px < 2 or px > 20:
        reasons.append("PRICE_NOT_IN_2_TO_20")

    float_raw = entry.get("float_shares_raw")
    if not isinstance(float_raw, int) or float_raw <= 0:
        reasons.append("FLOAT_UNKNOWN")
    else:
        if float_raw > 50_000_000:
            reasons.append("FLOAT_TOO_HIGH_GT_50M")

    pct = safe_float(entry.get("current_percentage_change_from_prior_close"))
    if pct is None or pct < 10:
        reasons.append("PCT_CHANGE_LT_10")

    rvol = safe_float(entry.get("relative_volume"))
    if rvol is None or rvol < 2:
        reasons.append("RVOL_LT_2")

    news_total = int(entry.get("news_total_headlines") or 0)
    if news_total <= 0:
        reasons.append("NO_NEWS_PRESENT")

    return (len(reasons) == 0), reasons

# ============================================================
# Phase 6 — Your Sniper Strategy Selection
# ============================================================

def sniper_pass(entry: Dict[str, Any]) -> (bool, List[str]):
    """
    Your sniper overlay:
      - Must pass Ross 5 pillars first
      - Then prioritise news dominance:
          a) news_total_headlines >= 5
          b) news_region_count >= 2
          c) news_velocity_10m >= 2  OR  news_velocity_60m >= 5

    Returns: (pass, reasons_failed)
    """
    reasons = []

    ross_pass, ross_reasons = ross_5_pillars_pass(entry)
    if not ross_pass:
        reasons.extend([f"ROSS_FAIL:{r}" for r in ross_reasons])
        return False, reasons

    news_total = int(entry.get("news_total_headlines") or 0)
    if news_total < 5:
        reasons.append("NEWS_TOTAL_LT_5")

    region_count = int(entry.get("news_region_count") or 0)
    if region_count < 2:
        reasons.append("REGION_COUNT_LT_2")

    vel10 = int(entry.get("news_velocity_10m") or 0)
    vel60 = int(entry.get("news_velocity_60m") or 0)
    if not (vel10 >= 2 or vel60 >= 5):
        reasons.append("NEWS_VELOCITY_TOO_LOW")

    return (len(reasons) == 0), reasons

# ============================================================
# Fire indicator (keep consistent and simple)
# ============================================================

def compute_fire_indicator(entry: Dict[str, Any]) -> str:
    """
    Keep fire stable, as you requested.

    Fire rule (simple):
      - % change >= 20 AND RVOL >= 2
    """
    pct = safe_float(entry.get("current_percentage_change_from_prior_close"))
    rvol = safe_float(entry.get("relative_volume"))
    if pct is not None and rvol is not None and pct >= 20 and rvol >= 2:
        return "🔥"
    return ""

# ============================================================
# Build entry
# ============================================================

def build_entry(ib: IB, contract: Contract, sort_rank: int) -> Dict[str, Any]:
    sym = contract.symbol

    price = get_price_truth(ib, contract)
    float_data = get_float_truth(contract)
    volume = get_volume_truth(ib, contract)
    news = get_news_truth(sym)

    entry = {
        "momentum_fire_indicator": "",
        "symbol": sym,
        "market_session_label": "RTH",
        "sort_rank_by_gap_desc": sort_rank,
        **price,
        **float_data,
        **volume,
        **news,
        "composite_momentum_score": None,
        "score_components_breakdown": None,
        "attention_tier": None,
        "trade_suggestion_label": None,
        "trade_suggestion_rationale": None,
    }

    # Ensure float_category is consistent if float raw exists
    if entry.get("float_shares_raw") is not None and entry.get("float_category") in (None, "UNKNOWN"):
        try:
            entry["float_category"] = float_category_from_shares(int(entry["float_shares_raw"]))
        except Exception:
            pass

    # Ensure formatted float if raw exists
    if isinstance(entry.get("float_shares_raw"), int) and entry.get("float_shares_formatted") in (None, "N/A"):
        entry["float_shares_formatted"] = format_float_shares(entry["float_shares_raw"])

    # RVOL category
    entry["relative_volume_category"] = rvol_category(safe_float(entry.get("relative_volume")))

    # Fire indicator
    entry["momentum_fire_indicator"] = compute_fire_indicator(entry)

    # Composite score
    score_fields = compute_composite_score(entry)
    entry.update(score_fields)

    return entry

# ============================================================
# Printers
# ============================================================

def print_master(entries: List[Dict[str, Any]], max_symbols: Optional[int] = None):
    print("=" * 106)
    print(f"MASTER SCANNER PRINTER (GENERAL) — {now_utc()}")
    print("Sorted by: current_percentage_change_from_prior_close (desc)")
    print("=" * 106)

    shown = 0
    for e in entries:
        if max_symbols is not None and shown >= max_symbols:
            break
        shown += 1

        header_line = (
            f"{e['momentum_fire_indicator']} {e['symbol']} | "
            f"%Chg:{e.get('current_percentage_change_from_prior_close')} | "
            f"Gap:{e.get('overnight_gap_percentage')} | "
            f"Px:{e.get('last_trade_price')} | "
            f"Float:{e.get('float_shares_formatted')} | "
            f"RVOL:{e.get('relative_volume')} | "
            f"News:{e.get('news_total_headlines')} | "
            f"Score:{e.get('composite_momentum_score')} ({e.get('attention_tier')})"
        )
        print(header_line)

        # Print ALL canonical fields in frozen order
        for k in CANONICAL_FIELDS_54:
            print(f"  - {k}: {e.get(k)}")

        # News headlines (top 5) in compact clickable-ish format
        headlines = e.get("news_top_headlines_list") or []
        if headlines:
            print("  - top_headlines_clickable:")
            for h in headlines[:5]:
                title = h.get("title", "N/A")
                url = h.get("url", "")
                src = h.get("source", "N/A")
                age = h.get("age_min", None)
                region = h.get("region", "N/A")
                print(f"      • {title} | {src} | age_min={age} | region={region} | {url}")

        print("-" * 106)

def print_ross_watchlist(entries: List[Dict[str, Any]], max_symbols: int = 25, show_reasons: bool = True):
    print("=" * 106)
    print(f"ROSS 5-PILLARS PRINTER (WATCHLIST) — {now_utc()}")
    print("Filter: Ross 5 pillars proxy. Sorted by: composite_momentum_score (desc)")
    print("=" * 106)

    filtered = []
    for e in entries:
        ok, reasons = ross_5_pillars_pass(e)
        if ok:
            filtered.append((e, []))
        elif show_reasons:
            pass  # we only show pass list by default

    # Sort by score desc
    filtered.sort(key=lambda x: x[0].get("composite_momentum_score") or -999, reverse=True)

    for i, (e, _) in enumerate(filtered[:max_symbols], start=1):
        print(
            f"{i:02d}. {e['momentum_fire_indicator']} {e['symbol']} | "
            f"%Chg:{e.get('current_percentage_change_from_prior_close')} | "
            f"Px:{e.get('last_trade_price')} | "
            f"Float:{e.get('float_shares_formatted')} | "
            f"RVOL:{e.get('relative_volume')} | "
            f"News:{e.get('news_total_headlines')} | "
            f"Score:{e.get('composite_momentum_score')} ({e.get('attention_tier')})"
        )

def print_sniper_list(entries: List[Dict[str, Any]], max_symbols: int = 10):
    print("=" * 106)
    print(f"SNIPER PRINTER (ROSS + NEWS DOMINANCE) — {now_utc()}")
    print("Filter: Ross pillars + Sniper overlay. Sorted by: composite_momentum_score (desc)")
    print("=" * 106)

    filtered = []
    for e in entries:
        ok, reasons = sniper_pass(e)
        if ok:
            filtered.append((e, reasons))

    filtered.sort(key=lambda x: x[0].get("composite_momentum_score") or -999, reverse=True)

    for i, (e, _) in enumerate(filtered[:max_symbols], start=1):
        print(
            f"{i:02d}. {e['momentum_fire_indicator']} {e['symbol']} | "
            f"%Chg:{e.get('current_percentage_change_from_prior_close')} | "
            f"Px:{e.get('last_trade_price')} | "
            f"RVOL:{e.get('relative_volume')} | "
            f"News:{e.get('news_total_headlines')} "
            f"(Vel10m:{e.get('news_velocity_10m')}, Regions:{e.get('news_region_count')}) | "
            f"Score:{e.get('composite_momentum_score')} ({e.get('attention_tier')})"
        )
        # print top headlines if present
        headlines = e.get("news_top_headlines_list") or []
        for h in headlines[:5]:
            print(f"      • {h.get('title','N/A')} | {h.get('url','')}")
        print()

# ============================================================
# Main
# ============================================================

def fetch_scanner_contracts(ib: IB, rows: int = 50) -> List[Contract]:
    sub = ScannerSubscription(
        instrument="STK",
        locationCode="STK.US.MAJOR",
        scanCode="TOP_PERC_GAIN",
        numberOfRows=rows
    )
    scan = ib.reqScannerData(sub)
    contracts = []
    for s in scan:
        try:
            contracts.append(s.contractDetails.contract)
        except Exception:
            continue
    return contracts

def main():
    ib = IB()
    client_id = int(time.time()) % 9999
    print(f"[INFO] Connecting to 127.0.0.1:7496 with clientId {client_id}...")
    ib.connect("127.0.0.1", 7496, clientId=client_id)
    print("[INFO] Connected")

    contracts = fetch_scanner_contracts(ib, rows=50)
    print(f"[INFO] Scanner returned {len(contracts)} symbols")

    entries = []
    for idx, c in enumerate(contracts, start=1):
        sym = getattr(c, "symbol", "N/A")
        print(f"[INFO] ({idx}/{len(contracts)}) Enriching {sym}")
        try:
            entries.append(build_entry(ib, c, sort_rank=idx))
        except Exception as e:
            print(f"[WARN] Failed {sym}: {e}")

    # MASTER sort by % change desc (your preference)
    entries.sort(key=lambda x: x.get("current_percentage_change_from_prior_close") or -999, reverse=True)

    # 1) General Printer (full 54 fields)
    print_master(entries, max_symbols=None)

    # 2) Ross Watchlist
    print_ross_watchlist(entries, max_symbols=25, show_reasons=False)

    # 3) Sniper (top 10)
    print_sniper_list(entries, max_symbols=10)

    print(f"[INFO] Disconnecting from 127.0.0.1:7496...")
    ib.disconnect()
    print("[INFO] Done.")

if __name__ == "__main__":
    main()
