"""
IBKR Scanner Diagnostic Harness

Tests each layer independently:

1. Raw IBKR API
2. MarketDataClient adapter
3. Scanner provider
4. Scanner runtime

Produces a structured report identifying the failure layer.
"""

from src.runtime.async_runtime_bootstrap import safe_import_ib_insync
from src.adapters.brokers.ibkr.ibkr_connection_manager import (
    get_shared_ibkr_connection_manager,
)
from src.ibkr.market_data_client import MarketDataClient
from src.scanner.providers.ibkr_provider import IbkrScannerProvider
from src.scanner.scanner_contract import ScannerRequest


def test_raw_ibkr():
    print("\n=== TEST 1: RAW IBKR ===")

    IB, _, ScannerSubscription = safe_import_ib_insync()

    ib = IB()
    try:
        ib.connect("127.0.0.1", 7496, clientId=999)
    except Exception as exc:
        print("RAW CONNECT ERROR:", exc)
        return 0

    sub = ScannerSubscription(
        instrument="STK",
        locationCode="STK.US.MAJOR",
        scanCode="TOP_PERC_GAIN",
        numberOfRows=50,
        abovePrice=1,
        belowPrice=20,
    )

    results = ib.reqScannerData(sub)

    print("RAW RESULT COUNT:", len(results))

    symbols = []
    for r in results[:10]:
        contract = r.contractDetails.contract
        symbols.append(contract.symbol)

    print("RAW SAMPLE:", symbols)

    ib.disconnect()

    return len(results)


def test_market_data_client():
    print("\n=== TEST 2: MARKET DATA CLIENT ===")

    _, _, ScannerSubscription = safe_import_ib_insync()

    manager = get_shared_ibkr_connection_manager()

    client = MarketDataClient(connection_manager=manager)

    try:
        client.connect()
    except Exception as exc:
        print("ADAPTER CONNECT ERROR:", exc)
        return 0

    sub = ScannerSubscription(
        instrument="STK",
        locationCode="STK.US.MAJOR",
        scanCode="TOP_PERC_GAIN",
        numberOfRows=50,
        abovePrice=1,
        belowPrice=20,
    )

    results = client.request_scanner_data(sub)

    print("ADAPTER RESULT COUNT:", len(results))

    return len(results)


def test_provider():
    print("\n=== TEST 3: PROVIDER ===")

    provider = IbkrScannerProvider()
    try:
        provider.connect()
    except Exception as exc:
        print("PROVIDER CONNECT ERROR:", exc)
        return 0

    request = ScannerRequest(
        strategy_name="diagnostic",
        policy_name="diagnostic",
        ranking_intent="diagnostic",
        session_phase="RTH",
        universe_source="IBKR_TOP_GAINERS",
        ibkr_scan_code="TOP_PERC_GAIN",
        requested_top_n=50,
        above_price=1,
        below_price=20,
        region="US",
        instrument="STK",
        location_code="STK.US",
        exchanges=["SMART"],
    )

    symbols = provider.get_top_gainers(50, request)

    print("PROVIDER RESULT COUNT:", len(symbols))
    print("PROVIDER SAMPLE:", symbols[:10])

    return len(symbols)


def run_diagnostics():
    print("\n==========================")
    print(" IBKR SCANNER DIAGNOSTIC")
    print("==========================")

    raw = test_raw_ibkr()
    adapter = test_market_data_client()
    provider = test_provider()

    print("\n=== DIAGNOSTIC SUMMARY ===")

    print("RAW:", raw)
    print("ADAPTER:", adapter)
    print("PROVIDER:", provider)

    if raw == 0:
        print("CAUSE: IBKR scanner parameters invalid or IBKR API returning empty.")
    elif adapter == 0:
        print("CAUSE: MarketDataClient dropping scanner results.")
    elif provider == 0:
        print("CAUSE: Provider scanner configuration bug.")
    else:
        print("CAUSE: Scanner runtime pipeline.")


if __name__ == "__main__":
    run_diagnostics()
