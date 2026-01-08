# File: us_top_gainers_list.py
from ib_insync import *

def get_top_gainers_symbols(number_of_rows=10):
    """
    Fetch top US stock gainers from IBKR scanner.

    Returns:
        List of ib_insync Contract objects.
    """
    ib = IB()
    ib.connect('127.0.0.1', 7496, clientId=1)

    # Scanner request: Top % Gainers, US stocks
    scan_sub = ScannerSubscription(
        instrument='STK',
        locationCode='STK.US.MAJOR',
        scanCode='TOP_PERC_GAIN',
        numberOfRows=number_of_rows
    )

    scan_data = ib.reqScannerData(scan_sub)

    # Collect contracts
    instruments = [item.contractDetails.contract for item in scan_data]

    ib.disconnect()
    return instruments

if __name__ == "__main__":
    top_instruments = get_top_gainers_symbols()
    for c in top_instruments:
        print(c.symbol)
