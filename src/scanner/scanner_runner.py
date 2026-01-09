from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

if __package__ is None or __package__ == "":
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root))

from src.config.config_resolver import get_config, get_config_record
from src.news.news_fetcher import Headline, fetch_headlines_for_symbols
from src.news.news_normalizer import normalize_headlines
from src.news.verified_sources import load_verified_rss_sources
from src.scanner.audit import audit_field_population, write_field_audit, write_mechanical_checklist
from src.scanner.contracts import SCANNER_GIT_SHA, SCANNER_VERSION, ScannerRow54
from src.scanner.field_mapper import build_scanner_row54
from src.scanner.filters import FilterDecision, evaluate_scan_row
from src.scanner.providers.base import ScannerDataProvider
from src.scanner.providers.factory import build_provider


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
        return "RTH"
    if 21.5 <= h < 23.0:
        return "AFT"
    return "OVN"


def _fmt_float_human(value: Optional[int]) -> Optional[str]:
    if value is None:
        return None
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.2f}K"
    return str(value)


def _categorize_float(value: Optional[int]) -> Optional[str]:
    if value is None:
        return None
    if value <= 5_000_000:
        return "LOW"
    if value <= 20_000_000:
        return "MID"
    return "HIGH"


def _build_symbol_context(
    provider: ScannerDataProvider,
    symbol: str,
    session_label: str,
    sort_rank: int,
) -> Dict[str, Any]:
    quote = provider.get_quote(symbol)
    prev_close = quote.close if quote.close is not None else provider.get_prev_close(symbol)
    intraday = provider.get_intraday_stats(symbol)
    float_raw = provider.get_float(symbol)
    open_price = quote.open
    last_price = quote.last
    bid = quote.bid
    ask = quote.ask
    mid = None
    if bid is not None and ask is not None:
        mid = round((bid + ask) / 2, 4)
    spread = None
    if bid is not None and ask is not None:
        spread = round(ask - bid, 4)

    gap_pct = None
    if prev_close and open_price:
        gap_pct = round(((open_price - prev_close) / prev_close) * 100.0, 2)

    pct_change = None
    if prev_close and last_price:
        pct_change = round(((last_price - prev_close) / prev_close) * 100.0, 2)

    intraday_range_pct = None
    if quote.high is not None and quote.low is not None and prev_close:
        intraday_range_pct = round(((quote.high - quote.low) / prev_close) * 100.0, 2)

    return {
        "symbol": symbol,
        "market_session_label": session_label,
        "sort_rank_by_gap_desc": sort_rank,
        "previous_close_price": prev_close,
        "session_open_price": open_price,
        "overnight_gap_percentage": gap_pct,
        "last_trade_price": last_price,
        "current_percentage_change_from_prior_close": pct_change,
        "bid_price": bid,
        "ask_price": ask,
        "bid_ask_spread": spread,
        "mid_price": mid,
        "vwap_price": quote.vwap,
        "day_high_price": quote.high,
        "day_low_price": quote.low,
        "intraday_range_percentage": intraday_range_pct,
        "price_data_type_label": provider.source_name,
        "price_truth_source_label": provider.source_name,
        "daily_bars_count": None,
        "float_shares_raw": float_raw,
        "float_shares_formatted": _fmt_float_human(float_raw),
        "float_category": _categorize_float(float_raw),
        "float_shares_source": provider.source_name if float_raw is not None else None,
        "float_cache_hit": float_raw is not None,
        "current_intraday_volume": intraday.current_intraday_volume,
        "current_volume_source_label": intraday.current_volume_source_label,
        "average_daily_volume_20d": intraday.average_daily_volume_20d,
        "average_daily_volume_window_days": intraday.average_daily_volume_window_days,
        "relative_volume": intraday.relative_volume,
        "relative_volume_category": intraday.relative_volume_category,
        "volume_velocity_5m": intraday.volume_velocity_5m,
        "volume_velocity_15m": intraday.volume_velocity_15m,
        "volume_data_quality_flag": intraday.volume_data_quality_flag,
    }


