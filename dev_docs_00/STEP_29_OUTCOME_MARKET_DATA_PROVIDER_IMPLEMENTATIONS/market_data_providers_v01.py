# File: market_data_providers_v01.py
# Created: 2025-12-16
# Version Notes:
# - v01: IBKR and Yahoo market data provider stubs

"""
MARKET DATA PROVIDERS (IBKR + YAHOO STUBS)
-----------------------------------------

GLOBAL CONTEXT
--------------
This file contains concrete **market data provider implementations**
that plug into the DataSourceRegistry.

These are STUBS:
- no real APIs are called
- structure and contracts are validated

SOURCE OF TRUTH
---------------
Derived strictly from:
- STEP_29_OUTCOME_MARKET_DATA_PROVIDER_IMPLEMENTATIONS.md
- data_source_registry_v01.py

STANDALONE GUARANTEE
-------------------
This file runs without network access.

TRADING MODE
------------
Data access only (stubbed).
"""

# ================================
# 1. Imports
# ================================

from datetime import datetime
from typing import Dict

from data_source_registry_v01 import MarketDataProvider

# ================================
# 2. IBKR Market Data Provider (Stub)
# ================================

class IBKRMarketDataProvider(MarketDataProvider):
    """
    IBKRMarketDataProvider
    ----------------------
    Primary market data provider (stub).
    """

    provider_name = "IBKR"

    def fetch(self, symbol: str) -> Dict:
        """
        Fetch market data for a symbol (stub).
        """
        return {
            "symbol": symbol,
            "current_price": None,
            "bid_price": None,
            "ask_price": None,
            "previous_close_price": None,
            "volume": None,
            "timestamp": datetime.utcnow().isoformat(),
            "provider_name": self.provider_name,
        }

# ================================
# 3. Yahoo Market Data Provider (Stub)
# ================================

class YahooMarketDataProvider(MarketDataProvider):
    """
    YahooMarketDataProvider
    -----------------------
    Fallback public market data provider (stub).
    """

    provider_name = "YAHOO"

    def fetch(self, symbol: str) -> Dict:
        """
        Fetch market data for a symbol (stub).
        """
        return {
            "symbol": symbol,
            "current_price": None,
            "bid_price": None,
            "ask_price": None,
            "previous_close_price": None,
            "volume": None,
            "timestamp": datetime.utcnow().isoformat(),
            "provider_name": self.provider_name,
        }

# ================================
# 4. Standalone Demo
# ================================

if __name__ == "__main__":
    ibkr = IBKRMarketDataProvider()
    yahoo = YahooMarketDataProvider()

    print(ibkr.fetch("AAPL"))
    print(yahoo.fetch("AAPL"))

# ================================
# END OF FILE
# ================================
