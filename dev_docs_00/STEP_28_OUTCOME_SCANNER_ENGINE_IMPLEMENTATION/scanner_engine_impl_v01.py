# File: scanner_engine_impl_v01.py
# Created: 2025-12-16
# Version Notes:
# - v01: Minimal working Scanner implementation using registries + print contract + formatter.

"""
SCANNER ENGINE IMPLEMENTATION (MINIMAL WORKING, DRY-RUN SAFE)
-------------------------------------------------------------

WHAT THIS FILE DOES
-------------------
This file implements a *minimal working* Market Scanner that can:
- fetch market snapshots from a DataSourceRegistry (primary + fallbacks)
- fetch news context from a NewsSourceRegistry
- build a per-symbol payload that matches the frozen Scanner Print Contract
- validate contract completeness
- format and print results for the trader's eyes

WHY THIS FILE EXISTS
--------------------
Yesterday's pain point was: "We cannot trust what is printed unless we have a frozen contract."
This file is the bridge between:
- contract (Step 26)
- formatter (Step 27)
- real scanner behavior

HOW IT WORKS (HIGH LEVEL)
-------------------------
Market → (DataSourceRegistry) → market snapshot
News   → (NewsSourceRegistry) → news snapshot
Then we normalize into a single dict that includes ALL contract fields.
Then:
- validate payload fields exist
- print formatted output

DEPENDENCIES
------------
- data_source_registry_v01.py
- news_source_registry_v01.py
- scanner_print_contract_v01.py
- scanner_print_formatter_v01.py

INPUTS / OUTPUTS
----------------
Inputs:
- list of symbols (demo list by default)
Outputs:
- prints per symbol
- returns list[dict] payloads for downstream modules

TRADING MODE
------------
Observation only. Safe dry-run. No broker calls.

TEACHING NOTE
-------------
This file is intentionally conservative:
- we prefer explicit N/A over guessing
- we log what we know and what we don't know
"""

# ================================
# 1. Imports + Setup
# ================================

from datetime import datetime
from typing import Dict, List, Optional

from data_source_registry_v01 import DataSourceRegistry, MarketDataProvider
from news_source_registry_v01 import NewsSourceRegistry, NewsProvider

from scanner_print_contract_v01 import (
    SCANNER_PRINT_FIELDS_ORDERED,
    validate_scanner_print_payload,
)
from scanner_print_formatter_v01 import ScannerPrintFormatter


# ================================
# 2. Demo Providers (Safe Placeholders)
# ================================

class DemoMarketDataProvider(MarketDataProvider):
    """
    DemoMarketDataProvider
    ---------------------
    A safe placeholder provider to prove the scanner pipeline works end-to-end.

    TEACHING NOTE:
    This provider returns static data. It's not "correct market data" — it's a test harness.
    """
    provider_name = "DEMO_MARKET"

    def fetch(self, symbol: str) -> Dict:
        # Minimal plausible snapshot fields (everything else can become N/A)
        return {
            "symbol": symbol,
            "current_price": 4.25,
            "previous_close_price": 3.78,
            "bid_price": 4.24,
            "ask_price": 4.26,
            "float_shares": 12_300_000,
            "relative_volume": 5.2,
            "volume_spike": True,
        }


class DemoNewsProvider(NewsProvider):
    """
    DemoNewsProvider
    ---------------
    Safe placeholder news provider.

    TEACHING NOTE:
    The scanner cares about:
    - recency (headline age)
    - velocity (10m)
    - regions (global awareness)
    - raw URLs (click-through)
    """
    provider_name = "DEMO_NEWS"

    def fetch(self, symbol: str) -> List[Dict]:
        now = datetime.utcnow().isoformat()
        return [
            {
                "headline_text": f"{symbol} demo headline (release)",
                "published_timestamp": now,
                "source_name": "DemoWire",
                "region": "US",
                "credibility_tier": "HIGH",
                "url": f"https://example.com/{symbol}/demo1",
                "symbol_mentions": [symbol],
            },
            {
                "headline_text": f"{symbol} demo headline (follow-up)",
                "published_timestamp": now,
                "source_name": "DemoWire",
                "region": "UK",
                "credibility_tier": "HIGH",
                "url": f"https://example.com/{symbol}/demo2",
                "symbol_mentions": [symbol],
            },
        ]


# ================================
# 3. Scanner Engine Implementation
# ================================

