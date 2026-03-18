from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, time as dtime, timedelta, timezone
import hashlib
import json
import logging
from pathlib import Path
import sys
import time
from zoneinfo import ZoneInfo
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

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
from src.data.float_discovery_worker import get_float_discovery_worker
from src.news.news_fetcher import Headline, fetch_fast_headlines_for_symbols
from src.news.rss_registry import RSS_FAST_TRADING
from src.preparation.context_builder import SymbolContext, build_symbol_context
from src.preparation.event_driven_refresh import RuntimeContextRegistry

from src.scanner.contracts import (
    SCANNER_GIT_SHA,
    SCANNER_VERSION,
    StockSelectionPolicy,
    policy_from_config,
)
from src.scanner.scanner_contract import (
    ScannerRequest,
    scanner_request_from_policy,
    validate_scanner_request,
)
from src.prep.premarket_prep_artifact import load_canonical_premarket_prep_artifact
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
from src.scanner.ranking_registry import resolve_watchlist_selector
from src.scanner.result_models import CandidateMetrics, ScannerResult
from src.scanner.reference_resolver import resolve_reference_bundle
from src.market_data.market_snapshot_enricher import MarketSnapshotEnricher
from src.scanner.candidate_identity import CandidateIdentity

from src.scanner.session_pct_change import (
    canonical_session_label,
    compute_phase_aware_rvol,
    compute_scanner_rvol,
    compute_session_aligned_pct_change,
    compute_session_relative_volume_with_provenance,
    normalize_session_label,
    resolve_market_session_context,
    resolve_market_session_label,
    resolve_session_diagnostics,
)


_FLOAT_CACHE_STATE: Dict[str, Any] = {
    "mtime_ns": None,
    "data": {},
}
_FLOAT_SOURCE_BY_SYMBOL: Dict[str, str] = {}
_FLOAT_CACHE_HIT_SYMBOLS: set[str] = set()
_HISTORY_CACHE: Dict[str, Dict[str, Any]] = {}
_NEWS_CACHE: Dict[str, Dict[str, Any]] = {}
_PREV_WATCHLIST: set[str] = set()
_WATCHLIST_HASH: Optional[str] = None
_LAST_SESSION_LABEL: Optional[str] = None
_SCAN_CYCLE_COUNT = 0
_LAST_PRINT_CYCLE = 0
_LAST_BROKER_SCAN_TS: float | None = None
_LAST_SCANNER_PAYLOAD: Dict[str, Any] | None = None
NEWS_AGE_MAX_MINUTES = 360
ETF_EXCLUDED_SYMBOLS = {"SPY", "QQQ", "DIA", "IWM"}
NY_TZ = ZoneInfo("America/New_York")


def _context_identity(context: Dict[str, Any]) -> CandidateIdentity:
    return CandidateIdentity.from_mapping({
        "symbol": context.get("symbol"),
        "conId": context.get("con_id") or context.get("conId"),
        "secType": context.get("instrument_type") or context.get("secType") or "STK",
        "exchange": context.get("exchange") or "SMART",
        "primaryExchange": context.get("primary_exchange") or context.get("exchange"),
        "tradingClass": context.get("trading_class"),
        "currency": context.get("currency") or "USD",
        "localSymbol": context.get("local_symbol"),
    })


def _history_symbol_keys(symbol: str, context: Dict[str, Any] | None = None) -> list[str]:
    keys: list[str] = []
    values = [symbol]
    if context is not None:
        values.extend([context.get("local_symbol"), context.get("trading_class")])
    for value in values:
        normalized = str(value or "").upper().strip()
        if normalized and normalized not in keys:
            keys.append(normalized)
    return keys


def _enrichment_audit_summary(evaluated_contexts: list[Dict[str, Any]]) -> dict[str, int]:
    return {
        "candidates": len(evaluated_contexts),
        "snapshot_ok": sum(1 for c in evaluated_contexts if any(c.get(k) is not None for k in ("last_price", "bid", "ask", "volume", "close"))),
        "reference_ok": sum(1 for c in evaluated_contexts if c.get("reference_price") is not None),
        "pct_ready": sum(1 for c in evaluated_contexts if c.get("pct_change") is not None),
        "gap_ready": sum(1 for c in evaluated_contexts if c.get("gap_pct_resolved") is not None),
        "rvol_ready": sum(1 for c in evaluated_contexts if c.get("rvol_discovery") is not None or c.get("rvol_phase") is not None),
        "float_ready": sum(1 for c in evaluated_contexts if c.get("float_shares") is not None),
        "identity_merge_failures": sum(1 for c in evaluated_contexts if c.get("identity_merge_failed")),
    }


def _gate_outcome_summary(watchlist_contexts: list[Dict[str, Any]]) -> dict[str, int]:
    return {
        "true_gate_pass_count": sum(1 for c in watchlist_contexts if not c.get("prep_seeded") and str(c.get("promotion_reason") or "LIVE_SCAN") != "PREP_CONTEXT_BACKFILL"),
        "backfill_count": sum(1 for c in watchlist_contexts if str(c.get("promotion_reason") or "") == "PREP_CONTEXT_BACKFILL"),
        "seeded_count": sum(1 for c in watchlist_contexts if c.get("prep_seeded")),
    }

CATALYST_KEYWORDS = {
    "earnings": "EARNINGS",
    "guidance": "EARNINGS",
    "fda": "FDA",
    "approval": "FDA",
    "contract": "CONTRACT",
    "partnership": "CONTRACT",
    "upgrade": "ANALYST_ACTION",
    "downgrade": "ANALYST_ACTION",
    "initiates": "ANALYST_ACTION",
    "press release": "PRESS_RELEASE",
    "ai": "TECH_CATALYST",
    "artificial intelligence": "TECH_CATALYST",
    "crypto": "CRYPTO_CATALYST",
    "bitcoin": "CRYPTO_CATALYST",
    "ev": "EV_CATALYST",
    "electric vehicle": "EV_CATALYST",
    "battery": "EV_CATALYST",
    "defense": "DEFENSE_CATALYST",
    "military": "DEFENSE_CATALYST",
    "quantum": "TECH_CATALYST",
    "semiconductor": "TECH_CATALYST",
    "gpu": "TECH_CATALYST",
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
    watchlist_rvol_min: float
    focus_rvol_min: float
    focus_volume_min: int
    focus_volume_min_early_rth: int
    focus_volume_min_early_rth_ratio: float
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
    allow_unknown_float: bool


@dataclass(frozen=True)
class RuntimeThresholdResolution:
    watchlist_rvol_min: float
    watchlist_rvol_source: str
    focus_rvol_min: float
    focus_rvol_source: str
    spread_max_pct: Optional[float]
    spread_max_pct_source: str
    allow_unknown_float: bool
    allow_unknown_float_source: str


@dataclass(frozen=True)
class NewsDiagnostics:
    news_degraded: bool
    news_gate_bypassed: bool
    failure_reason: Optional[str]
    rss_sources: int
    rss_failures: int
    rss_failure_summary: Dict[str, Dict[str, int]]


@dataclass
class RossSymbolState:
    symbol: str
    current_rank: Optional[int] = None
    last_rank: Optional[int] = None
    first_seen_utc: str = ""
    last_seen_utc: str = ""
    last_session: str = ""
    evaluation_stale_after_cycle: int = 0
    last_evaluated_cycle: int = 0
    watch_pass_reasons: list[str] = field(default_factory=list)
    focus_ready_reasons: list[str] = field(default_factory=list)
    rejection_reason: Optional[str] = None
    rejection_stale_after_cycle: int = 0
    float_class: Optional[str] = None


@dataclass
class RossDailyState:
    trading_day: str
    top_universe: Dict[str, RossSymbolState] = field(default_factory=dict)
    watchlist_k: Dict[str, RossSymbolState] = field(default_factory=dict)
    focus_m: Dict[str, RossSymbolState] = field(default_factory=dict)
    rejected_tracked: Dict[str, RossSymbolState] = field(default_factory=dict)


_ROSS_DAILY_STATE: Optional[RossDailyState] = None
_PERSISTENT_PROVIDER: ScannerDataProvider | None = None
_PERSISTENT_PROVIDER_SOURCE: str | None = None
_RUNTIME_CONTEXT_REGISTRY = RuntimeContextRegistry()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def reset_scanner_runtime_state(*, clear_persistent_provider: bool = True) -> None:
    """Reset scanner module runtime globals to avoid cross-test/runtime leakage."""
    global _WATCHLIST_HASH, _LAST_SESSION_LABEL, _SCAN_CYCLE_COUNT, _LAST_PRINT_CYCLE, _PERSISTENT_PROVIDER, _PERSISTENT_PROVIDER_SOURCE, _ROSS_DAILY_STATE, _LAST_BROKER_SCAN_TS, _LAST_SCANNER_PAYLOAD
    _PREV_WATCHLIST.clear()
    _WATCHLIST_HASH = None
    _LAST_SESSION_LABEL = None
    _SCAN_CYCLE_COUNT = 0
    _LAST_PRINT_CYCLE = 0
    _LAST_BROKER_SCAN_TS = None
    _LAST_SCANNER_PAYLOAD = None
    _ROSS_DAILY_STATE = None
    if clear_persistent_provider:
        if _PERSISTENT_PROVIDER is not None:
            try:
                _PERSISTENT_PROVIDER.disconnect()
            except Exception:
                pass
        _PERSISTENT_PROVIDER = None
        _PERSISTENT_PROVIDER_SOURCE = None


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
    return resolve_market_session_label(now)


def _market_session_context_utc(now: datetime):
    return resolve_market_session_context(now)


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
        "[SCANNER][LIMITS] "
        f"requested_top_n={resolved_top_n} requested_top_n_source=scanner_request_or_policy "
        f"broker_rows_requested={resolved} broker_rows_source=resolved_symbol_limit "
        f"effective_internal_processing_limit={resolved} effective_limit_source=resolved_symbol_limit "
        f"reductions={reductions or ['none']}"
    )
    print(f"[SCANNER][LIMITS] Focus list limit={focus_limit}")

    _LAST_SCANNER_PAYLOAD = {
        "resolved_symbol_limit": resolved,
        "reductions": reductions,
        "watchlist_limit": watchlist_limit,
        "focus_limit": focus_limit,
    }
    return _LAST_SCANNER_PAYLOAD


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


def _load_float_cache(path: Path) -> Dict[str, Dict[str, Any]]:
    try:
        if not path.exists():
            print(f"[FLOAT][CACHE_LOAD] path={path.resolve()} entries=0")
            return {}
        data = path.read_text(encoding="utf-8")
        parsed = json.loads(data)
        if isinstance(parsed, dict):
            parsed.pop("_meta", None)
            normalized: Dict[str, Dict[str, Any]] = {}
            for k, v in parsed.items():
                if isinstance(v, dict):
                    value = v.get("float")
                    if value is None:
                        value = v.get("float_value")
                    if not isinstance(value, (int, float)):
                        continue
                    source = v.get("source")
                    if source is None:
                        source = v.get("float_source")
                    timestamp = v.get("timestamp")
                    if timestamp is None:
                        timestamp = v.get("float_asof")
                    if source is None:
                        print(f"[FLOAT][PROVENANCE] symbol={k} reason=schema_invalid detail=missing_source")
                        continue
                    if isinstance(timestamp, str):
                        try:
                            parsed_asof = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                            if parsed_asof.tzinfo is None:
                                parsed_asof = parsed_asof.replace(tzinfo=timezone.utc)
                            if datetime.now(timezone.utc) - parsed_asof > timedelta(days=7):
                                print(f"[FLOAT][PROVENANCE] symbol={k} reason=stale tolerated=True")
                        except ValueError:
                            pass
                    normalized[k] = {
                        "float_value": int(value),
                        "float_source": str(source),
                        "float_asof": timestamp,
                    }
            print(f"[FLOAT][CACHE_LOAD] path={path.resolve()} entries={len(normalized)}")
            return normalized
    except Exception:
        print(f"[FLOAT][CACHE_LOAD] path={path.resolve()} entries=0")
        return {}
    print(f"[FLOAT][CACHE_LOAD] path={path.resolve()} entries=0")
    return {}


def _resolve_float_cache_path() -> Path:
    path = Path("data/reference/float_cache.json")
    print(f"[FLOAT][CACHE_PATH] path={path.resolve()}")
    return path


def _bootstrap_float_cache(
    symbols: Iterable[str],
    provider: ScannerDataProvider,
) -> Dict[str, Dict[str, Any]]:
    global _FLOAT_CACHE_STATE, _FLOAT_SOURCE_BY_SYMBOL, _FLOAT_CACHE_HIT_SYMBOLS
    cache_path = _resolve_float_cache_path()

    file_mtime_ns = None
    if cache_path.exists():
        try:
            file_mtime_ns = cache_path.stat().st_mtime_ns
        except Exception:
            file_mtime_ns = None

    if _FLOAT_CACHE_STATE.get("mtime_ns") != file_mtime_ns:
        _FLOAT_CACHE_STATE = {"mtime_ns": file_mtime_ns, "data": _load_float_cache(cache_path)}

    float_cache: Dict[str, Dict[str, Any]] = _FLOAT_CACHE_STATE.get("data", {})
    worker = get_float_discovery_worker(cache_path)
    _FLOAT_SOURCE_BY_SYMBOL = {}
    _FLOAT_CACHE_HIT_SYMBOLS = set()

    requested = 0
    cache_hits = 0
    unknown_tolerated = 0
    discovery_queued = 0

    for symbol in symbols:
        requested += 1
        cached = float_cache.get(symbol)
        if isinstance(cached, dict) and isinstance(cached.get("float_value"), int):
            cache_hits += 1
            value = int(cached.get("float_value"))
            source = str(cached.get("float_source") or "CACHE")
            _FLOAT_CACHE_HIT_SYMBOLS.add(symbol)
            _FLOAT_SOURCE_BY_SYMBOL[symbol] = source
            print(
                "[FLOAT][RESOLVE] "
                f"symbol={symbol} source=CACHE value={round(value / 1_000_000.0, 2)}M"
            )
            continue

        _FLOAT_SOURCE_BY_SYMBOL[symbol] = "UNKNOWN"
        unknown_tolerated += 1
        if symbol not in float_cache:
            reason = "cache_missing" if not cache_path.exists() else "json_miss"
        else:
            reason = "schema_invalid"
        print(f"[FLOAT][PROVENANCE] symbol={symbol} reason={reason}")
        print(f"[FLOAT][RESOLVE] symbol={symbol} source=UNKNOWN tolerated=True")
        if worker.enqueue(symbol):
            discovery_queued += 1
            print(f"[FLOAT][QUEUE] symbol={symbol} queued_for_discovery")
            print(f"[FLOAT][RESOLVE] symbol={symbol} source=DISCOVERY_QUEUED")

    _FLOAT_CACHE_STATE["data"] = float_cache
    print(
        "[FLOAT][SUMMARY] "
        f"requested={requested} cache_hits={cache_hits} "
        f"unknown_tolerated={unknown_tolerated} discovery_queued={discovery_queued}"
    )
    return float_cache


def _allow_history_enrichment(provider: ScannerDataProvider | None = None) -> bool:
    run_mode = get_run_mode()
    if run_mode in {RunMode.SIM, RunMode.PAPER}:
        return True
    if provider is not None:
        provider_name = type(provider).__name__
        if provider_name != "IbkrScannerProvider":
            return True
    return bool(get_config("HISTORICAL_ENRICH_ENABLED"))


