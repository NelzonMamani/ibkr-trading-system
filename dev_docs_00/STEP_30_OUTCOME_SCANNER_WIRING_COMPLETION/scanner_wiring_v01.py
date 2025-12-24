# File: scanner_wiring_v01.py
# Created: 2025-12-16
# Version Notes:
# - v01: Scanner wiring completion (standalone runnable)

"""
SCANNER WIRING COMPLETION
------------------------

GLOBAL CONTEXT
--------------
This file wires together the full Scanner subsystem:
- market data providers
- news providers
- scanner engine
- print formatter

It produces a **fully runnable scanner** without live data.

SOURCE OF TRUTH
---------------
Derived strictly from:
- STEP_30_OUTCOME_SCANNER_WIRING_COMPLETION.md

STANDALONE GUARANTEE
-------------------
Run this file to validate scanner wiring end-to-end.

TRADING MODE
------------
Observation only.
"""

# ================================
# 1. Imports
# ================================

from data_source_registry_v01 import DataSourceRegistry
from news_source_registry_v01 import NewsSourceRegistry

from market_data_providers_v01 import (
    IBKRMarketDataProvider,
    YahooMarketDataProvider,
)

from scanner_engine_v02 import ScannerEngine

# ================================
# 2. Wiring Function
# ================================

class ScannerWiring:
    """
    ScannerWiring
    -------------
    Wires and runs the Scanner subsystem.
    """

    def __init__(self, symbols):
        # Market data registry
        self.data_registry = DataSourceRegistry()
        self.data_registry.register_provider(IBKRMarketDataProvider())
        self.data_registry.register_provider(YahooMarketDataProvider())

        # News registry (no providers yet)
        self.news_registry = NewsSourceRegistry()

        # Scanner engine
        self.scanner = ScannerEngine(
            symbols=symbols,
            data_registry=self.data_registry,
            news_registry=self.news_registry,
        )

    def run(self):
        """Run scanner."""
        return self.scanner.run_scan()

# ================================
# 3. Standalone Execution
# ================================

if __name__ == "__main__":
    symbols = ["AAPL", "MSFT", "TSLA"]
    wiring = ScannerWiring(symbols)
    wiring.run()

# ================================
# END OF FILE
# ================================
