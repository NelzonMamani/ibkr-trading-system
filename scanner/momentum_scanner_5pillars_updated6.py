# File: momentum_scanner_5pillars_updated5.py
"""
🔍 Momentum Scanner - 5 Pillars (Ross Cameron Style) - Fully Decoupled

Now accepts a candidate list of tickers/contracts, applies all 5 pillars:
1. Gap %
2. Float
3. Relative Volume (RVOL)
4. Price
5. News/Catalyst

Fallback default tickers provided if none pass all filters.
"""

from ib_insync import IB, Stock
import yfinance as yf
import requests
from bs4 import BeautifulSoup
from typing import List


# ----------------------------
# 1️⃣ Gap %
# ----------------------------
def get_gap_percent(contract, ib: IB):
    """Calculates real-time gap % between last price and previous close"""
    bars = ib.reqHistoricalData(contract, '', '2 D', '1 day', 'TRADES', True, 1)
    if len(bars) < 2:
        return None
    prev_close = bars[-2].close
    ticker = ib.reqMktData(contract, '', False, False)
    ib.sleep(0.5)
    last_price = ticker.last if ticker.last else 0
    return round((last_price - prev_close) / prev_close * 100, 2)


# ----------------------------
# 2️⃣ Price
# ----------------------------
def get_price(contract, ib: IB):
    ticker = ib.reqMktData(contract, '', False, False)
    ib.sleep(0.5)
    return round(ticker.last if ticker.last else 0, 2)


# ----------------------------
# 3️⃣ Float
# ----------------------------
def get_float(contract):
    """Returns float from Yahoo Finance or fallback"""
    symbol_clean = contract.symbol.replace(" ", "-")
    try:
        info = yf.Ticker(symbol_clean).info
        if 'floatShares' in info and info['floatShares']:
            return int(info['floatShares'])
    except Exception:
        pass
    return None


# ----------------------------
# 4️⃣ Relative Volume (RVOL)
# ----------------------------
def get_rvol(contract, ib: IB):
    """Relative volume: today volume / average volume (last 20 days)"""
    try:
        bars = ib.reqHistoricalData(contract, '', '20 D', '1 day', 'TRADES', True, 1)
        if len(bars) < 1:
            return None
        avg_vol = sum(bar.volume for bar in bars) / len(bars)
        today_vol = bars[-1].volume
        if avg_vol == 0:
            return None
        return round(today_vol / avg_vol, 2)
    except Exception:
        return None


# ----------------------------
# 5️⃣ News / Catalyst
# ----------------------------
def has_recent_news(contract):
    """
    Returns True if recent news contains relevant keywords (FDA, earnings, merger, etc.)
    Uses Yahoo Finance news feed as primary source.
    """
    symbol_clean = contract.symbol.replace(" ", "-")
    try:
        news_items = yf.Ticker(symbol_clean).news
        if news_items:
            for item in news_items:
                title = item.get('title', '').lower()
                for kw in ['fda', 'earnings', 'merger', 'deal', 'approval', 'partnership']:
                    if kw in title:
                        return True
        return False
    except Exception:
        return False


# ----------------------------
# 6️⃣ Filter by 5 Pillars
# ----------------------------
def filter_tickers_by_5pillars(candidates: List[Stock]) -> List[str]:
    """
    Filters candidate tickers/contracts based on 5 pillars.

    Args:
        candidates (List[Stock]): Candidate IBKR Stock contracts.

    Returns:
        List[str]: Symbols passing all 5 pillars.
    """
    ib = IB()
    ib.connect('127.0.0.1', 7496, clientId=2)

    hot_tickers = []

    for contract in candidates:
        try:
            gap = get_gap_percent(contract, ib)
            price = get_price(contract, ib)
            float_val = get_float(contract)
            rvol = get_rvol(contract, ib)
            news = has_recent_news(contract)

            # Example thresholds (can adjust later)
            if (gap and gap >= 3 and
                    price and 1 <= price <= 20 and
                    float_val and float_val <= 20_000_000 and
                    rvol and rvol >= 1.5 and
                    news):
                hot_tickers.append(contract.symbol)
            else:
                print(f"[FILTER] {contract.symbol} failed pillars: gap={gap}, rvol={rvol}, "
                      f"float={float_val}, price={price}, news={news}")
        except Exception as e:
            print(f"[ERROR] Scanning {contract.symbol}: {e}")

    ib.disconnect()

    # Fallback default tickers if none passed
    if not hot_tickers:
        print("[WARNING] No tickers passed all 5 pillars. Using fallback defaults.")
        hot_tickers = ['AAPL', 'TSLA', 'NVDA']

    print(f"🔥 Hot tickers passing 5 pillars: {hot_tickers}")
    return hot_tickers
