# stock_selection_scanner_25_jan_2026.py

from ib_insync import IB, ScannerSubscription, Stock
import math
import requests
import yfinance as yf
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET


# ======================================================
# Basic numeric hygiene and formatting
# ======================================================

def sanitize_numeric(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (int, float)) and value <= 0:
        return None
    return value


def format_price_value(value):
    value = sanitize_numeric(value)
    return "N/A" if value is None else f"{value:.2f}"


def format_percentage_value(value):
    value = sanitize_numeric(value)
    return "N/A" if value is None else f"{value:+.2f}%"


def format_ratio_value(value):
    value = sanitize_numeric(value)
    return "N/A" if value is None else f"{value:.2f}"


def calculate_percent_change(current_value, reference_value):
    current_value = sanitize_numeric(current_value)
    reference_value = sanitize_numeric(reference_value)
    if current_value is None or reference_value is None:
        return None
    return ((current_value - reference_value) / reference_value) * 100.0


# ======================================================
# Historical price retrieval (weekend logic)
# ======================================================

def fetch_last_two_session_closes(ib: IB, contract: Stock):
    daily_bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr="10 D",
        barSizeSetting="1 day",
        whatToShow="TRADES",
        useRTH=True
    )

    if not daily_bars or len(daily_bars) < 2:
        return None, None

    most_recent_close = sanitize_numeric(daily_bars[-1].close)
    prior_session_close = sanitize_numeric(daily_bars[-2].close)

    return most_recent_close, prior_session_close


# ======================================================
# Relative volume calculations
# ======================================================

def calculate_relative_volume_vs_20_day_average(
    ib: IB,
    contract: Stock,
    average_window_days: int = 20
):
    daily_bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr=f"{average_window_days + 5} D",
        barSizeSetting="1 day",
        whatToShow="TRADES",
        useRTH=True
    )

    valid_bars = [b for b in daily_bars if b.volume and b.volume > 0]
    if len(valid_bars) < average_window_days + 1:
        return None

    latest_session = valid_bars[-1]
    prior_sessions = valid_bars[-(average_window_days + 1):-1]

    average_volume = sum(b.volume for b in prior_sessions) / len(prior_sessions)
    if average_volume <= 0:
        return None

    return latest_session.volume / average_volume


def calculate_relative_volume_vs_previous_day(ib: IB, contract: Stock):
    daily_bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr="5 D",
        barSizeSetting="1 day",
        whatToShow="TRADES",
        useRTH=True
    )

    if not daily_bars or len(daily_bars) < 2:
        return None

    today_volume = sanitize_numeric(daily_bars[-1].volume)
    previous_day_volume = sanitize_numeric(daily_bars[-2].volume)

    if today_volume is None or previous_day_volume is None:
        return None

    return today_volume / previous_day_volume


# ======================================================
# Float retrieval (best-effort, diagnostic)
# ======================================================

def fetch_float_shares_best_effort(symbol: str):
    cleaned_symbol = symbol.replace(" ", "-")

    # Yahoo Finance
    try:
        ticker = yf.Ticker(cleaned_symbol)
        info = ticker.info
        if 'floatShares' in info and info['floatShares']:
            return int(info['floatShares'])
    except Exception:
        pass

    # Finviz fallback (reliable for small caps / OTC)
    try:
        url = f"https://finviz.com/quote.ashx?t={cleaned_symbol}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.content, 'html.parser')
        table = soup.find('table', class_='snapshot-table2')
        if table:
            cells = table.find_all('td')
            for index, cell in enumerate(cells):
                if cell.text.strip() == 'Float':
                    float_text = cells[index + 1].text.strip().replace(',', '')
                    if float_text.endswith('B'):
                        return int(float(float_text[:-1]) * 1_000_000_000)
                    if float_text.endswith('M'):
                        return int(float(float_text[:-1]) * 1_000_000)
                    if float_text.endswith('K'):
                        return int(float(float_text[:-1]) * 1_000)
    except Exception:
        pass

    return None


def format_float_for_display(float_value):
    if float_value is None:
        return "N/A"
    if float_value >= 1_000_000_000:
        return f"{float_value / 1_000_000_000:.2f}B"
    if float_value >= 1_000_000:
        return f"{float_value / 1_000_000:.2f}M"
    if float_value >= 1_000:
        return f"{float_value / 1_000:.0f}K"
    return str(float_value)


# ======================================================
# News (visibility only)
# ======================================================

def fetch_latest_news_headline(symbol: str):
    try:
        url = (
            f"https://feeds.finance.yahoo.com/rss/2.0/"
            f"headline?s={symbol}&region=US&lang=en-US"
        )
        response = requests.get(url, timeout=5)
        root = ET.fromstring(response.text)
        item = root.find(".//item/title")
        if item is not None:
            return item.text.strip()[:80]
    except Exception:
        pass
    return "-"


# ======================================================
# Main execution
# ======================================================

def main():
    ib = IB()

    print("\n==================")
    print("CONNECTING TO IBKR")
    print("==================")
    ib.connect("127.0.0.1", 7496, clientId=99, timeout=10)
    print("Connected:", ib.isConnected())

    scanner_definition = ScannerSubscription(
        instrument="STK",
        locationCode="STK.US",
        scanCode="TOP_PERC_GAIN",
        numberOfRows=10,
        abovePrice=1,
        belowPrice=60
    )

    scanner_results = ib.reqScannerData(scanner_definition)

    print("\n=========================")
    print(f"SCANNER RESULTS — {len(scanner_results)} ROWS")
    print("=========================")

    print(
        f"{'SYM':<6} "
        f"{'FRI':>7} "
        f"{'THU':>7} "
        f"{'%FRIvsTHU':>12} "
        f"{'RV20':>6} "
        f"{'RV1D':>6} "
        f"{'FLOAT':>8} "
        f"NEWS"
    )
    print("-" * 140)

    for row in scanner_results:
        contract_details = row.contractDetails
        if not contract_details:
            continue

        symbol = contract_details.contract.symbol
        contract = Stock(
            symbol,
            "SMART",
            "USD",
            primaryExchange=contract_details.contract.primaryExchange
        )
        ib.qualifyContracts(contract)

        friday_close, thursday_close = fetch_last_two_session_closes(ib, contract)
        weekend_price_change = calculate_percent_change(friday_close, thursday_close)

        relative_volume_20_day = calculate_relative_volume_vs_20_day_average(ib, contract)
        relative_volume_vs_yesterday = calculate_relative_volume_vs_previous_day(ib, contract)

        float_shares = fetch_float_shares_best_effort(symbol)
        float_display = format_float_for_display(float_shares)

        headline = fetch_latest_news_headline(symbol)

        print(
            f"{symbol:<6} "
            f"{format_price_value(friday_close):>7} "
            f"{format_price_value(thursday_close):>7} "
            f"{format_percentage_value(weekend_price_change):>12} "
            f"{format_ratio_value(relative_volume_20_day):>6} "
            f"{format_ratio_value(relative_volume_vs_yesterday):>6} "
            f"{float_display:>8} "
            f"{headline}"
        )

    ib.disconnect()
    print("\n============")
    print("DISCONNECTED")
    print("============")


if __name__ == "__main__":
    main()
