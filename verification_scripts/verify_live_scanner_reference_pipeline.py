from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys
from typing import Optional
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config.runtime_config import resolve_ibkr_connection
from src.scanner import scanner_runner
from src.scanner.candidate_identity import CandidateIdentity
from src.scanner.providers.base import IntradayStats, QuoteData, ScannerDataProvider
from src.scanner.providers.ibkr_provider import IbkrScannerProvider

DEFAULT_SYMBOLS = ["AIM", "ARTL", "AGRO", "ALDX", "BATL"]
NY_TZ = ZoneInfo("America/New_York")


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

    def connect(self) -> None: return None
    def disconnect(self) -> None: return None
    def get_top_gainers(self, limit: int, request=None) -> list[str]: return DEFAULT_SYMBOLS[:limit]

    def get_quote(self, symbol: str) -> QuoteData:
        last = 11.0 if symbol == "AIM" else 7.25
        close = 10.0 if symbol == "AIM" else None
        return QuoteData(symbol=symbol, bid=last - 0.02, ask=last + 0.03, last=last, vwap=last - 0.05, open=last - 0.4, high=last + 0.2, low=last - 0.6, close=close, change_percent=10.0 if symbol == "AIM" else 7.4, volume=250_000 if symbol == "AIM" else 180_000, timestamp_utc="2026-03-18T00:00:00Z", data_quality_flags=())
    def get_prev_close(self, symbol: str) -> Optional[float]: return 10.0 if symbol == "AIM" else 6.75
    def get_previous_rth_close(self, identity) -> Optional[float]: return self.get_prev_close(getattr(identity, "symbol", identity))
    def get_intraday_stats(self, symbol: str) -> IntradayStats:
        adv20 = 125_000 if symbol == "AIM" else 90_000
        return IntradayStats(current_intraday_volume=250_000 if symbol == "AIM" else 180_000, current_volume_source_label="STUB", average_daily_volume_20d=adv20, average_daily_volume_window_days=20, relative_volume=None, relative_volume_category=None, volume_velocity_5m=None, volume_velocity_15m=None, volume_data_quality_flag="STUB")
    def get_float(self, symbol: str) -> Optional[int]: return 8_500_000
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


def _print_block(title: str, payload: dict) -> None:
    print(title)
    for key, value in payload.items():
        print(f"  - {key}: {value}")


def _build_identity(symbol: str, details: dict) -> CandidateIdentity:
    return CandidateIdentity.from_mapping({
        "symbol": symbol,
        "conId": details.get("conId"),
        "secType": details.get("secType") or "STK",
        "exchange": details.get("exchange") or details.get("primaryExchange") or "SMART",
        "primaryExchange": details.get("primaryExchange"),
        "tradingClass": details.get("tradingClass"),
        "currency": details.get("currency") or "USD",
        "localSymbol": details.get("localSymbol") or symbol,
    })


def _contract_dict(identity: CandidateIdentity) -> dict:
    return {
        "symbol": identity.symbol,
        "conId": identity.con_id,
        "secType": identity.sec_type,
        "exchange": identity.exchange,
        "primaryExchange": identity.primary_exchange,
        "tradingClass": identity.trading_class,
        "localSymbol": identity.local_symbol,
        "currency": identity.currency,
        "identity_key": identity.key,
    }


def _normalize_bars(raw) -> list:
    bars = []
    for bar in raw or []:
        bars.append({
            "date": getattr(bar, "trading_date", None) or getattr(bar, "date", None),
            "close": getattr(bar, "close", None),
            "volume": getattr(bar, "volume", None),
        })
    return bars


def _history_attempts(provider, identity: CandidateIdentity):
    explicit_end = f"{datetime.now(NY_TZ).strftime('%Y%m%d')} 09:29:59 US/Eastern"
    attempts = [
        {"label": "provider_primary", "use_rth": True, "end_datetime": ""},
        {"label": "provider_retry", "use_rth": False, "end_datetime": explicit_end},
    ]
    results = []
    for attempt in attempts:
        try:
            bars = _normalize_bars(provider.get_daily_bars(identity, lookback_days=25, use_rth=attempt["use_rth"], end_datetime=attempt["end_datetime"]))
            results.append({**attempt, "error": None, "bars": bars})
        except Exception as exc:
            results.append({**attempt, "error": repr(exc), "bars": []})
    return results, explicit_end


