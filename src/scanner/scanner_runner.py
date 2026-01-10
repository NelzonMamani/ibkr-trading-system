from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from src.config.config_resolver import get_config, get_config_record
from src.news.news_fetcher import Headline, fetch_headlines_for_symbols
from src.news.news_normalizer import normalize_headlines
from src.news.verified_sources import load_verified_rss_sources

from src.scanner.audit import audit_field_population, write_field_audit, write_mechanical_checklist
from src.scanner.contracts import (
    SCANNER_GIT_SHA,
    SCANNER_VERSION,
    ScannerArtifact,
    ScannerRow54,
    validate_row,
)
from src.scanner.field_mapper import build_scanner_row54
from src.scanner.filters import evaluate_filters
from src.scanner.print_contract_54 import format_watchlist_lines, print_master, print_watchlist_compact
from src.scanner.providers.base import ScannerDataProvider
from src.scanner.providers.factory import build_provider
from src.scanner.providers.mock_provider import MockScannerProvider


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


def _print_symbol_limits(scanner_mode: str, provider_source: str) -> Dict[str, Any]:
    limit_keys = [
        "SCANNER_TOP_GAINERS_COUNT",
        "IBKR_MAX_SYMBOLS_PER_CYCLE",
        "SCANNER_TEACHING_SYMBOL_CAP",
        "SCANNER_WATCHLIST_LIMIT",
    ]
    records = {key: get_config_record(key) for key in limit_keys}
    print("[SCANNER][LIMITS] Symbol limits (value/source/env)")
    for key in limit_keys:
        record = records[key]
        env = record.env or "-"
        print(f"[SCANNER][LIMITS] {key}={record.value} source={record.source} env={env}")

    resolved = int(records["SCANNER_TOP_GAINERS_COUNT"].value)
    reductions: list[str] = []
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

    print(
        "[SCANNER][LIMITS] Resolved symbol request limit="
        f"{resolved} reductions={reductions or ['none']}"
    )
    return {
        "resolved_symbol_limit": resolved,
        "reductions": reductions,
        "watchlist_limit": int(records["SCANNER_WATCHLIST_LIMIT"].value),
    }


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
            headlines_by_symbol = _mock_headlines_for_symbols(symbols)
            news_degraded = True
            reason_override = reason_override or "mock_headlines_injected"

    news_by_symbol: Dict[str, Dict[str, Any]] = {}
    for symbol, headlines in headlines_by_symbol.items():
        news_context = normalize_headlines(headlines)
        vel10 = news_context.get("news_velocity_10m") or 0
        vel60 = news_context.get("news_velocity_60m") or 0
        spike = bool(vel10 >= 2 or (vel60 and vel10 > (vel60 / 6.0)))
        news_context["news_spike_indicator"] = spike
        news_by_symbol[symbol] = news_context
    news_gate_bypassed = all_failed or reason_override in {"no_sources", "feedparser_missing"}
    diagnostics = {
        "rss_sources": summary.total_sources,
        "rss_failures": summary.failure_count,
        "rss_failure_summary": summary.failures_by_domain,
        "rss_failure_reason": reason_override,
        "news_degraded": news_degraded,
        "news_gate_bypassed": news_gate_bypassed,
    }
    return news_by_symbol, diagnostics


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
    bypass_news_gates: bool,
    require_news_override: Optional[bool],
) -> tuple[List[ScannerRow54], Counter, int]:
    filtered: List[ScannerRow54] = []
    exclusion_reasons: Counter = Counter()
    for row in rows:
        passed, reasons = evaluate_filters(
            row,
            require_news_override=require_news_override,
            bypass_news_gates=bypass_news_gates,
        )
        if passed:
            filtered.append(row)
        else:
            exclusion_reasons.update(reasons or ["excluded"])
    ranked = _rank_watchlist(filtered)
    return ranked[:limit], exclusion_reasons, len(filtered)


