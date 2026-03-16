from __future__ import annotations

import argparse
from typing import Sequence

from src.adapters.brokers.ibkr.ibkr_connection_manager import get_shared_ibkr_connection_manager
from src.scanner.providers.factory import build_provider
from src.scanner.scanner_contract import ScannerRequest
from src.strategies.ross_momentum.strategy_policy import UniverseSource


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IBKR scanner diagnostics utility")
    parser.add_argument("--dry-run", action="store_true", help="Skip broker calls and print deterministic diagnostics")
    return parser.parse_args(argv)


def _ross_scanner_request() -> ScannerRequest:
    return ScannerRequest(
        strategy_name="ross_momentum",
        policy_name="RossMomentumPolicy",
        ranking_intent="momentum_top_percent_gainers",
        session_phase="PREMARKET",
        universe_source=UniverseSource.IBKR_TOP_GAINERS,
        ibkr_scan_code="TOP_PERC_GAIN",
        requested_top_n=50,
        above_price=1,
        below_price=20,
        instrument="STK",
        location_code="STK.US",
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    manager = get_shared_ibkr_connection_manager(readonly_enabled=True)
    metadata = manager.connection_metadata()
    status = "INACTIVE"
    if args.dry_run:
        status = "DRY_RUN"
    else:
        try:
            manager.ensure_connected()
            status = "ACTIVE"
        except Exception as exc:
            status = f"ERROR:{exc}"

    print("[BROKER]")
    print("provider=IBKR")
    print(f"connection={status}")
    print(f"host={metadata.get('host')}")
    print(f"port={metadata.get('port')}")
    print(f"client_id={metadata.get('base_client_id')}")
    print(f"market_data_type={manager.config.market_data_type}")

    request = _ross_scanner_request()

    symbols: list[str] = []
    rows: list[tuple[str, float | None, float | None, float | None]] = []
    scanner_operational = True

    if args.dry_run:
        scanner_operational = True
    else:
        try:
            provider = build_provider(connection_manager=manager)
            try:
                symbols = provider.get_top_gainers(limit=request.requested_top_n, request=request)
                for symbol in symbols:
                    quote = provider.get_quote(symbol)
                    rows.append((symbol, quote.last, quote.change_percent, quote.volume))
            finally:
                provider.disconnect()
        except Exception as exc:
            scanner_operational = False
            print(f"[SCANNER_TEST_ERROR] {exc}")

    print("\n[SCANNER_TEST]")
    print(f"returned_symbols={len(symbols)}")
    print("\nSYMBOLS")
    print("SYMBOL PRICE PCT_CHANGE VOLUME")
    for symbol, price, pct_change, volume in rows:
        print(f"{symbol} {price} {pct_change} {volume}")

    print("\n[SCANNER_TEST_SUMMARY]")
    print(f"symbols_returned={len(symbols)}")
    print(f"scanner_operational={scanner_operational}")

    return 0 if scanner_operational else 1


if __name__ == "__main__":
    raise SystemExit(main())
