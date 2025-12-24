# File: news_source_registry_v01.py
# Created: 2025-12-16
# Version Notes:
# - v01: News source registry skeleton

"""
NEWS SOURCE REGISTRY (CATALYST & SENTIMENT DATA)
-----------------------------------------------

GLOBAL CONTEXT
--------------
This file defines the **News Source Registry**.

The registry:
- manages multiple news providers
- normalizes headlines and metadata
- computes velocity and aggregation metrics

SOURCE OF TRUTH
---------------
Derived strictly from:
- STEP_19_OUTCOME_NEWS_SOURCE_REGISTRY.md

STANDALONE GUARANTEE
-------------------
This file can run without external APIs.

TRADING MODE
------------
Observation & context only.
"""

# ================================
# 1. Imports & Setup
# ================================

from datetime import datetime
from typing import Dict, List

# ================================
# 2. News Provider Base
# ================================

class NewsProvider:
    """
    NewsProvider
    ------------
    Base interface for news providers.
    """

    provider_name: str = "UNKNOWN"

    def fetch(self, symbol: str) -> List[Dict]:
        """
        Fetch raw news items for a symbol.
        """
        raise NotImplementedError

# ================================
# 3. News Source Registry
# ================================

class NewsSourceRegistry:
    """
    NewsSourceRegistry
    ------------------
    Maintains prioritized news providers and aggregates results.
    """

    def __init__(self):
        self.providers: List[NewsProvider] = []

    # ================================
    # 4. Registry Management
    # ================================

    def register_provider(self, provider: NewsProvider):
        """
        Register a news provider.
        """
        self.providers.append(provider)

    def list_providers(self) -> List[str]:
        """List registered news providers."""
        return [p.provider_name for p in self.providers]

    # ================================
    # 5. Unified Fetch & Aggregation
    # ================================

    def fetch_news(self, symbol: str) -> Dict:
        """
        Fetch and aggregate news across providers.
        """
        headlines: List[Dict] = []

        for provider in self.providers:
            try:
                items = provider.fetch(symbol)
                headlines.extend(items)
            except Exception as exc:
                print(f"[NEWS][WARN] Provider {provider.provider_name} failed: {exc}")

        return self._aggregate(symbol, headlines)

    # ================================
    # 6. Aggregation Helpers
    # ================================

    def _aggregate(self, symbol: str, headlines: List[Dict]) -> Dict:
        """
        Aggregate normalized news metrics.
        """
        unique_urls = {h.get("url") for h in headlines}
        regions = {h.get("region") for h in headlines}

        return {
            "symbol": symbol,
            "total_news_events": len(headlines),
            "unique_headline_count": len(unique_urls),
            "unique_region_count": len(regions),
            "headlines": headlines,
            "aggregated_at": datetime.utcnow().isoformat(),
        }

# ================================
# 7. Standalone Execution
# ================================

if __name__ == "__main__":
    registry = NewsSourceRegistry()
    print(registry.list_providers())

# ================================
# END OF FILE
# ================================
