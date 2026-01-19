from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
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
from src.news.news_fetcher import Headline, fetch_headlines_for_symbols
from src.news.verified_sources import load_verified_rss_sources

from src.scanner.contracts import (
    SCANNER_GIT_SHA,
    SCANNER_VERSION,
    StockSelectionPolicy,
    policy_from_config,
)
from src.scanner.phase24_views import (
    DeepViewRow,
    FastViewRow,
    format_fast_view_lines,
    print_deep_view,
    print_fast_view,
)
from src.scanner.print_contract import print_scanner_contract, summarize_drop_reasons
from src.scanner.providers.base import ScannerDataProvider
from src.scanner.providers.factory import build_provider
from src.scanner.providers.mock_provider import MockScannerProvider


_FLOAT_CACHE_STATE: Dict[str, Any] = {
    "as_of": None,
    "data": {},
}
_FLOAT_CACHE_REQUESTED: set[str] = set()
_HISTORY_CACHE: Dict[str, Dict[str, Any]] = {}
_NEWS_CACHE: Dict[str, Dict[str, Any]] = {}
_PREV_WATCHLIST: set[str] = set()
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
    print(
        "[SCANNER][LIMITS] Policy caps "
        f"top_gainers_n={policy.top_gainers_n} "
        f"watchlist_k={policy.watchlist_limit_k} "
        f"focus_m={policy.focus_limit_m} "
        f"max_symbols_per_cycle={policy.max_symbols_per_cycle}"
    )

    resolved = int(policy.top_gainers_n)
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


def _pct_change(last_price: Optional[float], prev_close: Optional[float]) -> Optional[float]:
    if last_price is None or prev_close is None or prev_close == 0:
        return None
    return round(((last_price - prev_close) / prev_close) * 100.0, 2)


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
        spread_max_pct=policy.spread_max,
        min_dollar_volume=policy.liquidity_min_dollar_volume,
        require_price=policy.data_quality_require_price,
        require_bid_ask=policy.data_quality_require_bid_ask,
    )


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

    if thresholds.require_price and price is None:
        return "DROP_MISSING_PRICE"
    if pct_change is None:
        return "DROP_MISSING_PCT_CHANGE"
    if pct_change < thresholds.min_pct_change:
        return "DROP_PCT_CHANGE"
    if thresholds.max_pct_change is not None and pct_change > thresholds.max_pct_change:
        return "DROP_PCT_CHANGE_MAX"
    if price is not None and not (thresholds.min_price <= price <= thresholds.max_price):
        return "DROP_PRICE_RANGE"
    if rvol is None:
        return "DROP_MISSING_RVOL"
    if rvol < thresholds.min_rvol:
        return "DROP_RVOL"
    if volume is None:
        return "DROP_MISSING_VOLUME"
    if session in {"PRE", "OVN"}:
        if volume < thresholds.min_premarket_volume:
            return "DROP_PREMARKET_VOLUME"
    elif volume < thresholds.min_volume:
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


def _score_context(context: Dict[str, Any]) -> float:
    pct = _safe_float(context.get("pct_change"), 0.0) or 0.0
    rvol = _safe_float(context.get("rvol"), 0.0) or 0.0
    dvol = _safe_float(context.get("dollar_volume"), 0.0) or 0.0
    pct_n = min(max(pct / 20.0, 0.0), 2.0)
    rvol_n = min(max(rvol / 5.0, 0.0), 2.0)
    dvol_n = min(max(dvol / 1_000_000.0, 0.0), 2.0)
    score = (0.45 * pct_n) + (0.35 * rvol_n) + (0.20 * dvol_n)
    return round(min(score, 1.0) * 100.0, 2)


