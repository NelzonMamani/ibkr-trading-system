# File: news_providers_v01.py
# Created: 2025-12-16
# Version Notes:
# - v01: News provider stubs (Yahoo, Finviz, Generic RSS)

"""
NEWS PROVIDER IMPLEMENTATIONS (STUBS)
------------------------------------

GLOBAL CONTEXT
--------------
This file contains **stub implementations** of concrete news providers
that plug into the NewsSourceRegistry.

They validate:
- normalization contracts
- aggregation behavior
- region awareness

SOURCE OF TRUTH
---------------
Derived strictly from:
- STEP_31_OUTCOME_NEWS_PROVIDER_IMPLEMENTATIONS.md
- news_source_registry_v01.py

STANDALONE GUARANTEE
-------------------
This file runs without network access.

TRADING MODE
------------
Observation only.
"""

# ================================
# 1. Imports
# ================================

from datetime import datetime
from typing import List, Dict

from news_source_registry_v01 import NewsProvider

# ================================
# 2. Yahoo News Provider (Stub)
# ================================

class YahooNewsProvider(NewsProvider):
    """
    YahooNewsProvider
    -----------------
    Public Yahoo Finance news (stub).
    """

    provider_name = "YAHOO_NEWS"

    def fetch(self, symbol: str) -> List[Dict]:
        return [
            {
                "headline_text": f"{symbol} sees unusual trading activity",
                "published_timestamp": datetime.utcnow().isoformat(),
                "source_name": "Yahoo Finance",
                "region": "US",
                "credibility_tier": "MEDIUM",
                "url": "https://finance.yahoo.com",
                "symbol_mentions": [symbol],
            }
        ]

# ================================
# 3. Finviz News Provider (Stub)
# ================================

class FinvizNewsProvider(NewsProvider):
    """
    FinvizNewsProvider
    ------------------
    Market-focused headline aggregator (stub).
    """

    provider_name = "FINVIZ"

    def fetch(self, symbol: str) -> List[Dict]:
        return [
            {
                "headline_text": f"Finviz reports momentum in {symbol}",
                "published_timestamp": datetime.utcnow().isoformat(),
                "source_name": "Finviz",
                "region": "US",
                "credibility_tier": "HIGH",
                "url": "https://finviz.com",
                "symbol_mentions": [symbol],
            }
        ]

# ================================
# 4. Generic RSS News Provider (Stub)
# ================================

class GenericRSSNewsProvider(NewsProvider):
    """
    GenericRSSNewsProvider
    ----------------------
    Placeholder for arbitrary RSS feeds.
    """

    provider_name = "GENERIC_RSS"

    def fetch(self, symbol: str) -> List[Dict]:
        return [
            {
                "headline_text": f"Global markets react to {symbol} news",
                "published_timestamp": datetime.utcnow().isoformat(),
                "source_name": "Generic RSS",
                "region": "EU",
                "credibility_tier": "LOW",
                "url": "https://example.com/rss",
                "symbol_mentions": [symbol],
            }
        ]

# ================================
# 5. Standalone Demo
# ================================

if __name__ == "__main__":
    providers = [YahooNewsProvider(), FinvizNewsProvider(), GenericRSSNewsProvider()]

    for p in providers:
        print(p.provider_name, p.fetch("AAPL"))

# ================================
# END OF FILE
# ================================
