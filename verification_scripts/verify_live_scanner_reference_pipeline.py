from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config.runtime_config import resolve_ibkr_connection
from src.scanner import scanner_runner
from src.scanner.candidate_identity import CandidateIdentity
from src.scanner.providers.base import IntradayStats, QuoteData, ScannerDataProvider
from src.scanner.providers.ibkr_provider import IbkrScannerProvider


DEFAULT_SYMBOLS = ["AIM", "ARTL", "AGRO", "ALDX", "BATL"]


@dataclass(frozen=True)
class _Bar:
    date: str
    close: Optional[float]
    volume: Optional[int]


class _StubLiveLikeProvider(ScannerDataProvider):
    source_name = "STUB_LIVE_LIKE"

    def __init__(self) -> None:
        self.last_scan_details = {
            "symbol_details": {
                "AIM": {"conId": 1001, "secType": "STK", "exchange": "SMART", "primaryExchange": "NASDAQ", "tradingClass": "AIM", "currency": "USD", "localSymbol": "AIM"},
                "ARTL": {"conId": 1002, "secType": "STK", "exchange": "SMART", "primaryExchange": "NASDAQ", "tradingClass": "ARTL", "currency": "USD", "localSymbol": "ARTL"},
            }
        }

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def get_top_gainers(self, limit: int, request=None) -> list[str]:
        return DEFAULT_SYMBOLS[:limit]

    def get_quote(self, symbol: str) -> QuoteData:
        last = 11.0 if symbol == "AIM" else 7.25
        close = 10.0 if symbol == "AIM" else None
        return QuoteData(symbol=symbol, bid=last - 0.02, ask=last + 0.03, last=last, vwap=last - 0.05, open=last - 0.4, high=last + 0.2, low=last - 0.6, close=close, change_percent=10.0 if symbol == "AIM" else 7.4, volume=250_000 if symbol == "AIM" else 180_000, timestamp_utc="2026-03-18T00:00:00Z", data_quality_flags=())

    def get_prev_close(self, symbol: str) -> Optional[float]:
        return 10.0 if symbol == "AIM" else 6.75

    def get_previous_rth_close(self, identity) -> Optional[float]:
        return self.get_prev_close(getattr(identity, "symbol", identity))

    def get_intraday_stats(self, symbol: str) -> IntradayStats:
        adv20 = 125_000 if symbol == "AIM" else 90_000
        return IntradayStats(current_intraday_volume=250_000 if symbol == "AIM" else 180_000, current_volume_source_label="STUB", average_daily_volume_20d=adv20, average_daily_volume_window_days=20, relative_volume=None, relative_volume_category=None, volume_velocity_5m=None, volume_velocity_15m=None, volume_data_quality_flag="STUB")

    def get_float(self, symbol: str) -> Optional[int]:
        return 8_500_000

    def get_average_daily_volume(self, identity, window: int) -> tuple[Optional[int], Optional[int]]:
        stats = self.get_intraday_stats(getattr(identity, "symbol", identity))
        return stats.average_daily_volume_20d, min(window, stats.average_daily_volume_window_days or window)

    def get_daily_bars(self, identity, lookback_days: int, *, use_rth: bool = True, end_datetime: str = ""):
        symbol = getattr(identity, "symbol", identity)
        if symbol == "ARTL" and use_rth:
            return []
        prev_close = self.get_prev_close(symbol)
        avg, _ = self.get_average_daily_volume(identity, 20)
        return [_Bar(date=f"2026-02-{idx+1:02d}", close=prev_close, volume=avg) for idx in range(20)]


def _build_identity(symbol: str, details: dict) -> CandidateIdentity:
    return CandidateIdentity.from_mapping(
        {
            "symbol": symbol,
            "conId": details.get("conId"),
            "secType": details.get("secType") or "STK",
            "exchange": details.get("exchange") or details.get("primaryExchange") or "SMART",
            "primaryExchange": details.get("primaryExchange"),
            "tradingClass": details.get("tradingClass"),
            "currency": details.get("currency") or "USD",
            "localSymbol": details.get("localSymbol") or symbol,
        }
    )


def _print_block(title: str, payload: dict) -> None:
    print(title)
    for key, value in payload.items():
        print(f"  - {key}: {value}")


