from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, Iterable, List, Optional

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from src.config.config_resolver import get_config, get_config_record
from src.config.runtime_config import (
    RunMode,
    get_run_mode,
    get_scanner_mode,
    get_watchlist_print_every_n_cycles,
)
from src.core.event_collector import EventCollector
from src.news.news_fetcher import Headline, fetch_headlines_for_symbols
from src.news.verified_sources import load_verified_rss_sources

from src.scanner.contracts import (
    SCANNER_GIT_SHA,
    SCANNER_VERSION,
    StockSelectionPolicy,
    policy_from_config,
)
from src.scanner.scanner_contract import ScannerRequest, scanner_request_from_policy
from src.strategies.ross_momentum.strategy_policy import UniverseSource
from src.scanner.phase24_views import (
    DeepViewRow,
    FastViewRow,
    format_fast_view_lines,
    print_deep_view,
    print_fast_view,
)
from src.scanner.print_contract import print_scanner_contract, summarize_drop_reasons
from src.scanner.providers.base import ProviderConnectionError, ScannerDataProvider
from src.models.data_models import ScannerCandidate
from src.scanner.providers.factory import build_provider
from src.scanner.providers.mock_provider import MockScannerProvider
from src.scanner.result_models import CandidateMetrics, ScannerResult
from src.scanner.session_pct_change import (
    compute_session_aligned_pct_change,
    normalize_session_label,
)


_FLOAT_CACHE_STATE: Dict[str, Any] = {
    "as_of": None,
    "data": {},
}
_FLOAT_CACHE_REQUESTED: set[str] = set()
_HISTORY_CACHE: Dict[str, Dict[str, Any]] = {}
_NEWS_CACHE: Dict[str, Dict[str, Any]] = {}
_PREV_WATCHLIST: set[str] = set()
_WATCHLIST_HASH: Optional[str] = None
_LAST_SESSION_LABEL: Optional[str] = None
_SCAN_CYCLE_COUNT = 0
_LAST_PRINT_CYCLE = 0
NEWS_AGE_MAX_MINUTES = 360

CATALYST_KEYWORDS = {
    "earnings": "earnings",
    "guidance": "guidance",
    "merger": "merger",
    "acquisition": "acquisition",
    "fda": "regulatory",
    "approval": "regulatory",
    "contract": "contract",
    "partnership": "partnership",
    "upgrade": "upgrade",
    "downgrade": "downgrade",
}
DILUTION_KEYWORDS = {
    "offering",
    "dilution",
    "s-1",
    "s1",
    "atm",
    "registered direct",
}


@dataclass(frozen=True)
class GateThresholds:
    min_price: float
    max_price: float
    min_pct_change: float
    max_pct_change: Optional[float]
    min_rvol: float
    min_volume: int
    min_premarket_volume: int
    max_float: int
    spread_max_pct: Optional[float]
    min_dollar_volume: Optional[float]
    require_price: bool
    require_bid_ask: bool
    require_catalyst: bool
    allow_halts: bool
    allow_ssr: bool


@dataclass(frozen=True)
class NewsDiagnostics:
    news_degraded: bool
    news_gate_bypassed: bool
    failure_reason: Optional[str]
    rss_sources: int
    rss_failures: int
    rss_failure_summary: Dict[str, Dict[str, int]]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _is_unsubscribed_market_data_error(exc: Exception) -> bool:
    message = str(exc).lower()
    if not message:
        return False
    keywords = (
        "market data subscription",
        "not subscribed",
        "no market data",
        "market data permissions",
        "not authorized",
    )
    return any(keyword in message for keyword in keywords)


def _market_session_label_utc(now: datetime) -> str:
    h = now.hour + now.minute / 60.0
    if 12.0 <= h < 14.0:
        return "PRE"
    if 14.0 <= h < 21.5:
        return "REG"
    if 21.5 <= h < 23.0:
        return "AFTER"
    return "AFTER"


def _print_symbol_limits(
    scanner_mode: str,
    provider_source: str,
    policy: StockSelectionPolicy,
    requested_top_n: Optional[int] = None,
) -> Dict[str, Any]:
    limit_keys = [
        "IBKR_MAX_SYMBOLS_PER_CYCLE",
        "SCANNER_TEACHING_SYMBOL_CAP",
    ]
    records = {key: get_config_record(key) for key in limit_keys}
    print("[SCANNER][LIMITS] Symbol limits (value/source/env)")
    for key in limit_keys:
        record = records[key]
        env = record.env or "-"
        print(f"[SCANNER][LIMITS] {key}={record.value} source={record.source} env={env}")
    resolved_top_n = int(requested_top_n or policy.top_gainers_n)
    print(
        "[SCANNER][LIMITS] Policy caps "
        f"top_gainers_n={policy.top_gainers_n} "
        f"watchlist_k={policy.watchlist_limit_k} "
        f"focus_m={policy.focus_limit_m} "
        f"max_symbols_per_cycle={policy.max_symbols_per_cycle}"
    )
    if requested_top_n and requested_top_n != policy.top_gainers_n:
        print(f"[SCANNER][LIMITS] Universe override top_n={requested_top_n}")

    resolved = resolved_top_n
    reductions: list[str] = []
    if policy.max_symbols_per_cycle and resolved > policy.max_symbols_per_cycle:
        reductions.append(f"policy_max_symbols({policy.max_symbols_per_cycle})")
        resolved = policy.max_symbols_per_cycle
    if scanner_mode == "TEACHING":
        teaching_cap = int(records["SCANNER_TEACHING_SYMBOL_CAP"].value)
        if teaching_cap and resolved > teaching_cap:
            reductions.append(f"teaching_cap({teaching_cap})")
            resolved = teaching_cap
    if provider_source == "IBKR":
        ibkr_cap = int(records["IBKR_MAX_SYMBOLS_PER_CYCLE"].value)
        if ibkr_cap and resolved > ibkr_cap:
            reductions.append(f"ibkr_snapshot_cap({ibkr_cap})")
            resolved = ibkr_cap

    watchlist_limit = int(policy.watchlist_limit_k)
    focus_limit = int(policy.focus_limit_m)
    if watchlist_limit and focus_limit > watchlist_limit:
        focus_limit = watchlist_limit
    print(
        "[SCANNER][LIMITS] Resolved symbol request limit="
        f"{resolved} reductions={reductions or ['none']}"
    )
    print(f"[SCANNER][LIMITS] Focus list limit={focus_limit}")
    return {
        "resolved_symbol_limit": resolved,
        "reductions": reductions,
        "watchlist_limit": watchlist_limit,
        "focus_limit": focus_limit,
    }


