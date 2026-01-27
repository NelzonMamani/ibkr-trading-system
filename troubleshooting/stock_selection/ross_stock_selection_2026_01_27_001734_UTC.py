# ross_stock_selection_2026_01_27_001734_UTC.py

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import requests
import xml.etree.ElementTree as ET
import yfinance as yf
from bs4 import BeautifulSoup
from ib_insync import IB, ScannerSubscription, Stock, Ticker


# ======================================================
# Configuration
# ======================================================

EASTERN_TZ = ZoneInfo("America/New_York")
REGULAR_START = time(9, 30)


# ======================================================
# Basic numeric hygiene and formatting
# ======================================================

def sanitize_numeric(value, min_value: Optional[float] = None, allow_zero: bool = True):
    if value is None:
        return None
    if isinstance(value, (int, float)) and not math.isfinite(value):
        return None
    if isinstance(value, (int, float)) and min_value is not None:
        if allow_zero and value < min_value:
            return None
        if not allow_zero and value <= min_value:
            return None
    return value


def safe_divide(numerator, denominator):
    numerator = sanitize_numeric(numerator)
    denominator = sanitize_numeric(denominator, min_value=0, allow_zero=False)
    if numerator is None or denominator is None:
        return None
    return numerator / denominator


def format_price_value(value):
    value = sanitize_numeric(value, min_value=0, allow_zero=False)
    return "N/A" if value is None else f"{value:.2f}"


def format_percentage_value(value):
    value = sanitize_numeric(value)
    return "N/A" if value is None else f"{value:+.2f}%"


def format_ratio_value(value):
    value = sanitize_numeric(value, min_value=0, allow_zero=True)
    return "N/A" if value is None else f"{value:.2f}"


def format_volume_value(value):
    value = sanitize_numeric(value, min_value=0, allow_zero=True)
    return "N/A" if value is None else f"{int(value):,}"


def format_dollar_volume_millions(price, volume):
    price = sanitize_numeric(price, min_value=0, allow_zero=False)
    volume = sanitize_numeric(volume, min_value=0, allow_zero=True)
    if price is None or volume is None:
        return "N/A"
    dollar_volume = (price * volume) / 1_000_000
    return "N/A" if not math.isfinite(dollar_volume) else f"{dollar_volume:.2f}"


def format_float_millions(float_shares):
    float_shares = sanitize_numeric(float_shares, min_value=0, allow_zero=False)
    if float_shares is None:
        return "N/A"
    return f"{float_shares / 1_000_000:.2f}"


def calculate_percent_change(current_value, reference_value):
    current_value = sanitize_numeric(current_value)
    reference_value = sanitize_numeric(reference_value, min_value=0, allow_zero=False)
    if current_value is None or reference_value is None:
        return None
    return ((current_value - reference_value) / reference_value) * 100.0


# ======================================================
# Session determination
# ======================================================

def infer_session(scan_code: str, now_et: datetime) -> str:
    if scan_code == "TOP_AFTER_HOURS_PERC_GAIN":
        return "AFTER"
    local_time = now_et.time()
    if local_time < REGULAR_START:
        return "PRE"
    return "REG"


# ======================================================
# Historical price retrieval (daily bars)
# ======================================================

def fetch_daily_bars(ib: IB, contract: Stock, duration_days: int):
    return ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr=f"{duration_days} D",
        barSizeSetting="1 day",
        whatToShow="TRADES",
        useRTH=True,
    )


def fetch_most_recent_close(daily_bars):
    if not daily_bars:
        return None
    return sanitize_numeric(daily_bars[-1].close, min_value=0, allow_zero=False)


# ======================================================
# Relative volume calculations
# ======================================================

def calculate_average_volume(daily_bars, average_window_days: int = 20):
    valid_bars = [b for b in daily_bars if b.volume and b.volume > 0]
    if len(valid_bars) < average_window_days:
        return None
    prior_sessions = valid_bars[-average_window_days:]
    average_volume = sum(b.volume for b in prior_sessions) / len(prior_sessions)
    if average_volume <= 0:
        return None
    return average_volume


# ======================================================
# Float retrieval (best-effort, diagnostic)
# ======================================================

