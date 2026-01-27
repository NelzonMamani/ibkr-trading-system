"""
Ross Momentum Stock Selection Scanner (v2 diagnostic)

Derived from: troubleshooting/stock_selection/ross_stock_selection_scanner_v1_2026_01_27_003749_UTC.py
This script preserves v1 columns and appends diagnostic transparency.
"""

from __future__ import annotations

import argparse
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone, time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import xml.etree.ElementTree as ET
import yfinance as yf
from bs4 import BeautifulSoup
from ib_insync import IB, ScannerSubscription, Stock, Ticker


ET_TZ = ZoneInfo("America/New_York")


# ======================================================
# Basic numeric hygiene and formatting
# ======================================================

def sanitize_numeric(value, min_value=None, allow_zero=True):
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


def format_price_value(value):
    value = sanitize_numeric(value, min_value=0, allow_zero=False)
    return "N/A" if value is None else f"{value:.2f}"


def format_percentage_value(value):
    value = sanitize_numeric(value)
    return "N/A" if value is None else f"{value:+.2f}%"


def format_ratio_value(value):
    value = sanitize_numeric(value, min_value=0, allow_zero=False)
    return "N/A" if value is None else f"{value:.2f}"


def format_volume_value(value):
    value = sanitize_numeric(value, min_value=0, allow_zero=False)
    if value is None:
        return "N/A"
    return f"{int(value):d}"


def format_dollar_volume_millions(last_price, volume):
    last_price = sanitize_numeric(last_price, min_value=0, allow_zero=False)
    volume = sanitize_numeric(volume, min_value=0, allow_zero=False)
    if last_price is None or volume is None:
        return "N/A"
    dollar_volume = last_price * volume
    if not math.isfinite(dollar_volume):
        return "N/A"
    return f"{dollar_volume / 1_000_000:.2f}"


def format_float_millions(float_value):
    float_value = sanitize_numeric(float_value, min_value=0, allow_zero=False)
    if float_value is None:
        return "N/A"
    return f"{float_value / 1_000_000:.2f}"


def format_spread_value(value):
    value = sanitize_numeric(value, min_value=0, allow_zero=False)
    return "N/A" if value is None else f"{value:.4f}"


def format_liquidity_shares(value):
    value = sanitize_numeric(value, min_value=0, allow_zero=False)
    return "N/A" if value is None else f"{int(value):d}"


def format_liquidity_usd(value):
    value = sanitize_numeric(value, min_value=0, allow_zero=False)
    return "N/A" if value is None else f"{value:,.0f}"


def calculate_percent_change(current_value, reference_value):
    current_value = sanitize_numeric(current_value)
    reference_value = sanitize_numeric(reference_value, min_value=0, allow_zero=False)
    if current_value is None or reference_value is None:
        return None
    return ((current_value - reference_value) / reference_value) * 100.0


def safe_divide(numerator, denominator):
    numerator = sanitize_numeric(numerator)
    denominator = sanitize_numeric(denominator, min_value=0, allow_zero=False)
    if numerator is None or denominator is None:
        return None
    return numerator / denominator


# ======================================================
# Session label
# ======================================================

def infer_session_label(scan_code: str) -> str:
    if scan_code == "TOP_AFTER_HOURS_PERC_GAIN":
        return "AH"
    now_et = datetime.now(ET_TZ).time()
    regular_start = dt_time(9, 30)
    regular_end = dt_time(16, 0)
    if regular_start <= now_et <= regular_end:
        return "RTH"
    return "PRE"


# ======================================================
# Historical price retrieval (weekend logic)
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


def fetch_last_two_session_closes(daily_bars):
    if not daily_bars or len(daily_bars) < 2:
        return None, None

    most_recent_close = sanitize_numeric(daily_bars[-1].close, min_value=0, allow_zero=False)
    prior_session_close = sanitize_numeric(daily_bars[-2].close, min_value=0, allow_zero=False)

    return most_recent_close, prior_session_close