def run_scanner_cycle(mode: str = "integrated") -> ScannerArtifact:
    utc_now = _utc_now()
    session_label = _market_session_label_utc(utc_now)
    rows: List[ScannerRow54] = []
    diagnostics: Dict[str, Any] = {"mode": mode}
    row_validations: Dict[str, Dict[str, Any]] = {}
    provider: ScannerDataProvider = build_provider()
    scanner_mode = str(get_config("SCANNER_MODE"))
    limits = _print_symbol_limits(scanner_mode, provider.source_name)
    diagnostics["symbol_limits"] = limits

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
                limits = _print_symbol_limits(scanner_mode, provider.source_name)
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

        news_by_symbol, news_diagnostics = (
            _enrich_news_context(symbols, provider.source_name) if symbols else ({}, {})
        )
        diagnostics["news"] = news_diagnostics
        bypass_news_gates = bool(news_diagnostics.get("news_gate_bypassed"))

        raw_contexts = []
        for idx, symbol in enumerate(symbols, start=1):
            try:
                symbol_ctx = _build_symbol_context(provider, symbol, session_label, idx)
            except Exception as exc:
                diagnostics.setdefault("enrichment_errors", {})[symbol] = str(exc)
                diagnostics.setdefault("degraded_symbols", {})[symbol] = "provider_error"
                symbol_ctx = {
                    "symbol": symbol,
                    "market_session_label": session_label,
                    "sort_rank_by_gap_desc": idx,
                    "price_data_type_label": "ERROR",
                    "price_truth_source_label": provider.source_name,
                    "volume_data_quality_flag": "ERROR",
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
            row = build_scanner_row54(item["symbol"], item["news"], {}, diagnostics)
            missing_fields, non_allowed, _, integrity = validate_row(row)
            row_validations[row.symbol or f"row_{idx}"] = {
                "missing_fields": missing_fields,
                "non_allowed_na_fields": non_allowed,
                "integrity_score": integrity,
            }
            rows.append(row)
    finally:
        provider.disconnect()

    watchlist, exclusion_reasons, filtered_count = _apply_filters(
        rows,
        limit=limits["watchlist_limit"],
        bypass_news_gates=bypass_news_gates,
        require_news_override=False if bypass_news_gates else None,
    )
    if limits["watchlist_limit"] <= 0 and rows:
        exclusion_reasons.update(["watchlist_limit_zero"])
    watchlist_symbols = [row.symbol for row in watchlist if row.symbol]
    excluded_count = max(len(rows) - filtered_count, 0)

    report = audit_field_population(rows)

    docs_dir = Path("docs")
    write_field_audit(report, docs_dir / "PHASE_24_SCANNER_FIELD_AUDIT.json")
    write_mechanical_checklist(report, docs_dir / "PHASE_24_SCANNER_MECHANICAL_CHECKLIST.md")
    ts = utc_now.strftime("%Y%m%d_%H%M%S_UTC")
    watchlist_dir = Path("output/watchlists")
    watchlist_dir.mkdir(parents=True, exist_ok=True)
    file_path = watchlist_dir / f"watchlist_RossMomentum_{ts}.txt"
    exclusion_summary = exclusion_reasons.most_common(3)
    exclusion_summary_str = ", ".join(
        f"{reason}:{count}" for reason, count in exclusion_summary
    )
    header_lines = [
        f"# candidates_count={len(symbols)}",
        f"# enriched_count={len(rows)}",
        f"# excluded_count={excluded_count}",
        f"# watchlist_count={len(watchlist_symbols)}",
    ]
    if not watchlist_symbols:
        header_lines.append(
            f"# exclusion_reasons={exclusion_summary_str or 'no_candidates'}"
        )
    watchlist_lines = format_watchlist_lines(watchlist)
    file_path.write_text(
        "\n".join(header_lines + [""] + watchlist_lines) + "\n", encoding="utf-8"
    )

    diagnostics["row_validations"] = row_validations
    price_truth_source_labels = Counter(
        row.price_truth_source_label for row in rows if row.price_truth_source_label
    )
    news_diag = diagnostics.get("news", {})
    news_degraded_reason = None
    if news_diag.get("news_degraded"):
        news_degraded_reason = news_diag.get("rss_failure_reason") or "news_degraded"
    provider_fallback_reason = None
    if diagnostics.get("provider_fallback"):
        provider_fallback_reason = diagnostics.get("provider_fallback", {}).get("reason")
    top_exclusion_reasons = (
        dict(exclusion_reasons.most_common(5)) if exclusion_reasons else None
    )

    return ScannerArtifact(
        scanner_version=SCANNER_VERSION,
        scanner_git_sha=SCANNER_GIT_SHA,
        timestamp_utc=utc_now.isoformat(),
        run_mode=mode,
        provider_source=diagnostics.get("provider_source") or provider.source_name,
        candidates_count=len(symbols),
        enriched_count=len(rows),
        watchlist_count=len(watchlist_symbols),
        watchlist=watchlist_symbols,
        artifact_path=str(file_path),
        symbol_rows=rows,
        row_validations=row_validations,
        price_truth_source_labels=dict(price_truth_source_labels)
        if price_truth_source_labels
        else None,
        news_degraded_reason=news_degraded_reason,
        provider_fallback_reason=provider_fallback_reason,
        top_exclusion_reasons=top_exclusion_reasons,
        diagnostics=diagnostics,
    )


if __name__ == "__main__":
    payload = run_scanner_cycle(mode="standalone")

    print("\n[SCANNER] Standalone scan complete")
    print(f"[SCANNER] Version: {payload.scanner_version}")
    print(f"[SCANNER] Timestamp (UTC): {payload.timestamp_utc}")
    print(f"[SCANNER] Symbols scanned: {payload.enriched_count}")
    print(f"[SCANNER] Watchlist size: {payload.watchlist_count}")
    diagnostics = payload.diagnostics or {}
    news_diag = diagnostics.get("news", {})
    if news_diag:
        print(
            "[SCANNER][NEWS] RSS failures "
            f"{news_diag.get('rss_failures')}/{news_diag.get('rss_sources')} "
            f"reason={news_diag.get('rss_failure_reason')}"
        )
        print(f"[SCANNER][NEWS] RSS failure summary: {news_diag.get('rss_failure_summary')}")
        print(f"[SCANNER][NEWS] News gate bypassed: {news_diag.get('news_gate_bypassed')}")

    print("\n[WATCHLIST]")
    for symbol in payload.watchlist:
        print(f" - {symbol}")
    watchlist_rows = [row for row in payload.symbol_rows if row.symbol in payload.watchlist]
    watchlist_rows.sort(
        key=lambda row: payload.watchlist.index(row.symbol) if row.symbol in payload.watchlist else 0
    )
    print_watchlist_compact(watchlist_rows)
    print_master(payload.symbol_rows)
