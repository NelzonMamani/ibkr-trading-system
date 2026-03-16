from __future__ import annotations

import argparse
from typing import Any, Sequence

from src.adapters.brokers.ibkr.ibkr_connection_manager import get_shared_ibkr_connection_manager
from src.config.config_resolver import get_config
from src.core.managers.market_data_snapshot_manager import MarketDataSnapshotManager
from src.scanner.scanner_contract import scanner_request_from_policy
from src.scanner.scanner_runner import run_scanner_cycle
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IBKR scanner diagnostics utility")
    parser.add_argument("--dry-run", action="store_true", help="Skip broker calls and print deterministic diagnostics")
    return parser.parse_args(argv)


def run_diagnostics(*, dry_run: bool) -> dict[str, Any]:
    policy = RossMomentumPolicy().stock_selection
    request = scanner_request_from_policy(policy, strategy_name="ross_momentum", session_phase="PREMARKET")
    manager = None
    metadata: dict[str, Any] = {
        "host": get_config("IBKR_HOST"),
        "port": get_config("IBKR_PORT"),
        "base_client_id": get_config("IBKR_CLIENT_ID"),
    }
    market_data_type = str(get_config("IBKR_MARKET_DATA_TYPE") or "UNKNOWN")

    status = "DRY_RUN"
    scanner_operational = True
    symbols: list[str] = []
    rows: list[tuple[str, Any, Any, Any]] = []
    diagnostics: dict[str, Any] = {}

    if not dry_run:
        try:
            manager = get_shared_ibkr_connection_manager(readonly_enabled=True)
            metadata = manager.connection_metadata()
            market_data_type = str(getattr(manager.config, "market_data_type", market_data_type) or market_data_type)
            manager.ensure_connected()
            status = "ACTIVE"
        except Exception as exc:
            status = f"FAILED:{exc}"
            scanner_operational = False

        if scanner_operational:
            try:
                payload = run_scanner_cycle(
                    mode="READ_ONLY",
                    policy=policy,
                    scanner_request=request,
                )
                diagnostics = payload.get("diagnostics") or {}
                universe_entries = payload.get("universe_top_n") or []
                symbols = [str(entry.get("symbol") or "") for entry in universe_entries if isinstance(entry, dict)]
                symbols = [symbol for symbol in symbols if symbol]
                snapshot_manager = MarketDataSnapshotManager(manager.get_client())
                for symbol in symbols:
                    snapshot, quality = snapshot_manager.get_snapshot(symbol)
                    hydration = "PARTIAL" if quality.missing_fields else "SUCCESS"
                    price = snapshot.last if snapshot.last is not None else "UNAVAILABLE"
                    volume = snapshot.volume if snapshot.volume is not None else "UNAVAILABLE"
                    rows.append((symbol, price, hydration, volume))
            except Exception as exc:
                scanner_operational = False
                status = status if status.startswith("FAILED:") else "ACTIVE"
                rows = [("SCANNER_ERROR", None, None, str(exc))]
    else:
        symbols = ["AAPL", "TSLA"]
        rows = [("AAPL", 175.0, "SUCCESS", 1_500_000), ("TSLA", 240.0, "SUCCESS", 2_100_000)]
        diagnostics = {
            "scanner_contract": {"top_n": 50, "watchlist_k": 2, "focus_m": 1, "contract_valid": True},
            "raw_zero_attribution": {
                "provider": "IBKR",
                "broker_returned_zero": False,
                "instrument": "STK",
                "location": "STK.US",
                "scanCode": "TOP_PERC_GAIN",
                "requested_top_n": 50,
                "broker_rows_requested": 50,
                "effective_internal_processing_limit": 50,
                "translation_or_truncation_occurred": False,
                "local_gating_applied": True,
                "local_gating_eliminated_all": False,
                "raw_broker_count": 2,
                "candidate_count_entering_gates": 2,
                "survivor_count_after_gates": 2,
                "watchlist_count": 2,
                "focus_count": 1,
                "drop_reasons": {},
            },
            "scanner_refresh": {
                "cycle_seconds": 5,
                "scanner_refresh_active": True,
                "last_refresh_utc": "DRY_RUN",
                "next_refresh_due_utc": "DRY_RUN",
            },
        }

    return {
        "broker": {
            "provider": "IBKR",
            "connection": status,
            "host": metadata.get("host"),
            "port": metadata.get("port"),
            "client_id": metadata.get("base_client_id"),
            "market_data_type": market_data_type,
        },
        "scanner": {
            "returned_symbols": len(symbols),
            "rows": rows,
            "scanner_operational": scanner_operational,
            "diagnostics": diagnostics,
            "scanner_contract": diagnostics.get("scanner_contract") or {},
            "raw_zero_attribution": diagnostics.get("raw_zero_attribution") or {},
            "scanner_refresh": diagnostics.get("scanner_refresh") or {},
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_diagnostics(dry_run=args.dry_run)

    print("[BROKER]")
    broker = result["broker"]
    print(f"provider={broker['provider']}")
    print(f"connection={broker['connection']}")
    print(f"host={broker['host']}")
    print(f"port={broker['port']}")
    print(f"client_id={broker['client_id']}")
    print(f"market_data_type={broker['market_data_type']}")

    print("\n[SCANNER_TEST]")
    scanner = result["scanner"]
    print(f"returned_symbols={scanner['returned_symbols']}")
    print("\nSYMBOLS")
    print("SYMBOL PRICE HYDRATION VOLUME")
    for symbol, price, hydration, volume in scanner["rows"]:
        print(f"{symbol} {price if price is not None else 'N/A'} {hydration if hydration is not None else 'N/A'} {volume if volume is not None else 'N/A'}")

    contract = scanner.get("scanner_contract") or {}
    print("\n[SCANNER][CONTRACT]")
    print(f"top_n={contract.get('top_n', 0)}")
    print(f"watchlist_k={contract.get('watchlist_k', 0)}")
    print(f"focus_m={contract.get('focus_m', 0)}")
    print(f"contract_valid={contract.get('contract_valid', False)}")

    refresh = scanner.get("scanner_refresh") or {}
    print("\n[SCANNER][REFRESH]")
    print(f"cycle_seconds={refresh.get('cycle_seconds', 0)}")
    print(f"scanner_refresh_active={refresh.get('scanner_refresh_active', False)}")
    print(f"last_refresh_utc={refresh.get('last_refresh_utc', 'UNKNOWN')}")
    print(f"next_refresh_due_utc={refresh.get('next_refresh_due_utc', 'UNKNOWN')}")

    raw_zero = scanner.get("raw_zero_attribution") or {}
    print("\n[SCANNER][RAW_ZERO]")
    for key in [
        "provider",
        "broker_returned_zero",
        "instrument",
        "location",
        "scanCode",
        "requested_top_n",
        "broker_rows_requested",
        "effective_internal_processing_limit",
        "translation_or_truncation_occurred",
        "local_gating_applied",
        "local_gating_eliminated_all",
        "raw_broker_count",
        "candidate_count_entering_gates",
        "survivor_count_after_gates",
        "watchlist_count",
        "focus_count",
        "drop_reasons",
    ]:
        print(f"{key}={raw_zero.get(key)}")

    print("\n[SCANNER_TEST_SUMMARY]")
    print(f"symbols_returned={scanner['returned_symbols']}")
    print(f"scanner_operational={scanner['scanner_operational']}")

    return 0 if scanner["scanner_operational"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