def derive_current_last_price(ticker: Ticker | None):
    last_price = sanitize_numeric(getattr(ticker, "last", None)) if ticker else None
    if last_price is not None:
        return last_price
    market_price = getattr(ticker, "marketPrice", None) if ticker else None
    if callable(market_price):
        market_price = market_price()
    return sanitize_numeric(market_price)


# ======================================================
# Relative volume calculations
# ======================================================

def calculate_relative_volume_vs_20_day_average(daily_bars, average_window_days: int = 20):
    valid_bars = [b for b in daily_bars if b.volume and b.volume > 0]
    if len(valid_bars) < average_window_days + 1:
        return None

    latest_session = valid_bars[-1]
    prior_sessions = valid_bars[-(average_window_days + 1):-1]

    average_volume = sum(b.volume for b in prior_sessions) / len(prior_sessions)
    if average_volume <= 0:
        return None

    return latest_session.volume / average_volume


def calculate_relative_volume_vs_previous_day(session_volume, daily_bars):
    if session_volume is None or not daily_bars or len(daily_bars) < 2:
        return None

    previous_day_volume = sanitize_numeric(daily_bars[-2].volume, min_value=0, allow_zero=False)
    if previous_day_volume is None:
        return None

    return session_volume / previous_day_volume


# ======================================================
# Session volume (best-effort)
# ======================================================

def fetch_session_volume_best_effort(ib: IB, contract: Stock, req_id_symbol_map):
    ticker = None
    try:
        ticker = ib.reqMktData(contract, "", snapshot=True, regulatorySnapshot=False)
        if ticker is not None and hasattr(ticker, "reqId"):
            req_id_symbol_map[ticker.reqId] = contract.symbol
        ib.sleep(1)
        volume = getattr(ticker, "volume", None)
        return sanitize_numeric(volume, min_value=0, allow_zero=False), ticker
    except Exception:
        return None, None
    finally:
        if ticker is not None:
            ib.cancelMktData(contract)


# ======================================================
# Float retrieval (best-effort)
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
# News (visibility only)
# ======================================================

def has_recent_news(symbol: str) -> bool:
    try:
        url = (
            "https://feeds.finance.yahoo.com/rss/2.0/"
            f"headline?s={symbol}&region=US&lang=en-US"
        )
        response = requests.get(url, timeout=5)
        root = ET.fromstring(response.text)
        item = root.find(".//item/title")
        return item is not None and item.text is not None and item.text.strip() != ""
    except Exception:
        return False


# ======================================================
# Diagnostic helpers
# ======================================================

def classify_exchange(primary_exchange: str | None) -> str:
    if not primary_exchange:
        return "N/A"
    exchange = primary_exchange.upper()
    if exchange in {"NASDAQ", "NSDQ", "ISLAND"}:
        return "NASDAQ"
    if exchange in {"NYSE", "ARCA", "NYSEARCA"}:
        return "NYSE"
    if exchange in {"AMEX", "ASE", "MKT"}:
        return "AMEX"
    if exchange.startswith("OTC") or exchange in {"OTCMKT", "OTCQB", "OTCQX"}:
        return "OTC"
    if exchange.startswith("PINK"):
        return "PINK"
    return "N/A"


def derive_spread_metrics(ticker: Ticker, last_price: float | None):
    bid = sanitize_numeric(getattr(ticker, "bid", None), min_value=0, allow_zero=False)
    ask = sanitize_numeric(getattr(ticker, "ask", None), min_value=0, allow_zero=False)
    if bid is None or ask is None:
        return None, None
    spread_abs = ask - bid
    spread_pct = None
    if last_price is not None:
        spread_pct = safe_divide(spread_abs, last_price)
        if spread_pct is not None:
            spread_pct *= 100.0
    return spread_abs, spread_pct