def fetch_float_shares_best_effort(symbol: str):
    cleaned_symbol = symbol.replace(" ", "-")

    try:
        ticker = yf.Ticker(cleaned_symbol)
        info = ticker.info
        if "floatShares" in info and info["floatShares"]:
            return int(info["floatShares"])
    except Exception:
        pass

    try:
        url = f"https://finviz.com/quote.ashx?t={cleaned_symbol}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.content, "html.parser")
        table = soup.find("table", class_="snapshot-table2")
        if table:
            cells = table.find_all("td")
            for index, cell in enumerate(cells):
                if cell.text.strip() == "Float":
                    float_text = cells[index + 1].text.strip().replace(",", "")
                    if float_text.endswith("B"):
                        return int(float(float_text[:-1]) * 1_000_000_000)
                    if float_text.endswith("M"):
                        return int(float(float_text[:-1]) * 1_000_000)
                    if float_text.endswith("K"):
                        return int(float(float_text[:-1]) * 1_000)
    except Exception:
        pass

    return None


# ======================================================
# News (headline presence only)
# ======================================================

def has_recent_news_headline(symbol: str) -> bool:
    try:
        url = (
            "https://feeds.finance.yahoo.com/rss/2.0/"
            f"headline?s={symbol}&region=US&lang=en-US"
        )
        response = requests.get(url, timeout=5)
        root = ET.fromstring(response.text)
        item = root.find(".//item/title")
        return item is not None and item.text is not None
    except Exception:
        return False


# ======================================================
# Output handling
# ======================================================

def build_output_path(run_timestamp_utc: str) -> Path:
    output_dir = Path("troubleshooting/stock_selection/output")
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"ross_stock_selection_{run_timestamp_utc}.txt"
    return output_dir / filename


def emit_line(line: str, output_lines: list[str]):
    print(line)
    output_lines.append(line)


@dataclass
class ScannerRowFacts:
    symbol: str
    session: str
    last: Optional[float]
    prior: Optional[float]
    percent_change: Optional[float]
    volume: Optional[float]
    dollar_volume_m: str
    rv20: Optional[float]
    rv1d: Optional[float]
    float_m: str
    news_flag: str


# ======================================================
# Main execution
# ======================================================

def build_scanner_subscription(scan_code: str) -> ScannerSubscription:
    return ScannerSubscription(
        instrument="STK",
        locationCode="STK.US",
        scanCode=scan_code,
        numberOfRows=10,
        abovePrice=1.0,
        belowPrice=20.0,
    )


def resolve_session_volume(ticker: Ticker) -> Optional[float]:
    if ticker.volume is not None:
        return sanitize_numeric(ticker.volume, min_value=0, allow_zero=True)
    return sanitize_numeric(getattr(ticker, "rtVolume", None), min_value=0, allow_zero=True)


def build_row_facts(
    symbol: str,
    session: str,
    ticker: Ticker,
    daily_bars,
) -> ScannerRowFacts:
    last_price = sanitize_numeric(ticker.last, min_value=0, allow_zero=False)
    prior_close = fetch_most_recent_close(daily_bars)
    percent_change = calculate_percent_change(last_price, prior_close)

    session_volume = resolve_session_volume(ticker)
    dollar_volume_m = format_dollar_volume_millions(last_price, session_volume)

    avg_volume_20d = calculate_average_volume(daily_bars, average_window_days=20)
    rv20 = safe_divide(session_volume, avg_volume_20d)

    previous_day_volume = sanitize_numeric(
        daily_bars[-1].volume if daily_bars else None, min_value=0, allow_zero=False
    )
    rv1d = safe_divide(session_volume, previous_day_volume)

    float_shares = fetch_float_shares_best_effort(symbol)
    float_m = format_float_millions(float_shares)

    news_flag = "Y" if has_recent_news_headline(symbol) else "N"

    return ScannerRowFacts(
        symbol=symbol,
        session=session,
        last=last_price,
        prior=prior_close,
        percent_change=percent_change,
        volume=session_volume,
        dollar_volume_m=dollar_volume_m,
        rv20=rv20,
        rv1d=rv1d,
        float_m=float_m,
        news_flag=news_flag,
    )