def _mock_headlines_for_symbols(symbols: List[str]) -> Dict[str, List[Headline]]:
    now_ts = datetime.now(timezone.utc).timestamp()
    headlines: Dict[str, List[Headline]] = {symbol: [] for symbol in symbols}
    for symbol in symbols[:20]:
        headlines[symbol] = [
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
    return headlines


def _enrich_news_context(
    symbols: List[str],
    provider_source: str,
) -> tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    news_enabled = bool(get_config("NEWS_ENABLED"))
    if not news_enabled:
        return {}, {"news_enabled": False, "news_degraded_reason": "NEWS_DISABLED"}

    sources = load_verified_rss_sources()
    headlines_by_symbol = fetch_headlines_for_symbols(
        symbols,
        sources,
        lookback_hours=float(get_config("NEWS_LOOKBACK_HOURS")),
        request_timeout_s=float(get_config("NEWS_REQUEST_TIMEOUT_S")),
    )
    news_summary = {
        "sources_total": len(sources),
        "sources_used": len([source for source in sources if source]),
        "headlines_total": sum(len(items) for items in headlines_by_symbol.values()),
        "news_enabled": news_enabled,
    }
    if provider_source == "MOCK":
        if all(len(items) == 0 for items in headlines_by_symbol.values()):
            headlines_by_symbol = _mock_headlines_for_symbols(symbols)
            news_summary["mock_fallback"] = True
    if not sources:
        news_summary["news_degraded_reason"] = "NO_VERIFIED_SOURCES"
    elif not any(headlines_by_symbol.values()):
        news_summary["news_degraded_reason"] = "NO_HEADLINES"
    news_by_symbol: Dict[str, Dict[str, Any]] = {}
    for symbol, headlines in headlines_by_symbol.items():
        news_context = normalize_headlines(headlines)
        vel10 = news_context.get("news_velocity_10m") or 0
        vel60 = news_context.get("news_velocity_60m") or 0
        spike = bool(vel10 >= 2 or (vel60 and vel10 > (vel60 / 6.0)))
        news_context["news_spike_indicator"] = spike
        news_by_symbol[symbol] = news_context
    return news_by_symbol, news_summary


def _rank_watchlist(rows: List[ScannerRow54]) -> List[ScannerRow54]:
    scored: List[tuple[float, ScannerRow54]] = []
    for row in rows:
        momentum = _safe_float(row.composite_momentum_score, 0.0) or 0.0
        news_score = _safe_float(row.composite_news_score, 0.0) or 0.0
        rank_score = (momentum * 0.7) + (news_score * 0.3)
        scored.append((rank_score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in scored]


def _apply_filters(
    rows: List[ScannerRow54],
    limit: int,
    enforce_news_gate: bool,
) -> tuple[List[ScannerRow54], Dict[str, int], int]:
    decisions: List[FilterDecision] = []
    for row in rows:
        decisions.append(evaluate_scan_row(row, enforce_news_gate=enforce_news_gate))

    filtered = [decision.row for decision in decisions if decision.passes]
    ranked = _rank_watchlist(filtered)
    ranked = ranked[:limit]

    excluded_reasons: Dict[str, int] = {}
    for decision in decisions:
        if decision.passes:
            continue
        for reason in decision.reasons:
            excluded_reasons[reason] = excluded_reasons.get(reason, 0) + 1

    excluded_count = len(rows) - len(ranked)
    return ranked, excluded_reasons, excluded_count


def _resolve_symbol_limits() -> Dict[str, Any]:
    top_gainers = int(get_config("SCANNER_TOP_GAINERS_COUNT"))
    ibkr_cap = int(get_config("IBKR_MAX_SYMBOLS_PER_CYCLE"))
    teaching_cap = int(get_config("SCANNER_TEACHING_SYMBOL_CAP"))
    scanner_mode = str(get_config("SCANNER_MODE"))

    resolved_limit = min(top_gainers, ibkr_cap)
    reasons = []
    if top_gainers > ibkr_cap:
        reasons.append("IBKR_MAX_SYMBOLS_PER_CYCLE cap applied")
    if scanner_mode == "TEACHING" and teaching_cap > 0:
        resolved_limit = min(resolved_limit, teaching_cap)
        reasons.append("SCANNER_TEACHING_SYMBOL_CAP applied (TEACHING mode)")

    return {
        "top_gainers": top_gainers,
        "ibkr_cap": ibkr_cap,
        "teaching_cap": teaching_cap,
        "scanner_mode": scanner_mode,
        "resolved_limit": resolved_limit,
        "reasons": reasons,
    }


def run_scanner_cycle(mode: str = "integrated") -> Dict[str, Any]:
    utc_now = _utc_now()
    session_label = _market_session_label_utc(utc_now)
    rows: List[ScannerRow54] = []
    diagnostics: Dict[str, Any] = {"mode": mode}
    provider: ScannerDataProvider = build_provider()

    try:
        limits = _resolve_symbol_limits()
        config_sources = {
            "TOP_GAINERS_COUNT": get_config_record("SCANNER_TOP_GAINERS_COUNT").source,
            "IBKR_MAX_SYMBOLS_PER_CYCLE": get_config_record("IBKR_MAX_SYMBOLS_PER_CYCLE").source,
            "SCANNER_TEACHING_SYMBOL_CAP": get_config_record("SCANNER_TEACHING_SYMBOL_CAP").source,
        }
        print(
            "[SCANNER] Symbol limits resolved "
            f"TOP_GAINERS_COUNT={limits['top_gainers']}({config_sources['TOP_GAINERS_COUNT']}) "
            f"IBKR_MAX_SYMBOLS_PER_CYCLE={limits['ibkr_cap']}({config_sources['IBKR_MAX_SYMBOLS_PER_CYCLE']}) "
            f"SCANNER_TEACHING_SYMBOL_CAP={limits['teaching_cap']}({config_sources['SCANNER_TEACHING_SYMBOL_CAP']}) "
            f"RESOLVED_LIMIT={limits['resolved_limit']}"
        )
        if limits["reasons"]:
            print("[SCANNER] Symbol limit reasons: " + "; ".join(limits["reasons"]))
            if "SCANNER_TEACHING_SYMBOL_CAP applied (TEACHING mode)" in limits["reasons"]:
                print("[SCANNER] Override with env SCANNER_TEACHING_SYMBOL_CAP=0 to disable teaching cap")

        symbols = provider.get_top_gainers(limits["resolved_limit"])
        diagnostics["provider_source"] = provider.source_name
        diagnostics["symbol_count"] = len(symbols)
        diagnostics["symbol_limit"] = limits
        if not symbols:
            symbols = []
        if len(symbols) < limits["resolved_limit"]:
            print(
                "[SCANNER] Provider returned fewer symbols "
                f"returned={len(symbols)} resolved_limit={limits['resolved_limit']}"
            )

        news_by_symbol: Dict[str, Dict[str, Any]] = {}
        news_summary: Dict[str, Any] = {}
        if symbols:
            news_by_symbol, news_summary = _enrich_news_context(symbols, provider.source_name)
        diagnostics["news_summary"] = news_summary

        raw_contexts = []
        for idx, symbol in enumerate(symbols, start=1):
            try:
                symbol_ctx = _build_symbol_context(provider, symbol, session_label, idx)
            except Exception as exc:
                diagnostics.setdefault("enrichment_errors", {})[symbol] = str(exc)
                symbol_ctx = {
                    "symbol": symbol,
                    "market_session_label": session_label,
                    "sort_rank_by_gap_desc": idx,
                }
            news_ctx = news_by_symbol.get(symbol, {})
            raw_contexts.append({"symbol": symbol_ctx, "news": news_ctx})

        raw_contexts.sort(
            key=lambda item: (
                item["symbol"].get("current_percentage_change_from_prior_close") is None,
                -(item["symbol"].get("current_percentage_change_from_prior_close") or -10**9),
            )
        )
        for idx, item in enumerate(raw_contexts, start=1):
            item["symbol"]["sort_rank_by_gap_desc"] = idx
            rows.append(build_scanner_row54(item["symbol"], item["news"], {}, diagnostics))
    finally:
        provider.disconnect()

    enforce_news_gate = bool(get_config("NEWS_ENABLED"))
    if news_summary.get("news_degraded_reason"):
        enforce_news_gate = False
        print(
            "[NEWS] News degraded "
            f"reason={news_summary.get('news_degraded_reason')} "
            "=> bypassing news gate for watchlist eligibility"
        )

    watchlist_limit = int(get_config("SCANNER_WATCHLIST_LIMIT"))
    watchlist, exclusion_reasons, excluded_count = _apply_filters(
        rows,
        limit=watchlist_limit,
        enforce_news_gate=enforce_news_gate,
    )
    watchlist_symbols = [row.symbol for row in watchlist if row.symbol]

    report = audit_field_population(rows)

    if mode == "standalone":
        docs_dir = Path("docs")
        write_field_audit(report, docs_dir / "PHASE_24_SCANNER_FIELD_AUDIT.json")
        write_mechanical_checklist(report, docs_dir / "PHASE_24_SCANNER_MECHANICAL_CHECKLIST.md")
        ts = utc_now.strftime("%Y%m%d_%H%M%S_UTC")
        watchlist_dir = Path("output/watchlists")
        watchlist_dir.mkdir(parents=True, exist_ok=True)
        file_path = watchlist_dir / f"watchlist_RossMomentum_{ts}.txt"
        header = [
            "# Ross Momentum Watchlist",
            f"# Timestamp (UTC): {utc_now.isoformat()}",
            f"# candidates_count={len(rows)}",
            f"# enriched_count={len(rows)}",
            f"# excluded_count={excluded_count}",
            f"# watchlist_count={len(watchlist_symbols)}",
        ]
        if not watchlist_symbols and exclusion_reasons:
            sorted_reasons = sorted(exclusion_reasons.items(), key=lambda item: item[1], reverse=True)
            header.append("# exclusion_reasons=" + ", ".join(f"{reason}:{count}" for reason, count in sorted_reasons))
        file_path.write_text("\n".join(header + watchlist_symbols) + "\n", encoding="utf-8")

    print(
        "[WATCHLIST] candidates_count={candidates} enriched_count={enriched} "
        "excluded_count={excluded} watchlist_count={watchlist}".format(
            candidates=len(rows),
            enriched=len(rows),
            excluded=excluded_count,
            watchlist=len(watchlist_symbols),
        )
    )
    if not watchlist_symbols and exclusion_reasons:
        top_reasons = ", ".join(
            f"{reason}={count}" for reason, count in sorted(exclusion_reasons.items(), key=lambda item: item[1], reverse=True)[:5]
        )
        print(f"[WATCHLIST] Empty watchlist reasons: {top_reasons}")

    return {
        "scanner_version": SCANNER_VERSION,
        "scanner_git_sha": SCANNER_GIT_SHA,
        "timestamp_utc": utc_now.isoformat(),
        "symbols": watchlist_symbols,
        "watchlist": watchlist_symbols,
        "watchlist_rows": watchlist,
        "unfiltered_rows": rows,
        "audit": report,
        "diagnostics": diagnostics,
    }


if __name__ == "__main__":
    payload = run_scanner_cycle(mode="standalone")

    print("\n[SCANNER] Standalone scan complete")
    print(f"[SCANNER] Version: {payload.get('scanner_version')}")
    print(f"[SCANNER] Timestamp (UTC): {payload.get('timestamp_utc')}")
    print(f"[SCANNER] Symbols scanned: {len(payload.get('unfiltered_rows', []))}")
    print(f"[SCANNER] Watchlist size: {len(payload.get('watchlist', []))}")

    print("\n[WATCHLIST]")
    for symbol in payload.get("watchlist", []):
        print(f" - {symbol}")