def derive_liquidity_metrics(ticker: Ticker, last_price: float | None):
    bid_size = sanitize_numeric(getattr(ticker, "bidSize", None), min_value=0, allow_zero=False)
    ask_size = sanitize_numeric(getattr(ticker, "askSize", None), min_value=0, allow_zero=False)
    if bid_size is None or ask_size is None:
        return None, None
    liq_shares_min = min(bid_size, ask_size)
    liq_usd_min = None
    if last_price is not None:
        liq_usd_min = liq_shares_min * last_price
    return liq_shares_min, liq_usd_min


def derive_data_mode(ticker: Ticker | None, error_flags: set[str]):
    market_data_type = getattr(ticker, "marketDataType", None) if ticker else None
    if market_data_type is None:
        return "MISSING"
    if error_flags:
        return "MIXED"
    if market_data_type in {1, 2}:
        return "LIVE"
    if market_data_type in {3, 4}:
        return "DELAYED"
    return "MISSING"


def derive_subscription_ok(ticker: Ticker | None, error_flags: set[str]):
    if "354" in error_flags:
        return "N"
    has_any_data = False
    if ticker is not None:
        has_any_data = any(
            sanitize_numeric(getattr(ticker, attr, None)) is not None
            for attr in ("last", "close", "volume", "bid", "ask")
        )
    return "Y" if has_any_data else "N"


def derive_halted_flag(ticker: Ticker | None):
    halted_value = getattr(ticker, "halted", None) if ticker else None
    if halted_value is None:
        return "N/A"
    return "Y" if halted_value == 1 else "N"


def derive_ssr_flag(ticker: Ticker | None):
    shortable_shares = getattr(ticker, "shortableShares", None) if ticker else None
    if shortable_shares is None:
        return "N/A"
    return "Y" if shortable_shares == 0 else "N"


# ======================================================
# Output handling
# ======================================================

def build_output_path(run_timestamp_utc: str) -> Path:
    output_dir = Path("troubleshooting/stock_selection/output")
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"ross_stock_selection_v2_1_{run_timestamp_utc}.txt"
    return output_dir / filename


def emit_line(line, output_lines):
    print(line)
    output_lines.append(line)


@dataclass
class ScannerRow:
    symbol: str
    session: str
    last: float | None
    prior: float | None
    percent_change: float | None
    volume: float | None
    dollar_volume_m: str
    rv20: float | None
    rv1d: float | None
    float_shares: int | None
    float_m: str
    news_flag: str
    spread_abs: float | None
    spread_pct: float | None
    liq_shares_min: float | None
    liq_usd_min: float | None
    data_mode: str
    subscription_ok: str
    ibkr_error_flags: str
    exchange_class: str
    halted: str
    ssr: str
    cur_last: float | None
    ref_close_rth: float | None
    ibkr_chg_pct: float | None
    calc_gap_pct: float | None
    pct_source: str


# ======================================================
# Main execution
# ======================================================

def parse_args():
    parser = argparse.ArgumentParser(description="Ross Momentum Stock Selection Scanner (Diagnostic)")
    parser.add_argument(
        "--after-hours",
        action="store_true",
        help="Use TOP_AFTER_HOURS_PERC_GAIN scan code",
    )
    return parser.parse_args()


def build_scanner_subscription(scan_code: str) -> ScannerSubscription:
    return ScannerSubscription(
        instrument="STK",
        locationCode="STK.US",
        scanCode=scan_code,
        numberOfRows=50,
        abovePrice=1.0,
        belowPrice=20.0,
    )


def passes_ross_display_gates(row: ScannerRow, session_label: str) -> bool:
    min_price = 1.0
    max_price = 20.0
    min_pct_change = 10.0
    min_rvol = 5.0
    max_float = 20_000_000
    min_volume = 1_000_000 if session_label == "RTH" else 100_000

    if row.last is None or not (min_price <= row.last <= max_price):
        return False
    if row.percent_change is None or row.percent_change < min_pct_change:
        return False
    if row.rv20 is None or row.rv20 < min_rvol:
        return False
    if row.float_shares is None:
        return False
    if row.float_shares > max_float:
        return False
    if row.volume is None or row.volume < min_volume:
        return False
    return True


