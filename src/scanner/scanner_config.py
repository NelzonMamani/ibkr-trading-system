"""Local scanner configuration (stand-alone friendly).

Defaults are defined here and can be overridden via environment variables.
"""
from __future__ import annotations

import os
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except Exception:
        return default


IB_HOST = os.environ.get("IB_HOST") or os.environ.get("IBKR_HOST") or "127.0.0.1"
IB_PORT = _env_int("IB_PORT", _env_int("IBKR_PORT", 7496))
IB_CONNECT_TIMEOUT = _env_float("IB_CONNECT_TIMEOUT", 12.0)

TOP_GAINERS_COUNT = _env_int("TOP_GAINERS_COUNT", 50)

NEWS_ENABLED = _env_bool("NEWS_ENABLED", True)
NEWS_LOOKBACK_HOURS = _env_float("NEWS_LOOKBACK_HOURS", 48.0)
NEWS_REQUEST_TIMEOUT_S = _env_float("NEWS_REQUEST_TIMEOUT_S", 5.0)
NEWS_MAX_ENTRIES_PER_SYMBOL = _env_int("NEWS_MAX_ENTRIES_PER_SYMBOL", 50)

_VERIFIED_RSS_DEFAULT = Path(__file__).resolve().parents[2] / "verified_rss.txt"
VERIFIED_RSS_PATH = Path(os.environ.get("VERIFIED_RSS_PATH", str(_VERIFIED_RSS_DEFAULT)))

_FLOAT_CACHE_DEFAULT = Path(__file__).resolve().parent / "float_cache.json"
FLOAT_CACHE_FILE = Path(os.environ.get("FLOAT_CACHE_FILE", str(_FLOAT_CACHE_DEFAULT)))
