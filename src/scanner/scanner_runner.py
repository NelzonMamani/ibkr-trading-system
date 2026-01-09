from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.runtime_config import get_scanner_symbols

from .audit import audit_fields, write_field_audit, write_mechanical_checklist
from .contracts import SCANNER_GIT_SHA, SCANNER_VERSION, ScannerRow54
from .field_mapper import build_scanner_row54
from .filters import passes_catalyst_eligibility, passes_ross_5_pillars
from .news_engine import get_news_truth
from .print_contract_54 import format_watchlist_lines, print_master, print_watchlist_compact
from .scanner_master_v2026_01_06_07 import (
    categorize_float,
    fetch_top_gainers,
    fmt_float_human,
    get_float_shares,
    get_price_truth,
    get_volume_truth,
    ib_connect,
    load_json_file,
    market_session_label_utc,
    save_json_file,
)
from .scanner_config import FLOAT_CACHE_FILE, TOP_GAINERS_COUNT


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _build_symbol_context(
    symbol: str,
    session_label: str,
    sort_rank: int,
    price_truth,
    volume_truth,
    float_raw: Optional[int],
    float_source: str,
    cache_hit: bool,
) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "market_session_label": session_label,
        "sort_rank_by_gap_desc": sort_rank,
        "previous_close_price": price_truth.prev_close,
        "session_open_price": price_truth.session_open,
        "overnight_gap_percentage": price_truth.gap_pct,
        "last_trade_price": price_truth.last,
        "current_percentage_change_from_prior_close": price_truth.pct_change,
        "bid_price": price_truth.bid,
        "ask_price": price_truth.ask,
        "bid_ask_spread": price_truth.spread,
        "mid_price": price_truth.mid,
        "vwap_price": price_truth.vwap,
        "day_high_price": price_truth.day_high,
        "day_low_price": price_truth.day_low,
        "intraday_range_percentage": price_truth.intraday_range_pct,
        "price_data_type_label": price_truth.data_type_label,
        "price_truth_source_label": price_truth.truth_source_label,
        "daily_bars_count": price_truth.daily_bars_count,
        "float_shares_raw": float_raw,
        "float_shares_formatted": fmt_float_human(float_raw),
        "float_category": categorize_float(float_raw),
        "float_shares_source": float_source,
        "float_cache_hit": cache_hit,
        "current_intraday_volume": volume_truth.current_intraday_volume,
        "current_volume_source_label": volume_truth.current_volume_source_label,
        "average_daily_volume_20d": volume_truth.average_daily_volume_20d,
        "average_daily_volume_window_days": volume_truth.average_daily_volume_window_days,
        "relative_volume": volume_truth.relative_volume,
        "relative_volume_category": volume_truth.relative_volume_category,
        "volume_velocity_5m": volume_truth.volume_velocity_5m,
        "volume_velocity_15m": volume_truth.volume_velocity_15m,
        "volume_data_quality_flag": volume_truth.volume_data_quality_flag,
    }


def _fallback_symbol_context(symbol: str, session_label: str, sort_rank: int) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "market_session_label": session_label,
        "sort_rank_by_gap_desc": sort_rank,
    }