def format_row(row: ScannerRowFacts) -> str:
    return (
        f"{row.symbol:<6} "
        f"{row.session:>4} "
        f"{format_price_value(row.last):>7} "
        f"{format_price_value(row.prior):>7} "
        f"{format_percentage_value(row.percent_change):>9} "
        f"{format_volume_value(row.volume):>10} "
        f"{row.dollar_volume_m:>9} "
        f"{format_ratio_value(row.rv20):>6} "
        f"{format_ratio_value(row.rv1d):>6} "
        f"{row.float_m:>9} "
        f"{row.news_flag:>5}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Ross Momentum stock selection scanner")
    parser.add_argument(
        "--after-hours",
        action="store_true",
        help="Use TOP_AFTER_HOURS_PERC_GAIN and mark session as AFTER",
    )
    args = parser.parse_args()

    scan_code = "TOP_AFTER_HOURS_PERC_GAIN" if args.after_hours else "TOP_PERC_GAIN"

    ib = IB()
    output_lines: list[str] = []
    run_timestamp = datetime.now(timezone.utc)
    run_timestamp_label = run_timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    run_timestamp_filename = run_timestamp.strftime("%Y_%m_%d_%H%M%S_UTC")

    ibkr_host = "127.0.0.1"
    ibkr_port = 7496
    ibkr_client_id = 99

    emit_line("\n==================", output_lines)
    emit_line("CONNECTING TO IBKR", output_lines)
    emit_line("==================", output_lines)
    ib.connect(ibkr_host, ibkr_port, clientId=ibkr_client_id, timeout=10)
    emit_line(f"Connected: {ib.isConnected()}", output_lines)

    scanner_definition = build_scanner_subscription(scan_code)
    scanner_results = ib.reqScannerData(scanner_definition)

    now_et = datetime.now(timezone.utc).astimezone(EASTERN_TZ)
    session_label = infer_session(scan_code, now_et)

    emit_line("\n=========================", output_lines)
    emit_line(f"SCANNER RESULTS — {len(scanner_results)} ROWS", output_lines)
    emit_line("=========================", output_lines)
    emit_line("RUN HEADER", output_lines)
    emit_line(f"Run Timestamp (UTC): {run_timestamp_label}", output_lines)
    emit_line(
        f"IBKR Connection: host={ibkr_host} port={ibkr_port} clientId={ibkr_client_id}",
        output_lines,
    )
    emit_line(
        "Scanner Definition: "
        f"scanCode={scanner_definition.scanCode} "
        f"abovePrice={scanner_definition.abovePrice} "
        f"belowPrice={scanner_definition.belowPrice} "
        f"rows={scanner_definition.numberOfRows}",
        output_lines,
    )
    emit_line(f"Session Inference: {session_label} (ET {now_et:%H:%M})", output_lines)
    emit_line("-------------------------", output_lines)
    emit_line(
        f"{'SYM':<6} "
        f"{'SESS':>4} "
        f"{'LAST':>7} "
        f"{'PRIOR':>7} "
        f"{'%CHG':>9} "
        f"{'VOL':>10} "
        f"{'$VOL(M)':>9} "
        f"{'RV20':>6} "
        f"{'RV1D':>6} "
        f"{'FLOAT(M)':>9} "
        f"{'NEWS?':>5}",
        output_lines,
    )
    emit_line("-" * 140, output_lines)

    contracts: list[Stock] = []
    symbols: list[str] = []

    for row in scanner_results:
        contract_details = row.contractDetails
        if not contract_details:
            continue
        symbol = contract_details.contract.symbol
        contract = Stock(
            symbol,
            "SMART",
            "USD",
            primaryExchange=contract_details.contract.primaryExchange,
        )
        contracts.append(contract)
        symbols.append(symbol)

    if contracts:
        ib.qualifyContracts(*contracts)
        tickers = {t.contract.symbol: t for t in ib.reqTickers(*contracts)}
    else:
        tickers = {}

    for symbol, contract in zip(symbols, contracts):
        ticker = tickers.get(symbol)
        if ticker is None:
            continue
        daily_bars = fetch_daily_bars(ib, contract, duration_days=30)
        row_facts = build_row_facts(symbol, session_label, ticker, daily_bars)
        emit_line(format_row(row_facts), output_lines)

    ib.disconnect()
    emit_line("\n============", output_lines)
    emit_line("DISCONNECTED", output_lines)
    emit_line("============", output_lines)

    output_path = build_output_path(run_timestamp_filename)
    output_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
