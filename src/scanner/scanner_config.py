"""Scanner configuration shim backed by config_resolver."""
from __future__ import annotations

from pathlib import Path

from src.config.config_resolver import get_config

NEWS_ENABLED = bool(get_config("NEWS_ENABLED"))
NEWS_LOOKBACK_HOURS = float(get_config("NEWS_LOOKBACK_HOURS"))
NEWS_MAX_ENTRIES_PER_SYMBOL = int(get_config("NEWS_MAX_ENTRIES_PER_SYMBOL"))
NEWS_REQUEST_TIMEOUT_S = int(get_config("NEWS_REQUEST_TIMEOUT_S"))
VERIFIED_RSS_PATH = Path(get_config("VERIFIED_RSS_PATH"))
