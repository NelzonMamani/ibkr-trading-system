# File: data_source_registry_v01.py
# Created: 2025-12-16
# Version Notes:
# - v01: Data source registry skeleton

"""
DATA SOURCE REGISTRY (MARKET DATA PROVIDERS)
--------------------------------------------

GLOBAL CONTEXT
--------------
This file defines the **Data Source Registry** for market data.

The registry:
- manages primary and fallback data providers
- exposes a unified fetch interface
- reports data quality and provenance

SOURCE OF TRUTH
---------------
Derived strictly from:
- STEP_18_OUTCOME_DATA_SOURCE_REGISTRY.md

STANDALONE GUARANTEE
-------------------
This file can run without external APIs.

TRADING MODE
------------
Data access only.
"""

# ================================
# 1. Imports & Setup
# ================================

from typing import Dict, List, Optional

# ================================
# 2. Provider Base Contract
# ================================

class MarketDataProvider:
    """
    MarketDataProvider
    ------------------
    Abstract-style base for data providers (lightweight).
    """

    provider_name: str = "UNKNOWN"

    def fetch(self, symbol: str) -> Dict:
        """
        Fetch market data for a symbol.
        """
        raise NotImplementedError

# ================================
# 3. Data Source Registry
# ================================

class DataSourceRegistry:
    """
    DataSourceRegistry
    ------------------
    Maintains prioritized market data providers.
    """

    def __init__(self):
        self.providers: List[MarketDataProvider] = []

    # ================================
    # 4. Registry Management
    # ================================

    def register_provider(self, provider: MarketDataProvider):
        """
        Register a data provider.
        """
        self.providers.append(provider)

    def list_providers(self) -> List[str]:
        """Return provider names in priority order."""
        return [p.provider_name for p in self.providers]

    # ================================
    # 5. Unified Fetch Interface
    # ================================

    def fetch_market_data(self, symbol: str) -> Dict:
        """
        Attempt to fetch data using registered providers.
        Falls back on failure.
        """
        for provider in self.providers:
            try:
                data = provider.fetch(symbol)
                return {
                    "symbol": symbol,
                    "data": data,
                    "provider": provider.provider_name,
                }
            except Exception as exc:
                print(f"[DATA][WARN] Provider {provider.provider_name} failed: {exc}")

        raise RuntimeError("All data providers failed")

# ================================
# 6. Standalone Execution
# ================================

if __name__ == "__main__":
    registry = DataSourceRegistry()
    print(registry.list_providers())

# ================================
# END OF FILE
# ================================
