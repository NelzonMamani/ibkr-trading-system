from ib_insync import *

def get_top_gainers():
    ib = IB()
    ib.connect('127.0.0.1', 7496, clientId=1)

    # Scanner request: Top % Gainers, US stocks
    scan_sub = ScannerSubscription(
        instrument='STK',
        locationCode='STK.US.MAJOR',
        scanCode='TOP_PERC_GAIN',
        numberOfRows=20
    )

    scan_data = ib.reqScannerData(scan_sub)

    print("\n🔝 TOP 10 U.S. STOCK GAINERS")
    print("-" * 50)

    for item in scan_data:
        contract = item.contractDetails.contract
        symbol = contract.symbol
        exchange = contract.exchange

        # Extract fields safely
        last_price = getattr(item, 'last', 'N/A')
        pct_change = getattr(item, 'percentChange', 'N/A')

        print(f"{symbol} | {exchange} | Price: {last_price} | Change: {pct_change}%")

    ib.disconnect()

if __name__ == "__main__":
    get_top_gainers()