def _history_snapshot(symbol: str, provider: ScannerDataProvider, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not _allow_history_enrichment(provider):
        return {"prev_close": None, "average_daily_volume_20d": None, "average_daily_volume_window_days": None, "lookup_key": symbol}
    for lookup_key in _history_symbol_keys(symbol, context):
        cached = _HISTORY_CACHE.get(lookup_key)
        if cached:
            return cached
    snapshot: Dict[str, Any] = {"prev_close": None, "average_daily_volume_20d": None, "average_daily_volume_window_days": None, "lookup_key": symbol}
    for lookup_key in _history_symbol_keys(symbol, context):
        snapshot["lookup_key"] = lookup_key
        if snapshot["prev_close"] is None:
            try:
                snapshot["prev_close"] = provider.get_prev_close(lookup_key)
            except Exception:
                snapshot["prev_close"] = None
        if snapshot["average_daily_volume_20d"] is None:
            try:
                intraday = provider.get_intraday_stats(lookup_key)
                snapshot["average_daily_volume_20d"] = intraday.average_daily_volume_20d
                snapshot["average_daily_volume_window_days"] = intraday.average_daily_volume_window_days
            except Exception:
                pass
        if snapshot["prev_close"] is not None or snapshot["average_daily_volume_20d"] is not None:
            break
    for lookup_key in _history_symbol_keys(symbol, context):
        _HISTORY_CACHE[lookup_key] = dict(snapshot)
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


def _resolve_pct_change_min_for_session(session: str, thresholds: GateThresholds) -> float:
    normalized = normalize_session_label(session)
    if normalized in {"PRE", "OVN"}:
        return float(thresholds.min_pct_change)
    print("[ROSS][GATE] session=RTH pct_change_min=5")
    return 5.0


def _ensure_provider_connection(provider: ScannerDataProvider, *, max_attempts: int = 4) -> None:
    delay_s = 0.5
    for attempt in range(1, max_attempts + 1):
        try:
            provider.connect()
            print("[IBKR][MD] heartbeat ok")
            return
        except ProviderConnectionError:
            if attempt >= max_attempts:
                raise
            time.sleep(delay_s)
            delay_s = min(delay_s * 2.0, 8.0)


def _resolve_runtime_thresholds(policy: StockSelectionPolicy, session_label: str | None = None) -> RuntimeThresholdResolution:
    watchlist_override = get_config_record("WATCHLIST_RVOL_MIN")
    focus_override = get_config_record("FOCUS_RVOL_MIN")
    spread_override = get_config_record("MAX_SPREAD_PCT")
    allow_unknown_float_override = get_config_record("ALLOW_UNKNOWN_FLOAT")

    normalized = normalize_session_label(session_label or "PRE")
    canonical = canonical_session_label(normalized)
    watchlist_policy = dict(getattr(policy, "session_watchlist_rvol_min", {}) or {})
    focus_policy = dict(getattr(policy, "session_focus_rvol_min", {}) or {})
    watchlist_default = float(
        watchlist_policy.get(normalized, watchlist_policy.get(canonical, getattr(policy, "watchlist_rvol_min", 0.5)))
    )
    focus_default = float(
        focus_policy.get(normalized, focus_policy.get(canonical, getattr(policy, "focus_rvol_min", getattr(policy, "rvol_min", 2.0))))
    )
    spread_default = getattr(policy, "spread_max_pct", None)

    watchlist_rvol_min = watchlist_default
    watchlist_source = "STRATEGY"
    if watchlist_override.value is not None:
        watchlist_rvol_min = float(watchlist_override.value)
        watchlist_source = watchlist_override.source

    focus_rvol_min = focus_default
    focus_source = "STRATEGY"
    if focus_override.value is not None:
        focus_rvol_min = float(focus_override.value)
        focus_source = focus_override.source

    spread_max_pct = spread_default
    spread_source = "STRATEGY"
    if spread_override.value is not None:
        spread_max_pct = float(spread_override.value)
        spread_source = spread_override.source

    allow_unknown_float = bool(allow_unknown_float_override.value)
    allow_unknown_float_source = allow_unknown_float_override.source

    return RuntimeThresholdResolution(
        watchlist_rvol_min=watchlist_rvol_min,
        watchlist_rvol_source=watchlist_source,
        focus_rvol_min=focus_rvol_min,
        focus_rvol_source=focus_source,
        spread_max_pct=spread_max_pct,
        spread_max_pct_source=spread_source,
        allow_unknown_float=allow_unknown_float,
        allow_unknown_float_source=allow_unknown_float_source,
    )


def _gate_thresholds(policy: StockSelectionPolicy, runtime: RuntimeThresholdResolution) -> GateThresholds:
    execution_min_volume = int(policy.min_volume)
    premarket_min_volume = int(getattr(policy, "premarket_volume_min", policy.min_premarket_volume))
    early_rth_focus_ratio = 0.25
    early_rth_focus_min = max(premarket_min_volume, int(execution_min_volume * early_rth_focus_ratio))
    return GateThresholds(
        min_price=policy.price_min,
        max_price=policy.price_max,
        min_pct_change=policy.gap_min_pct,
        max_pct_change=policy.gap_max_pct,
        watchlist_rvol_min=runtime.watchlist_rvol_min,
        focus_rvol_min=runtime.focus_rvol_min,
        focus_volume_min=execution_min_volume,
        focus_volume_min_early_rth=early_rth_focus_min,
        focus_volume_min_early_rth_ratio=early_rth_focus_ratio,
        min_volume=execution_min_volume,
        min_premarket_volume=premarket_min_volume,
        max_float=int(policy.float_max_millions * 1_000_000),
        spread_max_pct=runtime.spread_max_pct,
        min_dollar_volume=policy.liquidity_min_dollar_volume,
        require_price=policy.data_quality_require_price,
        require_bid_ask=policy.data_quality_require_bid_ask,
        require_catalyst=policy.require_catalyst,
        allow_halts=policy.allow_halts,
        allow_ssr=policy.allow_ssr,
        allow_unknown_float=runtime.allow_unknown_float,
    )


def _gate_checks(
    context: Dict[str, Any],
    thresholds: GateThresholds,
    *,
    catalyst_present: Optional[bool] = None,
) -> Dict[str, bool]:
    watchlist_checks = _watchlist_gate_checks(context, thresholds)
    focus_checks = _focus_gate_checks(context, thresholds)
    catalyst_ok = True
    if thresholds.require_catalyst:
        catalyst_ok = bool(catalyst_present)
    return {
        "watch_pct_change": watchlist_checks.get("pct_change_ok", False),
        "watch_rvol": watchlist_checks.get("rvol_ok", False),
        "watch_float": watchlist_checks.get("float_ok", False),
        "focus_volume": focus_checks.get("volume_ok", False),
        "focus_spread": focus_checks.get("spread_ok", False),
        "focus_bid_ask": focus_checks.get("bid_ask_ok", False),
        "focus_halt": focus_checks.get("halt_ok", False),
        "focus_ssr": focus_checks.get("ssr_ok", False),
        "focus_dollar_volume": focus_checks.get("dollar_volume_ok", False),
        "catalyst_ok": catalyst_ok,
    }


def _evaluate_price_gate(
    context: Dict[str, Any],
    thresholds: GateThresholds,
) -> Optional[str]:
    price = _safe_float(context.get("last_price"), None)
    snapshot_fetch_attempted = bool(context.get("snapshot_fetch_attempted"))
    if thresholds.require_price and price is None and snapshot_fetch_attempted:
        return "DROP_MISSING_PRICE"
    return None


def _evaluate_gates(
    context: Dict[str, Any],
    thresholds: GateThresholds,
) -> Optional[str]:
    drop_reason = _evaluate_price_gate(context, thresholds)
    if drop_reason:
        return drop_reason
    drop_reason = _evaluate_watchlist_gates(context, thresholds)
    if drop_reason == "DROP_FLOAT_MISSING":
        drop_reason = None
    if drop_reason:
        return drop_reason
    return _evaluate_focus_gates(context, thresholds)


def _watchlist_gate_checks(
    context: Dict[str, Any],
    thresholds: GateThresholds,
) -> Dict[str, bool]:
    pct_change = _safe_float(context.get("pct_change"), None)
    _, scanner_rvol = _resolve_rvol_for_focus_gate(context)
    float_shares = context.get("float_shares")

    pct_ok = pct_change is not None and pct_change >= thresholds.min_pct_change
    if thresholds.max_pct_change is not None:
        pct_ok = pct_ok and pct_change is not None and pct_change <= thresholds.max_pct_change
    rvol_ok = scanner_rvol is not None and scanner_rvol >= thresholds.watchlist_rvol_min
    # Float can be legitimately missing on fallback/mock providers; treat missing
    # as soft-pass so deterministic fallback universes still produce candidates.
    float_ok = float_shares is None or float_shares <= thresholds.max_float

    return {
        "pct_change_ok": pct_ok,
        "rvol_ok": rvol_ok,
        "float_ok": float_ok,
    }


def _focus_gate_checks(
    context: Dict[str, Any],
    thresholds: GateThresholds,
) -> Dict[str, bool]:
    volume = _safe_float(context.get("volume"), None)
    premarket_volume = _safe_float(context.get("premarket_volume"), None)
    dollar_volume = _safe_float(context.get("dollar_volume"), None)
    session = normalize_session_label(str(context.get("session") or ""))
    spread_pct = _safe_float(context.get("spread_pct"), None)
    bid = _safe_float(context.get("bid"), None)
    ask = _safe_float(context.get("ask"), None)
    halted = context.get("halted")
    ssr = context.get("ssr")

    volume_ok = volume is not None and volume > 0
    if session in {"PRE", "OVN"}:
        volume_ok = volume is not None and volume >= thresholds.min_premarket_volume
    elif session == "RTH_OPEN":
        volume_ok = volume is not None and volume >= thresholds.focus_volume_min_early_rth
    else:
        volume_ok = volume is not None and volume >= thresholds.focus_volume_min

    dollar_volume_ok = True
    if thresholds.min_dollar_volume is not None:
        dollar_volume_ok = dollar_volume is not None and dollar_volume >= thresholds.min_dollar_volume

    spread_ok = True
    if thresholds.spread_max_pct is not None:
        spread_ok = spread_pct is not None and spread_pct <= thresholds.spread_max_pct

    bid_ask_ok = True
    if thresholds.require_bid_ask:
        bid_ask_ok = bid is not None and ask is not None

    halt_ok = not (halted is True and not thresholds.allow_halts)
    ssr_ok = not (ssr is True and not thresholds.allow_ssr)

    return {
        "volume_ok": volume_ok,
        "dollar_volume_ok": dollar_volume_ok,
        "spread_ok": spread_ok,
        "bid_ask_ok": bid_ask_ok,
        "halt_ok": halt_ok,
        "ssr_ok": ssr_ok,
    }


def _populate_pct_change(
    context: Dict[str, Any],
    provider: ScannerDataProvider,
) -> None:
    if context.get("pct_change") is not None:
        return
    last_price = _safe_float(context.get("last_price"), None)
    prev_close = _safe_float(context.get("prev_close"), None)
    if prev_close is None:
        history = _history_snapshot(context["symbol"], provider, context)
        prev_close = history.get("prev_close")
        context["prev_close"] = prev_close
        if prev_close is None:
            context.setdefault("data_quality_flags", []).append("HISTORY_UNKNOWN")
    identity = _context_identity(context)
    print(
        "[REFERENCE][REQUEST] "
        f"symbol={context['symbol']} conId={identity.con_id} session={normalize_session_label(str(context.get('session') or ''))} "
        "reference_type=LAST_RTH_CLOSE source=history_or_snapshot"
    )
    pct_payload = compute_session_aligned_pct_change(
        session_label=str(context.get("session") or ""),
        cur_last=last_price,
        ref_close_rth=prev_close,
        rth_open_price=_safe_float(context.get("rth_open_price"), None),
        rth_close_price=_safe_float(context.get("rth_close_price"), None),
        ibkr_change_pct=_safe_float(context.get("ibkr_change_pct"), None),
        persisted_pct_change=_safe_float(context.get("persisted_pct_change"), None),
    )
    if last_price is None:
        context.setdefault("data_quality_flags", []).append("MISSING_LAST")
    if prev_close is None:
        context.setdefault("data_quality_flags", []).append("MISSING_REF_CLOSE_RTH")
    if pct_payload.final_pct is None:
        context.setdefault("data_quality_flags", []).append("MISSING_PCT_CHANGE")
    context["pct_change"] = pct_payload.final_pct
    context["ref_close_rth"] = pct_payload.ref_close_rth
    context["reference_price"] = pct_payload.reference_price
    context["reference_label"] = pct_payload.reference_label
    context["ibkr_change_pct"] = pct_payload.ibkr_change_pct
    context["pct_source"] = pct_payload.pct_source
    context["open_relative_pct_change"] = pct_payload.open_relative_pct_change
    context["gap_pct_resolved"] = pct_payload.open_relative_pct_change if pct_payload.open_relative_pct_change is not None else pct_payload.final_pct
    context["gap_source"] = "SESSION_OPEN_VS_REF" if pct_payload.open_relative_pct_change is not None else pct_payload.pct_source
    print(
        "[REFERENCE][RESULT] "
        f"symbol={context['symbol']} conId={identity.con_id} found={pct_payload.reference_price is not None} "
        f"value={pct_payload.reference_price} asof={history.get('lookup_key') if 'history' in locals() else context.get('symbol')} source=history_or_snapshot"
    )
    print(
        "[REFERENCE][MERGE] "
        f"symbol={context['symbol']} merge_target_found=True reference_label={pct_payload.reference_label} value={pct_payload.reference_price}"
    )
    print(
        "[DERIVED][PCT_GAP] "
        f"symbol={context['symbol']} last={last_price} reference={pct_payload.reference_price} pct_change={pct_payload.final_pct} gap={context['gap_pct_resolved']} "
        f"pct_source={pct_payload.pct_source} gap_source={context['gap_source']}"
    )
    print(
        "[PCT] "
        f"symbol={context['symbol']} session={normalize_session_label(str(context.get('session') or ''))} "
        f"baseline={context.get('reference_label')} value={context.get('pct_change')}"
    )
    print(
        "[GAP] "
        f"symbol={context['symbol']} reference={context.get('reference_label')} value={context.get('pct_change')}"
    )
    if get_config("DEBUG_MARKET_DATA"):
        print(
            "[SCANNER][MD][DEBUG] pct_change "
            f"symbol={context['symbol']} last={last_price} ref_price={context.get('reference_price')} "
            f"ref_label={context.get('reference_label')} pct_change={context.get('pct_change')} "
            f"open_relative_pct_change={context.get('open_relative_pct_change')} "
            f"source={context.get('pct_source')}"
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
    if drop_reason in {"DROP_MISSING_RVOL", "DROP_RVOL_DISCOVERY", "DROP_RVOL_FOCUS"}:
        return {"rvol": context.get("rvol") is None}
    if drop_reason in {"DROP_MISSING_DOLLAR_VOLUME", "DROP_DOLLAR_VOLUME"}:
        return {"dollar_volume": context.get("dollar_volume") is None}
    if drop_reason in {"DROP_MISSING_VOLUME", "DROP_VOLUME", "DROP_PREMARKET_VOLUME"}:
        return {"volume": context.get("volume") is None}
    if drop_reason in {"DROP_FLOAT_MISSING", "DROP_FLOAT_MAX"}:
        return {"float_shares": context.get("float_shares") is None}
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


def _resolve_rvol_for_focus_gate(context: Dict[str, Any]) -> tuple[str, Optional[float]]:
    """Return canonical RVOL input for FOCUS promotion with provenance."""
    scanner_rvol = _safe_float(context.get("scanner_rvol"), None)
    if scanner_rvol is not None:
        return "scanner_rvol", scanner_rvol

    session = normalize_session_label(str(context.get("session") or ""))
    if session in {"RTH_OPEN", "RTH_MID", "RTH_LATE"}:
        return "rvol_phase", _safe_float(context.get("rvol_phase"), None)
    return "rvol_discovery", _safe_float(context.get("rvol_discovery"), None)


def _load_premarket_prep_candidates() -> Dict[str, Dict[str, Any]]:
    payload = load_canonical_premarket_prep_artifact() or {}
    symbols = payload.get("symbols") if isinstance(payload, dict) else []
    result: Dict[str, Dict[str, Any]] = {}
    for entry in symbols or []:
        if not isinstance(entry, dict):
            continue
        symbol = str(entry.get("symbol") or "").upper()
        if not symbol:
            continue
        result[symbol] = entry
    return result


def _seed_watchlist_from_prep(
    *,
    session_label: str,
    watchlist_contexts: List[Dict[str, Any]],
    context_by_symbol: Dict[str, Dict[str, Any]],
    candidates: List[Dict[str, Any]],
    drop_ledger: Dict[str, str],
    watchlist_limit: int,
    prep_candidates: Dict[str, Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], int, int]:
    if normalize_session_label(session_label) != "PRE" or not prep_candidates:
        return watchlist_contexts, 0, 0
    prep_seeded_count = 0
    prep_invalidated_count = 0
    existing = {context["symbol"]: context for context in watchlist_contexts if context.get("symbol")}
    live_confirmed_symbols = {c["symbol"] for c in candidates}
    for symbol, prep_entry in prep_candidates.items():
        context = existing.get(symbol) or context_by_symbol.get(symbol)
        if context is None:
            context = {
                "symbol": symbol,
                "session": session_label,
                "pct_change": prep_entry.get("pct_change_context"),
                "rvol_discovery": prep_entry.get("persisted_rvol"),
                "rvol_phase": prep_entry.get("persisted_rvol"),
                "phase_volume_ratio": None,
                "scanner_rvol": prep_entry.get("persisted_rvol"),
                "rvol": prep_entry.get("persisted_rvol"),
                "volume": prep_entry.get("persisted_volume"),
                "avg_volume_20d": None,
                "reference_label": prep_entry.get("persisted_reference_label"),
                "prep_only": False,
                "data_quality_flags": ["PREP_WATCHLIST_SEEDED"],
            }
        drop_reason = drop_ledger.get(symbol)
        if drop_reason in {"DROP_QUOTE_UNAVAILABLE", "DROP_MD_CONFLICT", "DROP_UNSUBSCRIBED_MARKET_DATA"}:
            prep_invalidated_count += 1
            print(f"[PREP][INVALIDATE] symbol={symbol} reason={drop_reason}")
            continue
        context["prep_seeded"] = True
        context["live_confirmation_pending"] = symbol not in live_confirmed_symbols
        context["promotion_reason"] = context.get("promotion_reason") or "PREP_WATCHLIST_SEEDED"
        context["watchlist_source"] = "HYBRID" if symbol in context_by_symbol else "PREP_SEEDED"
        if symbol not in existing:
            watchlist_contexts.append(context)
            existing[symbol] = context
        prep_seeded_count += 1
    if watchlist_limit > 0:
        watchlist_contexts = watchlist_contexts[:watchlist_limit]
    return watchlist_contexts, prep_seeded_count, prep_invalidated_count


def _evaluate_watchlist_gates(
    context: Dict[str, Any],
    thresholds: GateThresholds,
) -> Optional[str]:
    _evaluate_float_gate(context, thresholds)
    pct_change = _safe_float(context.get("pct_change"), None)

    if pct_change is None:
        return "DROP_MISSING_PCT_CHANGE"
    pct_change_min = _resolve_pct_change_min_for_session(str(context.get("session") or ""), thresholds)
    if pct_change < pct_change_min:
        return "DROP_PCT_CHANGE"
    if thresholds.max_pct_change is not None and pct_change > thresholds.max_pct_change:
        return "DROP_PCT_CHANGE_MAX"
    return None


def _evaluate_float_gate(
    context: Dict[str, Any],
    thresholds: GateThresholds,
) -> Optional[str]:
    float_shares = context.get("float_shares")
    if float_shares is None:
        context["float_status"] = "UNKNOWN"
        if not thresholds.allow_unknown_float:
            return "DROP_FLOAT_MISSING"
        flags = context.setdefault("data_quality_flags", [])
        context["float_tolerated"] = True
        if isinstance(flags, list) and "FLOAT_UNKNOWN" in flags:
            context["data_quality_flags"] = [flag for flag in flags if flag != "FLOAT_UNKNOWN"]
        return None
    context["float_status"] = "KNOWN"
    if float_shares > thresholds.max_float:
        return "DROP_FLOAT_MAX"
    return None


def _is_etf_context(context: Dict[str, Any]) -> bool:
    symbol = str(context.get("symbol") or "").upper()
    if symbol in ETF_EXCLUDED_SYMBOLS:
        return True
    instrument_type = str(context.get("instrument_type") or "").upper()
    return instrument_type == "ETF"


def _evaluate_focus_gates(
    context: Dict[str, Any],
    thresholds: GateThresholds,
) -> Optional[str]:
    price = _safe_float(context.get("last_price"), None)
    volume = _safe_float(context.get("volume"), None)
    premarket_volume = _safe_float(context.get("premarket_volume"), None)
    dollar_volume = _safe_float(context.get("dollar_volume"), None)
    session = normalize_session_label(str(context.get("session") or ""))
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
    if bool(context.get("live_confirmation_pending")):
        return "DROP_LIVE_CONFIRMATION_PENDING"
    rvol_metric_used, focus_rvol_value = _resolve_rvol_for_focus_gate(context)
    rvol_phase = _safe_float(context.get("rvol_phase"), None)
    rvol_discovery = _safe_float(context.get("rvol_discovery"), None)
    threshold_value = thresholds.focus_rvol_min
    if focus_rvol_value is None:
        print(
            "[FOCUS_GATE] "
            f"symbol={context.get('symbol')} focus_threshold_used={threshold_value} "
            f"rvol_metric_used={rvol_metric_used} rvol_metric_value=None "
            "reason=WAIT_MISSING_RVOL decision=WAIT"
        )
        return "DROP_MISSING_RVOL"

    early_rth = session == "RTH_OPEN"
    has_momentum_context = bool(
        (_safe_float(context.get("pct_change"), 0.0) or 0.0) >= thresholds.min_pct_change
        and (rvol_discovery is not None and rvol_discovery >= thresholds.watchlist_rvol_min)
    )
    has_catalyst_context = bool(context.get("catalyst_present") or context.get("news_present") or context.get("catalyst_summary"))

    if focus_rvol_value >= threshold_value:
        focus_decision = "KEEP"
        focus_reason = "PASS_RVOL_THRESHOLD"
    elif early_rth and has_momentum_context and has_catalyst_context and rvol_phase is not None and rvol_phase >= thresholds.watchlist_rvol_min:
        focus_decision = "KEEP_EARLY_RTH_CONTEXT"
        focus_reason = "PASS_EARLY_RTH_CONTEXT"
    else:
        focus_decision = "WAIT"
        focus_reason = "WAIT_RVOL_BELOW_THRESHOLD"

    print(
        "[FOCUS_GATE] "
        f"symbol={context.get('symbol')} focus_threshold_used={threshold_value} "
        f"rvol_metric_used={rvol_metric_used} rvol_metric_value={focus_rvol_value} "
        f"rvol_discovery={rvol_discovery} rvol_phase={rvol_phase} "
        f"reason={focus_reason} decision={focus_decision}"
    )
    if focus_decision == "WAIT":
        return "DROP_RVOL_FOCUS"
    if focus_decision == "KEEP_EARLY_RTH_CONTEXT":
        print(
            "[FOCUS_GATE] "
            f"symbol={context.get('symbol')} focus_threshold_used={threshold_value} "
            f"rvol_metric_used={rvol_metric_used} rvol_metric_value={focus_rvol_value} "
            "reason=PASS_EARLY_RTH_CONTEXT_TERMINAL decision=PASS"
        )
        return None
    if volume is None:
        _log_focus_volume_drop(
            context=context,
            stage="focus",
            compared_field="volume",
            threshold=None,
            threshold_source="missing",
        )
        return "DROP_MISSING_VOLUME"
    if session in {"PRE", "OVN"}:
        effective_premarket_volume = premarket_volume if premarket_volume is not None else volume
        now_ny = datetime.now(NY_TZ)
        premarket_threshold = _resolve_premarket_volume_threshold(now_ny.time(), thresholds)
        decision = "PASS" if effective_premarket_volume is not None and effective_premarket_volume >= premarket_threshold else "FAIL"
        print(
            "[VOLUME_GATE_POLICY] "
            f"session={session} time_ny={now_ny.strftime('%H:%M')} "
            f"threshold={int(premarket_threshold)} symbol_volume={int(effective_premarket_volume or 0)} "
            f"decision={decision}"
        )
        if effective_premarket_volume is None or effective_premarket_volume < premarket_threshold:
            _log_focus_volume_drop(
                context=context,
                stage="focus",
                compared_field="premarket_volume",
                threshold=float(premarket_threshold),
                threshold_source="policy.session_aware_premarket_volume",
            )
            print(f"[ROSS][GATE] symbol={context.get('symbol')} premarket_volume={int(effective_premarket_volume or 0)} FAIL")
            return "DROP_PREMARKET_VOLUME"
    else:
        focus_threshold, threshold_source = _focus_volume_threshold_for_session(session, thresholds)
        if volume < focus_threshold:
            _log_focus_volume_drop(
                context=context,
                stage="focus",
                compared_field="volume",
                threshold=focus_threshold,
                threshold_source=threshold_source,
            )
            return "DROP_VOLUME"
    if thresholds.min_dollar_volume is not None:
        if dollar_volume is None:
            return "DROP_MISSING_DOLLAR_VOLUME"
        if dollar_volume < thresholds.min_dollar_volume:
            return "DROP_DOLLAR_VOLUME"
    if thresholds.spread_max_pct is not None:
        if spread_pct is None:
            return "DROP_MISSING_SPREAD"
        if spread_pct > thresholds.spread_max_pct:
            return "DROP_SPREAD"
    if thresholds.require_bid_ask and (bid is None or ask is None):
        print(
            "[FOCUS_GATE] "
            f"symbol={context.get('symbol')} focus_threshold_used={threshold_value} "
            f"rvol_metric_used={rvol_metric_used} rvol_metric_value={focus_rvol_value} "
            "reason=DROP_MISSING_BID_ASK decision=DROP"
        )
        return "DROP_MISSING_BID_ASK"
    print(
        "[FOCUS_GATE] "
        f"symbol={context.get('symbol')} focus_threshold_used={threshold_value} "
        f"rvol_metric_used={rvol_metric_used} rvol_metric_value={focus_rvol_value} "
        "reason=PASS_ALL_FOCUS_GATES decision=PASS"
    )
    return None


def _resolve_premarket_volume_threshold(session_time_ny: dtime, thresholds: GateThresholds) -> int:
    if session_time_ny < dtime(7, 30):
        return 10_000
    if session_time_ny < dtime(9, 30):
        return 50_000
    return int(thresholds.min_premarket_volume)


def _focus_volume_threshold_for_session(session: str, thresholds: GateThresholds) -> tuple[float, str]:
    if session == "RTH_OPEN":
        return (
            float(thresholds.focus_volume_min_early_rth),
            (
                "early_rth_focus=max(policy.min_premarket_volume, "
                f"policy.min_volume*{thresholds.focus_volume_min_early_rth_ratio:.2f})"
            ),
        )
    return float(thresholds.focus_volume_min), "policy.min_volume"


def _log_focus_volume_drop(
    *,
    context: Dict[str, Any],
    stage: str,
    compared_field: str,
    threshold: Optional[float],
    threshold_source: str,
) -> None:
    session = normalize_session_label(str(context.get("session") or ""))
    phase = str(context.get("phase") or session or "UNKNOWN")
    value = _safe_float(context.get(compared_field), None)
    threshold_value = "None" if threshold is None else f"{threshold:g}"
    value_repr = "None" if value is None else f"{value:g}"
    print(
        "[VOLUME_GATE] "
        f"symbol={context.get('symbol')} stage={stage} reason=DROP_VOLUME "
        f"field={compared_field} value={value_repr} threshold={threshold_value} "
        f"threshold_source={threshold_source} session={session} phase={phase}"
    )


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
    sources = list(RSS_FAST_TRADING)
    headlines_by_symbol, summary = fetch_fast_headlines_for_symbols(
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
            print(f"[NEWS] symbol={symbol} catalyst_tag={cached['context'].get('catalyst_type') or 'NONE'} news_changed=False")
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
                "news_count": 0,
                "fresh_news_count": 0,
                "stale_news_count": 0,
                "top_news_title": None,
                "top_news_age_hours": None,
                "top_news_catalyst_tag": None,
                "news_source_mode": "rss_batch",
                "news_asof": datetime.now(timezone.utc).isoformat(),
            }
            news_by_symbol[symbol] = context
            _NEWS_CACHE[symbol] = {"signature": signature, "context": context}
            print(f"[NEWS] symbol={symbol} catalyst_tag=NONE headlines=0")
            print(f"[NEWS] symbol={symbol} news_changed=True")
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

        top_news = unique_headlines[0] if unique_headlines else None
        source_mode = "rss_batch"
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
            "news_count": len(unique_headlines),
            "fresh_news_count": sum(1 for age in ages if age <= NEWS_AGE_MAX_MINUTES),
            "stale_news_count": sum(1 for age in ages if age > NEWS_AGE_MAX_MINUTES),
            "top_news_title": top_news.title if top_news else None,
            "top_news_age_hours": round((news_age_minutes or 0) / 60.0, 3) if news_age_minutes is not None else None,
            "top_news_catalyst_tag": catalyst_type or "generic",
            "news_source_mode": source_mode,
            "news_asof": datetime.now(timezone.utc).isoformat(),
        }
        news_by_symbol[symbol] = context
        _NEWS_CACHE[symbol] = {"signature": signature, "context": context}
        print(
            f"[NEWS] symbol={symbol} catalyst_tag={(catalyst_type or 'generic news').upper()} "
            f"headlines={len(unique_headlines)}"
        )
        print(f"[NEWS] symbol={symbol} news_changed=True")

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
        symbol = item.get("symbol", "")
        return (-pct, -rvol, -dvol, symbol)

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
    catalyst_present_override: Optional[bool] = None,
    session_label_override: Optional[str] = None,
) -> CandidateMetrics:
    float_shares = context.get("float_shares")
    float_millions = (
        round(float_shares / 1_000_000.0, 2) if float_shares is not None else None
    )
    session_value = session_label_override if session_label_override is not None else context.get("session")
    session = (session_value or "").upper()
    volume = context.get("volume")
    premarket_volume = volume if session in {"PRE", "OVN"} else None
    catalyst_present = bool(
        news_context.get("ross_catalyst_valid") or news_context.get("news_present")
    )
    if catalyst_present_override is not None:
        catalyst_present = catalyst_present_override
    catalyst_type = news_context.get("catalyst_type")
    news_age = news_context.get("news_age_minutes")
    news_count = int(news_context.get("news_count") or (1 if news_context.get("news_present") else 0))
    fresh_news_count = int(news_context.get("fresh_news_count") or (1 if news_age is not None and news_age <= 6 * 60 else 0))
    stale_news_count = int(news_context.get("stale_news_count") or max(news_count - fresh_news_count, 0))
    top_news_title = news_context.get("top_news_title")
    top_news_age_hours = news_context.get("top_news_age_hours")
    top_news_catalyst_tag = news_context.get("top_news_catalyst_tag") or catalyst_type
    news_source_mode = news_context.get("news_source_mode")
    news_asof = news_context.get("news_asof")
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
        con_id=context.get("con_id"),
        exchange=context.get("exchange"),
        session_label=session_value,
        session_phase=context.get("session_phase"),
        last_price=context.get("last_price"),
        prev_close=context.get("prev_close"),
        ref_close_rth=context.get("ref_close_rth"),
        reference_price=context.get("reference_price"),
        reference_label=context.get("reference_label"),
        gap_pct=context.get("pct_change"),
        pct_change=context.get("pct_change"),
        pct_change_resolved=context.get("pct_change_resolved", context.get("pct_change")),
        gap_pct_resolved=context.get("gap_pct_resolved", context.get("open_relative_pct_change")),
        gap_source=context.get("gap_source"),
        context_status=context.get("context_status"),
        execution_ready=context.get("execution_ready"),
        prep_only=context.get("prep_only"),
        live_rvol_deferred=bool(context.get("live_rvol_deferred", False)),
        prep_seeded=bool(context.get("prep_seeded", False)),
        live_confirmation_pending=bool(context.get("live_confirmation_pending", False)),
        watchlist_source=context.get("watchlist_source"),
        promotion_reason=context.get("promotion_reason"),
        ibkr_change_pct=context.get("ibkr_change_pct"),
        pct_source=context.get("pct_source"),
        open_relative_pct_change=context.get("open_relative_pct_change"),
        hod_pct=context.get("hod_pct"),
        rvol=context.get("rvol"),
        rvol_discovery=context.get("rvol_discovery"),
        rvol_phase=context.get("rvol_phase"),
        phase_volume_ratio=context.get("phase_volume_ratio"),
        relative_volume=context.get("relative_volume"),
        avg_volume_20d=context.get("avg_volume_20d"),
        float_shares=float_shares,
        float_source=context.get("float_source"),
        float_asof=context.get("float_asof"),
        float_cache_hit=context.get("float_cache_hit"),
        float_millions=float_millions,
        volume=volume,
        premarket_volume=premarket_volume,
        dollar_volume=context.get("dollar_volume"),
        bid=context.get("bid"),
        ask=context.get("ask"),
        spread=context.get("spread"),
        spread_pct=context.get("spread_pct"),
        halted=context.get("halted"),
        ssr=context.get("ssr"),
        catalyst_present=catalyst_present,
        catalyst_summary=catalyst_summary,
        news_count=news_count,
        fresh_news_count=fresh_news_count,
        stale_news_count=stale_news_count,
        top_news_title=top_news_title,
        top_news_age_hours=top_news_age_hours,
        top_news_catalyst_tag=top_news_catalyst_tag,
        news_source_mode=news_source_mode,
        news_asof=news_asof,
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
    reference_price = (
        candidate.reference_price
        if candidate.reference_price is not None
        else candidate.ref_close_rth
        if candidate.ref_close_rth is not None
        else candidate.prev_close
    )
    reference_label = candidate.reference_label or "REF"
    return (
        f"{candidate.symbol} session={session_label} price=${_format_value(candidate.last_price)} "
        f"gap={_format_value(getattr(candidate, 'gap_pct_resolved', candidate.gap_pct))}% "
        f"{reference_label}={_format_value(reference_price)} "
        f"ibkr_pct={_format_value(candidate.ibkr_change_pct)}% "
        f"pct_change_resolved={_format_value(getattr(candidate, 'pct_change_resolved', candidate.pct_change))}% "
        f"pct_source={candidate.pct_source or 'NA'} "
        f"gap_pct_resolved={_format_value(getattr(candidate, 'gap_pct_resolved', candidate.gap_pct))}% "
        f"gap_source={getattr(candidate, 'gap_source', 'NA')} "
        f"reference_label={candidate.reference_label or 'NA'} "
        f"context_status={getattr(candidate, 'context_status', 'NA')} "
        f"rvol={_format_value(candidate.rvol)} rvol_discovery={_format_value(getattr(candidate, 'rvol_discovery', candidate.rvol))} "
        f"rvol_phase={_format_value(getattr(candidate, 'rvol_phase', candidate.rvol))} "
        f"phase_volume_ratio={_format_value(getattr(candidate, 'phase_volume_ratio', None), 4)} "
        f"float={_format_float_millions(candidate.float_millions)} "
        f"vol={_format_int(candidate.volume)} pm={_format_int(candidate.premarket_volume)} "
        f"spread={_format_value(candidate.spread_pct, 4)}% news_flag={catalyst} "
        f"news_count={getattr(candidate, 'news_count', 0)} news_fresh_count={getattr(candidate, 'fresh_news_count', 0)} "
        f"float_source={candidate.float_source or 'NA'} float_asof={candidate.float_asof or 'NA'} "
        f"execution_ready={getattr(candidate, 'execution_ready', False)} prep_only={getattr(candidate, 'prep_only', False)} "
        f"live_rvol_deferred={getattr(candidate, 'live_rvol_deferred', False)} "
        f"prep_seeded={getattr(candidate, 'prep_seeded', False)} "
        f"live_confirmation_pending={getattr(candidate, 'live_confirmation_pending', False)} "
        f"promotion_reason={getattr(candidate, 'promotion_reason', 'NA') or 'NA'} "
        f"watchlist_source={getattr(candidate, 'watchlist_source', 'LIVE_SCAN')} "
        f"source_of_candidate={'PREP_SEED' if getattr(candidate, 'prep_seeded', False) else 'LIVE_RTH'} "
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
    float_class = str(context.get("float_class") or "").upper()
    priority_boost = 0.0
    if float_class == "ULTRA_LOW_FLOAT":
        priority_boost = 2.0
    elif float_class == "LOW_FLOAT":
        priority_boost = 1.0
    if priority_boost:
        print(f"[ROSS][PRIORITY] symbol={context.get('symbol')} float_class={float_class} boost={int(priority_boost)}")
    components = {
        "pct_change": round(0.45 * pct_n * 100.0, 2),
        "rvol": round(0.35 * rvol_n * 100.0, 2),
        "dollar_volume": round(0.20 * dvol_n * 100.0, 2),
        "float_priority_boost": round(priority_boost, 2),
    }
    score = (components["pct_change"] + components["rvol"] + components["dollar_volume"]) / 100.0
    score += priority_boost
    return round(min(score, 1.0) * 100.0, 2), components


def _build_symbol_context(
    provider: ScannerDataProvider,
    symbol: str,
    session_label: str,
    float_cache: Dict[str, Dict[str, Any]],
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
    if any("10197" in str(flag) for flag in data_quality_flags):
        if "MD_CONFLICT_10197" not in data_quality_flags:
            data_quality_flags.append("MD_CONFLICT_10197")
        return {
            "symbol": symbol,
            "session": session_label,
            "data_quality_flags": data_quality_flags,
            "snapshot_error": "MD_CONFLICT",
        }
    last_price = _resolve_price(quote)
    spread, spread_pct = _spread_values(quote)
    snapshot_timeout = "MD_TIMEOUT" in data_quality_flags
    if get_config("DEBUG_MARKET_DATA"):
        print(
            "[SCANNER][MD][DEBUG] ticks "
            f"symbol={symbol} bid={quote.bid} ask={quote.ask} last={quote.last} "
            f"close={quote.close} volume={quote.volume} vwap={quote.vwap}"
        )

    scan_details = _provider_symbol_scan_details(provider)
    scan_detail = scan_details.get(symbol, {}) if isinstance(scan_details, dict) else {}
    intraday = None
    try:
        intraday = provider.get_intraday_stats(symbol)
    except Exception:
        intraday = None

    volume = intraday.current_intraday_volume if intraday else None
    avg_volume_20d = intraday.average_daily_volume_20d if intraday else None
    day_high = _safe_float(getattr(intraday, "day_high", None), None) if intraday else None
    persisted_rvol = _safe_float(getattr(quote, "persisted_rvol", None), None)
    rvol_payload = compute_session_relative_volume_with_provenance(
        session_label=session_label,
        session_volume=volume,
        avg_volume_20d=avg_volume_20d,
        persisted_rvol=persisted_rvol,
    )
    time_normalized_rvol = rvol_payload.value
    if time_normalized_rvol is None:
        time_normalized_rvol = intraday.relative_volume if intraday else None
    rvol_discovery = compute_scanner_rvol(
        session_label=session_label,
        session_volume=volume,
        avg_volume_20d=avg_volume_20d,
        persisted_rvol=persisted_rvol,
    )
    phase_rvol_payload = compute_phase_aware_rvol(
        session_label=session_label,
        session_volume=volume,
        avg_volume_20d=avg_volume_20d,
    )
    rvol_phase = phase_rvol_payload.rvol_phase
    scanner_rvol = rvol_phase if rvol_phase is not None else rvol_discovery
    print(
        "[SCANNER_RVOL] "
        f"symbol={symbol} session={normalize_session_label(session_label)} "
        f"volume={volume} avg_volume_20d={avg_volume_20d} "
        f"scanner_rvol={scanner_rvol}"
    )
    if intraday is None:
        data_quality_flags.append("VOLUME_UNKNOWN")
    if volume is None:
        data_quality_flags.append("MISSING_VOLUME")
    if scanner_rvol is None:
        data_quality_flags.append("RVOL_UNKNOWN")

    session_open = _safe_float(getattr(quote, "open", None), None)
    session_close = _safe_float(getattr(quote, "close", None), None)
    prev_close = session_close
    if include_pct_change and prev_close is None:
        history = _history_snapshot(symbol, provider, {"local_symbol": scan_detail.get("localSymbol"), "trading_class": scan_detail.get("tradingClass")})
        prev_close = history.get("prev_close")
        if prev_close is None and not _allow_history_enrichment(provider):
            data_quality_flags.append("HISTORY_DISABLED")
    if include_pct_change and prev_close is None:
        data_quality_flags.append("HISTORY_UNKNOWN")

    ibkr_change_pct = _safe_float(getattr(quote, "change_percent", None), None)
    pct_change = None
    pct_source = None
    reference_price = None
    reference_label = None
    open_relative_pct_change = None
    if include_pct_change:
        normalized_session = normalize_session_label(session_label)
        rth_open_price = session_open
        if normalized_session in {"RTH_OPEN", "RTH_MID", "RTH_LATE"} and ibkr_change_pct is None:
            rth_open_price = None
        rth_close_price = session_close if normalized_session == "AH" else prev_close
        reference_identity = CandidateIdentity.from_mapping({
            "symbol": symbol,
            "conId": scan_detail.get("conId"),
            "secType": scan_detail.get("secType") or "STK",
            "exchange": scan_detail.get("exchange") or scan_detail.get("primaryExchange") or "SMART",
            "primaryExchange": scan_detail.get("primaryExchange"),
            "tradingClass": scan_detail.get("tradingClass"),
            "currency": scan_detail.get("currency") or "USD",
            "localSymbol": scan_detail.get("localSymbol") or symbol,
        })
        print(
            "[REFERENCE][REQUEST] "
            f"symbol={symbol} conId={reference_identity.con_id} session={normalized_session} "
            "reference_type=LAST_RTH_CLOSE source=history_or_snapshot"
        )
        pct_payload = compute_session_aligned_pct_change(
            session_label=normalized_session,
            cur_last=last_price,
            ref_close_rth=prev_close,
            rth_open_price=rth_open_price,
            rth_close_price=rth_close_price,
            ibkr_change_pct=ibkr_change_pct,
            persisted_pct_change=_safe_float(getattr(quote, "persisted_pct_change", None), None),
        )
        pct_change = pct_payload.final_pct
        pct_source = pct_payload.pct_source
        reference_price = pct_payload.reference_price
        reference_label = pct_payload.reference_label
        open_relative_pct_change = pct_payload.open_relative_pct_change
        print(
            "[REFERENCE][RESULT] "
            f"symbol={symbol} conId={reference_identity.con_id} found={pct_payload.reference_price is not None} "
            f"value={pct_payload.reference_price} asof={(history.get('lookup_key') if 'history' in locals() else symbol)} source=history_or_snapshot"
        )
        print(
            "[REFERENCE][MERGE] "
            f"symbol={symbol} merge_target_found=True reference_label={pct_payload.reference_label} value={pct_payload.reference_price}"
        )
        print(
            "[DERIVED][PCT_GAP] "
            f"symbol={symbol} last={last_price} reference={pct_payload.reference_price} pct_change={pct_payload.final_pct} "
            f"gap={(pct_payload.open_relative_pct_change if pct_payload.open_relative_pct_change is not None else pct_payload.final_pct)} "
            f"pct_source={pct_payload.pct_source} gap_source={'SESSION_OPEN_VS_REF' if pct_payload.open_relative_pct_change is not None else pct_payload.pct_source}"
        )
    bundle = resolve_reference_bundle(
        session_label=session_label,
        reference_price=reference_price,
        reference_label=reference_label,
        pct_change=pct_change,
        pct_source=pct_source,
        gap_pct=open_relative_pct_change,
        gap_source=None,
    )
    reference_price = bundle.reference_price
    reference_label = bundle.reference_label
    pct_change = bundle.pct_change_resolved
    pct_source = bundle.pct_source
    gap_pct_resolved = bundle.gap_pct_resolved
    gap_source = bundle.gap_source
    context_status = bundle.context_status
    execution_ready = bundle.execution_ready
    prep_only = bundle.prep_only
    hod_pct = None
    if last_price is not None and day_high is not None and day_high != 0:
        hod_pct = round(((last_price - day_high) / day_high) * 100, 2)

    dollar_volume = None
    if last_price is not None and volume is not None:
        dollar_volume = round(last_price * volume, 2)

    float_entry = float_cache.get(symbol) or {}
    float_shares = float_entry.get("float_value") if isinstance(float_entry, dict) else None
    float_source = (
        float_entry.get("float_source") if isinstance(float_entry, dict) else None
    ) or _FLOAT_SOURCE_BY_SYMBOL.get(symbol, "missing")
    float_asof = float_entry.get("float_asof") if isinstance(float_entry, dict) else None
    float_cache_hit = symbol in _FLOAT_CACHE_HIT_SYMBOLS and float_shares is not None
    if float_shares is None:
        data_quality_flags.append("FLOAT_UNKNOWN")
    print(
        "[FLOAT][PROVENANCE] "
        f"symbol={symbol} value={float_shares} source={float_source} asof={float_asof} cache_hit={float_cache_hit}"
    )

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

    con_id = scan_detail.get("conId")
    if con_id in {None, 0, "0"} and getattr(provider, "source_name", "") != "IBKR":
        con_id = abs(hash(symbol)) % 10_000_000 + 1
    return {
        "symbol": symbol,
        "session": session_label,
        "con_id": con_id,
        "exchange": scan_detail.get("exchange") or scan_detail.get("primaryExchange"),
        "primary_exchange": scan_detail.get("primaryExchange"),
        "trading_class": scan_detail.get("tradingClass"),
        "local_symbol": scan_detail.get("localSymbol") or symbol,
        "currency": scan_detail.get("currency") or "USD",
        "instrument_type": scan_detail.get("secType") or "STK",
        "last_price": last_price,
        "close": quote.close,
        "prev_close": prev_close,
        "ref_close_rth": prev_close,
        "rth_open_price": session_open,
        "rth_close_price": session_close,
        "reference_price": reference_price,
        "reference_label": reference_label,
        "pct_change": pct_change,
        "pct_change_resolved": pct_change,
        "pct_source": pct_source,
        "open_relative_pct_change": open_relative_pct_change,
        "gap_pct_resolved": gap_pct_resolved,
        "gap_source": gap_source,
        "context_status": context_status,
        "execution_ready": execution_ready,
        "prep_only": prep_only,
        "hod_pct": hod_pct,
        "persisted_pct_change": _safe_float(getattr(quote, "persisted_pct_change", None), None),
        "persisted_rvol": persisted_rvol,
        "ibkr_change_pct": ibkr_change_pct,
        "volume": volume,
        "avg_volume_20d": avg_volume_20d,
        "dollar_volume": dollar_volume,
        "bid": quote.bid,
        "ask": quote.ask,
        "spread": spread,
        "spread_pct": spread_pct,
        "high": _safe_float(getattr(quote, "high", None), None),
        "low": _safe_float(getattr(quote, "low", None), None),
        "vwap": _safe_float(getattr(quote, "vwap", None), None),
        "scanner_rvol": scanner_rvol,
        "rvol_discovery": rvol_discovery,
        "rvol_phase": rvol_phase,
        "phase_volume_ratio": phase_rvol_payload.phase_ratio,
        "expected_phase_volume": phase_rvol_payload.expected_phase_volume,
        "time_normalized_rvol": time_normalized_rvol,
        "rvol": scanner_rvol,
        "relative_volume": time_normalized_rvol,
        "rvol_baseline": rvol_payload.baseline,
        "rvol_method": rvol_payload.method,
        "float_shares": float_shares,
        "float_source": float_source,
        "float_asof": float_asof,
        "float_cache_hit": float_cache_hit,
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
    allow_mock_fallback: bool,
) -> List[str]:
    ibkr_location_code = "STK.US.MAJOR"
    diagnostics["universe_request"] = {
        "source": request.universe_source.value,
        "scan_code": request.ibkr_scan_code,
        "requested_top_n": request.requested_top_n,
        "region": request.region,
        "instrument": request.instrument,
        "location_code": ibkr_location_code if request.universe_source == UniverseSource.IBKR_TOP_GAINERS else request.location_code,
        "above_price": request.above_price,
        "below_price": request.below_price,
        "exchanges": list(request.exchanges or []),
    }
    if request.universe_source == UniverseSource.IBKR_TOP_GAINERS:
        primary_request = replace(
            request,
            instrument="STK",
            location_code=ibkr_location_code,
            ibkr_scan_code="TOP_PERC_GAIN",
        )
        symbols = provider.get_top_gainers(
            limits["resolved_symbol_limit"],
            request=primary_request,
        )
        provider_scan_details = getattr(provider, "last_scan_details", {}) or {}
        effective_location_code = provider_scan_details.get(
            "selected_location_code",
            provider_scan_details.get("requested_location_code", primary_request.location_code),
        )
        effective_scan_code = provider_scan_details.get(
            "selected_scan_code",
            provider_scan_details.get("requested_scan_code", primary_request.ibkr_scan_code),
        )
        retry_attempts = int(provider_scan_details.get("retry_attempts", 0) or 0)
        retry_exhausted = bool(provider_scan_details.get("retry_exhausted", False))
        returned_rows = int(provider_scan_details.get("returned_rows", len(symbols)) or 0)
        print(
            f"[SCANNER][RAW_RESULT] broker_symbols={returned_rows} "
            f"provider_symbols={len(symbols)}"
        )
        if (
            not symbols
            and effective_location_code == primary_request.location_code
            and retry_attempts == 0
        ):
            print("[SCANNER][INVARIANT_WARNING] provider fallback did not execute in live path")

        ibkr_returned_count = returned_rows
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
            "effective_location_code": effective_location_code,
            "effective_scan_code": effective_scan_code,
            "retry_attempts": retry_attempts,
            "retry_exhausted": retry_exhausted,
            "returned_rows": returned_rows,
        }
        print(
            "[SCANNER][IBKR] universe_return "
            f"ibkr_returned_count={ibkr_returned_count} "
            f"requested_top_n={requested_top_n} "
            f"truncation={truncation} "
            f"reasons={reasons or ['none']}"
        )
        print(
            "[SCANNER][IBKR][ATTRIBUTION] "
            f"raw_zero={ibkr_returned_count == 0} "
            f"reason={'broker_returned_zero_candidates' if ibkr_returned_count == 0 else 'broker_returned_candidates'} "
            f"effective_location={effective_location_code} effective_scanCode={effective_scan_code}"
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
            if not allow_mock_fallback:
                print(
                    "[SCANNER][WARN] CONFIG_SYMBOLS requested but no symbols provided; "
                    "MOCK fallback disabled in this run mode"
                )
                diagnostics["symbol_fallback"] = "EMPTY_UNIVERSE"
                return []
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


def _provider_symbol_scan_details(provider: ScannerDataProvider | None) -> Dict[str, Dict[str, Any]]:
    if provider is None:
        return {}
    scan_details = getattr(provider, "last_scan_details", {}) or {}
    if not isinstance(scan_details, dict):
        return {}
    symbol_details = scan_details.get("symbol_details")
    if isinstance(symbol_details, dict):
        return symbol_details
    return scan_details


def _provider_contract_details_by_symbol(provider: ScannerDataProvider | None) -> Dict[str, Dict[str, Any]]:
    details = _provider_symbol_scan_details(provider)
    if not isinstance(details, dict):
        return {}
    payload: Dict[str, Dict[str, Any]] = {}
    for symbol, meta in details.items():
        if not isinstance(meta, dict):
            continue
        normalized = str(symbol or "").upper().strip()
        if not normalized:
            continue
        payload[normalized] = {
            "symbol": normalized,
            "secType": meta.get("secType") or "STK",
            "conId": meta.get("conId"),
            "primaryExchange": meta.get("primaryExchange"),
            "tradingClass": meta.get("tradingClass"),
            "localSymbol": meta.get("localSymbol") or normalized,
            "exchange": meta.get("exchange") or "SMART",
            "currency": meta.get("currency") or "USD",
        }
    return payload


def _build_universe_entries(symbols: list[str], provider: ScannerDataProvider | None = None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    scan_details = _provider_symbol_scan_details(provider)
    for rank, symbol in enumerate(symbols, start=1):
        details = scan_details.get(symbol, {}) if isinstance(scan_details, dict) else {}
        entries.append(
            {
                "symbol": symbol,
                "conId": details.get("conId"),
                "exchange": details.get("primaryExchange"),
                "rank": rank,
            }
        )
    return entries


def _apply_non_tradable_universe_gate(
    symbols: list[str],
    provider: ScannerDataProvider | None,
    drop_ledger: Dict[str, str],
    event_collector: EventCollector | None = None,
) -> list[str]:
    blocked_trading_classes = {"EXPERT", "OTCID", "LIMITED"}
    scan_details = _provider_symbol_scan_details(provider)
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


def _classify_float(float_shares: Optional[int] | Dict[str, Any]) -> Optional[str]:
    if isinstance(float_shares, dict):
        candidate = float_shares.get("float_value")
        if isinstance(candidate, (int, float)):
            float_shares = int(candidate)
        else:
            float_shares = None
    if float_shares is None or float_shares <= 0:
        return None
    if float_shares < 1_000_000:
        return "ULTRA_LOW_FLOAT"
    if float_shares < 10_000_000:
        return "LOW_FLOAT"
    if float_shares <= 20_000_000:
        return "ROSS_SWEET_SPOT"
    return "HIGH_FLOAT"


def _ross_reason_from_drop(drop_reason: str) -> str:
    mapping = {
        "DROP_MISSING_RVOL": "RVOL_FAIL",
        "DROP_RVOL_DISCOVERY": "RVOL_FAIL",
        "DROP_RVOL_FOCUS": "RVOL_FAIL",
        "DROP_PCT_CHANGE": "GAP_FAIL",
        "DROP_PCT_CHANGE_MAX": "GAP_FAIL",
        "DROP_MISSING_PCT_CHANGE": "GAP_FAIL",
        "DROP_FLOAT_MAX": "FLOAT_FAIL",
        "DROP_FLOAT_MISSING": "FLOAT_FAIL",
        "DROP_SPREAD": "SPREAD_FAIL",
        "DROP_MISSING_SPREAD": "SPREAD_FAIL",
        "DROP_DOLLAR_VOLUME": "LIQUIDITY_FAIL",
        "DROP_MISSING_DOLLAR_VOLUME": "LIQUIDITY_FAIL",
        "DROP_MISSING_BID_ASK": "DATA_QUALITY_FAIL",
        "DROP_MISSING_VOLUME": "LIQUIDITY_FAIL",
        "DROP_PREMARKET_VOLUME": "LIQUIDITY_FAIL",
        "DROP_QUOTE_UNAVAILABLE": "DATA_QUALITY_FAIL",
        "DROP_MD_CONFLICT": "DATA_QUALITY_FAIL",
        "DROP_UNSUBSCRIBED_MARKET_DATA": "DATA_QUALITY_FAIL",
        "DROP_SNAPSHOT_TIMEOUT": "DATA_QUALITY_FAIL",
    }
    return mapping.get(drop_reason, "DATA_QUALITY_FAIL")


def _resolve_trading_day(now: datetime, session_label: str) -> str:
    normalized = normalize_session_label(session_label or "PRE")
    day = now.date()
    if normalized in {"OVN", "AH", "WEEKEND"}:
        return day.isoformat()
    return day.isoformat()


def _get_ross_daily_state(now: datetime, session_label: str) -> RossDailyState:
    global _ROSS_DAILY_STATE
    trading_day = _resolve_trading_day(now, session_label)
    if _ROSS_DAILY_STATE is None or _ROSS_DAILY_STATE.trading_day != trading_day:
        _ROSS_DAILY_STATE = RossDailyState(trading_day=trading_day)
        print(f"[ROSS][STATE] reset trading_day={trading_day} session={session_label}")
    return _ROSS_DAILY_STATE


def _is_material_rank_move(prev_rank: Optional[int], current_rank: Optional[int]) -> bool:
    if prev_rank is None or current_rank is None:
        return False
    if abs(prev_rank - current_rank) >= 8:
        return True
    thresholds = [10, 20, 30, 50, 100]
    return any(prev_rank > t >= current_rank for t in thresholds)


def _edge_rank(rank: Optional[int], universe_size: int) -> bool:
    if rank is None or universe_size <= 0:
        return False
    return rank >= max(universe_size - 2, 1)


def _should_recheck_symbol(
    symbol_state: RossSymbolState,
    *,
    current_rank: int,
    cycle: int,
    session_label: str,
    universe_size: int,
) -> bool:
    normalized = normalize_session_label(session_label or "PRE")
    if symbol_state.last_evaluated_cycle == 0:
        return True
    if symbol_state.last_session != normalized:
        return True
    if _is_material_rank_move(symbol_state.last_rank, current_rank):
        return True
    if symbol_state.evaluation_stale_after_cycle and cycle >= symbol_state.evaluation_stale_after_cycle:
        return True
    if symbol_state.rejection_reason and cycle >= symbol_state.rejection_stale_after_cycle:
        return True
    if _edge_rank(current_rank, universe_size) and symbol_state.last_rank == current_rank:
        return False
    return False


def _update_top_universe_state(
    daily_state: RossDailyState,
    symbols: list[str],
    *,
    now_iso: str,
    session_label: str,
    cycle: int,
) -> Tuple[Set[str], Set[str], Set[str], Set[str]]:
    incoming = set(symbols)
    existing = set(daily_state.top_universe.keys())
    new_symbols = incoming - existing
    exited_symbols = existing - incoming
    unchanged: Set[str] = set()
    escalated: Set[str] = set()

    for rank, symbol in enumerate(symbols, start=1):
        state = daily_state.top_universe.get(symbol)
        if state is None:
            daily_state.top_universe[symbol] = RossSymbolState(
                symbol=symbol,
                current_rank=rank,
                last_rank=rank,
                first_seen_utc=now_iso,
                last_seen_utc=now_iso,
                last_session=session_label,
                evaluation_stale_after_cycle=cycle + 5,
            )
            continue
        prior_rank = state.current_rank
        state.last_rank = prior_rank
        state.current_rank = rank
        state.last_seen_utc = now_iso
        state.last_session = session_label
        if _is_material_rank_move(prior_rank, rank):
            escalated.add(symbol)
        else:
            unchanged.add(symbol)

    for symbol in exited_symbols:
        daily_state.top_universe.pop(symbol, None)

    return new_symbols, exited_symbols, unchanged, escalated


def _log_ross_lists(daily_state: RossDailyState) -> None:
    print(f"[ROSS][LIST] TOP_UNIVERSE size={len(daily_state.top_universe)}")
    print(f"[ROSS][LIST] WATCHLIST_K size={len(daily_state.watchlist_k)}")
    print(f"[ROSS][LIST] FOCUS_M size={len(daily_state.focus_m)}")
    print(f"[ROSS][LIST] REJECTED_TRACKED size={len(daily_state.rejected_tracked)}")


def _scanner_request_reject_payload(
    *,
    utc_now: datetime,
    diagnostics: Dict[str, Any],
) -> Dict[str, Any]:
    empty_result = ScannerResult(
        top_n_symbols=[],
        candidates=[],
        watchlist_k=[],
        focus_m=[],
        drops_by_reason={},
        new_symbols=[],
        continuing_symbols=[],
        dropped_symbols=[],
    )
    _LAST_SCANNER_PAYLOAD = {
        "scanner_version": SCANNER_VERSION,
        "scanner_git_sha": SCANNER_GIT_SHA,
        "timestamp_utc": utc_now.isoformat(),
        "universe_top_n": [],
        "symbols": [],
        "watchlist": [],
        "watchlist_rows": [],
        "focus_rows": [],
        "drop_ledger": {},
        "watchlist_k": [],
        "focus_m": [],
        "watchlist_k_symbols": [],
        "focus_m_symbols": [],
        "candidates": [],
        "candidate_metrics": [],
        "scanner_result": empty_result,
        "topn_count": 0,
        "survivors_count": 0,
        "new_symbols": [],
        "continuing_symbols": [],
        "dropped_symbols": [],
        "drop_reason_summary": {},
        "data_quality_by_symbol": {},
        "data_quality_counts": {},
        "diagnostics": diagnostics,
        "cacheable": False,
    }
    return dict(_LAST_SCANNER_PAYLOAD)


def _payload_indicates_broker_empty(payload: Dict[str, Any]) -> bool:
    diagnostics = payload.get("diagnostics", {}) if isinstance(payload, dict) else {}
    raw_zero = diagnostics.get("raw_zero_attribution", {}) if isinstance(diagnostics, dict) else {}
    raw_broker_count = payload.get("raw_broker_count")
    if raw_broker_count is None:
        raw_broker_count = raw_zero.get("raw_broker_count")
    watchlist_count = payload.get("watchlist_count")
    if watchlist_count is None:
        watchlist_count = raw_zero.get("watchlist_count")
    if watchlist_count is None:
        watchlist_count = len(payload.get("watchlist_k_symbols", payload.get("watchlist", [])))
    broker_zero = payload.get("broker_returned_zero")
    if broker_zero is None:
        broker_zero = raw_zero.get("broker_returned_zero")
    try:
        raw_broker_count_int = int(raw_broker_count)
    except Exception:
        raw_broker_count_int = -1
    return bool(broker_zero) or raw_broker_count_int == 0 or (
        watchlist_count == 0 and raw_broker_count_int == 0
    )


def _is_payload_cacheable(payload: Dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    explicit_cacheable = payload.get("cacheable")
    if explicit_cacheable is False:
        return False
    if _payload_indicates_broker_empty(payload):
        return False
    return True


def run_scanner_cycle(
    mode: str = "integrated",
    policy: StockSelectionPolicy | None = None,
    scanner_request: ScannerRequest | None = None,
    event_collector: EventCollector | None = None,
    provider: ScannerDataProvider | None = None,
    disconnect_provider: bool | None = None,
    market_data_client: object | None = None,
    forced_session_label: str | None = None,
    forced_session_source: str | None = None,
) -> Dict[str, Any]:
    global _SCAN_CYCLE_COUNT, _WATCHLIST_HASH, _LAST_SESSION_LABEL, _LAST_PRINT_CYCLE, _PERSISTENT_PROVIDER, _PERSISTENT_PROVIDER_SOURCE, _LAST_BROKER_SCAN_TS, _LAST_SCANNER_PAYLOAD
    _SCAN_CYCLE_COUNT += 1
    utc_now = _utc_now()
    session_ctx = _market_session_context_utc(utc_now)
    session_label = forced_session_label or session_ctx.phase
    session_phase = forced_session_label or session_ctx.phase
    session_diag = resolve_session_diagnostics(
        utc_now,
        forced_session_label=forced_session_label,
        forced_session_source=forced_session_source,
    )
    daily_state = _get_ross_daily_state(utc_now, session_label)
    diagnostics: Dict[str, Any] = {"mode": mode, "ross_trading_day": daily_state.trading_day, "session_phase": session_phase}
    drop_ledger: Dict[str, str] = {}
    universe_top_n: list[dict[str, Any]] = []
    print(f"[SCANNER] MODE={mode} SESSION={session_label}")
    print(
        "[SESSION][MODE] "
        f"utc={session_diag.utc_time} ny={session_diag.ny_time} resolved={session_diag.resolved_session} "
        f"canonical={session_diag.canonical_session} reason={session_diag.reason} "
        f"forced={session_diag.resolved_session if session_diag.override_source != 'NONE' else 'NONE'} forced_source={session_diag.override_source} "
        f"reference_trading_date={session_diag.reference_trading_date} "
        f"previous_valid_market_session_date={session_diag.previous_valid_market_session_date}"
    )
    scanner_mode = get_scanner_mode()
    policy_source = "STRATEGY" if policy is not None else "CONFIG_DEFAULTS"
    resolved_policy = policy or policy_from_config()
    runtime_thresholds = _resolve_runtime_thresholds(resolved_policy, session_label)
    execution_allowlist = [normalize_session_label(value) for value in getattr(resolved_policy, "execution_permitted_sessions", ())]
    execution_allowed = normalize_session_label(session_label) in set(execution_allowlist)
    print(
        "[SESSION][RVOL_POLICY] "
        f"session={normalize_session_label(session_label)} watchlist_rvol_min={runtime_thresholds.watchlist_rvol_min}({runtime_thresholds.watchlist_rvol_source}) "
        f"focus_rvol_min={runtime_thresholds.focus_rvol_min}({runtime_thresholds.focus_rvol_source})"
    )
    print(
        "[SESSION][PCT_REFERENCE] "
        f"session={normalize_session_label(session_label)} pct_reference=LAST_RTH_CLOSE "
        "gap_reference=SESSION_OPEN_VS_LAST_RTH_CLOSE closed_prep_reference=LAST_SESSION_REFERENCE"
    )
    prep_mode_seed_enabled = normalize_session_label(session_label) == "PRE"
    print(
        "[PREP][MODE] "
        f"session={normalize_session_label(session_label)} prep_watchlist_enabled=True "
        f"seed_enabled={prep_mode_seed_enabled} seed_semantics=PRE_ONLY execution_allowed={execution_allowed}"
    )
    print(
        "[PREP][REFERENCE] "
        f"session={normalize_session_label(session_label)} pct_reference=LAST_RTH_CLOSE "
        f"gap_reference=SESSION_OPEN_VS_LAST_RTH_CLOSE reference_date={session_diag.reference_trading_date}"
    )
    print(
        "[SESSION][EXECUTION_WINDOW] "
        f"session={normalize_session_label(session_label)} execution_allowed={execution_allowed} "
        f"execution_allowlist={execution_allowlist} prep_or_closed_mode={canonical_session_label(session_label) == 'CLOSED'}"
    )
    refresh_cycle_seconds = int(get_config("FOCUS_REFRESH_SECONDS") or 0)
    last_refresh_utc = utc_now.isoformat()
    next_refresh_due_utc = (utc_now + timedelta(seconds=max(refresh_cycle_seconds, 0))).isoformat()
    print("[SCANNER][REFRESH]")
    print(f"cycle_seconds={refresh_cycle_seconds}")
    print("scanner_refresh_active=True")
    print(f"last_refresh_utc={last_refresh_utc}")
    print(f"next_refresh_due_utc={next_refresh_due_utc}")
    diagnostics["scanner_refresh"] = {
        "cycle_seconds": refresh_cycle_seconds,
        "scanner_refresh_active": True,
        "last_refresh_utc": last_refresh_utc,
        "next_refresh_due_utc": next_refresh_due_utc,
    }
    print(
        "[SCANNER][POLICY] source={source} policy_name={policy_name} price={price_min}-{price_max} "
        "gap_min={gap_min} watchlist_rvol_min={watchlist_rvol_min}({watchlist_src}) focus_rvol_min={focus_rvol_min}({focus_src}) float_max_millions={float_max} "
        "spread_max_pct={spread_max_pct}({spread_src}) allow_unknown_float={allow_unknown_float}({allow_unknown_float_src}) watchlist_k={watchlist_k} focus_m={focus_m}".format(
            source=policy_source,
            policy_name=resolved_policy.policy_name,
            price_min=resolved_policy.price_min,
            price_max=resolved_policy.price_max,
            gap_min=resolved_policy.gap_min_pct,
            watchlist_rvol_min=runtime_thresholds.watchlist_rvol_min,
            watchlist_src=runtime_thresholds.watchlist_rvol_source,
            focus_rvol_min=runtime_thresholds.focus_rvol_min,
            focus_src=runtime_thresholds.focus_rvol_source,
            float_max=resolved_policy.float_max_millions,
            spread_max_pct=runtime_thresholds.spread_max_pct,
            spread_src=runtime_thresholds.spread_max_pct_source,
            allow_unknown_float=runtime_thresholds.allow_unknown_float,
            allow_unknown_float_src=runtime_thresholds.allow_unknown_float_source,
            watchlist_k=resolved_policy.watchlist_limit_k,
            focus_m=resolved_policy.focus_limit_m,
        )
    )
    # Authority chain audit note:
    # strategy policy (StockSelectionSpec.universe) -> scanner_request_from_policy -> ScannerRequest
    # -> _resolve_universe_symbols / provider.get_top_gainers -> broker subscription.
    # Adapter defaults are generic safety defaults only and must not silently narrow strategy intent.
    request = scanner_request or scanner_request_from_policy(resolved_policy)
    print(
        "[SCANNER][ENTRY] "
        f"strategy={resolved_policy.policy_name} strategy_policy_version=v1 "
        f"requested_top_n={request.requested_top_n} "
        f"watchlist_k={resolved_policy.watchlist_limit_k} "
        f"focus_m={resolved_policy.focus_limit_m} "
        f"universe={request.universe_source.value} universe_source=scanner_request "
        f"scan_code={request.ibkr_scan_code} scan_code_source=scanner_request "
        f"instrument={request.instrument} instrument_source=scanner_request "
        f"location={request.location_code} location_source=scanner_request "
        f"above_price={request.above_price} "
        f"below_price={request.below_price}"
    )
    diagnostics["selection_spec"] = {
        "strategy": resolved_policy.policy_name,
        "requested_top_n": request.requested_top_n,
        "watchlist_k": resolved_policy.watchlist_limit_k,
        "focus_m": resolved_policy.focus_limit_m,
        "universe": request.universe_source.value,
        "scan_code": request.ibkr_scan_code,
        "instrument": request.instrument,
        "location_code": request.location_code,
        "above_price": request.above_price,
        "below_price": request.below_price,
        "ranking_intent": request.ranking_intent,
        "session_phase": request.session_phase,
    }

    validation_errors = validate_scanner_request(request)
    if validation_errors:
        diagnostics["scanner_request_valid"] = False
        diagnostics["scanner_request_errors"] = validation_errors
        print("[SCANNER][ERROR] Invalid scanner request — aborting scan.")
        for error in validation_errors:
            print(f"[SCANNER][ERROR] {error}")
        return _scanner_request_reject_payload(
            utc_now=utc_now,
            diagnostics=diagnostics,
        )
    diagnostics["scanner_request_valid"] = True

    logger = logging.getLogger(__name__)
    if _LAST_BROKER_SCAN_TS is not None and _LAST_SCANNER_PAYLOAD is not None:
        time_since_last_scan = time.time() - _LAST_BROKER_SCAN_TS
        payload_is_broker_empty = _payload_indicates_broker_empty(_LAST_SCANNER_PAYLOAD)
        in_live_mode = get_run_mode() == RunMode.LIVE
        if in_live_mode and payload_is_broker_empty:
            print("[SCANNER][REFRESH_BYPASS] previous payload empty from broker; forcing fresh rescan")
            diagnostics["scanner_refresh_window_protection"] = {
                "applied": False,
                "time_since_last_scan": round(time_since_last_scan, 3),
                "bypassed_for_broker_empty": True,
            }
        elif time_since_last_scan < 15:
            if not _is_payload_cacheable(_LAST_SCANNER_PAYLOAD):
                print("[SCANNER][REFRESH_BYPASS] previous payload empty from broker; forcing fresh rescan")
                diagnostics["scanner_refresh_window_protection"] = {
                    "applied": False,
                    "time_since_last_scan": round(time_since_last_scan, 3),
                    "bypassed_for_non_cacheable": True,
                }
            else:
                logger.debug(
                    "[SCANNER] skipping scan — IBKR refresh window protection"
                )
                diagnostics["scanner_refresh_window_protection"] = {
                    "applied": True,
                    "time_since_last_scan": round(time_since_last_scan, 3),
                }
                return dict(_LAST_SCANNER_PAYLOAD)

    run_mode = get_run_mode()
    fallback_enabled = bool(get_config("IBKR_FALLBACK_ENABLED"))
    explicit_mock = str(get_config("SCANNER_DATA_SOURCE") or "").upper() == "MOCK"
    allow_mock_fallback = run_mode in {RunMode.SIM, RunMode.PAPER} or explicit_mock
    allow_symbol_fallback = allow_mock_fallback
    using_external_provider = provider is not None
    provider_error: Optional[str] = None
    provider_fallback: Optional[dict[str, str | None]] = None
    provider_source = "IBKR"
    try:
        if provider is None:
            if market_data_client is None:
                provider = build_provider()
            else:
                provider = build_provider(market_data_client=market_data_client)
        _ensure_provider_connection(provider)
        _PERSISTENT_PROVIDER = provider
        _PERSISTENT_PROVIDER_SOURCE = provider.source_name
        print(f"[IBKR][MD] persistent connection active provider={_PERSISTENT_PROVIDER_SOURCE}")
    except ProviderConnectionError as exc:
        provider_error = str(exc)
        diagnostics["provider_error"] = provider_error
        print("STATE=DEGRADED")
        if allow_mock_fallback:
            provider_fallback = {
                "from": "IBKR",
                "to": "MOCK",
                "reason": provider_error,
            }
            diagnostics["provider_fallback"] = provider_fallback
            print(
                "[SCANNER][WARN] Provider connection failed — "
                f"falling back to MOCK reason={exc}"
            )
            provider = MockScannerProvider()
        else:
            allow_symbol_fallback = False
            provider = None
    if provider is not None:
        provider_source = provider.source_name
    if run_mode == RunMode.LIVE and provider_source == "MOCK":
        print("[CRITICAL] LIVE mode requires real broker")
        print("[CRITICAL] Scanner provider MOCK is not permitted")
        print("[CRITICAL] Shutting down trading loop")
        raise RuntimeError("LIVE mode requires IBKR scanner provider; MOCK is not permitted")
    fallback_reason = (
        provider_error
        if provider_error
        else provider_fallback["reason"]
        if provider_fallback
        else "SCANNER_DATA_SOURCE=MOCK"
        if explicit_mock and provider_source == "MOCK"
        else None
    )
    provider_trace_source = (
        "fallback"
        if provider_fallback
        else "live_broker"
        if provider_source == "IBKR"
        else "scanner_request"
    )
    print(
        "[SCANNER][PROVIDER] "
        f"provider={provider_source}"
    )
    print(f"[SCANNER][PROVIDER] source={provider_trace_source}")
    diagnostics["provider_trace_source"] = provider_trace_source
    if fallback_reason:
        print(f"[SCANNER][PROVIDER] fallback_reason={fallback_reason}")
    limits = _print_symbol_limits(
        scanner_mode,
        provider_source,
        resolved_policy,
        requested_top_n=request.requested_top_n,
    )
    # --- HARD INVARIANT: scanner limits must always be valid ---
    if limits is None:
        limits = {}

    resolved_symbol_limit = limits.get("resolved_symbol_limit")

    if resolved_symbol_limit is None:
        # canonical Ross Momentum scanner limit fallback
        resolved_symbol_limit = 50
        limits["resolved_symbol_limit"] = resolved_symbol_limit

    if limits.get("watchlist_limit") is None:
        limits["watchlist_limit"] = 15

    if limits.get("focus_limit") is None:
        limits["focus_limit"] = 5

    if limits.get("reductions") is None:
        limits["reductions"] = []

    # additional safety guard
    if "resolved_symbol_limit" not in limits:
        raise RuntimeError(
            "[SCANNER][INVARIANT] resolved_symbol_limit missing from limits structure"
        )

    diagnostics["symbol_limits"] = limits
    print("[SCANNER][STAGE] bootstrap")

    try:
        _LAST_BROKER_SCAN_TS = time.time()
        try:
            if provider is None:
                symbols = []
                diagnostics["symbol_fallback"] = "EMPTY_UNIVERSE"
            else:
                symbols = _resolve_universe_symbols(
                    provider=provider,
                    request=request,
                    limits=limits,
                    diagnostics=diagnostics,
                    allow_mock_fallback=allow_mock_fallback,
                )
        except Exception as exc:
            diagnostics["provider_error"] = str(exc)
            if provider is not None and provider.source_name != "MOCK":
                if allow_mock_fallback:
                    diagnostics["provider_fallback"] = {
                        "from": provider.source_name,
                        "to": "MOCK",
                        "reason": str(exc),
                    }
                    provider.disconnect()
                    provider = MockScannerProvider()
                    provider_source = provider.source_name
                    limits = _print_symbol_limits(
                        scanner_mode,
                        provider_source,
                        resolved_policy,
                        requested_top_n=request.requested_top_n,
                    )
                    # --- HARD INVARIANT: scanner limits must always be valid ---
                    if limits is None:
                        limits = {}

                    resolved_symbol_limit = limits.get("resolved_symbol_limit")

                    if resolved_symbol_limit is None:
                        # canonical Ross Momentum scanner limit fallback
                        resolved_symbol_limit = 50
                        limits["resolved_symbol_limit"] = resolved_symbol_limit

                    if limits.get("watchlist_limit") is None:
                        limits["watchlist_limit"] = 15

                    if limits.get("focus_limit") is None:
                        limits["focus_limit"] = 5

                    if limits.get("reductions") is None:
                        limits["reductions"] = []

                    # additional safety guard
                    if "resolved_symbol_limit" not in limits:
                        raise RuntimeError(
                            "[SCANNER][INVARIANT] resolved_symbol_limit missing from limits structure"
                        )

                    diagnostics["symbol_limits"] = limits
                    symbols = _resolve_universe_symbols(
                        provider=provider,
                        request=request,
                        limits=limits,
                        diagnostics=diagnostics,
                        allow_mock_fallback=allow_mock_fallback,
                    )
                else:
                    allow_symbol_fallback = False
                    symbols = []
            else:
                symbols = []

        diagnostics["provider_source"] = provider_source
        diagnostics["symbol_count"] = len(symbols)
        if not symbols and allow_symbol_fallback:
            symbols = list(get_config("SCANNER_DEFAULT_SYMBOLS"))
            diagnostics["symbol_fallback"] = "SCANNER_DEFAULT_SYMBOLS"
        if not symbols and allow_symbol_fallback:
            fallback_provider = MockScannerProvider()
            symbols = fallback_provider.get_top_gainers(
                limits["resolved_symbol_limit"]
            )
            diagnostics["symbol_fallback"] = "MOCK_UNIVERSE"
        raw_symbols = list(symbols)
        upper_symbols = [symbol.upper() for symbol in raw_symbols]
        translation_applied = any(before != after for before, after in zip(raw_symbols, upper_symbols))
        truncation_applied = len(upper_symbols) > limits["resolved_symbol_limit"]
        symbols = upper_symbols[: limits["resolved_symbol_limit"]]
        requested_top_n = int(request.requested_top_n or len(symbols))
        ibkr_universe_diag = diagnostics.get("ibkr_universe", {})
        diagnostics["scanner_flow"] = {
            "requested_top_n": requested_top_n,
            "broker_rows_requested": int(limits["resolved_symbol_limit"]),
            "effective_internal_processing_limit": int(limits["resolved_symbol_limit"]),
            "instrument": request.instrument,
            "location": ibkr_universe_diag.get("effective_location_code", request.location_code),
            "scanCode": ibkr_universe_diag.get("effective_scan_code", request.ibkr_scan_code),
            "effective_location_code": ibkr_universe_diag.get("effective_location_code", request.location_code),
            "effective_scan_code": ibkr_universe_diag.get("effective_scan_code", request.ibkr_scan_code),
            "retry_attempts": int(ibkr_universe_diag.get("retry_attempts", 0) or 0),
            "retry_exhausted": bool(ibkr_universe_diag.get("retry_exhausted", False)),
            "returned_rows": int(ibkr_universe_diag.get("returned_rows", len(raw_symbols)) or 0),
            "provider": provider_source,
            "translation_applied": translation_applied,
            "truncation_applied": truncation_applied,
            "raw_broker_count": int(ibkr_universe_diag.get("returned_rows", len(raw_symbols)) or 0),
        }
        if len(symbols) == 0:
            logger.error(
                "[SCANNER][BROKER_EMPTY] IBKR returned zero symbols "
                f"(scanCode={diagnostics['scanner_flow'].get('effective_scan_code', request.ibkr_scan_code)}, "
                f"location={diagnostics['scanner_flow'].get('effective_location_code', request.location_code)}, "
                f"price_range={request.above_price}-{request.below_price})"
            )
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
        universe_top_n = _build_universe_entries(symbols, provider)

        new_symbols_delta, exited_symbols_delta, unchanged_symbols_delta, escalated_symbols_delta = _update_top_universe_state(
            daily_state,
            symbols,
            now_iso=utc_now.isoformat(),
            session_label=normalize_session_label(session_label),
            cycle=_SCAN_CYCLE_COUNT,
        )
        print(
            "[ROSS][DELTA] "
            f"new={len(new_symbols_delta)} exited={len(exited_symbols_delta)} "
            f"unchanged={len(unchanged_symbols_delta)} escalated={len(escalated_symbols_delta)}"
        )

        snapshot_enricher = MarketSnapshotEnricher(
            connection_manager=getattr(provider, "connection_manager", None),
            batch_timeout_seconds=5.0,
        )
        contract_details_by_symbol = _provider_contract_details_by_symbol(provider)
        market_snapshots = snapshot_enricher.fetch_snapshots(
            symbols,
            contract_details_by_symbol=contract_details_by_symbol,
        )
        snapshot_diag = getattr(snapshot_enricher, "last_fetch_diagnostics", {}) or {}
        diagnostics["market_snapshot_enrichment"] = {
            "requested_symbols": len(symbols),
            "snapshots_returned": len(market_snapshots),
            "batch_timeout_seconds": 5.0,
            "snapshot_success_count": sum(1 for d in snapshot_diag.values() if d.get("snapshot_received")),
            "snapshot_failure_count": sum(1 for d in snapshot_diag.values() if not d.get("snapshot_received")),
            "symbols_with_last_price": sum(1 for d in snapshot_diag.values() if d.get("last_price") is not None),
            "symbols_with_bid_ask": sum(1 for d in snapshot_diag.values() if d.get("bid") is not None and d.get("ask") is not None),
            "symbols_with_volume": sum(1 for d in snapshot_diag.values() if d.get("volume") is not None),
        }

        float_cache = _bootstrap_float_cache(symbols, provider)
        thresholds = _gate_thresholds(resolved_policy, runtime_thresholds)
        candidates: List[Dict[str, Any]] = []
        evaluated_contexts: List[Dict[str, Any]] = []

        print("[SCANNER][STAGE] market_snapshot_enrichment")
        print("[SCANNER][STAGE] gates")
        for rank, symbol in enumerate(symbols, start=1):
            symbol_state = daily_state.top_universe.get(symbol)
            should_recheck = True
            if symbol_state is not None:
                should_recheck = _should_recheck_symbol(
                    symbol_state,
                    current_rank=rank,
                    cycle=_SCAN_CYCLE_COUNT,
                    session_label=session_label,
                    universe_size=len(symbols),
                )
            if provider_source != "MOCK" and not should_recheck and symbol in daily_state.rejected_tracked:
                continue
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
            if context.get("snapshot_error") == "MD_CONFLICT":
                drop_ledger.setdefault(symbol, "DROP_MD_CONFLICT")
                flags = context.setdefault("data_quality_flags", [])
                if "DROP_MD_CONFLICT" not in flags:
                    flags.append("DROP_MD_CONFLICT")
                print("[SCANNER][DROP] " f"symbol={symbol} reason=DROP_MD_CONFLICT")
                evaluated_contexts.append(context)
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
            snapshot_data = market_snapshots.get(symbol, {}) if isinstance(market_snapshots, dict) else {}
            context["snapshot_fetch_attempted"] = True
            if isinstance(snapshot_data, dict):
                context["snapshot_last_price"] = snapshot_data.get("last_price")
                context["snapshot_bid"] = snapshot_data.get("bid")
                context["snapshot_ask"] = snapshot_data.get("ask")
                context["snapshot_volume"] = snapshot_data.get("volume")
                context["snapshot_close"] = snapshot_data.get("close")
                if context.get("last_price") is None and snapshot_data.get("last_price") is not None:
                    context["last_price"] = snapshot_data.get("last_price")
                if context.get("bid") is None and snapshot_data.get("bid") is not None:
                    context["bid"] = snapshot_data.get("bid")
                if context.get("ask") is None and snapshot_data.get("ask") is not None:
                    context["ask"] = snapshot_data.get("ask")
                if context.get("volume") is None and snapshot_data.get("volume") is not None:
                    context["volume"] = snapshot_data.get("volume")
                if context.get("close") is None and snapshot_data.get("close") is not None:
                    context["close"] = snapshot_data.get("close")
            identity = _context_identity(context)
            merge_target_found = isinstance(snapshot_data, dict) and any(snapshot_data.get(key) is not None for key in ("last_price", "bid", "ask", "volume", "close"))
            context["identity_key"] = identity.key
            context["identity_merge_failed"] = bool(context.get("snapshot_fetch_attempted") and not merge_target_found and symbol in market_snapshots)
            print(
                "[ENRICH][SNAPSHOT_MERGE] "
                f"symbol={symbol} conId={identity.con_id} last={context.get('last_price')} bid={context.get('bid')} ask={context.get('ask')} volume={context.get('volume')} merge_target_found={merge_target_found}"
            )
            snapshot_failed = all(context.get(key) is None for key in ("last_price", "bid", "ask", "volume", "close"))
            context["snapshot_fetch_failed"] = snapshot_failed
            if snapshot_failed:
                print(f"[SCANNER][DROP] symbol={symbol} reason=DATA_QUALITY_FAIL_SNAPSHOT")
                context.setdefault("data_quality_flags", []).append("DATA_QUALITY_FAIL_SNAPSHOT")

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

            float_class = _classify_float(context.get("float_shares"))
            context["float_class"] = float_class
            if context.get("float_shares") is not None:
                if context.get("float_source") == "cache":
                    print(f"[FLOAT] cache hit symbol={symbol}")
                else:
                    print(
                        f"[FLOAT] symbol={symbol} class={float_class or 'UNKNOWN'} "
                        f"shares={context.get('float_shares')}"
                    )

            _populate_pct_change(context, provider)
            print(
                "[PCT] "
                f"symbol={symbol} session={normalize_session_label(session_label)} "
                f"baseline={context.get('reference_label') or 'NA'} value={context.get('pct_change')}"
            )
            print(
                "[PCT_DEBUG] "
                f"symbol={symbol} session={normalize_session_label(session_label)} "
                f"reference={context.get('reference_label') or 'NA'} "
                f"last_price={context.get('last_price')} reference_price={context.get('reference_price')} "
                f"pct_change={context.get('pct_change')}"
            )
            if context.get("reference_label"):
                print(
                    "[GAP] "
                    f"symbol={symbol} source=prep reference={context.get('reference_label')} "
                    f"value={context.get('pct_change')}"
                )
            rvol_baseline = context.get("rvol_baseline") or "UNKNOWN"
            rvol_method = context.get("rvol_method") or "UNKNOWN"
            print(
                "[RVOL][REQUEST] "
                f"symbol={symbol} conId={identity.con_id} session={normalize_session_label(session_label)} source=intraday_stats"
            )
            print(
                "[RVOL][BASELINE] "
                f"symbol={symbol} avg_volume_20d={context.get('avg_volume_20d')} expected_phase_volume={context.get('expected_phase_volume')} source={rvol_method} found={context.get('avg_volume_20d') is not None}"
            )
            print(
                "[RVOL][MERGE] "
                f"symbol={symbol} merge_target_found=True rvol_discovery={context.get('rvol_discovery')} rvol_phase={context.get('rvol_phase')}"
            )

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
            if _is_etf_context(context):
                drop_reason = "DROP_ETF_EXCLUDED"
                drop_ledger.setdefault(symbol, drop_reason)
                print(f"[SCANNER][DROP] symbol={symbol} reason={drop_reason}")
                evaluated_contexts.append(context)
                continue
            drop_reason = _evaluate_watchlist_gates(context, thresholds)
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
                                "watchlist_rvol_min": thresholds.watchlist_rvol_min,
                                "focus_rvol_min": thresholds.focus_rvol_min,
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
            drop_reason = _evaluate_float_gate(context, thresholds)
            if drop_reason:
                drop_ledger.setdefault(symbol, drop_reason)
                print(f"[SCANNER][DROP] symbol={symbol} reason={drop_reason}")
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
        ranking_intent = request.ranking_intent or resolved_policy.ranking_intent
        selector = resolve_watchlist_selector(ranking_intent)
        watchlist_limit = limits["watchlist_limit"]
        allow_news = bool(get_config("NEWS_ENABLED")) and run_mode not in {
            RunMode.LIVE,
            RunMode.READ_ONLY,
            RunMode.PAPER,
        }
        catalyst_override = None if allow_news else True
        session_override = "" if session_label == "WEEKEND" and run_mode != RunMode.LIVE else None
        context_by_symbol = {
            context.get("symbol"): context for context in evaluated_contexts
        }
        candidate_symbols = [
            symbol for symbol in context_by_symbol.keys() if symbol
        ]
        news_by_symbol = {}
        news_diag = NewsDiagnostics(False, False, None, 0, 0, {})
        if selector is not None and allow_news and candidate_symbols:
            news_by_symbol, news_diag = _enrich_news_context(
                candidate_symbols,
                provider_source,
            )
        candidate_metrics_for_ranking: List[CandidateMetrics] = []
        for context in evaluated_contexts:
            symbol = context.get("symbol")
            if not symbol:
                continue
            candidate_metrics_for_ranking.append(
                _candidate_from_context(
                    context,
                    news_by_symbol.get(symbol, {}),
                    thresholds,
                    drop_reason=drop_ledger.get(symbol),
                    timestamp_utc=utc_now.isoformat(),
                    catalyst_present_override=catalyst_override,
                    session_label_override=session_override,
                )
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
        print(
            "[WATCHLIST][INPUT] "
            f"session={normalize_session_label(session_label)} gated_survivors={len(ranked)} k={watchlist_limit}"
        )
        if selector is not None:
            selection_metrics = candidate_metrics_for_ranking
            if session_label == "WEEKEND" and run_mode != RunMode.LIVE:
                selection_metrics = [
                    replace(metric, session_label=None)
                    for metric in candidate_metrics_for_ranking
                ]
            selected_metrics = selector(selection_metrics, resolved_policy)
            selected_symbols = [metric.symbol for metric in selected_metrics]
            if watchlist_limit > 0:
                selected_symbols = selected_symbols[:watchlist_limit]
            watchlist_contexts = [
                context_by_symbol[symbol]
                for symbol in selected_symbols
                if symbol in context_by_symbol
            ]
        else:
            watchlist_contexts = ranked[:watchlist_limit] if watchlist_limit > 0 else []
        if ranked:
            ordered_symbols = [context["symbol"] for context in ranked]
            print(
                "[WATCHLIST][ORDER] "
                f"symbols={ordered_symbols} ranking_basis=pct_change,rvol,dollar_volume"
            )
        if watchlist_limit > 0 and len(ranked) <= watchlist_limit:
            print(
                "[WATCHLIST][PASS] "
                f"survivor_count={len(ranked)} <= k={watchlist_limit}; all survivors expected unless explicitly rejected"
            )
            watchlist_contexts = ranked[:]
        elif watchlist_limit > 0 and len(watchlist_contexts) < watchlist_limit:
            selected_symbols = {context["symbol"] for context in watchlist_contexts}
            for context in ranked:
                symbol = context["symbol"]
                if symbol in selected_symbols:
                    continue
                watchlist_contexts.append(context)
                selected_symbols.add(symbol)
                if len(watchlist_contexts) >= watchlist_limit:
                    break

        normalized_session = normalize_session_label(session_label)
        prep_mode_seed_enabled = normalized_session == "PRE"
        can_seed_prep = prep_mode_seed_enabled and not provider_error and bool(symbols)
        prep_seed_blockers = []
        if provider_error:
            prep_seed_blockers.append("provider_error")
        if not symbols:
            prep_seed_blockers.append("empty_universe")
        print(
            "[SCANNER][SESSION_AWARE] "
            f"session={normalized_session} prep_mode_seed_enabled={prep_mode_seed_enabled} "
            f"prep_seed_enabled={can_seed_prep} prep_seed_blockers={prep_seed_blockers or ['none']}"
        )
        if can_seed_prep and len(watchlist_contexts) < 10:
            selected_symbols = {context["symbol"] for context in watchlist_contexts}
            topn_gap_sorted = sorted(
                [
                    context
                    for context in evaluated_contexts
                    if context.get("symbol")
                    and context.get("pct_change") is not None
                    and not _is_etf_context(context)
                ],
                key=lambda row: (_safe_float(row.get("pct_change"), 0.0) or 0.0),
                reverse=True,
            )
            target_size = max(10, min(15, watchlist_limit or 15))
            for context in topn_gap_sorted:
                symbol = context["symbol"]
                if symbol in selected_symbols:
                    continue
                watchlist_contexts.append(context)
                selected_symbols.add(symbol)
                if len(watchlist_contexts) >= target_size:
                    break
        enrich_summary = _enrichment_audit_summary(evaluated_contexts)
        diagnostics["enrichment_summary"] = enrich_summary
        print(
            "[ENRICH][SUMMARY] "
            f"candidates={enrich_summary['candidates']} snapshot_ok={enrich_summary['snapshot_ok']} reference_ok={enrich_summary['reference_ok']} "
            f"pct_ready={enrich_summary['pct_ready']} gap_ready={enrich_summary['gap_ready']} rvol_ready={enrich_summary['rvol_ready']} "
            f"float_ready={enrich_summary['float_ready']} identity_merge_failures={enrich_summary['identity_merge_failures']}"
        )

        discovery_stats = {
            "pct_change_pass": sum(1 for c in evaluated_contexts if _safe_float(c.get("pct_change"), None) is not None and _safe_float(c.get("pct_change"), None) >= _resolve_pct_change_min_for_session(str(c.get("session") or ""), thresholds)),
            "price_pass": sum(1 for c in evaluated_contexts if _evaluate_price_gate(c, thresholds) is None),
            "float_pass": sum(1 for c in candidates if _evaluate_float_gate(dict(c), thresholds) is None),
            "watchlist_final": len(watchlist_contexts),
        }
        print(
            "[DISCOVERY_STATS] "
            f"pct_change_pass={discovery_stats['pct_change_pass']} "
            f"price_pass={discovery_stats['price_pass']} "
            f"float_pass={discovery_stats['float_pass']} "
            f"watchlist_final={discovery_stats['watchlist_final']}"
        )
        if watchlist_limit > 0 and ranked and not watchlist_contexts:
            watchlist_contexts = ranked[:watchlist_limit]
            print(
                "[WATCHLIST][FALLBACK] "
                "selector_underflow=True reason=EMPTY_SELECTION_WITH_SURVIVORS"
            )

        watchlist_set = {context["symbol"] for context in watchlist_contexts}
        for context in ranked:
            if context["symbol"] in watchlist_set:
                drop_ledger.pop(context["symbol"], None)
                continue
            drop_ledger.setdefault(context["symbol"], "DROP_RANK_BELOW_WATCHLIST")
            rank_value = next((idx for idx, row in enumerate(ranked, start=1) if row["symbol"] == context["symbol"]), None)
            print(
                "[WATCHLIST][DROP] "
                f"symbol={context['symbol']} reason=DROP_RANK_BELOW_WATCHLIST rank={rank_value} threshold={watchlist_limit}"
            )
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
        print(
            "[WATCHLIST][SELECT] "
            f"selected={len(watchlist_contexts)} selected_symbols={[context['symbol'] for context in watchlist_contexts]}"
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
                context["promotion_reason"] = "PREP_CONTEXT_BACKFILL"
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

        prep_candidates = _load_premarket_prep_candidates() if can_seed_prep else {}
        print("[PREP][ARTIFACT]")
        print(f"session={normalized_session}")
        print(f"prep_mode_active={prep_mode_seed_enabled}")
        print(f"prep_seed_enabled={can_seed_prep}")
        if not prep_mode_seed_enabled:
            print("status=SKIPPED reason=session_not_pre")
        elif not can_seed_prep and provider_error:
            print("status=SKIPPED reason=provider_error")
        elif not can_seed_prep and not symbols:
            print("status=SKIPPED reason=empty_raw_universe")
        elif prep_candidates:
            print(f"status=LOADED symbols={len(prep_candidates)}")
        else:
            print("status=NOT_FOUND symbols=0")
        watchlist_contexts, prep_seeded_count, prep_invalidated_count = _seed_watchlist_from_prep(
            session_label=session_label,
            watchlist_contexts=watchlist_contexts,
            context_by_symbol=context_by_symbol,
            candidates=candidates,
            drop_ledger=drop_ledger,
            watchlist_limit=watchlist_limit,
            prep_candidates=prep_candidates,
        )
        if prep_candidates:
            print(
                "[PREP][SEED] "
                f"session={session_label} prep_symbols={len(prep_candidates)} seeded={prep_seeded_count} "
                f"invalidated={prep_invalidated_count}"
            )
            if prep_seeded_count == 0:
                print("[PREP][SEED] status=NO_SEED reason=prep_candidates_invalidated_or_unusable")
        elif prep_mode_seed_enabled:
            if not symbols:
                print("[PREP][SEED] status=NO_SEED reason=raw_scanner_universe_empty")
            else:
                print("[PREP][SEED] status=NO_SEED reason=no_prep_artifacts")
        if not watchlist_contexts and prep_candidates:
            print(
                "[PREP][HARD_FAIL] PRE watchlist empty after prep seeding "
                f"prep_symbols={len(prep_candidates)} invalidated={prep_invalidated_count}"
            )

        for context in watchlist_contexts:
            context.setdefault("prep_seeded", False)
            context.setdefault("live_confirmation_pending", False)
            context.setdefault("promotion_reason", "LIVE_SCAN")
            context.setdefault("watchlist_source", "LIVE_SCAN")
            context.setdefault("rvol_discovery", context.get("scanner_rvol"))
            context.setdefault("rvol_phase", context.get("scanner_rvol"))
            context.setdefault("phase_volume_ratio", None)

        watchlist_contexts = _rank_candidates(watchlist_contexts)

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
        if selector is None:
            if watchlist_symbols and allow_news:
                news_by_symbol, news_diag = _enrich_news_context(
                    watchlist_symbols, provider_source
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

        symbol_contexts: dict[str, SymbolContext] = {}
        for context in watchlist_contexts:
            symbol = str(context.get("symbol") or "")
            if not symbol:
                continue
            symbol_context = build_symbol_context(
                symbol,
                session_label=str(context.get("session") or session_label),
                base_context=context,
                news_context=news_by_symbol.get(symbol, {}),
            )
            symbol_contexts[symbol] = symbol_context
            _RUNTIME_CONTEXT_REGISTRY.refresh_if_needed(symbol_context)

        print("[SCANNER][STAGE] print")
        fast_rows = _build_fast_rows(watchlist_contexts, news_by_symbol)
        focus_limit = limits["focus_limit"]
        focus_candidates: list[Dict[str, Any]] = []
        for context in watchlist_contexts:
            focus_drop = _evaluate_focus_gates(context, thresholds)
            if focus_drop:
                context["focus_drop_reason"] = focus_drop
                print(
                    "[SCANNER][FOCUS_DROP] symbol="
                    f"{context.get('symbol')} reason={focus_drop}"
                )
                continue
            focus_candidates.append(context)
        focus_contexts = _rank_candidates(focus_candidates)
        focus_contexts = sorted(
            focus_contexts,
            key=lambda item: -(
                symbol_contexts.get(item.get("symbol", "")).focus_rank_score
                if symbol_contexts.get(item.get("symbol", ""))
                else 0.0
            ),
        )[:focus_limit]
        deep_rows = _build_deep_rows(focus_contexts, news_by_symbol)

        if not deep_rows and watchlist_contexts:
            focus_drop_reasons = Counter(
                str(context.get("focus_drop_reason") or "")
                for context in watchlist_contexts
                if context.get("focus_drop_reason")
            )
            print(
                "[SCANNER][FOCUS_EMPTY] "
                f"blocked_by_focus_rvol={focus_drop_reasons.get('DROP_RVOL_FOCUS', 0)} "
                f"blocked_by_spread={focus_drop_reasons.get('DROP_SPREAD', 0) + focus_drop_reasons.get('DROP_MISSING_SPREAD', 0)} "
                f"blocked_by_float={focus_drop_reasons.get('DROP_FLOAT_MAX', 0) + focus_drop_reasons.get('DROP_FLOAT_MISSING', 0)} "
                f"blocked_by_news={focus_drop_reasons.get('DROP_NO_CATALYST', 0)} "
                f"blocked_by_data_quality={focus_drop_reasons.get('DROP_MISSING_BID_ASK', 0) + focus_drop_reasons.get('DROP_MISSING_PRICE', 0) + focus_drop_reasons.get('DROP_MISSING_RVOL', 0)}"
            )

        exclusion_counts = Counter(drop_ledger.values())
        drop_summary = dict(exclusion_counts)
        diagnostics["drop_ledger_summary"] = drop_summary
        gate_outcome_summary = _gate_outcome_summary(watchlist_contexts)
        true_gate_pass_count = gate_outcome_summary["true_gate_pass_count"]
        backfill_count = gate_outcome_summary["backfill_count"]
        seeded_count = gate_outcome_summary["seeded_count"]
        diagnostics["gate_outcome_summary"] = gate_outcome_summary
        print(
            "[SCANNER][SUMMARY] "
            f"session={session_label} candidates={len(symbols)} survivors={len(watchlist_contexts)} "
            f"watchlist={len(watchlist_contexts)} true_gate_pass_count={true_gate_pass_count} "
            f"backfill_count={backfill_count} seeded_count={seeded_count} drop_reasons={drop_summary}"
        )

        watchlist_symbols = [context["symbol"] for context in watchlist_contexts]
        focus_symbols = [row.symbol for row in deep_rows]

        flow = diagnostics.get("scanner_flow", {})
        raw_count = int(flow.get("raw_broker_count", len(symbols)))
        broker_zero = raw_count == 0
        local_gating_eliminated_all = raw_count > 0 and len(watchlist_symbols) == 0
        print("[SCANNER][RAW_ZERO]")
        print(f"provider={flow.get('provider', provider_source)}")
        print(f"broker_returned_zero={broker_zero}")
        print(f"instrument={flow.get('instrument', request.instrument)}")
        print(f"location={flow.get('location', request.location_code)}")
        print(f"scanCode={flow.get('scanCode', request.ibkr_scan_code)}")
        print(f"effective_location_code={flow.get('effective_location_code', flow.get('location', request.location_code))}")
        print(f"effective_scan_code={flow.get('effective_scan_code', flow.get('scanCode', request.ibkr_scan_code))}")
        print(f"retry_attempts={flow.get('retry_attempts', 0)}")
        print(f"retry_exhausted={flow.get('retry_exhausted', False)}")
        print(f"returned_rows={flow.get('returned_rows', raw_count)}")
        print(f"requested_top_n={flow.get('requested_top_n', request.requested_top_n)}")
        print(f"broker_rows_requested={flow.get('broker_rows_requested', limits['resolved_symbol_limit'])}")
        print(f"effective_internal_processing_limit={flow.get('effective_internal_processing_limit', limits['resolved_symbol_limit'])}")
        print(f"translation_or_truncation_occurred={bool(flow.get('translation_applied') or flow.get('truncation_applied'))}")
        print(f"local_gating_applied={raw_count > 0}")
        print(f"local_gating_eliminated_all={local_gating_eliminated_all}")
        if local_gating_eliminated_all:
            print(f"drop_reasons={drop_summary}")
        print(f"raw_broker_count={raw_count}")
        print(f"candidate_count_entering_gates={len(symbols)}")
        print(f"survivor_count_after_gates={len(watchlist_contexts)}")
        print(f"watchlist_count={len(watchlist_symbols)}")
        print(f"focus_count={len(focus_symbols)}")

        scanner_contract = {
            "top_n": requested_top_n,
            "watchlist_k": len(watchlist_symbols),
            "focus_m": len(focus_symbols),
        }
        contract_valid = 0 <= scanner_contract["focus_m"] <= scanner_contract["watchlist_k"] <= scanner_contract["top_n"]
        scanner_contract["contract_valid"] = contract_valid
        print("[SCANNER][CONTRACT]")
        print(f"top_n={scanner_contract['top_n']}")
        print(f"watchlist_k={scanner_contract['watchlist_k']}")
        print(f"focus_m={scanner_contract['focus_m']}")
        print(f"contract_valid={contract_valid}")
        diagnostics["scanner_contract"] = scanner_contract

        raw_zero_payload = {
            "provider": flow.get("provider", provider_source),
            "broker_returned_zero": broker_zero,
            "instrument": flow.get("instrument", request.instrument),
            "location": flow.get("location", request.location_code),
            "scanCode": flow.get("scanCode", request.ibkr_scan_code),
            "effective_location_code": flow.get("effective_location_code", flow.get("location", request.location_code)),
            "effective_scan_code": flow.get("effective_scan_code", flow.get("scanCode", request.ibkr_scan_code)),
            "retry_attempts": int(flow.get("retry_attempts", 0) or 0),
            "retry_exhausted": bool(flow.get("retry_exhausted", False)),
            "returned_rows": int(flow.get("returned_rows", raw_count) or 0),
            "requested_top_n": flow.get("requested_top_n", request.requested_top_n),
            "broker_rows_requested": flow.get("broker_rows_requested", limits["resolved_symbol_limit"]),
            "effective_internal_processing_limit": flow.get("effective_internal_processing_limit", limits["resolved_symbol_limit"]),
            "translation_or_truncation_occurred": bool(flow.get("translation_applied") or flow.get("truncation_applied")),
            "local_gating_applied": raw_count > 0,
            "local_gating_eliminated_all": local_gating_eliminated_all,
            "raw_broker_count": raw_count,
            "candidate_count_entering_gates": len(symbols),
            "survivor_count_after_gates": len(watchlist_contexts),
            "watchlist_count": len(watchlist_symbols),
            "focus_count": len(focus_symbols),
            "drop_reasons": drop_summary if (local_gating_eliminated_all or drop_summary) else {},
        }
        diagnostics["raw_zero_attribution"] = raw_zero_payload
        if not contract_valid:
            diagnostics["scanner_contract_invalid"] = True

        previous_watch = set(daily_state.watchlist_k.keys())
        previous_focus = set(daily_state.focus_m.keys())
        current_watch = set(watchlist_symbols)
        current_focus = set(focus_symbols)

        watch_context_by_symbol = {ctx.get("symbol"): ctx for ctx in watchlist_contexts}
        for symbol in watchlist_symbols:
            symbol_state = daily_state.top_universe.get(symbol)
            if symbol_state is None:
                continue
            symbol_state.watch_pass_reasons = ["FILTER_PASS"]
            watch_ctx = watch_context_by_symbol.get(symbol) or {}
            reason = watch_ctx.get("promotion_reason") if isinstance(watch_ctx, dict) else None
            if reason:
                symbol_state.watch_pass_reasons = [reason]
            symbol_state.last_evaluated_cycle = _SCAN_CYCLE_COUNT
            symbol_state.evaluation_stale_after_cycle = _SCAN_CYCLE_COUNT + 5
            symbol_state.rejection_reason = None
            symbol_state.float_class = _classify_float(float_cache.get(symbol))
            if symbol not in previous_watch:
                promote_reason = symbol_state.watch_pass_reasons[0] if symbol_state.watch_pass_reasons else "FILTER_PASS"
                print(f"[ROSS][PROMOTE] symbol={symbol} from=TOP_UNIVERSE to=WATCHLIST_K reason={promote_reason}")
            else:
                persist_reason = symbol_state.watch_pass_reasons[0] if symbol_state.watch_pass_reasons else "FILTER_PASS"
                print(f"[ROSS][PERSIST] symbol={symbol} list=WATCHLIST_K reason={persist_reason}")
            daily_state.watchlist_k[symbol] = symbol_state
            daily_state.rejected_tracked.pop(symbol, None)

        for symbol in list(daily_state.watchlist_k.keys()):
            if symbol not in current_watch:
                state = daily_state.watchlist_k.pop(symbol)
                if symbol in current_focus:
                    continue
                reason = drop_ledger.get(symbol, "RANK_DECAY")
                print(f"[ROSS][DROP] symbol={symbol} list=WATCHLIST_K reason={reason}")
                state.rejection_reason = _ross_reason_from_drop(reason) if reason.startswith("DROP_") else reason
                state.rejection_stale_after_cycle = _SCAN_CYCLE_COUNT + 6
                daily_state.rejected_tracked[symbol] = state

        for symbol in focus_symbols:
            symbol_state = daily_state.top_universe.get(symbol)
            if symbol_state is None:
                continue
            symbol_state.focus_ready_reasons = ["FOCUS_FILTERS_PASS"]
            symbol_state.last_evaluated_cycle = _SCAN_CYCLE_COUNT
            symbol_state.evaluation_stale_after_cycle = _SCAN_CYCLE_COUNT + 3
            if symbol not in previous_focus:
                print(f"[ROSS][PROMOTE] symbol={symbol} from=WATCHLIST_K to=FOCUS_M reason=SETUP_READY")
            else:
                print(f"[ROSS][PERSIST] symbol={symbol} list=FOCUS_M reason=SETUP_STILL_VALID")
            daily_state.focus_m[symbol] = symbol_state

        for symbol in list(daily_state.focus_m.keys()):
            if symbol not in current_focus:
                daily_state.focus_m.pop(symbol, None)
                if symbol in current_watch:
                    print(f"[ROSS][DEMOTE] symbol={symbol} from=FOCUS_M to=WATCHLIST_K reason=FOCUS_GATES")

        for symbol, reason in drop_ledger.items():
            state = daily_state.top_universe.get(symbol)
            if state is None:
                continue
            mapped = _ross_reason_from_drop(reason)
            state.rejection_reason = mapped
            state.rejection_stale_after_cycle = _SCAN_CYCLE_COUNT + 8
            state.last_evaluated_cycle = _SCAN_CYCLE_COUNT
            daily_state.rejected_tracked[symbol] = state
            if symbol not in current_watch:
                print(f"[ROSS][REJECT] symbol={symbol} reason={mapped}")

        real_focus_symbols = list(daily_state.focus_m.keys())
        if focus_symbols != real_focus_symbols:
            print(
                "[SCANNER][FOCUS_RECONCILE] "
                f"printed={focus_symbols} real={real_focus_symbols} action=use_real_focus_list"
            )
            focus_symbols = real_focus_symbols

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
                    catalyst_present_override=catalyst_override,
                    session_label_override=session_override,
                )
            )
        if session_override == "":
            candidate_metrics = [
                replace(candidate, session_label=None)
                for candidate in candidate_metrics
            ]
        candidate_lookup = {candidate.symbol: candidate for candidate in candidate_metrics}
        watchlist_metrics = [
            candidate_lookup[symbol]
            for symbol in watchlist_symbols
            if symbol in candidate_lookup
        ]
        focus_metrics = [candidate_lookup[symbol] for symbol in focus_symbols if symbol in candidate_lookup]
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
        _log_ross_lists(daily_state)
        logger.info(
            f"[SCANNER][RESULT] broker_rows={len(symbols)} "
            f"watchlist_k={len(watchlist_symbols)} focus_m={len(focus_symbols)}"
        )

        watchlist_dir = Path("output/watchlists")
        watchlist_dir.mkdir(parents=True, exist_ok=True)
        ts = utc_now.strftime("%Y%m%d_%H%M%S_UTC")
        file_path = watchlist_dir / f"watchlist_RossMomentum_{ts}.txt"
        watchlist_empty_reason = None
        if not watchlist_contexts:
            if not symbols:
                watchlist_empty_reason = "EMPTY_UNIVERSE"
            elif not candidates:
                watchlist_empty_reason = "NO_GATED_SURVIVORS"
            else:
                watchlist_empty_reason = "NO_WATCHLIST_SELECTED"
        header_lines = [
            f"# session={session_label}",
            f"# provider={provider_source}",
            f"# provider_fallback_reason={fallback_reason or 'none'}",
            "# subscription="
            f"instrument={request.instrument} "
            f"locationCode={request.location_code} "
            f"scanCode={request.ibkr_scan_code} "
            f"numberOfRows={request.requested_top_n} "
            f"abovePrice={request.above_price} "
            f"belowPrice={request.below_price}",
            f"# requested_top_n={request.requested_top_n} returned_top_n={len(symbols)}",
            f"# policy_source={policy_source}",
            f"# policy_name={resolved_policy.policy_name}",
            f"# ranking_intent={request.ranking_intent}",
            f"# candidates_count={len(symbols)}",
            f"# gated_count={len(candidates)}",
            f"# watchlist_count={len(watchlist_contexts)}",
            f"# watchlist_k={len(watchlist_symbols)} focus_m={len(focus_symbols)}",
            f"# drop_reasons={dict(exclusion_counts)}",
        ]
        if watchlist_empty_reason:
            header_lines.append(f"# watchlist_empty_reason={watchlist_empty_reason}")
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
        if disconnect_provider is None:
            disconnect_provider = False
        if disconnect_provider and provider is not None:
            provider.disconnect()

    new_symbols = sorted(set(watchlist_symbols) - _PREV_WATCHLIST)
    continuing_symbols = sorted(set(watchlist_symbols) & _PREV_WATCHLIST)
    dropped_symbols = sorted(_PREV_WATCHLIST - set(watchlist_symbols))
    # Canonical accounting:
    # TopN = raw scanner symbols returned by provider.
    # GatedSurvivors = symbols that passed discovery gates into the watchlist selection pool.
    # WATCHLIST_K = final selected watchlist after ranking/capping.
    # FOCUS_M = final focus set after focus gates/capping.
    print_scanner_contract(
        topn_count=len(symbols),
        survivors_count=len(watchlist_contexts),
        watchlist_k=watchlist_symbols,
        focus_m=focus_symbols,
        drop_summary=drop_summary,
        new_symbols=new_symbols,
        continuing_symbols=continuing_symbols,
        dropped_symbols=dropped_symbols,
    )
    _PREV_WATCHLIST.clear()
    _PREV_WATCHLIST.update(watchlist_symbols)

    data_quality_counts: Dict[str, int] = {}
    for row in fast_rows:
        for flag in list(row.data_quality_flags or []):
            data_quality_counts[flag] = data_quality_counts.get(flag, 0) + 1
    for reason in drop_ledger.values():
        if reason.startswith("DROP_MD"):
            data_quality_counts[reason] = data_quality_counts.get(reason, 0) + 1

    broker_returned_zero = bool(raw_zero_payload.get("broker_returned_zero", False))
    raw_broker_count = int(raw_zero_payload.get("raw_broker_count", len(raw_symbols)))
    watchlist_count = len(watchlist_symbols)
    cacheable = not (broker_returned_zero or raw_broker_count == 0)

    _LAST_SCANNER_PAYLOAD = {
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
        "ross_top_universe_symbols": sorted(daily_state.top_universe.keys()),
        "ross_rejected_tracked_symbols": sorted(daily_state.rejected_tracked.keys()),
        "ross_daily_state": {
            "trading_day": daily_state.trading_day,
            "top_universe": {k: asdict(v) for k, v in daily_state.top_universe.items()},
            "watchlist_k": {k: asdict(v) for k, v in daily_state.watchlist_k.items()},
            "focus_m": {k: asdict(v) for k, v in daily_state.focus_m.items()},
            "rejected_tracked": {k: asdict(v) for k, v in daily_state.rejected_tracked.items()},
        },
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
        "survivors_count": len(watchlist_contexts),
        "new_symbols": new_symbols,
        "continuing_symbols": continuing_symbols,
        "dropped_symbols": dropped_symbols,
        "drop_reason_summary": drop_summary,
        "data_quality_by_symbol": {
            row.symbol: list(row.data_quality_flags or []) for row in fast_rows
        },
        "data_quality_counts": data_quality_counts,
        "broker_returned_zero": broker_returned_zero,
        "raw_broker_count": raw_broker_count,
        "watchlist_count": watchlist_count,
        "cacheable": cacheable,
        "diagnostics": diagnostics,
        "symbol_context_registry": {
            symbol: symbol_contexts[symbol]
            for symbol in sorted(symbol_contexts.keys())
        },
    }
    return dict(_LAST_SCANNER_PAYLOAD)



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scanner runner")
    parser.add_argument("--mode", default="READ_ONLY")
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
