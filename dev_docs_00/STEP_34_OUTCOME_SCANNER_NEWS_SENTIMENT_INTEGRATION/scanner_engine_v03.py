# File: scanner_engine_v03.py
# Created: 2025-12-16
# Version Notes:
# - v03: Scanner integrated with news aggregation + sentiment

"""
SCANNER ENGINE — NEWS + SENTIMENT INTEGRATED
-------------------------------------------

GLOBAL CONTEXT
--------------
This version of the Scanner Engine integrates:
- market data
- news aggregation metrics
- sentiment analysis

The scanner now answers:
- WHAT is moving
- WHY it is moving

SOURCE OF TRUTH
---------------
Derived strictly from:
- STEP_34_OUTCOME_SCANNER_NEWS_SENTIMENT_INTEGRATION.md

STANDALONE GUARANTEE
-------------------
This scanner runs without live data or broker connectivity.

TRADING MODE
------------
Observation only.
"""

# ================================
# 1. Imports
# ================================

from typing import List, Dict

from data_source_registry_v01 import DataSourceRegistry
from news_source_registry_v01 import NewsSourceRegistry
from news_aggregation_metrics_v01 import NewsAggregationMetricsEngine
from sentiment_analysis_engine_v01 import SentimentAnalysisEngine
from scanner_print_contract_v01 import validate_scanner_print_payload
from scanner_print_formatter_v01 import ScannerPrintFormatter

# ================================
# 2. Scanner Engine
# ================================

class ScannerEngine:
    """
    ScannerEngine (Integrated)
    --------------------------
    Scanner with news and sentiment awareness.
    """

    def __init__(self,
                 symbols: List[str],
                 data_registry: DataSourceRegistry,
                 news_registry: NewsSourceRegistry):
        self.symbols = symbols
        self.data_registry = data_registry
        self.news_registry = news_registry
        self.news_metrics = NewsAggregationMetricsEngine()
        self.sentiment_engine = SentimentAnalysisEngine()
        self.formatter = ScannerPrintFormatter()

    def run_scan(self) -> List[Dict]:
        results = []

        for symbol in self.symbols:
            payload = self._scan_symbol(symbol)

            missing = validate_scanner_print_payload(payload)
            if missing:
                payload["scanner_error"] = f"Missing fields: {missing}"

            print(self.formatter.format(payload))
            results.append(payload)

        return results

    def _scan_symbol(self, symbol: str) -> Dict:
        market = self.data_registry.fetch_market_data(symbol)
        headlines = self.news_registry.fetch_news(symbol).get("headlines", [])

        news_metrics = self.news_metrics.compute(headlines)
        sentiment = self.sentiment_engine.compute(headlines)

        payload = {
            "symbol": symbol,
            "alert_priority_level": "NONE",

            "current_price": market.get("data", {}).get("current_price"),
            "previous_close_price": market.get("data", {}).get("previous_close_price"),
            "gap_percent": None,
            "bid_price": market.get("data", {}).get("bid_price"),
            "ask_price": market.get("data", {}).get("ask_price"),
            "spread": None,
            "float_shares": None,
            "relative_volume": None,
            "volume_spike": False,

            "scanner_score": None,
            "scanner_rank": None,
            "scoring_rationale": "Not implemented",

            "news_velocity_10m": news_metrics.get("news_velocity_10m"),
            "headline_age_minutes": news_metrics.get("headline_age_minutes"),
            "total_news_events": len(headlines),
            "unique_headline_count": news_metrics.get("unique_headline_count"),
            "repeated_headline_count": news_metrics.get("repeated_headline_count"),
            "unique_region_count": news_metrics.get("unique_region_count"),
            "sentiment_score": sentiment.get("sentiment_score"),
            "breaking_news_urls": [h.get("url") for h in headlines],
            "earnings_links": [],
            "sec_filing_links": [],

            "corporate_actions_detected": None,
            "sector": None,
            "industry": None,
            "subcategory": None,

            "trend_direction": None,
            "trend_strength": None,
            "signal_bias": "NEUTRAL",

            "liquidity_risk_flag": False,
            "volatility_risk_flag": False,
            "max_position_size_hint": None,
        }

        return payload

# ================================
# 3. Standalone Demo
# ================================

if __name__ == "__main__":
    scanner = ScannerEngine(
        symbols=["AAPL"],
        data_registry=DataSourceRegistry(),
        news_registry=NewsSourceRegistry(),
    )

    scanner.run_scan()

# ================================
# END OF FILE
# ================================

