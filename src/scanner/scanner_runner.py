from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..news.news_fetcher import Headline, fetch_headlines_for_symbols
from ..news.news_normalizer import normalize_headlines
from ..news.verified_sources import load_verified_rss_sources

from .audit import audit_field_population, write_field_audit, write_mechanical_checklist
from .contracts import SCANNER_GIT_SHA, SCANNER_VERSION, ScannerRow54
from .field_mapper import build_scanner_row54
from .filters import passes_catalyst_eligibility, passes_ross_5_pillars
from .providers.base import ScannerDataProvider
from src.config.config_resolver import get_config

from .providers.factory import build_provider


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
) -> Dict[str, Dict[str, Any]]:
    sources = load_verified_rss_sources()
    headlines_by_symbol = fetch_headlines_for_symbols(symbols, sources)
    if provider_source == "MOCK":
        if all(len(items) == 0 for items in headlines_by_symbol.values()):
            headlines_by_symbol = _mock_headlines_for_symbols(symbols)
    news_by_symbol: Dict[str, Dict[str, Any]] = {}
    for symbol, headlines in headlines_by_symbol.items():
        news_context = normalize_headlines(headlines)
        vel10 = news_context.get("news_velocity_10m") or 0
        vel60 = news_context.get("news_velocity_60m") or 0
        spike = bool(vel10 >= 2 or (vel60 and vel10 > (vel60 / 6.0)))
        news_context["news_spike_indicator"] = spike
        news_by_symbol[symbol] = news_context
    return news_by_symbol


def _rank_watchlist(rows: List[ScannerRow54]) -> List[ScannerRow54]:
    scored: List[tuple[float, ScannerRow54]] = []
    for row in rows:
        momentum = _safe_float(row.composite_momentum_score, 0.0) or 0.0
        news_score = _safe_float(row.composite_news_score, 0.0) or 0.0
        rank_score = (momentum * 0.7) + (news_score * 0.3)
        scored.append((rank_score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in scored]


def _apply_filters(rows: List[ScannerRow54], limit: int = 15) -> List[ScannerRow54]:
    filtered = [row for row in rows if passes_ross_5_pillars(row) and passes_catalyst_eligibility(row)]
    ranked = _rank_watchlist(filtered)
    return ranked[:limit]


def run_scanner_cycle(mode: str = "integrated") -> Dict[str, Any]:
    utc_now = _utc_now()
    session_label = _market_session_label_utc(utc_now)
    rows: List[ScannerRow54] = []
    diagnostics: Dict[str, Any] = {"mode": mode}
    provider: ScannerDataProvider = build_provider()

    try:
        symbols = provider.get_top_gainers(get_config("SCANNER_TOP_GAINERS_COUNT"))
        diagnostics["provider_source"] = provider.source_name
        diagnostics["symbol_count"] = len(symbols)
        if not symbols:
            symbols = []

        news_by_symbol = _enrich_news_context(symbols, provider.source_name) if symbols else {}

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

    watchlist = _apply_filters(rows, limit=get_config("SCANNER_WATCHLIST_LIMIT"))
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
        file_path.write_text("\n".join(watchlist_symbols) + "\n", encoding="utf-8")

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
