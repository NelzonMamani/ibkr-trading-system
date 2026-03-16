from __future__ import annotations

from pprint import pformat
from typing import Any, Dict

from src.scanner.providers.ibkr_provider import IbkrScannerProvider
from src.scanner.scanner_runner import run_scanner_cycle


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def run_runtime_diagnostic() -> Dict[str, Any]:
    """Execute scanner runtime using the live IBKR provider and print flow diagnostics."""
    provider = IbkrScannerProvider()
    payload = run_scanner_cycle(mode="READ_ONLY", provider=provider)

    diagnostics = payload.get("diagnostics", {}) or {}
    scanner_flow = diagnostics.get("scanner_flow", {}) or {}
    ibkr_universe = diagnostics.get("ibkr_universe", {}) or {}

    provider_source = scanner_flow.get("provider") or getattr(provider, "source_name", "UNKNOWN")
    raw_broker_count = _to_int(payload.get("raw_broker_count", scanner_flow.get("raw_broker_count", 0)))
    returned_rows = _to_int(scanner_flow.get("returned_rows", ibkr_universe.get("returned_rows", raw_broker_count)))
    raw_symbols_count = len(payload.get("symbols", []) or [])
    survivors_count = _to_int(payload.get("survivors_count", scanner_flow.get("survivor_count_after_gates", 0)))
    watchlist_symbols = payload.get("watchlist_k_symbols") or payload.get("watchlist") or []
    focus_symbols = payload.get("focus_m_symbols") or []
    watchlist_count = _to_int(payload.get("watchlist_count", len(watchlist_symbols)))
    focus_count = len(focus_symbols)
    effective_location_code = (
        scanner_flow.get("effective_location_code")
        or ibkr_universe.get("effective_location_code")
        or "UNKNOWN"
    )
    effective_scan_code = (
        scanner_flow.get("effective_scan_code")
        or ibkr_universe.get("effective_scan_code")
        or "UNKNOWN"
    )
    retry_attempts = _to_int(scanner_flow.get("retry_attempts", ibkr_universe.get("retry_attempts", 0)))
    retry_exhausted = bool(scanner_flow.get("retry_exhausted", ibkr_universe.get("retry_exhausted", False)))

    print("=== SCANNER RUNTIME DIAGNOSTIC ===")
    print(f"provider_source={provider_source}")
    print(f"raw_broker_count={raw_broker_count}")
    print(f"returned_rows={returned_rows}")
    print(f"raw_symbols_count={raw_symbols_count}")
    print(f"survivors_count={survivors_count}")
    print(f"watchlist_count={watchlist_count}")
    print(f"focus_count={focus_count}")
    print(f"effective_location_code={effective_location_code}")
    print(f"effective_scan_code={effective_scan_code}")
    print(f"retry_attempts={retry_attempts}")
    print(f"retry_exhausted={retry_exhausted}")
    print(f"watchlist_symbols={watchlist_symbols}")
    print(f"focus_symbols={focus_symbols}")

    if scanner_flow:
        print("scanner_flow=")
        print(pformat(scanner_flow))
    if ibkr_universe:
        print("ibkr_universe=")
        print(pformat(ibkr_universe))

    if raw_broker_count > 0 and watchlist_count == 0:
        print("[RUNTIME][FAILURE] symbols acquired but lost inside scanner runtime")
    elif raw_broker_count == 0:
        print("[RUNTIME][FAILURE] runtime acquisition still empty")
    elif watchlist_count > 0:
        print("[RUNTIME][SUCCESS] scanner runtime is producing watchlists")

    return payload