def _rank_watchlist(rows: List[ScannerRow54]) -> List[ScannerRow54]:
    scored: List[tuple[float, ScannerRow54]] = []
    for row in rows:
        momentum = _safe_float(row.composite_momentum_score, 0.0) or 0.0
        news_score = 0.0
        if row.score_components_breakdown:
            news_score = _safe_float(
                row.score_components_breakdown.get("news_heat_score"), 0.0
            ) or 0.0
        rank_score = (momentum * 0.7) + (news_score * 0.3)
        if row.score_components_breakdown is not None:
            row.score_components_breakdown["watchlist_rank_score"] = round(rank_score, 2)
            row.score_components_breakdown["composite_news_score"] = round(news_score, 2)
        scored.append((rank_score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in scored]


def _apply_filters(rows: List[ScannerRow54], limit: int = 15) -> List[ScannerRow54]:
    filtered = []
    for row in rows:
        if passes_ross_5_pillars(row) and passes_catalyst_eligibility(row):
            reason = row.trade_suggestion_rationale or ""
            suffix = "Filters: Ross5 + Catalyst"
            row.trade_suggestion_rationale = f"{reason} | {suffix}".strip(" |")
            filtered.append(row)
    ranked = _rank_watchlist(filtered)
    return ranked[:limit]


def _print_field_audit(rows: List[ScannerRow54]) -> Dict[str, Any]:
    report = audit_fields(rows)
    present = report.get("present_fields", [])
    missing = report.get("missing_fields", [])
    print(
        "[SCANNER][AUDIT] field status: "
        f"present={len(present)} missing={len(missing)} unwired=0"
    )
    return report


def run_scanner_cycle(mode: str = "integrated") -> Dict[str, Any]:
    utc_now = _utc_now()
    session_label = market_session_label_utc(utc_now)
    float_cache: Dict[str, Any] = load_json_file(FLOAT_CACHE_FILE, {})
    if not isinstance(float_cache, dict):
        float_cache = {}

    rows: List[ScannerRow54] = []
    diagnostics: Dict[str, Any] = {"mode": mode}
    ib = None
    contracts = []

    try:
        ib = ib_connect()
        contracts = fetch_top_gainers(ib, TOP_GAINERS_COUNT)
    except Exception as exc:
        diagnostics["ib_connect_error"] = str(exc)
        contracts = []

    if not contracts:
        fallback_symbols = get_scanner_symbols(default=["AAPL", "MSFT", "NVDA", "AMD", "TSLA"])
        print("[SCANNER] Falling back to configured symbols:", ", ".join(fallback_symbols))
        for idx, symbol in enumerate(fallback_symbols, start=1):
            symbol_ctx = _fallback_symbol_context(symbol, session_label, idx)
            news_ctx = get_news_truth(symbol)
            rows.append(build_scanner_row54(symbol_ctx, news_ctx, {}, diagnostics))
    else:
        raw_contexts: List[Dict[str, Any]] = []
        for idx, contract in enumerate(contracts, start=1):
            symbol = contract.symbol.upper()
            try:
                price_truth = get_price_truth(ib, contract)
                float_raw, float_source, cache_hit = get_float_shares(ib, contract, float_cache)
                volume_truth = get_volume_truth(ib, contract, session_label=session_label)
                symbol_ctx = _build_symbol_context(
                    symbol,
                    session_label,
                    idx,
                    price_truth,
                    volume_truth,
                    float_raw,
                    float_source,
                    cache_hit,
                )
            except Exception as exc:
                diagnostics.setdefault("enrichment_errors", {})[symbol] = str(exc)
                symbol_ctx = _fallback_symbol_context(symbol, session_label, idx)
            news_ctx = get_news_truth(symbol)
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

    if ib is not None:
        try:
            if ib.isConnected():
                ib.disconnect()
        except Exception:
            pass

    if float_cache:
        save_json_file(FLOAT_CACHE_FILE, float_cache)

    print_master(rows) if mode == "standalone" else None
    watchlist = _apply_filters(rows, limit=15)
    print_watchlist_compact(watchlist)

    report = _print_field_audit(rows)
    docs_dir = Path("docs")
    write_field_audit(report, docs_dir / "PHASE_24_SCANNER_FIELD_AUDIT.json")
    write_mechanical_checklist(report, docs_dir / "PHASE_24_SCANNER_MECHANICAL_CHECKLIST.md")

    if mode == "standalone":
        session = (os.getenv("SCANNER_SESSION") or "DEFAULT").strip().upper()
        ts = utc_now.strftime("%Y-%m-%d_%H-%M-%S")
        watchlist_dir = Path("output/watchlists")
        watchlist_dir.mkdir(parents=True, exist_ok=True)
        file_path = watchlist_dir / f"watchlist_{session}_{ts}.txt"
        file_path.write_text("\n".join(format_watchlist_lines(watchlist)) + "\n", encoding="utf-8")
        local_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[SCANNER] Local time: {local_now}")
        print(f"[SCANNER] Saved watchlist to: {file_path}")

    return {
        "scanner_version": SCANNER_VERSION,
        "scanner_git_sha": SCANNER_GIT_SHA,
        "timestamp_utc": utc_now.isoformat(),
        "symbols": [row.symbol for row in watchlist],
        "watchlist": watchlist,
        "unfiltered_rows": rows,
        "diagnostics": diagnostics,
    }