def _client_history_attempts(provider, identity: CandidateIdentity, explicit_end: str):
    client = getattr(provider, "market_data_client", None)
    if client is None:
        return None
    contract = scanner_runner._REFERENCE_RESOLVER._contract_from_identity(identity)
    try:
        qualified = provider.qualifyContracts(contract)
        if qualified:
            contract = qualified[0]
    except Exception:
        pass
    attempts = [
        {"label": "client_primary", "use_rth": True, "end_datetime": ""},
        {"label": "client_retry", "use_rth": False, "end_datetime": explicit_end},
    ]
    results = []
    for attempt in attempts:
        try:
            bars = _normalize_bars(client.daily_bars_from_history(contract, lookback_days=25, use_rth=attempt["use_rth"], end_datetime=attempt["end_datetime"]))
            results.append({**attempt, "error": None, "bars": bars})
        except Exception as exc:
            results.append({**attempt, "error": repr(exc), "bars": []})
    return {"contract": contract, "attempts": results}


def _verify_symbol(provider: ScannerDataProvider, symbol: str, *, session_label: str) -> None:
    base_detail = ((getattr(provider, "last_scan_details", {}) or {}).get("symbol_details") or {}).get(symbol, {"symbol": symbol})
    base_identity = _build_identity(symbol, base_detail)
    qualified_identity = base_identity
    qualify_error = None
    try:
        contract = scanner_runner._REFERENCE_RESOLVER._contract_from_identity(base_identity)
        qualified = provider.qualifyContracts(contract) if hasattr(provider, "qualifyContracts") else []
        if qualified:
            qualified_identity = CandidateIdentity.from_contract(qualified[0], fallback_symbol=symbol)
    except Exception as exc:
        qualify_error = repr(exc)

    _print_block(f"\n[VERIFY][{symbol}] A) scanner metadata / identity", {
        **_contract_dict(qualified_identity),
        "qualification_error": qualify_error,
    })

    quote = None
    quote_error = None
    try:
        quote = provider.get_quote(symbol)
    except Exception as exc:
        quote_error = repr(exc)
    _print_block(f"[VERIFY][{symbol}] B) direct live quote", {
        "last": getattr(quote, "last", None),
        "bid": getattr(quote, "bid", None),
        "ask": getattr(quote, "ask", None),
        "close": getattr(quote, "close", None),
        "volume": getattr(quote, "volume", None),
        "change_percent": getattr(quote, "change_percent", None),
        "timestamp_utc": getattr(quote, "timestamp_utc", None),
        "data_quality_flags": list(getattr(quote, "data_quality_flags", []) or []) if quote is not None else None,
        "quote_error": quote_error,
        "quote_empty": quote is None or all(getattr(quote, field, None) is None for field in ("last", "bid", "ask", "close", "volume")),
    })

    provider_history, explicit_end = _history_attempts(provider, qualified_identity)
    for idx, attempt in enumerate(provider_history, start=1):
        bars = attempt["bars"]
        _print_block(f"[VERIFY][{symbol}] C{idx}) direct provider history", {
            "params": {"lookback_days": 25, "use_rth": attempt["use_rth"], "end_datetime": attempt["end_datetime"]},
            "error": attempt["error"],
            "raw_bar_count": len(bars),
            "first_bar_date": bars[0]["date"] if bars else None,
            "last_bar_date": bars[-1]["date"] if bars else None,
            "last_close": bars[-1]["close"] if bars else None,
        })

    client_history = _client_history_attempts(provider, qualified_identity, explicit_end)
    if client_history is None:
        _print_block(f"[VERIFY][{symbol}] D) direct market_data_client history", {"available": False})
    else:
        _print_block(f"[VERIFY][{symbol}] D0) direct market_data_client contract", {
            "symbol": getattr(client_history['contract'], 'symbol', None),
            "conId": getattr(client_history['contract'], 'conId', None),
            "exchange": getattr(client_history['contract'], 'exchange', None),
            "primaryExchange": getattr(client_history['contract'], 'primaryExchange', None),
            "tradingClass": getattr(client_history['contract'], 'tradingClass', None),
            "localSymbol": getattr(client_history['contract'], 'localSymbol', None),
        })
        for idx, attempt in enumerate(client_history["attempts"], start=1):
            bars = attempt["bars"]
            _print_block(f"[VERIFY][{symbol}] D{idx}) direct market_data_client history", {
                "params": {"lookback_days": 25, "use_rth": attempt["use_rth"], "end_datetime": attempt["end_datetime"]},
                "error": attempt["error"],
                "raw_bar_count": len(bars),
                "last_close": bars[-1]["close"] if bars else None,
                "last_volume": bars[-1]["volume"] if bars else None,
            })

    intraday = provider.get_intraday_stats(symbol)
    resolver = scanner_runner._REFERENCE_RESOLVER
    result = resolver.resolve(
        identity=qualified_identity,
        provider=provider,
        session_label=session_label,
        current_volume=getattr(intraday, "current_intraday_volume", None) if intraday else getattr(quote, "volume", None),
        intraday_avg_volume_20d=getattr(intraday, "average_daily_volume_20d", None) if intraday else None,
        current_last_price=getattr(quote, "last", None),
        rth_open_price=getattr(quote, "open", None),
        rth_close_price=getattr(quote, "close", None),
        ibkr_change_pct=getattr(quote, "change_percent", None),
        persisted_pct_change=getattr(quote, "persisted_pct_change", None),
    )
    trace = resolver.get_last_resolution_trace(result.identity_key)
    _print_block(f"[VERIFY][{symbol}] E) resolver", {
        "selected_reference_source": result.reference_source,
        "selected_reference_price": result.reference_price,
        "selected_reference_quality_tier": result.reference_quality_tier,
        "selected_adv20_source": result.adv20_source,
        "selected_avg_volume_20d": result.avg_volume_20d,
        "rvol_discovery": result.rvol_discovery,
        "rvol_phase": result.rvol_phase,
        "reference_failure_reason": result.reference_failure_reason,
        "rvol_failure_reason": result.rvol_failure_reason,
        "history_attempts_trace": trace.get("history_attempts"),
    })

    context = scanner_runner._build_symbol_context(provider, symbol, session_label, float_cache={}, include_pct_change=True)
    if context is None:
        print(f"[VERIFY][ERROR] symbol={symbol} reason=context_build_failed")
        return
    propagation_ok = all(context.get(field) is not None for field in ("con_id", "exchange", "primary_exchange", "trading_class", "identity_key"))
    _print_block(f"[VERIFY][{symbol}] F) final context", {
        "con_id": context.get("con_id"),
        "exchange": context.get("exchange"),
        "primary_exchange": context.get("primary_exchange"),
        "trading_class": context.get("trading_class"),
        "identity_key": context.get("identity_key"),
        "last_price": context.get("last_price"),
        "bid": context.get("bid"),
        "ask": context.get("ask"),
        "close": context.get("close"),
        "volume": context.get("volume"),
        "reference_source": context.get("reference_source"),
        "reference_resolved": context.get("reference_resolved"),
        "reference_price": context.get("reference_price"),
        "pct_change_resolved": context.get("pct_change_resolved"),
        "avg_volume_20d": context.get("avg_volume_20d"),
        "adv20_resolved": context.get("adv20_resolved"),
        "rvol_status": context.get("rvol_status"),
        "data_quality_flags": context.get("data_quality_flags"),
        "propagation_ok": propagation_ok,
    })

    provider_history_ok = any(attempt["bars"] for attempt in provider_history)
    client_history_ok = bool(client_history and any(attempt["bars"] for attempt in client_history["attempts"]))
    quote_ok = quote is not None and any(getattr(quote, field, None) is not None for field in ("last", "bid", "ask", "close", "volume"))
    if client_history is not None:
        if client_history_ok and not provider_history_ok:
            print(f"[VERIFY][{symbol}] lower-level client works but provider path fails")
        elif not client_history_ok and provider_history_ok:
            print(f"[VERIFY][{symbol}] provider path works but lower-level client fails")
    print(f"RESULT: quote_ok={'yes' if quote_ok else 'no'} history_provider={'yes' if provider_history_ok else 'no'} history_client={'yes' if client_history_ok else 'no'} propagation_ok={'yes' if propagation_ok else 'no'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify live scanner reference/pct/adv20/rvol pipeline.")
    parser.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS)
    parser.add_argument("--session", default="RTH_OPEN")
    parser.add_argument("--provider", choices=("live", "stub"), default="live")
    args = parser.parse_args()

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
                print(f"[VERIFY][ERROR] symbol={symbol.upper()} error={exc!r}")
    finally:
        provider.disconnect()


if __name__ == "__main__":
    main()
