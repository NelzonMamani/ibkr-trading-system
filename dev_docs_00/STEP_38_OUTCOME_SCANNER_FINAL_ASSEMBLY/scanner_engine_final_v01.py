# File: scanner_engine_final_v01.py
# Created: 2025-12-17
# Version Notes:
# - v01: Complete scanner assembly (market + news + metrics + sentiment + score + alert + rank + print)

"""
SCANNER ENGINE — FINAL ASSEMBLY
-------------------------------

GLOBAL CONTEXT
--------------
This file assembles the full Scanner pipeline into one runnable unit.

Pipeline:
Market Data + News + Metrics + Sentiment → Payload → Score → Alert → Rank → Print

This is the trader-facing watchlist feed.

SOURCE OF TRUTH
---------------
Derived strictly from:
- STEP_38_OUTCOME_SCANNER_FINAL_ASSEMBLY.md

STANDALONE GUARANTEE
-------------------
Runs without live data or broker.

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

from scanner_scoring_engine_v01 import ScannerScoringEngine
from alert_priority_engine_v01 import AlertPriorityEngine
from scanner_ranking_engine_v01 import ScannerRankingEngine

from scanner_print_contract_v01 import validate_scanner_print_payload
from scanner_print_formatter_v01 import ScannerPrintFormatter

# ================================
# 2. Final Scanner Assembly
# ================================

class FinalScannerEngine:
    """
    FinalScannerEngine
    ------------------
    Full scanner assembly.
    """

    def __init__(self,
                 symbols: List[str],
                 data_registry: DataSourceRegistry,
                 news_registry: NewsSourceRegistry):
        self.symbols = symbols
        self.data_registry = data_registry
        self.news_registry = news_registry

        self.news_metrics_engine = NewsAggregationMetricsEngine()
        self.sentiment_engine = SentimentAnalysisEngine()
        self.scoring_engine = ScannerScoringEngine()
        self.alert_engine = AlertPriorityEngine()
        self.ranking_engine = ScannerRankingEngine()
        self.formatter = ScannerPrintFormatter()

    def run_scan(self) -> List[Dict]:
        """Run full scanner pipeline."""
        payloads = [self._scan_symbol(s) for s in self.symbols]

        # Score + alert per symbol
        for p in payloads:
            p.update(self.scoring_engine.compute(p))
            p.update(self.alert_engine.compute(p))

        # Rank globally
        ranked = self.ranking_engine.rank(payloads)

        # Validate + print
        for p in ranked:
            missing = validate_scanner_print_payload(p)
            if missing:
                p["scanner_error"] = f"Missing fields: {missing}"

            print(self.formatter.format(p))

        return ranked

    def _scan_symbol(self, symbol: str) -> Dict:
        """Scan one symbol and build contract payload."""
        market = self.data_registry.fetch_market_data(symbol)
        headlines = self.news_registry.fetch_news(symbol).get("headlines", [])

        news_metrics = self.news_metrics_engine.compute(headlines)
        sentiment = self.sentiment_engine.compute(headlines)

        # Build contract payload (placeholders allowed)
        payload = {
            "symbol": symbol,
            "alert_priority_level": "NONE",  # overwritten by alert engine

            "current_price": market.get("data", {}).get("current_price"),
            "previous_close_price": market.get("data", {}).get("previous_close_price"),
            "gap_percent": None,
            "bid_price": market.get("data", {}).get("bid_price"),
            "ask_price": market.get("data", {}).get("ask_price"),
            "spread": None,
            "float_shares": None,
            "relative_volume": None,
            "volume_spike": False,

            "scanner_score": 0.0,  # computed later
            "scanner_rank": None,  # computed later
            "scoring_rationale": "Pending",

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
    # NOTE: Registries can be wired with providers using scanner_wiring_v01.py
    scanner = FinalScannerEngine(
        symbols=["AAPL", "TSLA", "MSFT"],
        data_registry=DataSourceRegistry(),
        news_registry=NewsSourceRegistry(),
    )
    scanner.run_scan()

# ================================
# END OF FILE
# ================================
