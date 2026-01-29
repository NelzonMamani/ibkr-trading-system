"""
Strategy Configuration (All options implemented, activation via config only).
"""

# Input Modes
INPUT_MODE = "MARKET_DISCOVERY"  # or MANUAL_SYMBOL_LIST

MANUAL_SYMBOL_LIST = [
    # Example: "AAPL", "NVDA", "TSLA"
]

# Global Market Priority (never exclusion)
MARKET_PRIORITY_ORDER = [
    "US",
    "JP",
    "EU_CORE",
    "UK",
    "CAN",
    "AUS",
    "DEVELOPED_ASIA",
    "EMERGING",
]

# Watchlist Processing Limits
MAX_DEEP_EVALUATIONS_PER_RUN = 50

# Dividend Handling
DIVIDEND_REINVESTMENT_ENABLED = True