def main():
    args = parse_args()
    scan_code = "TOP_AFTER_HOURS_PERC_GAIN" if args.after_hours else "TOP_PERC_GAIN"

    ib = IB()
    output_lines = []
    run_timestamp = datetime.now(timezone.utc)
    run_timestamp_label = run_timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    run_timestamp_filename = run_timestamp.strftime("%Y_%m_%d_%H%M%S_UTC")
    session_label = infer_session_label(scan_code)

    ibkr_host = "127.0.0.1"
    ibkr_port = 7496
    ibkr_client_id = 99

    error_flags_by_symbol: dict[str, set[str]] = defaultdict(set)
    req_id_symbol_map: dict[int, str] = {}

    def on_ib_error(req_id, error_code, error_string, contract):
        symbol = None
        if contract is not None and getattr(contract, "symbol", None):
            symbol = contract.symbol
        elif req_id in req_id_symbol_map:
            symbol = req_id_symbol_map[req_id]
        if symbol:
            error_flags_by_symbol[symbol].add(str(error_code))

    ib.errorEvent += on_ib_error

    emit_line("\n==================", output_lines)
    emit_line("CONNECTING TO IBKR", output_lines)
    emit_line("==================", output_lines)
    ib.connect(ibkr_host, ibkr_port, clientId=ibkr_client_id, timeout=10)
    emit_line(f"Connected: {ib.isConnected()}", output_lines)

    scanner_definition = build_scanner_subscription(scan_code)
    scanner_results = ib.reqScannerData(scanner_definition)

    emit_line("\n=========================", output_lines)
    emit_line(f"SCANNER RESULTS — {len(scanner_results)} ROWS", output_lines)
    emit_line("=========================", output_lines)
    emit_line("RUN HEADER", output_lines)
    emit_line(f"Script Filename: {Path(__file__).name}", output_lines)
    emit_line("Version: v2.1", output_lines)
    emit_line(f"Run Timestamp (UTC): {run_timestamp_label}", output_lines)
    emit_line(f"Market Session: {session_label}", output_lines)
    emit_line(
        "NOTE: %CHG aligns to PRE/AH gap vs last RTH close using current price.",
        output_lines,
    )
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
    emit_line(
        "Derived From: ross_stock_selection_scanner_v1_2026_01_27_003749_UTC.py",
        output_lines,
    )
    emit_line("-------------------------", output_lines)
    emit_line(
        f"{'SYM':<6} "
        f"{'SESS':<6} "
        f"{'LAST':>7} "
        f"{'PRIOR':>7} "
        f"{'%CHG':>8} "
        f"{'VOL':>10} "
        f"{'$VOL(M)':>8} "
        f"{'RV20':>6} "
        f"{'RV1D':>6} "
        f"{'FLOAT(M)':>9} "
        f"{'NEWS?':>6} "
        f"{'SPREAD_ABS':>10} "
        f"{'SPREAD_PCT':>10} "
        f"{'LIQ_SHARES_MIN':>14} "
        f"{'LIQ_USD_MIN':>12} "
        f"{'DATA_MODE':>10} "
        f"{'SUBSCRIPTION_OK':>16} "
        f"{'IBKR_ERROR_FLAGS':>18} "
        f"{'EXCHANGE_CLASS':>15} "
        f"{'HALTED':>8} "
        f"{'SSR':>6} "
        f"{'CUR_LAST':>9} "
        f"{'REF_CLOSE_RTH':>14} "
        f"{'IBKR_CHG_PCT':>13} "
        f"{'CALC_GAP_PCT':>13} "
        f"{'PCT_SOURCE':>10}",
        output_lines,
    )
    emit_line("-" * 286, output_lines)

    rows: list[ScannerRow] = []

    for row in scanner_results:
        contract_details = row.contractDetails
        contract = None
        symbol = None
        primary_exchange = None
        if contract_details:
            symbol = contract_details.contract.symbol
            primary_exchange = contract_details.contract.primaryExchange
            contract = Stock(
                symbol,
                "SMART",
                "USD",
                primaryExchange=primary_exchange,
            )
            ib.qualifyContracts(contract)
        elif getattr(row, "contract", None):
            symbol = row.contract.symbol
            contract = Stock(symbol, "SMART", "USD")
            ib.qualifyContracts(contract)

        if not symbol:
            continue

        daily_bars = fetch_daily_bars(ib, contract, duration_days=30) if contract else []
        last_close, prior_close = fetch_last_two_session_closes(daily_bars)
        ref_close_rth = last_close

        relative_volume_20_day = calculate_relative_volume_vs_20_day_average(daily_bars)
        session_volume, ticker = (
            fetch_session_volume_best_effort(ib, contract, req_id_symbol_map)
            if contract
            else (None, None)
        )
        relative_volume_vs_yesterday = calculate_relative_volume_vs_previous_day(
            session_volume,
            daily_bars,
        )

        float_shares = fetch_float_shares_best_effort(symbol)
        news_flag = "Y" if has_recent_news(symbol) else "N"

        cur_last = derive_current_last_price(ticker)
        spread_abs, spread_pct = derive_spread_metrics(ticker, cur_last)
        liq_shares_min, liq_usd_min = derive_liquidity_metrics(ticker, cur_last)
        ibkr_chg_pct = sanitize_numeric(getattr(ticker, "changePercent", None)) if ticker else None
        calc_gap_pct = calculate_percent_change(cur_last, ref_close_rth)
        pct_source = "N/A"
        if ibkr_chg_pct is not None:
            percent_change = ibkr_chg_pct
            pct_source = "IBKR"
        else:
            percent_change = calc_gap_pct
            if calc_gap_pct is not None:
                pct_source = "CALC"
        if session_label == "RTH" and ibkr_chg_pct is None:
            percent_change = calculate_percent_change(last_close, prior_close)
        error_flags = error_flags_by_symbol.get(symbol, set())
        data_mode = derive_data_mode(ticker, error_flags)
        subscription_ok = derive_subscription_ok(ticker, error_flags)
        exchange_class = classify_exchange(primary_exchange)
        halted_flag = derive_halted_flag(ticker)
        ssr_flag = derive_ssr_flag(ticker)

        ibkr_error_flags = "N/A"
        if error_flags:
            ibkr_error_flags = "|".join(sorted(error_flags))

        rows.append(
            ScannerRow(
                symbol=symbol,
                session=session_label,
                last=last_close,
                prior=prior_close,
                percent_change=percent_change,
                volume=session_volume,
                dollar_volume_m=format_dollar_volume_millions(last_close, session_volume),
                rv20=relative_volume_20_day,
                rv1d=relative_volume_vs_yesterday,
                float_shares=float_shares,
                float_m=format_float_millions(float_shares),
                news_flag=news_flag,
                spread_abs=spread_abs,
                spread_pct=spread_pct,
                liq_shares_min=liq_shares_min,
                liq_usd_min=liq_usd_min,
                data_mode=data_mode,
                subscription_ok=subscription_ok,
                ibkr_error_flags=ibkr_error_flags,
                exchange_class=exchange_class,
                halted=halted_flag,
                ssr=ssr_flag,
                cur_last=cur_last,
                ref_close_rth=ref_close_rth,
                ibkr_chg_pct=ibkr_chg_pct,
                calc_gap_pct=calc_gap_pct,
                pct_source=pct_source,
            )
        )

    rows_sorted = sorted(
        rows,
        key=lambda r: (r.percent_change is None, -(r.percent_change or 0)),
    )

    for row in rows_sorted:
        emit_line(
            f"{row.symbol:<6} "
            f"{row.session:<6} "
            f"{format_price_value(row.last):>7} "
            f"{format_price_value(row.prior):>7} "
            f"{format_percentage_value(row.percent_change):>8} "
            f"{format_volume_value(row.volume):>10} "
            f"{row.dollar_volume_m:>8} "
            f"{format_ratio_value(row.rv20):>6} "
            f"{format_ratio_value(row.rv1d):>6} "
            f"{row.float_m:>9} "
            f"{row.news_flag:>6} "
            f"{format_spread_value(row.spread_abs):>10} "
            f"{format_percentage_value(row.spread_pct):>10} "
            f"{format_liquidity_shares(row.liq_shares_min):>14} "
            f"{format_liquidity_usd(row.liq_usd_min):>12} "
            f"{row.data_mode:>10} "
            f"{row.subscription_ok:>16} "
            f"{row.ibkr_error_flags:>18} "
            f"{row.exchange_class:>15} "
            f"{row.halted:>8} "
            f"{row.ssr:>6} "
            f"{format_price_value(row.cur_last):>9} "
            f"{format_price_value(row.ref_close_rth):>14} "
            f"{format_percentage_value(row.ibkr_chg_pct):>13} "
            f"{format_percentage_value(row.calc_gap_pct):>13} "
            f"{row.pct_source:>10}",
            output_lines,
        )

    ibkr_count = sum(1 for row in rows_sorted if row.ibkr_chg_pct is not None)
    calc_count = sum(1 for row in rows_sorted if row.calc_gap_pct is not None)
    diffs = [
        abs(row.ibkr_chg_pct - row.calc_gap_pct)
        for row in rows_sorted
        if row.ibkr_chg_pct is not None and row.calc_gap_pct is not None
    ]
    top_diffs = sorted(diffs, reverse=True)[:5]

    emit_line("", output_lines)
    emit_line("DIAGNOSTIC SUMMARY", output_lines)
    emit_line(f"IBKR_CHG_PCT present: {ibkr_count}", output_lines)
    emit_line(f"CALC_GAP_PCT present: {calc_count}", output_lines)
    if top_diffs:
        emit_line("Top 5 |IBKR - CALC| diffs:", output_lines)
        for diff in top_diffs:
            emit_line(f"  {diff:.2f}%", output_lines)
    else:
        emit_line("Top 5 |IBKR - CALC| diffs: N/A", output_lines)

    emit_line("", output_lines)
    emit_line(
        "FILTERED VIEW — TOP 15 (DISPLAY ONLY, NO DATA REMOVAL)",
        output_lines,
    )
    emit_line("Purpose: visual explanation only.", output_lines)
    emit_line("-" * 286, output_lines)

    filtered_rows = [row for row in rows_sorted if passes_ross_display_gates(row, session_label)]
    for row in filtered_rows[:15]:
        emit_line(
            f"{row.symbol:<6} "
            f"{row.session:<6} "
            f"{format_price_value(row.last):>7} "
            f"{format_price_value(row.prior):>7} "
            f"{format_percentage_value(row.percent_change):>8} "
            f"{format_volume_value(row.volume):>10} "
            f"{row.dollar_volume_m:>8} "
            f"{format_ratio_value(row.rv20):>6} "
            f"{format_ratio_value(row.rv1d):>6} "
            f"{row.float_m:>9} "
            f"{row.news_flag:>6} "
            f"{format_spread_value(row.spread_abs):>10} "
            f"{format_percentage_value(row.spread_pct):>10} "
            f"{format_liquidity_shares(row.liq_shares_min):>14} "
            f"{format_liquidity_usd(row.liq_usd_min):>12} "
            f"{row.data_mode:>10} "
            f"{row.subscription_ok:>16} "
            f"{row.ibkr_error_flags:>18} "
            f"{row.exchange_class:>15} "
            f"{row.halted:>8} "
            f"{row.ssr:>6} "
            f"{format_price_value(row.cur_last):>9} "
            f"{format_price_value(row.ref_close_rth):>14} "
            f"{format_percentage_value(row.ibkr_chg_pct):>13} "
            f"{format_percentage_value(row.calc_gap_pct):>13} "
            f"{row.pct_source:>10}",
            output_lines,
        )

    ib.disconnect()
    emit_line("\n============", output_lines)
    emit_line("DISCONNECTED", output_lines)
    emit_line("============", output_lines)

    output_path = build_output_path(run_timestamp_filename)
    output_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