def _verify_symbol(provider: ScannerDataProvider, symbol: str, *, session_label: str) -> None:
    scan_detail = ((getattr(provider, "last_scan_details", {}) or {}).get("symbol_details") or {}).get(symbol, {"symbol": symbol})
    identity = _build_identity(symbol, scan_detail)
    context = scanner_runner._build_symbol_context(provider, symbol, session_label, float_cache={}, include_pct_change=True)
    if context is None:
        print(f"[VERIFY][ERROR] symbol={symbol} reason=context_build_failed")
        return
    scanner_runner._populate_pct_change(context, provider)
    thresholds = scanner_runner.GateThresholds(
        min_price=1.0,
        max_price=50.0,
        min_pct_change=5.0,
        max_pct_change=None,
        watchlist_rvol_min=0.5,
        focus_rvol_min=0.5,
        focus_volume_min=1000,
        focus_volume_min_early_rth=1000,
        focus_volume_min_early_rth_ratio=0.25,
        min_volume=1000,
        min_premarket_volume=1000,
        max_float=1_000_000_000,
        spread_max_pct=5.0,
        min_dollar_volume=None,
        require_price=True,
        require_bid_ask=False,
        require_catalyst=False,
        allow_halts=True,
        allow_ssr=True,
        allow_unknown_float=True,
    )
    scanner_runner._evaluate_focus_gates(context, thresholds)
    trace = scanner_runner._REFERENCE_RESOLVER.get_last_resolution_trace(context.get("identity_key") or identity.key)
    history_attempts = trace.get("history_attempts") or []
    primary_attempt = next((attempt for attempt in history_attempts if attempt.get("attempt") == "primary"), {})
    fallback_attempt = next((attempt for attempt in history_attempts if attempt.get("attempt") != "primary"), {})

    print(f"\n[VERIFY][SYMBOL] {symbol}")
    _print_block("1. identity", {
        "symbol": symbol,
        "conId": context.get("con_id"),
        "exchange": context.get("exchange"),
        "primaryExchange": context.get("primary_exchange"),
        "tradingClass": context.get("trading_class"),
        "identity_key": context.get("identity_key") or identity.key,
    })
    _print_block("2. snapshot", {
        "last": context.get("last_price"),
        "bid": context.get("bid"),
        "ask": context.get("ask"),
        "close": context.get("close"),
        "volume": context.get("volume"),
        "change_percent": context.get("ibkr_change_pct"),
    })
    _print_block("3. history_attempts", {
        "primary_request_params": primary_attempt.get("params"),
        "primary_raw_bar_count": primary_attempt.get("raw_bar_count"),
        "fallback_request_params": fallback_attempt.get("params"),
        "fallback_raw_bar_count": fallback_attempt.get("raw_bar_count"),
    })
    _print_block("4. resolved_reference", {
        "reference_source": context.get("reference_source"),
        "reference_quality_tier": context.get("reference_quality_tier"),
        "reference_resolved": context.get("reference_resolved"),
        "reference_price": context.get("reference_price"),
        "reference_failure_reason": context.get("reference_failure_reason"),
        "qualification_usable_reference": context.get("qualification_usable_reference"),
        "execution_usable_reference": context.get("pct_change_execution_usable"),
    })
    _print_block("5. resolved_pct", {
        "pct_change": context.get("pct_change"),
        "pct_change_resolved": context.get("pct_change_resolved"),
        "pct_change_qualification_usable": context.get("pct_change_qualification_usable"),
        "pct_change_execution_usable": context.get("pct_change_execution_usable"),
        "pct_change_failure_reason": context.get("pct_change_failure_reason"),
    })
    _print_block("6. resolved_adv20_rvol", {
        "adv20_source": context.get("adv20_source"),
        "avg_volume_20d": context.get("avg_volume_20d"),
        "adv20_resolved": context.get("adv20_resolved"),
        "rvol_status": context.get("rvol_status"),
        "rvol_phase": context.get("rvol_phase"),
        "rvol_discovery": context.get("rvol_discovery"),
        "rvol_failure_reason": context.get("rvol_failure_reason"),
    })
    _print_block("7. final_scanner_context", {
        "focus_eligible": context.get("focus_eligible"),
        "execution_eligible": context.get("execution_eligible"),
        "degraded_data_profile": context.get("degraded_data_profile"),
        "data_quality_flags": context.get("data_quality_flags"),
    })


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify live scanner reference/pct/adv20/rvol pipeline.")
    parser.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS)
    parser.add_argument("--session", default="RTH_OPEN")
    parser.add_argument("--provider", choices=("live", "stub"), default="live")
    args = parser.parse_args()

    print("Run from repo root:")
    print("python verification_scripts/verify_live_scanner_reference_pipeline.py --provider live --symbols AIM ARTL AGRO ALDX BATL")

    provider: ScannerDataProvider
    if args.provider == "stub":
        provider = _StubLiveLikeProvider()
        print("[VERIFY] provider=stub readonly=True")
    else:
        host, port, client_id, mode = resolve_ibkr_connection()
        print(f"[VERIFY] provider=live readonly=True mode={mode} host={host} port={port} client_id={client_id}")
        provider = IbkrScannerProvider(host=host, port=port, client_id=client_id)

    scanner_runner.reset_scanner_runtime_state()
    scanner_runner._REFERENCE_RESOLVER.reset_cycle()
    try:
        provider.connect()
        for symbol in args.symbols:
            try:
                _verify_symbol(provider, symbol.upper(), session_label=args.session)
            except Exception as exc:
                print(f"[VERIFY][ERROR] symbol={symbol.upper()} error={exc}")
    finally:
        provider.disconnect()


if __name__ == "__main__":
    main()
