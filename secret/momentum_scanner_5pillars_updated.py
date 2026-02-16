# File: momentum_scanner_5pillars_updated.py
"""
🔍 Momentum Scanner - 5 Pillars (Ross Cameron Style) - Updated

Enhancements:
- Cleans ticker symbols for Yahoo Finance / Finviz lookups.
- Tracks which source provided the float.
- Removes deprecated BeautifulSoup warnings.
- Keeps raw float value, formats display with K / M / B.
"""

def _import_ib_insync_all():
    from src.runtime.asyncio_runtime import ensure_event_loop

    ensure_event_loop()
    import ib_insync as ibi

    return ibi

ibi = _import_ib_insync_all()
globals().update(vars(ibi))
from us_top_gainers_list import get_top_gainers_symbols
import yfinance as yf
import requests
from bs4 import BeautifulSoup

# ----------------------------
# 1️⃣ Real-time Gap % (current last price vs previous close)
# ----------------------------
def get_gap_percent(contract, ib: IB):
    bars = ib.reqHistoricalData(
        contract,
        endDateTime='',
        durationStr='2 D',
        barSizeSetting='1 day',
        whatToShow='TRADES',
        useRTH=True,
        formatDate=1
    )
    if len(bars) < 2:
        return None
    prev_close = bars[-2].close
    ticker = ib.reqMktData(contract, '', False, False)
    ib.sleep(0.5)
    last_price = ticker.last if ticker.last is not None else 0
    gap_percent = ((last_price - prev_close) / prev_close) * 100
    return round(gap_percent, 2)

# ----------------------------
# 2️⃣ Real-time Price
# ----------------------------
def get_price(contract, ib: IB):
    ticker = ib.reqMktData(contract, '', False, False)
    ib.sleep(0.5)
    last_price = ticker.last if ticker.last is not None else 0
    return round(last_price, 2)

# ----------------------------
# 3️⃣ Float retrieval with fallback sources
# Returns a tuple: (raw_float_value, source)
# ----------------------------
def get_float(contract, ib: IB):
    symbol_clean = contract.symbol.replace(" ", "-")  # Clean ticker

    # 3a. IBKR
    try:
        fundamentals = ib.reqFundamentalData(contract, reportType='ReportSnapshot')
        if fundamentals and 'floatShares' in fundamentals:
            return int(fundamentals['floatShares']), 'IBKR'
    except Exception:
        pass

    # 3b. Yahoo Finance
    try:
        ticker = yf.Ticker(symbol_clean)
        info = ticker.info
        if 'floatShares' in info and info['floatShares'] is not None:
            return int(info['floatShares']), 'Yahoo'
    except Exception:
        pass

    # 3c. Finviz
    try:
        url = f"https://finviz.com/quote.ashx?t={symbol_clean}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers)
        soup = BeautifulSoup(resp.content, 'html.parser')
        table = soup.find('table', class_='snapshot-table2')
        if table:
            for row in table.find_all('tr'):
                for cell in row.find_all('td'):
                    if 'Float' in cell.text:
                        float_text = cell.find_next_sibling('td').text.strip().replace(',', '')
                        if float_text[-1] == 'M':
                            return int(float(float_text[:-1]) * 1_000_000), 'Finviz'
                        elif float_text[-1] == 'K':
                            return int(float(float_text[:-1]) * 1_000), 'Finviz'
                        else:
                            return int(float(float_text)), 'Finviz'
    except Exception:
        pass

    return "Not available", 'None'

# ----------------------------
# 4️⃣ Format float for display (K / M / B)
# ----------------------------
def format_float_display(raw_float):
    if isinstance(raw_float, int):
        if raw_float >= 1_000_000_000:
            return f"{raw_float/1_000_000_000:.2f}B"
        elif raw_float >= 1_000_000:
            return f"{raw_float/1_000_000:.2f}M"
        elif raw_float >= 1_000:
            return f"{raw_float/1_000:.0f}K"
        else:
            return str(raw_float)
    return raw_float

# ----------------------------
# 5️⃣ Placeholder functions
# ----------------------------

# ----------------------------
# 5️⃣ Function: Relative Volume (RVOL)
# ----------------------------
def get_rvol(contract, ib: IB):
    """
    Returns Relative Volume (RVOL) for a stock.
    RVOL = Current Intraday Volume / Average Volume for same period (default last 20 days)
    Uses IBKR historical data.
    """
    try:
        # Request 20 days of historical daily volume
        bars = ib.reqHistoricalData(
            contract,
            endDateTime='',
            durationStr='20 D',
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True,
            formatDate=1
        )
        if len(bars) < 1:
            return "Not available"

        # Calculate average daily volume over the period
        avg_volume = sum(bar.volume for bar in bars) / len(bars)

        # Get today's intraday volume (or last close if intraday not available)
        today_bar = bars[-1]
        today_volume = today_bar.volume

        if avg_volume == 0:
            return "N/A"

        rvol = today_volume / avg_volume
        return round(rvol, 2)  # e.g., 3.5 means 3.5x normal
    except Exception as e:
        print(f"Error calculating RVOL for {contract.symbol}: {e}")
        return "Not available"


def get_breaking_news(contract, ib: IB):
    return "Not implemented"

# ----------------------------
# 6️⃣ Sort by Gap % descending
# ----------------------------
def sort_by_gap(scanned_data):
    return sorted(scanned_data, key=lambda x: x['gap'] if x['gap'] is not None else -999, reverse=True)

# ----------------------------
# Main
# ----------------------------
def main():
    ib = IB()
    ib.connect('127.0.0.1', 7496, clientId=2)

    top_instruments = get_top_gainers_symbols()
    scanned_data = []

    for contract in top_instruments:
        gap = get_gap_percent(contract, ib)
        price = get_price(contract, ib)
        raw_float, float_source = get_float(contract, ib)
        scanned_data.append({
            'contract': contract,
            'gap': gap,
            'float': format_float_display(raw_float),
            'float_source': float_source,
            'rvol': get_rvol(contract, ib),
            'news': get_breaking_news(contract, ib),
            'price': price
        })

    scanned_data_sorted = sort_by_gap(scanned_data)

    # Print results
    print("\n🔍 Momentum Scanner - 5 Pillars (Ross Cameron Style)")
    print("-" * 80)
    for data in scanned_data_sorted:
        c = data['contract']
        print(f"{c.symbol} | Gap %: {data['gap']} | Float: {data['float']} ({data['float_source']}) | "
              f"RVOL: {data['rvol']} | Price: {data['price']}| News: {data['news']} ")

    ib.disconnect()


if __name__ == "__main__":
    main()