def _build_symbol_context(
    provider: ScannerDataProvider,
    symbol: str,
    session_label: str,
    float_cache: Dict[str, int],
) -> Optional[Dict[str, Any]]:
    try:
        quote = provider.get_quote(symbol)
    except Exception:
        return None

    data_quality_flags = list(getattr(quote, "data_quality_flags", []) or [])
    last_price = _resolve_price(quote)
    spread, spread_pct = _spread_values(quote)

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
    if prev_close is None:
        history = _history_snapshot(symbol, provider)
        prev_close = history.get("prev_close")
    if prev_close is None:
        data_quality_flags.append("HISTORY_UNKNOWN")

    pct_change = _pct_change(last_price, prev_close)
    dollar_volume = None
    if last_price is not None and volume is not None:
        dollar_volume = round(last_price * volume, 2)

    float_shares = float_cache.get(symbol)
    if float_shares is None:
        data_quality_flags.append("FLOAT_UNKNOWN")

    if spread is None:
        data_quality_flags.append("SPREAD_UNKNOWN")

    return {
        "symbol": symbol,
        "session": session_label,
        "last_price": last_price,
        "pct_change": pct_change,
        "volume": volume,
        "dollar_volume": dollar_volume,
        "bid": quote.bid,
        "ask": quote.ask,
        "spread": spread,
        "spread_pct": spread_pct,
        "rvol": rvol,
        "float_shares": float_shares,
        "data_quality_flags": data_quality_flags,
    }