class ScannerEngineImpl:
    """
    ScannerEngineImpl
    -----------------
    Minimal working scanner that produces contract-compliant payloads and prints them.

    DESIGN RULE:
    If we cannot populate a field confidently, we still include it and mark it N/A.
    """

    def __init__(
        self,
        data_registry: Optional[DataSourceRegistry] = None,
        news_registry: Optional[NewsSourceRegistry] = None,
    ):
        self.data_registry = data_registry or self._build_default_data_registry()
        self.news_registry = news_registry or self._build_default_news_registry()
        self.formatter = ScannerPrintFormatter()

    # ----------------------------
    # Registry Builders
    # ----------------------------

    def _build_default_data_registry(self) -> DataSourceRegistry:
        registry = DataSourceRegistry()
        registry.register_provider(DemoMarketDataProvider())
        return registry

    def _build_default_news_registry(self) -> NewsSourceRegistry:
        registry = NewsSourceRegistry()
        registry.register_provider(DemoNewsProvider())
        return registry

    # ----------------------------
    # Public API
    # ----------------------------

    def run_scan(self, symbols: Optional[List[str]] = None) -> List[Dict]:
        """
        Run a minimal scan over provided symbols.

        Parameters
        ----------
        symbols : list[str] | None
            Symbols to scan. If None, uses a small demo list.

        Returns
        -------
        list[dict]
            Contract-compliant scanner payloads (one per symbol).
        """
        symbols = symbols or ["DEMO", "RYM"]
        results: List[Dict] = []

        self._log(f"Starting scan for {len(symbols)} symbol(s)")

        for sym in symbols:
            payload = self._build_symbol_payload(sym)
            payload = self._normalize_payload(payload)

            missing = validate_scanner_print_payload(payload)
            if missing:
                # We do NOT hide this. Missing contract fields means our pipeline is wrong.
                self._log(f"[WARN] Contract missing fields for {sym}: {missing}")

            print(self.formatter.format(payload))
            print()  # visual separation between symbols

            results.append(payload)

        self._log("Scan finished")
        return results

    # ----------------------------
    # Payload Construction
    # ----------------------------

    def _build_symbol_payload(self, symbol: str) -> Dict:
        """
        Build the raw payload from market + news.

        TEACHING NOTE:
        This is where "market reality" becomes "structured observation".
        """
        market = self.data_registry.fetch_market_data(symbol)
        news = self.news_registry.fetch_news(symbol)

        # Minimal derived metrics (safe, deterministic)
        bid = market["data"].get("bid_price")
        ask = market["data"].get("ask_price")
        prev_close = market["data"].get("previous_close_price")
        last = market["data"].get("current_price")

        spread = (ask - bid) if (isinstance(ask, (int, float)) and isinstance(bid, (int, float))) else None
        gap_pct = None
        if isinstance(prev_close, (int, float)) and prev_close != 0 and isinstance(last, (int, float)):
            gap_pct = ((last - prev_close) / prev_close) * 100.0

        # Scanner scoring is placeholder here (real scoring lives in scanner_scoring)
        scanner_score = 0.0
        scanner_rank = 0

        # Headline age (minutes): placeholder computed from now since demo timestamps are 'now'
        headline_age_minutes = 0

        # Alert level placeholder (later: use score + velocity + spread + credibility)
        alert = "NONE"
        if market["data"].get("volume_spike") and (market["data"].get("relative_volume") or 0) >= 5:
            alert = "🔥"

        return {
            # Core identification
            "symbol": symbol,
            "alert_priority_level": alert,

            # Price & liquidity context
            "current_price": last,
            "previous_close_price": prev_close,
            "gap_percent": gap_pct,
            "bid_price": bid,
            "ask_price": ask,
            "spread": spread,
            "float_shares": market["data"].get("float_shares"),
            "relative_volume": market["data"].get("relative_volume"),
            "volume_spike": bool(market["data"].get("volume_spike")),

            # Momentum & ranking
            "scanner_score": scanner_score,
            "scanner_rank": scanner_rank,
            "scoring_rationale": "Placeholder scoring rationale (Step 28: minimal run)",

            # News & catalyst context
            "news_velocity_10m": None,  # will be computed in Step 29+ when we have real time windows
            "headline_age_minutes": headline_age_minutes,
            "total_news_events": news.get("total_news_events"),
            "unique_headline_count": news.get("unique_headline_count"),
            "repeated_headline_count": None,  # placeholder until we implement dedup by headline text
            "unique_region_count": news.get("unique_region_count"),
            "sentiment_score": None,  # explicit None until we implement sentiment
            "breaking_news_urls": [h.get("url") for h in news.get("headlines", []) if h.get("url")],
            "earnings_links": [],
            "sec_filing_links": [],

            # Structural context (placeholders until we add symbol metadata providers)
            "corporate_actions_detected": None,
            "sector": None,
            "industry": None,
            "subcategory": None,

            # Strategy context (scanner-level only)
            "trend_direction": None,
            "trend_strength": None,
            "signal_bias": "NEUTRAL",

            # Risk pre-checks (scanner-level hints only)
            "liquidity_risk_flag": None,
            "volatility_risk_flag": None,
            "max_position_size_hint": None,
        }

    def _normalize_payload(self, payload: Dict) -> Dict:
        """
        Ensure ALL contract fields exist.

        TEACHING NOTE:
        This is the key lesson: printing is a contract.
        If a field is missing, we fill it as N/A instead of crashing or hiding it.
        """
        normalized = dict(payload)
        for field in SCANNER_PRINT_FIELDS_ORDERED:
            if field not in normalized:
                normalized[field] = "N/A"
        return normalized

    # ----------------------------
    # Logging Helper
    # ----------------------------

    def _log(self, msg: str) -> None:
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[SCANNER_IMPL][{ts}] {msg}")


# ================================
# 4. Standalone Execution
# ================================

if __name__ == "__main__":
    # TEACHING NOTE:
    # Running this file proves:
    # - the contract is real
    # - the formatter is working
    # - the pipeline can be tested without IBKR or real APIs
    scanner = ScannerEngineImpl()
    scanner.run_scan()

# ================================
# END OF FILE
# ================================