def _watchlist_hash(symbols: list[str], focus: list[str]) -> str:
    payload = json.dumps({"watchlist": symbols, "focus": focus}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _should_print_watchlist(
    *,
    watchlist_changed: bool,
    session_label: str,
    cycle_count: int,
) -> bool:
    global _LAST_PRINT_CYCLE, _LAST_SESSION_LABEL
    every_n = max(int(get_watchlist_print_every_n_cycles()), 1)
    session_changed = _LAST_SESSION_LABEL is not None and session_label != _LAST_SESSION_LABEL
    if watchlist_changed or session_changed:
        return True
    return (cycle_count - _LAST_PRINT_CYCLE) >= every_n


def _load_float_cache(path: Path) -> Dict[str, int]:
    try:
        if not path.exists():
            return {}
        data = path.read_text(encoding="utf-8")
        parsed = json.loads(data)
        if isinstance(parsed, dict):
            parsed.pop("_meta", None)
            return {k: int(v) for k, v in parsed.items() if isinstance(v, (int, float))}
    except Exception:
        return {}
    return {}


def _persist_float_cache(path: Path, float_cache: Dict[str, int]) -> None:
    try:
        path.write_text(json.dumps(float_cache, sort_keys=True, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"[SCANNER][FLOAT] Failed to persist float cache: {exc}")


def _bootstrap_float_cache(
    symbols: Iterable[str],
    provider: ScannerDataProvider,
) -> Dict[str, int]:
    global _FLOAT_CACHE_STATE
    today = datetime.now(timezone.utc).date().isoformat()
    cache_path = Path(get_config("SCANNER_FLOAT_CACHE_FILE"))

    if _FLOAT_CACHE_STATE.get("as_of") != today:
        _FLOAT_CACHE_STATE = {"as_of": today, "data": _load_float_cache(cache_path)}
        _FLOAT_CACHE_REQUESTED.clear()

    float_cache: Dict[str, int] = _FLOAT_CACHE_STATE.get("data", {})
    updated = False

    for symbol in symbols:
        if symbol in float_cache or symbol in _FLOAT_CACHE_REQUESTED:
            continue
        _FLOAT_CACHE_REQUESTED.add(symbol)
        try:
            value = provider.get_float(symbol)
        except Exception:
            value = None
        if value:
            float_cache[symbol] = int(value)
            updated = True

    if updated:
        _persist_float_cache(cache_path, float_cache)
    _FLOAT_CACHE_STATE["data"] = float_cache
    return float_cache


def _history_snapshot(symbol: str, provider: ScannerDataProvider) -> Dict[str, Any]:
    cached = _HISTORY_CACHE.get(symbol)
    if cached:
        return cached
    snapshot: Dict[str, Any] = {}
    try:
        snapshot["prev_close"] = provider.get_prev_close(symbol)
    except Exception:
        snapshot["prev_close"] = None
    try:
        intraday = provider.get_intraday_stats(symbol)
        snapshot["average_daily_volume_20d"] = intraday.average_daily_volume_20d
        snapshot["average_daily_volume_window_days"] = intraday.average_daily_volume_window_days
    except Exception:
        snapshot["average_daily_volume_20d"] = None
        snapshot["average_daily_volume_window_days"] = None
    _HISTORY_CACHE[symbol] = snapshot
    return snapshot


def _resolve_price(quote) -> Optional[float]:
    if quote.last is not None:
        return float(quote.last)
    if quote.bid is not None and quote.ask is not None:
        return float(round((quote.bid + quote.ask) / 2.0, 4))
    if quote.bid is not None:
        return float(quote.bid)
    if quote.ask is not None:
        return float(quote.ask)
    return None


def _spread_values(quote) -> tuple[Optional[float], Optional[float]]:
    if quote.bid is None or quote.ask is None:
        return None, None
    spread = float(round(quote.ask - quote.bid, 4))
    mid = float(round((quote.ask + quote.bid) / 2.0, 4))
    if mid <= 0:
        return spread, None
    return spread, float(round(spread / mid, 4))


def _gate_thresholds(policy: StockSelectionPolicy) -> GateThresholds:
    return GateThresholds(
        min_price=policy.price_min,
        max_price=policy.price_max,
        min_pct_change=policy.gap_min_pct,
        max_pct_change=policy.gap_max_pct,
        min_rvol=policy.rvol_min,
        min_volume=policy.min_volume,
        min_premarket_volume=policy.min_premarket_volume,
        max_float=int(policy.float_max_millions * 1_000_000),
        spread_max_pct=policy.spread_max_pct,
        min_dollar_volume=policy.liquidity_min_dollar_volume,
        require_price=policy.data_quality_require_price,
        require_bid_ask=policy.data_quality_require_bid_ask,
        require_catalyst=policy.require_catalyst,
        allow_halts=policy.allow_halts,
        allow_ssr=policy.allow_ssr,
    )


def _gate_checks(
    context: Dict[str, Any],
    thresholds: GateThresholds,
    *,
    catalyst_present: Optional[bool] = None,
) -> Dict[str, bool]:
    price = _safe_float(context.get("last_price"), None)
    pct_change = _safe_float(context.get("pct_change"), None)
    rvol = _safe_float(context.get("rvol"), None)
    volume = _safe_float(context.get("volume"), None)
    dollar_volume = _safe_float(context.get("dollar_volume"), None)
    float_shares = context.get("float_shares")
    session = (context.get("session") or "").upper()
    spread_pct = _safe_float(context.get("spread_pct"), None)
    bid = _safe_float(context.get("bid"), None)
    ask = _safe_float(context.get("ask"), None)
    halted = context.get("halted")
    ssr = context.get("ssr")

    price_ok = price is not None and thresholds.min_price <= price <= thresholds.max_price
    gap_ok = pct_change is not None and pct_change >= thresholds.min_pct_change
    if thresholds.max_pct_change is not None:
        gap_ok = gap_ok and pct_change is not None and pct_change <= thresholds.max_pct_change
    rvol_ok = rvol is not None and rvol >= thresholds.min_rvol
    volume_ok = volume is not None and volume >= thresholds.min_volume
    pm_volume_ok = volume is not None and volume >= thresholds.min_premarket_volume
    if session in {"PRE", "OVN"}:
        volume_ok = pm_volume_ok
    dollar_volume_ok = True
    if thresholds.min_dollar_volume is not None:
        dollar_volume_ok = (
            dollar_volume is not None and dollar_volume >= thresholds.min_dollar_volume
        )
    float_ok = float_shares is None or float_shares <= thresholds.max_float
    spread_ok = True
    if thresholds.spread_max_pct is not None:
        spread_ok = spread_pct is not None and spread_pct <= thresholds.spread_max_pct
    bid_ask_ok = True
    if thresholds.require_bid_ask:
        bid_ask_ok = bid is not None and ask is not None
    catalyst_ok = True
    if thresholds.require_catalyst:
        catalyst_ok = bool(catalyst_present)
    halt_ok = True
    if halted is True and not thresholds.allow_halts:
        halt_ok = False
    ssr_ok = True
    if ssr is True and not thresholds.allow_ssr:
        ssr_ok = False

    return {
        "price_range_ok": price_ok,
        "gap_ok": gap_ok,
        "rvol_ok": rvol_ok,
        "volume_ok": volume_ok,
        "pm_volume_ok": pm_volume_ok,
        "dollar_volume_ok": dollar_volume_ok,
        "float_ok": float_ok,
        "spread_ok": spread_ok,
        "bid_ask_ok": bid_ask_ok,
        "catalyst_ok": catalyst_ok,
        "halt_ok": halt_ok,
        "ssr_ok": ssr_ok,
    }


def _evaluate_price_gate(
    context: Dict[str, Any],
    thresholds: GateThresholds,
) -> Optional[str]:
    price = _safe_float(context.get("last_price"), None)
    if thresholds.require_price and price is None:
        return "DROP_MISSING_PRICE"
    if price is not None and not (thresholds.min_price <= price <= thresholds.max_price):
        return "DROP_PRICE_RANGE"
    return None


def _populate_pct_change(
    context: Dict[str, Any],
    provider: ScannerDataProvider,
) -> None:
    if context.get("pct_change") is not None:
        return
    last_price = _safe_float(context.get("last_price"), None)
    prev_close = _safe_float(context.get("prev_close"), None)
    if prev_close is None:
        history = _history_snapshot(context["symbol"], provider)
        prev_close = history.get("prev_close")
        context["prev_close"] = prev_close
        if prev_close is None:
            context.setdefault("data_quality_flags", []).append("HISTORY_UNKNOWN")
    pct_payload = compute_session_aligned_pct_change(
        session_label=str(context.get("session") or ""),
        cur_last=last_price,
        ref_close_rth=prev_close,
        ibkr_change_pct=_safe_float(context.get("ibkr_change_pct"), None),
    )
    if last_price is None:
        context.setdefault("data_quality_flags", []).append("MISSING_LAST")
    if prev_close is None:
        context.setdefault("data_quality_flags", []).append("MISSING_REF_CLOSE_RTH")
    if pct_payload.final_pct is None:
        context.setdefault("data_quality_flags", []).append("MISSING_PCT_CHANGE")
    context["pct_change"] = pct_payload.final_pct
    context["ref_close_rth"] = pct_payload.ref_close_rth
    context["ibkr_change_pct"] = pct_payload.ibkr_change_pct
    context["pct_source"] = pct_payload.pct_source
    if get_config("DEBUG_MARKET_DATA"):
        print(
            "[SCANNER][MD][DEBUG] pct_change "
            f"symbol={context['symbol']} last={last_price} ref_close={prev_close} "
            f"pct_change={context.get('pct_change')} source={context.get('pct_source')}"
        )


def _missingness_map(drop_reason: str, context: Dict[str, Any]) -> Dict[str, bool]:
    if drop_reason in {"DROP_PCT_CHANGE", "DROP_PCT_CHANGE_MAX", "DROP_MISSING_PCT_CHANGE"}:
        return {
            "close": context.get("close") is None,
            "prev_close": context.get("prev_close") is None,
            "last": context.get("last_price") is None,
        }
    if drop_reason in {"DROP_PRICE_RANGE", "DROP_MISSING_PRICE"}:
        return {
            "last": context.get("last_price") is None,
            "bid": context.get("bid") is None,
            "ask": context.get("ask") is None,
        }
    if drop_reason in {"DROP_MISSING_RVOL", "DROP_RVOL"}:
        return {"rvol": context.get("rvol") is None}
    if drop_reason in {"DROP_MISSING_VOLUME", "DROP_VOLUME", "DROP_PREMARKET_VOLUME"}:
        return {"volume": context.get("volume") is None}
    if drop_reason in {"DROP_MISSING_BID_ASK"}:
        return {"bid": context.get("bid") is None, "ask": context.get("ask") is None}
    if drop_reason in {"DROP_MISSING_SPREAD", "DROP_SPREAD"}:
        return {
            "spread_pct": context.get("spread_pct") is None,
            "bid": context.get("bid") is None,
            "ask": context.get("ask") is None,
        }
    return {
        "last": context.get("last_price") is None,
        "prev_close": context.get("prev_close") is None,
        "pct_change": context.get("pct_change") is None,
        "volume": context.get("volume") is None,
    }


def _evaluate_gates(
    context: Dict[str, Any],
    thresholds: GateThresholds,
) -> Optional[str]:
    price = _safe_float(context.get("last_price"), None)
    pct_change = _safe_float(context.get("pct_change"), None)
    rvol = _safe_float(context.get("rvol"), None)
    volume = _safe_float(context.get("volume"), None)
    dollar_volume = _safe_float(context.get("dollar_volume"), None)
    float_shares = context.get("float_shares")
    session = (context.get("session") or "").upper()
    spread_pct = _safe_float(context.get("spread_pct"), None)
    bid = _safe_float(context.get("bid"), None)
    ask = _safe_float(context.get("ask"), None)
    halted = context.get("halted")
    ssr = context.get("ssr")

    if thresholds.require_price and price is None:
        return "DROP_MISSING_PRICE"
    if halted is True and not thresholds.allow_halts:
        return "DROP_HALTED"
    if ssr is True and not thresholds.allow_ssr:
        return "DROP_SSR"
    if price is not None and not (thresholds.min_price <= price <= thresholds.max_price):
        return "DROP_PRICE_RANGE"
    if pct_change is None:
        return "DROP_MISSING_PCT_CHANGE"
    if pct_change < thresholds.min_pct_change:
        return "DROP_PCT_CHANGE"
    if thresholds.max_pct_change is not None and pct_change > thresholds.max_pct_change:
        return "DROP_PCT_CHANGE_MAX"
    if rvol is not None and rvol < thresholds.min_rvol:
        return "DROP_RVOL"
    if session in {"PRE", "OVN"}:
        if volume is not None and volume < thresholds.min_premarket_volume:
            return "DROP_PREMARKET_VOLUME"
    elif volume is not None and volume < thresholds.min_volume:
        return "DROP_VOLUME"
    if thresholds.min_dollar_volume is not None:
        if dollar_volume is None:
            return "DROP_MISSING_DOLLAR_VOLUME"
        if dollar_volume < thresholds.min_dollar_volume:
            return "DROP_DOLLAR_VOLUME"
    if float_shares is not None and float_shares > thresholds.max_float:
        return "DROP_FLOAT_MAX"
    if thresholds.spread_max_pct is not None:
        if spread_pct is None:
            return "DROP_MISSING_SPREAD"
        if spread_pct > thresholds.spread_max_pct:
            return "DROP_SPREAD"
    if thresholds.require_bid_ask and (bid is None or ask is None):
        return "DROP_MISSING_BID_ASK"
    return None


def _attention_tier(vel5: int, vel10: int, vel30: int) -> str:
    if vel5 >= 3 or vel10 >= 5:
        return "T3"
    if vel5 >= 2 or vel10 >= 3 or vel30 >= 5:
        return "T2"
    if vel5 >= 1 or vel10 >= 2 or vel30 >= 3:
        return "T1"
    return "T0"


def _detect_catalyst_type(titles: Iterable[str]) -> Optional[str]:
    for title in titles:
        lowered = title.lower()
        for keyword, label in CATALYST_KEYWORDS.items():
            if keyword in lowered:
                return label
    return None


def _detect_dilution(titles: Iterable[str]) -> bool:
    for title in titles:
        lowered = title.lower()
        if any(keyword in lowered for keyword in DILUTION_KEYWORDS):
            return True
    return False


def _enrich_news_context(
    symbols: List[str],
    provider_source: str,
) -> tuple[Dict[str, Dict[str, Any]], NewsDiagnostics]:
    sources = load_verified_rss_sources()
    headlines_by_symbol, summary = fetch_headlines_for_symbols(
        symbols,
        sources,
        lookback_hours=float(get_config("NEWS_LOOKBACK_HOURS")),
        request_timeout_s=float(get_config("NEWS_REQUEST_TIMEOUT_S")),
    )
    all_failed = summary.total_sources > 0 and summary.failure_count >= summary.total_sources
    reason_override = summary.reason
    news_degraded = all_failed or bool(reason_override)

    if provider_source == "MOCK":
        if all(len(items) == 0 for items in headlines_by_symbol.values()):
            now_ts = datetime.now(timezone.utc).timestamp()
            for symbol in symbols[:20]:
                headlines_by_symbol[symbol] = [
                    Headline(
                        title=f"{symbol} reports earnings beat and raises guidance",
                        source="MOCK_NEWS",
                        published_ts=now_ts - 300,
                        url="https://mock.news/earnings",
                    ),
                    Headline(
                        title=f"{symbol} announces new partnership",
                        source="MOCK_NEWS",
                        published_ts=now_ts - 900,
                        url="https://mock.news/partnership",
                    ),
                ]
            news_degraded = True
            reason_override = reason_override or "mock_headlines_injected"

    news_by_symbol: Dict[str, Dict[str, Any]] = {}
    now_ts = time.time()
    for symbol, headlines in headlines_by_symbol.items():
        signature = tuple(
            sorted((headline.title.strip().lower(), headline.source.strip().lower()) for headline in headlines)
        )
        cached = _NEWS_CACHE.get(symbol)
        if cached and cached.get("signature") == signature:
            news_by_symbol[symbol] = cached["context"]
            continue

        if not headlines:
            context = {
                "news_present": False,
                "first_seen_ts": None,
                "news_age_minutes": None,
                "velocity_5m": 0,
                "velocity_10m": 0,
                "velocity_30m": 0,
                "attention_tier": "T0",
                "top_domains": [],
                "top_links": [],
                "catalyst_type": None,
                "dilution_flag": False,
                "gam_ea_eligible": False,
                "ross_catalyst_valid": False,
                "ross_catalyst_notes": "No news present",
            }
            news_by_symbol[symbol] = context
            _NEWS_CACHE[symbol] = {"signature": signature, "context": context}
            continue

        unique_map: Dict[str, Headline] = {}
        for headline in headlines:
            key = f"{headline.title.lower().strip()}|{headline.source.lower().strip()}"
            unique_map.setdefault(key, headline)
        unique_headlines = list(unique_map.values())

        ages = [max(0.0, (now_ts - headline.published_ts) / 60.0) for headline in unique_headlines]
        news_age_minutes = int(min(ages)) if ages else None
        vel5 = sum(1 for headline in unique_headlines if now_ts - headline.published_ts <= 5 * 60)
        vel10 = sum(1 for headline in unique_headlines if now_ts - headline.published_ts <= 10 * 60)
        vel30 = sum(1 for headline in unique_headlines if now_ts - headline.published_ts <= 30 * 60)
        attention_tier = _attention_tier(vel5, vel10, vel30)

        titles = [headline.title for headline in unique_headlines]
        catalyst_type = _detect_catalyst_type(titles)
        dilution_flag = _detect_dilution(titles)
        gam_ea_eligible = bool(
            not dilution_flag
            and news_age_minutes is not None
            and news_age_minutes <= NEWS_AGE_MAX_MINUTES
        )

        domains: list[str] = []
        links: list[str] = []
        seen_domains = set()
        for headline in unique_headlines:
            domain = headline.url.split("/")[2] if "//" in headline.url else headline.url
            if domain and domain not in seen_domains:
                seen_domains.add(domain)
                domains.append(domain)
            if len(links) < 5 and headline.url:
                links.append(headline.url)

        ross_catalyst_valid = bool(not dilution_flag and news_age_minutes is not None)
        ross_notes = "Catalyst present" if ross_catalyst_valid else "Catalyst missing or diluted"

        context = {
            "news_present": True,
            "first_seen_ts": min(headline.published_ts for headline in unique_headlines),
            "news_age_minutes": news_age_minutes,
            "velocity_5m": vel5,
            "velocity_10m": vel10,
            "velocity_30m": vel30,
            "attention_tier": attention_tier,
            "top_domains": domains[:2],
            "top_links": links[:5],
            "catalyst_type": catalyst_type,
            "dilution_flag": dilution_flag,
            "gam_ea_eligible": gam_ea_eligible,
            "ross_catalyst_valid": ross_catalyst_valid,
            "ross_catalyst_notes": ross_notes,
        }
        news_by_symbol[symbol] = context
        _NEWS_CACHE[symbol] = {"signature": signature, "context": context}

    news_gate_bypassed = all_failed or reason_override in {"no_sources", "feedparser_missing"}
    diagnostics = NewsDiagnostics(
        news_degraded=news_degraded,
        news_gate_bypassed=news_gate_bypassed,
        failure_reason=reason_override,
        rss_sources=summary.total_sources,
        rss_failures=summary.failure_count,
        rss_failure_summary=summary.failures_by_domain,
    )
    return news_by_symbol, diagnostics


def _rank_candidates(contexts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def sort_key(item: Dict[str, Any]) -> tuple:
        pct = _safe_float(item.get("pct_change"), -10**9)
        rvol = _safe_float(item.get("rvol"), -10**9)
        dvol = _safe_float(item.get("dollar_volume"), -10**9)
        float_missing = item.get("float_shares") is None
        symbol = item.get("symbol", "")
        return (float_missing, -pct, -rvol, -dvol, symbol)

    return sorted(contexts, key=sort_key)


def _build_fast_rows(
    contexts: List[Dict[str, Any]],
    news_by_symbol: Dict[str, Dict[str, Any]],
) -> List[FastViewRow]:
    rows: List[FastViewRow] = []
    for rank, context in enumerate(contexts, start=1):
        symbol = context["symbol"]
        news_context = news_by_symbol.get(symbol, {})
        rows.append(
            FastViewRow(
                symbol=symbol,
                session=context.get("session", ""),
                last_price=context.get("last_price"),
                pct_change=context.get("pct_change"),
                volume=context.get("volume"),
                dollar_volume=context.get("dollar_volume"),
                bid=context.get("bid"),
                ask=context.get("ask"),
                spread=context.get("spread"),
                spread_pct=context.get("spread_pct"),
                rvol=context.get("rvol"),
                float_shares=context.get("float_shares"),
                scanner_rank=rank,
                scanner_score=context.get("scanner_score"),
                drop_reason=None,
                data_quality_flags=context.get("data_quality_flags", []),
                news_present=bool(news_context.get("news_present")),
                catalyst_type=news_context.get("catalyst_type"),
                dilution_flag=bool(news_context.get("dilution_flag")),
                news_age_minutes=news_context.get("news_age_minutes"),
                velocity_5m=news_context.get("velocity_5m"),
                velocity_10m=news_context.get("velocity_10m"),
                velocity_30m=news_context.get("velocity_30m"),
                attention_tier=news_context.get("attention_tier"),
                gam_ea_eligible=news_context.get("gam_ea_eligible"),
            )
        )
    return rows


def _build_deep_rows(
    contexts: List[Dict[str, Any]],
    news_by_symbol: Dict[str, Dict[str, Any]],
) -> List[DeepViewRow]:
    rows: List[DeepViewRow] = []
    for rank, context in enumerate(contexts, start=1):
        symbol = context["symbol"]
        news_context = news_by_symbol.get(symbol, {})
        catalyst = news_context.get("catalyst_type") or "Unknown catalyst"
        age = news_context.get("news_age_minutes")
        if age is not None:
            catalyst_rationale = f"{catalyst} news within {age}m"
        else:
            catalyst_rationale = f"{catalyst} news (age unknown)"
        focus_reason = (
            "Ranked high by pct_change, rvol, and dollar_volume "
            f"(score={context.get('scanner_score')})"
        )
        rows.append(
            DeepViewRow(
                symbol=symbol,
                focus_rank=rank,
                links=news_context.get("top_links", []),
                catalyst_rationale=catalyst_rationale,
                focus_reason=focus_reason,
            )
        )
    return rows


def _format_value(value: Optional[float], digits: int = 2) -> str:
    if value is None:
        return "NA"
    return f"{value:.{digits}f}"


def _format_int(value: Optional[int]) -> str:
    if value is None:
        return "NA"
    return str(value)


def _format_float_millions(value: Optional[float]) -> str:
    if value is None:
        return "NA"
    return f"{value:.2f}M"


def _candidate_from_context(
    context: Dict[str, Any],
    news_context: Dict[str, Any],
    thresholds: GateThresholds,
    *,
    drop_reason: Optional[str],
    timestamp_utc: str,
) -> CandidateMetrics:
    float_shares = context.get("float_shares")
    float_millions = (
        round(float_shares / 1_000_000.0, 2) if float_shares is not None else None
    )
    session = (context.get("session") or "").upper()
    volume = context.get("volume")
    premarket_volume = volume if session in {"PRE", "OVN"} else None
    catalyst_present = bool(
        news_context.get("ross_catalyst_valid") or news_context.get("news_present")
    )
    catalyst_type = news_context.get("catalyst_type")
    news_age = news_context.get("news_age_minutes")
    catalyst_summary = None
    if catalyst_type:
        catalyst_summary = (
            f"{catalyst_type} age={news_age}m"
            if news_age is not None
            else f"{catalyst_type} age=NA"
        )
    gate_checks = _gate_checks(
        context,
        thresholds,
        catalyst_present=catalyst_present,
    )
    data_quality_flags = list(context.get("data_quality_flags", []) or [])
    return CandidateMetrics(
        symbol=context.get("symbol"),
        session_label=context.get("session"),
        last_price=context.get("last_price"),
        prev_close=context.get("prev_close"),
        ref_close_rth=context.get("ref_close_rth"),
        gap_pct=context.get("pct_change"),
        pct_change=context.get("pct_change"),
        ibkr_change_pct=context.get("ibkr_change_pct"),
        pct_source=context.get("pct_source"),
        rvol=context.get("rvol"),
        float_shares=float_shares,
        float_millions=float_millions,
        volume=volume,
        premarket_volume=premarket_volume,
        dollar_volume=context.get("dollar_volume"),
        spread_pct=context.get("spread_pct"),
        halted=context.get("halted"),
        ssr=context.get("ssr"),
        catalyst_present=catalyst_present,
        catalyst_summary=catalyst_summary,
        data_quality_ok=not data_quality_flags,
        data_quality_flags=data_quality_flags,
        drop_reasons=[drop_reason] if drop_reason else [],
        rank_score=context.get("scanner_score"),
        rank_components=context.get("scanner_score_components"),
        timestamp_utc=timestamp_utc,
        gate_checks=gate_checks,
    )


def _scanner_candidate_from_context(
    context: Dict[str, Any],
    *,
    drop_reason: Optional[str],
) -> ScannerCandidate:
    float_shares = context.get("float_shares")
    float_millions = (
        round(float_shares / 1_000_000.0, 2) if float_shares is not None else None
    )
    data_quality_flags = list(context.get("data_quality_flags", []) or [])
    if drop_reason:
        data_quality_flags.append(drop_reason)
    return ScannerCandidate(
        symbol=context.get("symbol"),
        price=context.get("last_price"),
        gap_percent=context.get("pct_change"),
        rvol=context.get("rvol"),
        float_millions=float_millions,
        rationale="scanner_runner candidate",
        session=context.get("session"),
        bid=context.get("bid"),
        ask=context.get("ask"),
        spread=context.get("spread"),
        volume=context.get("volume"),
        data_quality_flags=data_quality_flags,
    )


def _format_watchlist_line(candidate: CandidateMetrics) -> str:
    dq = "OK" if candidate.data_quality_ok else "BAD"
    catalyst = "YES" if candidate.catalyst_present else "NO"
    summary = candidate.catalyst_summary or "NA"
    if len(summary) > 80:
        summary = summary[:77] + "..."
    session_label = normalize_session_label(candidate.session_label or "")
    ref_close = candidate.ref_close_rth if candidate.ref_close_rth is not None else candidate.prev_close
    return (
        f"{candidate.symbol} session={session_label} price=${_format_value(candidate.last_price)} "
        f"ref_close_rth={_format_value(ref_close)} "
        f"ibkr_pct={_format_value(candidate.ibkr_change_pct)}% "
        f"final_pct={_format_value(candidate.pct_change)}% "
        f"pct_source={candidate.pct_source or 'NA'} "
        f"gap={_format_value(candidate.gap_pct)}% chg={_format_value(candidate.pct_change)}% "
        f"rvol={_format_value(candidate.rvol)} float={_format_float_millions(candidate.float_millions)} "
        f"vol={_format_int(candidate.volume)} pm={_format_int(candidate.premarket_volume)} "
        f"spread={_format_value(candidate.spread_pct, 4)}% catalyst={catalyst} "
        f"summary={summary} "
        f"halted={candidate.halted if candidate.halted is not None else 'NA'} "
        f"ssr={candidate.ssr if candidate.ssr is not None else 'NA'} dq={dq} "
        f"score={_format_value(candidate.rank_score)}"
    )


def _format_focus_line(candidate: CandidateMetrics) -> str:
    gates = candidate.gate_checks or {}
    gate_summary = " ".join(
        f"{name}={'OK' if passed else 'FAIL'}" for name, passed in gates.items()
    )
    components = candidate.rank_components or {}
    comp_summary = ",".join(f"{key}={value:.1f}" for key, value in components.items())
    return (
        f"{_format_watchlist_line(candidate)} "
        f"components={comp_summary or 'NA'} gates={gate_summary or 'NA'} "
        f"why={candidate.catalyst_summary or 'NA'}"
    )


def _print_watchlist_and_focus(
    watchlist: list[CandidateMetrics],
    focus: list[CandidateMetrics],
    *,
    session_label: str,
) -> None:
    session_display = normalize_session_label(session_label)
    print(f"[SCANNER][WATCHLIST] session={session_display} count={len(watchlist)}")
    for candidate in watchlist:
        print(_format_watchlist_line(candidate))
    print(f"[SCANNER][FOCUS] session={session_display} count={len(focus)}")
    for candidate in focus:
        print(_format_focus_line(candidate))


def _score_context(context: Dict[str, Any]) -> tuple[float, dict[str, float]]:
    pct = _safe_float(context.get("pct_change"), 0.0) or 0.0
    rvol = _safe_float(context.get("rvol"), 0.0) or 0.0
    dvol = _safe_float(context.get("dollar_volume"), 0.0) or 0.0
    pct_n = min(max(pct / 20.0, 0.0), 2.0)
    rvol_n = min(max(rvol / 5.0, 0.0), 2.0)
    dvol_n = min(max(dvol / 1_000_000.0, 0.0), 2.0)
    components = {
        "pct_change": round(0.45 * pct_n * 100.0, 2),
        "rvol": round(0.35 * rvol_n * 100.0, 2),
        "dollar_volume": round(0.20 * dvol_n * 100.0, 2),
    }
    score = sum(components.values()) / 100.0
    return round(min(score, 1.0) * 100.0, 2), components


def _build_symbol_context(
    provider: ScannerDataProvider,
    symbol: str,
    session_label: str,
    float_cache: Dict[str, int],
    *,
    universe_rank: Optional[int] = None,
    include_pct_change: bool = True,
) -> Optional[Dict[str, Any]]:
    try:
        quote = provider.get_quote(symbol)
    except Exception as exc:
        if _is_unsubscribed_market_data_error(exc):
            return {
                "symbol": symbol,
                "session": session_label,
                "data_quality_flags": ["UNSUBSCRIBED_MARKET_DATA"],
                "snapshot_error": "UNSUBSCRIBED_MARKET_DATA",
            }
        return None

    data_quality_flags = list(getattr(quote, "data_quality_flags", []) or [])
    last_price = _resolve_price(quote)
    spread, spread_pct = _spread_values(quote)
    snapshot_timeout = "MD_TIMEOUT" in data_quality_flags
    if get_config("DEBUG_MARKET_DATA"):
        print(
            "[SCANNER][MD][DEBUG] ticks "
            f"symbol={symbol} bid={quote.bid} ask={quote.ask} last={quote.last} "
            f"close={quote.close} volume={quote.volume} vwap={quote.vwap}"
        )

    intraday = None
    try:
        intraday = provider.get_intraday_stats(symbol)
    except Exception:
        intraday = None

    volume = intraday.current_intraday_volume if intraday else None
    rvol = intraday.relative_volume if intraday else None
    if intraday is None:
        data_quality_flags.append("VOLUME_UNKNOWN")
    if volume is None:
        data_quality_flags.append("MISSING_VOLUME")
    if rvol is None:
        data_quality_flags.append("RVOL_UNKNOWN")

    prev_close = quote.close
    if include_pct_change and prev_close is None:
        history = _history_snapshot(symbol, provider)
        prev_close = history.get("prev_close")
    if include_pct_change and prev_close is None:
        data_quality_flags.append("HISTORY_UNKNOWN")

    ibkr_change_pct = _safe_float(getattr(quote, "change_percent", None), None)
    pct_change = None
    pct_source = None
    if include_pct_change:
        pct_payload = compute_session_aligned_pct_change(
            session_label=session_label,
            cur_last=last_price,
            ref_close_rth=prev_close,
            ibkr_change_pct=ibkr_change_pct,
        )
        pct_change = pct_payload.final_pct
        pct_source = pct_payload.pct_source
    dollar_volume = None
    if last_price is not None and volume is not None:
        dollar_volume = round(last_price * volume, 2)

    float_shares = float_cache.get(symbol)
    if float_shares is None:
        data_quality_flags.append("FLOAT_UNKNOWN")

    if spread is None:
        data_quality_flags.append("SPREAD_UNKNOWN")
    if last_price is None:
        data_quality_flags.append("MISSING_LAST")
    if quote.close is None:
        data_quality_flags.append("MISSING_CLOSE_TICK")
    if include_pct_change and prev_close is None:
        data_quality_flags.append("MISSING_REF_CLOSE_RTH")
    if include_pct_change and pct_change is None:
        data_quality_flags.append("MISSING_PCT_CHANGE")
    if get_config("DEBUG_MARKET_DATA"):
        print(
            "[SCANNER][MD][DEBUG] snapshot "
            f"symbol={symbol} last={last_price} close={quote.close} "
            f"ref_close={prev_close} volume={volume} pct_change={pct_change} "
            f"source={pct_source}"
        )

    return {
        "symbol": symbol,
        "session": session_label,
        "last_price": last_price,
        "close": quote.close,
        "prev_close": prev_close,
        "ref_close_rth": prev_close,
        "pct_change": pct_change,
        "pct_source": pct_source,
        "ibkr_change_pct": ibkr_change_pct,
        "volume": volume,
        "dollar_volume": dollar_volume,
        "bid": quote.bid,
        "ask": quote.ask,
        "spread": spread,
        "spread_pct": spread_pct,
        "rvol": rvol,
        "float_shares": float_shares,
        "halted": None,
        "ssr": None,
        "data_quality_flags": data_quality_flags,
        "snapshot_timeout": snapshot_timeout,
        "universe_rank": universe_rank,
    }


def _resolve_universe_symbols(
    *,
    provider: ScannerDataProvider,
    request: ScannerRequest,
    limits: Dict[str, Any],
    diagnostics: Dict[str, Any],
) -> List[str]:
    diagnostics["universe_request"] = {
        "source": request.universe_source.value,
        "scan_code": request.ibkr_scan_code,
        "requested_top_n": request.requested_top_n,
        "region": request.region,
        "instrument": request.instrument,
        "exchanges": list(request.exchanges or []),
    }
    if request.universe_source == UniverseSource.IBKR_TOP_GAINERS:
        symbols = provider.get_top_gainers(limits["resolved_symbol_limit"])
        ibkr_returned_count = len(symbols)
        requested_top_n = int(request.requested_top_n)
        truncation = ibkr_returned_count != requested_top_n
        reasons: list[str] = []
        if limits.get("reductions"):
            reasons.extend(limits["reductions"])
        if ibkr_returned_count < limits["resolved_symbol_limit"]:
            reasons.append("ibkr_returned_fewer_than_requested")
        diagnostics["ibkr_universe"] = {
            "ibkr_returned_count": ibkr_returned_count,
            "requested_top_n": requested_top_n,
            "truncation": truncation,
            "reasons": reasons,
        }
        print(
            "[SCANNER][IBKR] universe_return "
            f"ibkr_returned_count={ibkr_returned_count} "
            f"requested_top_n={requested_top_n} "
            f"truncation={truncation} "
            f"reasons={reasons or ['none']}"
        )
        if truncation and not reasons:
            print(
                "[SCANNER][WARN] IBKR universe mismatch without explicit reason "
                f"requested_top_n={requested_top_n} ibkr_returned_count={ibkr_returned_count}"
            )
        return symbols

    if request.universe_source == UniverseSource.CONFIG_SYMBOLS:
        symbols = list(request.optional_symbols_override or [])
        if not symbols:
            symbols = list(get_config("SCANNER_SYMBOLS") or [])
        if not symbols:
            print(
                "[SCANNER][WARN] CONFIG_SYMBOLS requested but no symbols provided; "
                "falling back to SCANNER_DEFAULT_SYMBOLS"
            )
            diagnostics["symbol_fallback"] = "SCANNER_DEFAULT_SYMBOLS"
            symbols = list(get_config("SCANNER_DEFAULT_SYMBOLS") or [])
        if not symbols:
            print(
                "[SCANNER][WARN] CONFIG_SYMBOLS requested but no symbols provided; "
                "falling back to MOCK_UNIVERSE"
            )
            diagnostics["symbol_fallback"] = "MOCK_UNIVERSE"
            fallback_provider = MockScannerProvider()
            symbols = fallback_provider.get_top_gainers(limits["resolved_symbol_limit"])
        return symbols

    print(
        "[SCANNER][ERROR] Unknown universe source "
        f"{request.universe_source}; falling back to TEACHING static watchlist"
    )
    diagnostics["symbol_fallback"] = "TEACHING_STATIC"
    symbols = list(get_config("SCANNER_DEFAULT_SYMBOLS") or [])
    if not symbols:
        symbols = ["AAPL", "TSLA", "NVDA", "AMD", "SPY"]
    return symbols


def _build_universe_entries(symbols: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for rank, symbol in enumerate(symbols, start=1):
        entries.append(
            {
                "symbol": symbol,
                "conId": None,
                "exchange": None,
                "rank": rank,
            }
        )
    return entries


def _apply_non_tradable_universe_gate(
    symbols: list[str],
    provider: ScannerDataProvider,
    drop_ledger: Dict[str, str],
    event_collector: EventCollector | None = None,
) -> list[str]:
    blocked_trading_classes = {"EXPERT", "OTCID", "LIMITED"}
    scan_details = getattr(provider, "last_scan_details", {}) or {}
    filtered: list[str] = []
    for symbol in symbols:
        details = scan_details.get(symbol, {})
        trading_class = details.get("tradingClass")
        primary_exchange = details.get("primaryExchange")
        trading_class_upper = (
            trading_class.upper() if isinstance(trading_class, str) else None
        )
        primary_exchange_upper = (
            primary_exchange.upper() if isinstance(primary_exchange, str) else None
        )
        if trading_class_upper in blocked_trading_classes or primary_exchange_upper == "PINK":
            drop_ledger.setdefault(symbol, "DROP_NON_TRADABLE_UNIVERSE")
            print(
                "[SCANNER][DROP] "
                f"symbol={symbol} reason=DROP_NON_TRADABLE_UNIVERSE"
            )
            if event_collector is not None:
                event_collector.emit(
                    event_type="SCANNER_SYMBOL_DROPPED",
                    source="Scanner",
                    payload={
                        "symbol": symbol,
                        "drop_reason": "DROP_NON_TRADABLE_UNIVERSE",
                        "metric_value": trading_class_upper or primary_exchange_upper,
                        "threshold": "MAJOR_US_LISTING_ONLY",
                    },
                )
            continue
        filtered.append(symbol)
    return filtered


def run_scanner_cycle(
    mode: str = "integrated",
    policy: StockSelectionPolicy | None = None,
    scanner_request: ScannerRequest | None = None,
    event_collector: EventCollector | None = None,
) -> Dict[str, Any]:
    global _SCAN_CYCLE_COUNT, _WATCHLIST_HASH, _LAST_SESSION_LABEL, _LAST_PRINT_CYCLE
    _SCAN_CYCLE_COUNT += 1
    utc_now = _utc_now()
    session_label = _market_session_label_utc(utc_now)
    diagnostics: Dict[str, Any] = {"mode": mode}
    drop_ledger: Dict[str, str] = {}
    universe_top_n: list[dict[str, Any]] = []
    print(f"[SCANNER] MODE={mode} SESSION={session_label}")
    scanner_mode = get_scanner_mode()
    policy_source = "STRATEGY" if policy is not None else "CONFIG_DEFAULTS"
    resolved_policy = policy or policy_from_config()
    print(
        "[SCANNER][POLICY] source={source} policy_name={policy_name} price={price_min}-{price_max} "
        "gap_min={gap_min} rvol_min={rvol_min} float_max_millions={float_max} "
        "spread_max_pct={spread_max_pct} watchlist_k={watchlist_k} focus_m={focus_m}".format(
            source=policy_source,
            policy_name=resolved_policy.policy_name,
            price_min=resolved_policy.price_min,
            price_max=resolved_policy.price_max,
            gap_min=resolved_policy.gap_min_pct,
            rvol_min=resolved_policy.rvol_min,
            float_max=resolved_policy.float_max_millions,
            spread_max_pct=resolved_policy.spread_max_pct,
            watchlist_k=resolved_policy.watchlist_limit_k,
            focus_m=resolved_policy.focus_limit_m,
        )
    )
    request = scanner_request or scanner_request_from_policy(resolved_policy)
    print(
        "[SCANNER][ENTRY] "
        f"strategy={resolved_policy.policy_name} "
        f"requested_top_n={request.requested_top_n} "
        f"watchlist_k={resolved_policy.watchlist_limit_k} "
        f"focus_m={resolved_policy.focus_limit_m} "
        f"universe={request.universe_source.value} "
        f"scan_code={request.ibkr_scan_code}"
    )
    diagnostics["selection_spec"] = {
        "strategy": resolved_policy.policy_name,
        "requested_top_n": request.requested_top_n,
        "watchlist_k": resolved_policy.watchlist_limit_k,
        "focus_m": resolved_policy.focus_limit_m,
        "universe": request.universe_source.value,
        "scan_code": request.ibkr_scan_code,
    }

    run_mode = get_run_mode()
    fallback_enabled = bool(get_config("IBKR_FALLBACK_ENABLED"))
    allow_fallback = fallback_enabled or run_mode == RunMode.LIVE_READ_ONLY
    try:
        provider: ScannerDataProvider = build_provider()
    except ProviderConnectionError as exc:

        if run_mode == RunMode.PAPER and not allow_fallback:
            raise
        diagnostics["provider_error"] = str(exc)
        diagnostics["provider_fallback"] = {
            "from": "IBKR",
            "to": "MOCK",
            "reason": str(exc),
        }
        print("STATE=DEGRADED")
        print(
            "[SCANNER][WARN] Provider connection failed — "
            f"falling back to MOCK reason={exc}"
        )
        provider = MockScannerProvider()
    limits = _print_symbol_limits(
        scanner_mode,
        provider.source_name,
        resolved_policy,
        requested_top_n=request.requested_top_n,
    )
    diagnostics["symbol_limits"] = limits
    print("[SCANNER][STAGE] bootstrap")

    try:
        try:
            symbols = _resolve_universe_symbols(
                provider=provider,
                request=request,
                limits=limits,
                diagnostics=diagnostics,
            )
        except Exception as exc:
            diagnostics["provider_error"] = str(exc)
            if provider.source_name != "MOCK":
                diagnostics["provider_fallback"] = {
                    "from": provider.source_name,
                    "to": "MOCK",
                    "reason": str(exc),
                }
                provider.disconnect()
                provider = MockScannerProvider()
                limits = _print_symbol_limits(
                    scanner_mode,
                    provider.source_name,
                    resolved_policy,
                    requested_top_n=request.requested_top_n,
                )
                diagnostics["symbol_limits"] = limits
            symbols = _resolve_universe_symbols(
                provider=provider,
                request=request,
                limits=limits,
                diagnostics=diagnostics,
            )

        diagnostics["provider_source"] = provider.source_name
        diagnostics["symbol_count"] = len(symbols)
        if not symbols:
            symbols = list(get_config("SCANNER_DEFAULT_SYMBOLS"))
            diagnostics["symbol_fallback"] = "SCANNER_DEFAULT_SYMBOLS"
        if not symbols:
            fallback_provider = MockScannerProvider()
            symbols = fallback_provider.get_top_gainers(limits["resolved_symbol_limit"])
            diagnostics["symbol_fallback"] = "MOCK_UNIVERSE"
        symbols = [symbol.upper() for symbol in symbols][: limits["resolved_symbol_limit"]]
        requested_top_n = int(request.requested_top_n or len(symbols))
        print(f"SCANNER_RAW_N={requested_top_n} returned {len(symbols)} symbols")
        if event_collector is not None:
            event_payload = {
                "symbols": list(symbols),
                "requested_rows": requested_top_n,
                "returned_rows": len(symbols),
                "session": session_label,
                "timestamp": utc_now.isoformat(),
            }
            event_collector.emit(
                event_type="SCANNER_UNIVERSE_SNAPSHOT",
                source="Scanner",
                payload=event_payload,
            )
            event_collector.emit(
                event_type="RAW_SCAN_SYMBOLS",
                source="Scanner",
                payload=event_payload,
            )

        symbols = _apply_non_tradable_universe_gate(
            symbols, provider, drop_ledger, event_collector=event_collector
        )
        universe_top_n = _build_universe_entries(symbols)

        float_cache = _bootstrap_float_cache(symbols, provider)
        thresholds = _gate_thresholds(resolved_policy)
        candidates: List[Dict[str, Any]] = []
        evaluated_contexts: List[Dict[str, Any]] = []

        print("[SCANNER][STAGE] gates")
        for rank, symbol in enumerate(symbols, start=1):
            context = _build_symbol_context(
                provider,
                symbol,
                session_label,
                float_cache,
                universe_rank=rank,
                include_pct_change=False,
            )
            if context is None:
                drop_ledger.setdefault(symbol, "DROP_QUOTE_UNAVAILABLE")
                print(f"[SCANNER][DROP] symbol={symbol} reason=DROP_QUOTE_UNAVAILABLE")
                if event_collector is not None:
                    event_collector.emit(
                        event_type="SCANNER_SYMBOL_DROPPED",
                        source="Scanner",
                        payload={
                            "symbol": symbol,
                            "drop_reason": "DROP_QUOTE_UNAVAILABLE",
                            "metric_value": None,
                            "threshold": None,
                        },
                    )
                evaluated_contexts.append(
                    {
                        "symbol": symbol,
                        "session": session_label,
                        "data_quality_flags": ["QUOTE_UNAVAILABLE"],
                    }
                )
                continue
            if context.get("snapshot_error") == "UNSUBSCRIBED_MARKET_DATA":
                drop_ledger.setdefault(symbol, "DROP_UNSUBSCRIBED_MARKET_DATA")
                print(
                    "[SCANNER][DROP] "
                    f"symbol={symbol} reason=DROP_UNSUBSCRIBED_MARKET_DATA"
                )
                if event_collector is not None:
                    event_collector.emit(
                        event_type="SCANNER_SYMBOL_DROPPED",
                        source="Scanner",
                        payload={
                            "symbol": symbol,
                            "drop_reason": "DROP_UNSUBSCRIBED_MARKET_DATA",
                            "metric_value": None,
                            "threshold": None,
                        },
                    )
                evaluated_contexts.append(context)
                continue
            if context.get("snapshot_timeout"):
                drop_ledger.setdefault(symbol, "DROP_SNAPSHOT_TIMEOUT")
                print(f"[SCANNER][DROP] symbol={symbol} reason=DROP_SNAPSHOT_TIMEOUT")
                if event_collector is not None:
                    event_collector.emit(
                        event_type="SCANNER_SYMBOL_DROPPED",
                        source="Scanner",
                        payload={
                            "symbol": symbol,
                            "drop_reason": "DROP_SNAPSHOT_TIMEOUT",
                            "metric_value": None,
                            "threshold": None,
                        },
                    )
                evaluated_contexts.append(context)
                continue
            price_gate_reason = _evaluate_price_gate(context, thresholds)
            if price_gate_reason:
                drop_ledger.setdefault(symbol, price_gate_reason)
                print(f"[SCANNER][DROP] symbol={symbol} reason={price_gate_reason}")
                if event_collector is not None:
                    event_collector.emit(
                        event_type="SCANNER_SYMBOL_DROPPED",
                        source="Scanner",
                        payload={
                            "symbol": symbol,
                            "drop_reason": price_gate_reason,
                            "metric_value": context.get("last_price"),
                            "threshold": {
                                "min_price": thresholds.min_price,
                                "max_price": thresholds.max_price,
                            },
                        },
                    )
                if get_config("DEBUG_SCANNER"):
                    missingness = _missingness_map(price_gate_reason, context)
                    print(
                        "[SCANNER][DEBUG] "
                        f"symbol={symbol} reason={price_gate_reason} missing={missingness}"
                    )
                evaluated_contexts.append(context)
                continue
            _populate_pct_change(context, provider)
            drop_reason = _evaluate_gates(context, thresholds)
            if drop_reason:
                drop_ledger.setdefault(symbol, drop_reason)
                print(f"[SCANNER][DROP] symbol={symbol} reason={drop_reason}")
                if event_collector is not None:
                    event_collector.emit(
                        event_type="SCANNER_SYMBOL_DROPPED",
                        source="Scanner",
                        payload={
                            "symbol": symbol,
                            "drop_reason": drop_reason,
                            "metric_value": {
                                "last_price": context.get("last_price"),
                                "pct_change": context.get("pct_change"),
                                "rvol": context.get("rvol"),
                                "volume": context.get("volume"),
                                "float_shares": context.get("float_shares"),
                                "spread_pct": context.get("spread_pct"),
                            },
                            "threshold": {
                                "min_pct_change": thresholds.min_pct_change,
                                "max_pct_change": thresholds.max_pct_change,
                                "min_rvol": thresholds.min_rvol,
                                "min_volume": thresholds.min_volume,
                                "min_premarket_volume": thresholds.min_premarket_volume,
                                "max_float": thresholds.max_float,
                                "spread_max_pct": thresholds.spread_max_pct,
                            },
                        },
                    )
                if get_config("DEBUG_SCANNER"):
                    missingness = _missingness_map(drop_reason, context)
                    print(
                        "[SCANNER][DEBUG] "
                        f"symbol={symbol} reason={drop_reason} missing={missingness}"
                    )
                evaluated_contexts.append(context)
                continue
            score, components = _score_context(context)
            context["scanner_score"] = score
            context["scanner_score_components"] = components
            candidates.append(context)
            keep_parts = [
                f"[SCANNER][KEEP] symbol={symbol}",
                f"last={_format_value(context.get('last_price'))}",
                f"final_pct={_format_value(context.get('pct_change'))}",
                f"pct_source={context.get('pct_source') or 'NA'}",
                f"vol={_format_int(context.get('volume'))}",
            ]
            bid = context.get("bid")
            ask = context.get("ask")
            spread = context.get("spread")
            if bid is not None:
                keep_parts.append(f"bid={_format_value(bid)}")
            if ask is not None:
                keep_parts.append(f"ask={_format_value(ask)}")
            if spread is not None:
                keep_parts.append(f"spread={_format_value(spread, 4)}")
            print(" ".join(keep_parts))
            evaluated_contexts.append(context)

        missing_pct = sum(1 for context in evaluated_contexts if context.get("pct_change") is None)
        if evaluated_contexts and missing_pct >= max(1, len(evaluated_contexts) // 2):
            print(
                "[SCANNER][WARN] Percent change missing for many symbols "
                f"missing={missing_pct} total={len(evaluated_contexts)}"
            )
        after_gates_symbols = [context["symbol"] for context in candidates]
        print(
            f"AFTER_GATES_SYMBOLS (N={len(after_gates_symbols)}): {after_gates_symbols}"
        )
        if event_collector is not None:
            event_collector.emit(
                event_type="AFTER_GATES_SYMBOLS",
                source="Scanner",
                payload={
                    "symbols": after_gates_symbols,
                    "count": len(after_gates_symbols),
                    "session": session_label,
                    "timestamp": utc_now.isoformat(),
                },
            )

        # Watchlist gate is created here from the raw scanner universe (cheap metrics only).
        print("[SCANNER][STAGE] watchlist")
        ranked = _rank_candidates(candidates)
        watchlist_limit = limits["watchlist_limit"]
        watchlist_contexts = ranked[:watchlist_limit] if watchlist_limit > 0 else []
        for context in ranked[watchlist_limit:]:
            drop_ledger.setdefault(context["symbol"], "DROP_RANK_BELOW_WATCHLIST")
            print(
                "[SCANNER][DROP] symbol="
                f"{context['symbol']} reason=DROP_RANK_BELOW_WATCHLIST"
            )
            if event_collector is not None:
                event_collector.emit(
                    event_type="SCANNER_SYMBOL_DROPPED",
                    source="Scanner",
                    payload={
                        "symbol": context["symbol"],
                        "drop_reason": "DROP_RANK_BELOW_WATCHLIST",
                        "metric_value": context.get("scanner_rank"),
                        "threshold": watchlist_limit,
                    },
                )
        if watchlist_limit > 0 and len(watchlist_contexts) < watchlist_limit:
            ranked_all = _rank_candidates(evaluated_contexts)
            existing = {context["symbol"] for context in watchlist_contexts}
            for context in ranked_all:
                symbol = context.get("symbol")
                if not symbol or symbol in existing:
                    continue
                drop_reason = drop_ledger.get(symbol)
                if drop_reason and not drop_reason.startswith("DROP_MISSING_"):
                    continue
                flags = context.setdefault("data_quality_flags", [])
                if "BACKFILL_OPTIONAL_DATA" not in flags:
                    flags.append("BACKFILL_OPTIONAL_DATA")
                if drop_reason:
                    drop_ledger.pop(symbol, None)
                watchlist_contexts.append(context)
                existing.add(symbol)
                print(
                    "[SCANNER][BACKFILL] symbol="
                    f"{symbol} reason={drop_reason or 'OPTIONAL_DATA'}"
                )
                if len(watchlist_contexts) >= watchlist_limit:
                    break

        print("[SCANNER][STAGE] enrich")
        watchlist_symbols = [context["symbol"] for context in watchlist_contexts]
        print(
            f"WATCHLIST_K_SELECTED (K={len(watchlist_symbols)}): {watchlist_symbols}"
        )
        if event_collector is not None:
            event_collector.emit(
                event_type="WATCHLIST_K_SELECTED",
                source="Scanner",
                payload={
                    "watchlist_k": watchlist_symbols,
                    "K": watchlist_limit,
                    "policy_name": resolved_policy.policy_name,
                },
            )
            event_collector.emit(
                event_type="SCANNER_WATCHLIST_K_READY",
                source="Scanner",
                payload={
                    "watchlist_k": watchlist_symbols,
                    "K": watchlist_limit,
                    "policy_name": resolved_policy.policy_name,
                },
            )
        allow_news = bool(get_config("NEWS_ENABLED")) and run_mode not in {
            RunMode.LIVE,
            RunMode.LIVE_READ_ONLY,
            RunMode.LIVE_MICRO,
            RunMode.PAPER,
        }
        if watchlist_symbols and allow_news:
            news_by_symbol, news_diag = _enrich_news_context(
                watchlist_symbols, provider.source_name
            )
        else:
            news_by_symbol = {}
            news_diag = NewsDiagnostics(False, False, None, 0, 0, {})
        diagnostics["news"] = {
            "news_degraded": news_diag.news_degraded,
            "news_gate_bypassed": news_diag.news_gate_bypassed,
            "rss_sources": news_diag.rss_sources,
            "rss_failures": news_diag.rss_failures,
            "rss_failure_summary": news_diag.rss_failure_summary,
            "rss_failure_reason": news_diag.failure_reason,
            "news_skipped": not allow_news,
        }
        if news_diag.news_degraded:
            for context in watchlist_contexts:
                flags = context.get("data_quality_flags", [])
                if "NEWS_DELAYED" not in flags:
                    flags.append("NEWS_DELAYED")

        print("[SCANNER][STAGE] print")
        fast_rows = _build_fast_rows(watchlist_contexts, news_by_symbol)
        focus_limit = limits["focus_limit"]
        focus_contexts = watchlist_contexts[:focus_limit]
        deep_rows = _build_deep_rows(focus_contexts, news_by_symbol)

        exclusion_counts = Counter(drop_ledger.values())
        drop_summary = dict(exclusion_counts)
        diagnostics["drop_ledger_summary"] = drop_summary
        print(
            "[SCANNER][SUMMARY] "
            f"candidates={len(symbols)} gated={len(candidates)} "
            f"watchlist={len(watchlist_contexts)} drops={drop_summary}"
        )

        watchlist_symbols = [context["symbol"] for context in watchlist_contexts]
        focus_symbols = [row.symbol for row in deep_rows]
        watchlist_hash = _watchlist_hash(watchlist_symbols, focus_symbols)
        watchlist_changed = watchlist_hash != _WATCHLIST_HASH
        print(
            "[SCANNER][DROP_SUMMARY] "
            f"topn={len(symbols)} evaluated={len(evaluated_contexts)} "
            f"dropped={len(drop_ledger)} reasons={drop_summary}"
        )
        candidate_metrics: List[CandidateMetrics] = []
        scanner_candidates: List[ScannerCandidate] = []
        for context in evaluated_contexts:
            symbol = context.get("symbol")
            news_context = news_by_symbol.get(symbol, {})
            scanner_candidates.append(
                _scanner_candidate_from_context(context, drop_reason=drop_ledger.get(symbol))
            )
            candidate_metrics.append(
                _candidate_from_context(
                    context,
                    news_context,
                    thresholds,
                    drop_reason=drop_ledger.get(symbol),
                    timestamp_utc=utc_now.isoformat(),
                )
            )
        candidate_lookup = {candidate.symbol: candidate for candidate in candidate_metrics}
        watchlist_metrics = [
            candidate_lookup[symbol]
            for symbol in watchlist_symbols
            if symbol in candidate_lookup
        ]
        focus_metrics = watchlist_metrics[: len(focus_symbols)]
        if _should_print_watchlist(
            watchlist_changed=watchlist_changed,
            session_label=session_label,
            cycle_count=_SCAN_CYCLE_COUNT,
        ):
            _print_watchlist_and_focus(
                watchlist_metrics,
                focus_metrics,
                session_label=session_label,
            )
            _LAST_PRINT_CYCLE = _SCAN_CYCLE_COUNT
        _WATCHLIST_HASH = watchlist_hash
        _LAST_SESSION_LABEL = session_label

        if watchlist_changed or session_label == "PRE":
            watchlist_dir = Path("output/watchlists")
            watchlist_dir.mkdir(parents=True, exist_ok=True)
            ts = utc_now.strftime("%Y%m%d_%H%M%S_UTC")
            file_path = watchlist_dir / f"watchlist_RossMomentum_{ts}.txt"
            header_lines = [
                f"# candidates_count={len(symbols)}",
                f"# gated_count={len(candidates)}",
                f"# watchlist_count={len(watchlist_contexts)}",
                f"# drop_reasons={dict(exclusion_counts)}",
            ]
            file_path.write_text(
                "\n".join(header_lines + [""] + format_fast_view_lines(fast_rows)) + "\n",
                encoding="utf-8",
            )
            date_prefix = utc_now.strftime("%Y%m%d_")
            for existing in watchlist_dir.glob(f"watchlist_RossMomentum_{date_prefix}*"):
                if existing == file_path:
                    continue
                try:
                    existing.unlink()
                except OSError:
                    continue

    finally:
        provider.disconnect()

    new_symbols = sorted(set(watchlist_symbols) - _PREV_WATCHLIST)
    continuing_symbols = sorted(set(watchlist_symbols) & _PREV_WATCHLIST)
    dropped_symbols = sorted(_PREV_WATCHLIST - set(watchlist_symbols))
    print_scanner_contract(
        topn_count=len(symbols),
        survivors_count=len(candidates),
        watchlist_k=watchlist_symbols,
        focus_m=focus_symbols,
        drop_summary=drop_summary,
        new_symbols=new_symbols,
        continuing_symbols=continuing_symbols,
        dropped_symbols=dropped_symbols,
    )
    _PREV_WATCHLIST.clear()
    _PREV_WATCHLIST.update(watchlist_symbols)

    return {
        "scanner_version": SCANNER_VERSION,
        "scanner_git_sha": SCANNER_GIT_SHA,
        "timestamp_utc": utc_now.isoformat(),
        "universe_top_n": universe_top_n,
        "symbols": [row.symbol for row in fast_rows],
        "watchlist": [row.symbol for row in fast_rows],
        "watchlist_rows": fast_rows,
        "focus_rows": deep_rows,
        "drop_ledger": drop_ledger,
        "watchlist_k": watchlist_metrics,
        "focus_m": focus_metrics,
        "watchlist_k_symbols": watchlist_symbols,
        "focus_m_symbols": focus_symbols,
        "candidates": scanner_candidates,
        "candidate_metrics": candidate_metrics,
        "scanner_result": ScannerResult(
            top_n_symbols=symbols,
            candidates=candidate_metrics,
            watchlist_k=watchlist_metrics,
            focus_m=focus_metrics,
            drops_by_reason=drop_summary,
            new_symbols=new_symbols,
            continuing_symbols=continuing_symbols,
            dropped_symbols=dropped_symbols,
        ),
        "topn_count": len(symbols),
        "survivors_count": len(candidates),
        "new_symbols": new_symbols,
        "continuing_symbols": continuing_symbols,
        "dropped_symbols": dropped_symbols,
        "drop_reason_summary": drop_summary,
        "data_quality_by_symbol": {
            row.symbol: list(row.data_quality_flags or []) for row in fast_rows
        },
        "diagnostics": diagnostics,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scanner runner")
    parser.add_argument("--mode", default="READONLY")
    parser.add_argument("--cycles", type=int, default=1)
    args = parser.parse_args()

    payload = {}
    for _ in range(args.cycles):
        payload = run_scanner_cycle(mode=args.mode)

    print("\n[SCANNER] Standalone scan complete")
    print(f"[SCANNER] Version: {payload.get('scanner_version')}")
    print(f"[SCANNER] Timestamp (UTC): {payload.get('timestamp_utc')}")
    print(f"[SCANNER] Watchlist size: {len(payload.get('watchlist', []))}")

    diagnostics = payload.get("diagnostics", {})
    news_diag = diagnostics.get("news", {})
    if news_diag:
        print(
            "[SCANNER][NEWS] RSS failures "
            f"{news_diag.get('rss_failures')}/{news_diag.get('rss_sources')} "
            f"reason={news_diag.get('rss_failure_reason')}"
        )
        print(f"[SCANNER][NEWS] RSS failure summary: {news_diag.get('rss_failure_summary')}")
        print(f"[SCANNER][NEWS] News gate bypassed: {news_diag.get('news_gate_bypassed')}")

    drop_ledger = payload.get("drop_ledger", {})
    if drop_ledger:
        print("\n[SCANNER][DROP_LEDGER]")
        for symbol, reason in sorted(drop_ledger.items()):
            print(f" - {symbol}: {reason}")

    print_fast_view(payload.get("watchlist_rows", []))
    print_deep_view(payload.get("focus_rows", []))