def run_scanner_cycle(
    mode: str = "integrated",
    policy: StockSelectionPolicy | None = None,
) -> Dict[str, Any]:
    utc_now = _utc_now()
    session_label = _market_session_label_utc(utc_now)
    diagnostics: Dict[str, Any] = {"mode": mode}
    drop_ledger: Dict[str, str] = {}
    print(f"[SCANNER] MODE={mode} SESSION={session_label}")
    scanner_mode = str(get_config("SCANNER_MODE"))
    policy_source = "strategy" if policy is not None else "config_fallback"
    resolved_policy = policy or policy_from_config()
    print(
        "[SCANNER][POLICY] source={source} policy_name={policy_name} price={price_min}-{price_max} "
        "gap_min={gap_min} rvol_min={rvol_min} float_max_millions={float_max} "
        "spread_max={spread_max} watchlist_k={watchlist_k} focus_m={focus_m}".format(
            source=policy_source,
            policy_name=resolved_policy.policy_name,
            price_min=resolved_policy.price_min,
            price_max=resolved_policy.price_max,
            gap_min=resolved_policy.gap_min_pct,
            rvol_min=resolved_policy.rvol_min,
            float_max=resolved_policy.float_max_millions,
            spread_max=resolved_policy.spread_max,
            watchlist_k=resolved_policy.watchlist_limit_k,
            focus_m=resolved_policy.focus_limit_m,
        )
    )
    if scanner_mode == "TEACHING":
        limits = _print_symbol_limits(scanner_mode, "TEACHING", resolved_policy)
        diagnostics["symbol_limits"] = limits
        diagnostics["provider_source"] = "TEACHING"
        print("[SCANNER][STAGE] teaching")
        print("[SCANNER][TEACHING] Static watchlist — no IBKR connection or market data calls")
        symbols = list(get_config("SCANNER_DEFAULT_SYMBOLS") or [])
        if not symbols:
            symbols = ["AAPL"]
        symbols = [symbol.upper() for symbol in symbols][: limits["resolved_symbol_limit"]]
        fast_rows: List[FastViewRow] = []
        for idx, symbol in enumerate(symbols, start=1):
            fast_rows.append(
                FastViewRow(
                    symbol=symbol,
                    session=session_label,
                    last_price=None,
                    pct_change=None,
                    volume=None,
                    dollar_volume=None,
                    bid=None,
                    ask=None,
                    spread=None,
                    spread_pct=None,
                    rvol=None,
                    float_shares=None,
                    scanner_rank=idx,
                    scanner_score=None,
                    drop_reason=None,
                    data_quality_flags=["TEACHING_STATIC"],
                    news_present=False,
                    catalyst_type=None,
                    dilution_flag=False,
                    news_age_minutes=None,
                    velocity_5m=None,
                    velocity_10m=None,
                    velocity_30m=None,
                    attention_tier=None,
                    gam_ea_eligible=None,
                )
            )
        watchlist_limit = limits["watchlist_limit"]
        if watchlist_limit and len(fast_rows) > watchlist_limit:
            for row in fast_rows[watchlist_limit:]:
                drop_ledger.setdefault(row.symbol, "DROP_RANK_BELOW_WATCHLIST")
                print(
                    "[SCANNER][DROP] symbol="
                    f"{row.symbol} reason=DROP_RANK_BELOW_WATCHLIST"
                )
            fast_rows = fast_rows[:watchlist_limit]
        focus_limit = limits["focus_limit"]
        deep_rows = [
            DeepViewRow(
                symbol=row.symbol,
                focus_rank=idx,
                links=[],
                catalyst_rationale="Teaching mode static candidate.",
                focus_reason="Teaching mode static watchlist.",
            )
            for idx, row in enumerate(fast_rows[:focus_limit], start=1)
        ]
        drop_summary = summarize_drop_reasons(drop_ledger)
        print(
            "[SCANNER][SUMMARY] "
            f"candidates={len(symbols)} gated={len(symbols)} "
            f"watchlist={len(fast_rows)} drops={drop_summary}"
        )
        watchlist_symbols = [row.symbol for row in fast_rows]
        focus_symbols = [row.symbol for row in deep_rows]
        new_symbols = sorted(set(watchlist_symbols) - _PREV_WATCHLIST)
        continuing_symbols = sorted(set(watchlist_symbols) & _PREV_WATCHLIST)
        dropped_symbols = sorted(_PREV_WATCHLIST - set(watchlist_symbols))
        print_scanner_contract(
            topn_count=len(symbols),
            survivors_count=len(symbols),
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
            "symbols": [row.symbol for row in fast_rows],
            "watchlist": [row.symbol for row in fast_rows],
            "watchlist_rows": fast_rows,
            "focus_rows": deep_rows,
            "drop_ledger": drop_ledger,
            "watchlist_k": watchlist_symbols,
            "focus_m": focus_symbols,
            "topn_count": len(symbols),
            "survivors_count": len(symbols),
            "new_symbols": new_symbols,
            "continuing_symbols": continuing_symbols,
            "dropped_symbols": dropped_symbols,
            "drop_reason_summary": drop_summary,
            "data_quality_by_symbol": {
                row.symbol: list(row.data_quality_flags or []) for row in fast_rows
            },
            "diagnostics": diagnostics,
        }

    provider: ScannerDataProvider = build_provider()
    limits = _print_symbol_limits(scanner_mode, provider.source_name, resolved_policy)
    diagnostics["symbol_limits"] = limits
    print("[SCANNER][STAGE] bootstrap")

    try:
        try:
            symbols = provider.get_top_gainers(limits["resolved_symbol_limit"])
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
                limits = _print_symbol_limits(scanner_mode, provider.source_name, resolved_policy)
                diagnostics["symbol_limits"] = limits
            symbols = provider.get_top_gainers(limits["resolved_symbol_limit"])

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

        float_cache = _bootstrap_float_cache(symbols, provider)
        thresholds = _gate_thresholds(resolved_policy)
        candidates: List[Dict[str, Any]] = []

        print("[SCANNER][STAGE] gates")
        for symbol in symbols:
            context = _build_symbol_context(provider, symbol, session_label, float_cache)
            if context is None:
                drop_ledger.setdefault(symbol, "DROP_QUOTE_UNAVAILABLE")
                print(f"[SCANNER][DROP] symbol={symbol} reason=DROP_QUOTE_UNAVAILABLE")
                continue
            drop_reason = _evaluate_gates(context, thresholds)
            if drop_reason:
                drop_ledger.setdefault(symbol, drop_reason)
                print(f"[SCANNER][DROP] symbol={symbol} reason={drop_reason}")
                continue
            context["scanner_score"] = _score_context(context)
            candidates.append(context)

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

        print("[SCANNER][STAGE] enrich")
        watchlist_symbols = [context["symbol"] for context in watchlist_contexts]
        news_by_symbol, news_diag = (
            _enrich_news_context(watchlist_symbols, provider.source_name)
            if watchlist_symbols
            else ({}, NewsDiagnostics(False, False, None, 0, 0, {}))
        )
        diagnostics["news"] = {
            "news_degraded": news_diag.news_degraded,
            "news_gate_bypassed": news_diag.news_gate_bypassed,
            "rss_sources": news_diag.rss_sources,
            "rss_failures": news_diag.rss_failures,
            "rss_failure_summary": news_diag.rss_failure_summary,
            "rss_failure_reason": news_diag.failure_reason,
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

    finally:
        provider.disconnect()

    watchlist_symbols = [row.symbol for row in fast_rows]
    focus_symbols = [row.symbol for row in deep_rows]
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
        "symbols": [row.symbol for row in fast_rows],
        "watchlist": [row.symbol for row in fast_rows],
        "watchlist_rows": fast_rows,
        "focus_rows": deep_rows,
        "drop_ledger": drop_ledger,
        "watchlist_k": watchlist_symbols,
        "focus_m": focus_symbols,
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
