#!/usr/bin/env python3
"""
Standalone IBKR Top Gainers Scanner
-----------------------------------

- Single-file script
- No project dependencies
- Simulates orchestrator -> scanner flow
- Uses real IBKR scanner data
"""

def _import_ibkr_types():
    from src.runtime.asyncio_runtime import ensure_event_loop

    ensure_event_loop()
    from ib_insync import IB, ScannerSubscription

    return IB, ScannerSubscription

IB, ScannerSubscription = _import_ibkr_types()
import sys
import time


def scan_top_gainers(ib, number_of_rows=50):
    """
    Pure scanner function.
    Consumes a CONNECTED IB instance.
    """

    scan_sub = ScannerSubscription(
        instrument='STK',
        locationCode='STK.US.MAJOR',
        scanCode='TOP_PERC_GAIN',
        numberOfRows=number_of_rows
    )

    scan_data = ib.reqScannerData(scan_sub)

    contracts = []
    for item in scan_data:
        if item.contractDetails and item.contractDetails.contract:
            contracts.append(item.contractDetails.contract)

    return contracts


def main():
    ib = IB()

    try:
        print("[INFO] Connecting to IBKR...")
        ib.connect(
            host='127.0.0.1',
            port=7496,       # 7496 = TWS paper, 7497 = TWS live
            clientId=999,
            timeout=5
        )

        print("[INFO] Connected.")
        print("[INFO] Requesting top gainers...\n")

        contracts = scan_top_gainers(
            ib=ib,
            number_of_rows=10
        )

        print("🔍 Top % Gainers (Scanner Output)")
        print("-" * 60)

        for c in contracts:
            print(c.symbol)

        print("\n[INFO] Scan complete.")

    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)

    finally:
        if ib.isConnected():
            ib.disconnect()
            print("[INFO] Disconnected.")


if __name__ == "__main__":
    main()
