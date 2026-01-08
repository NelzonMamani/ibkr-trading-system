from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ib_insync import IB, Stock

logger = logging.getLogger(__name__)

FLOAT_CACHE_PATH = Path(__file__).resolve().parents[1] / "float_cache.json"

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None


def load_float_cache(path: Optional[Path] = None) -> Dict[str, Any]:
    path = path or FLOAT_CACHE_PATH
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_float_cache(cache: Dict[str, Any], path: Optional[Path] = None) -> None:
    path = path or FLOAT_CACHE_PATH
    try:
        path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to write float cache: %s", exc)


def get_float_shares(
    ib: IB,
    contract: Stock,
    float_cache: Dict[str, Any],
) -> Tuple[Optional[int], str, bool]:
    symbol = contract.symbol
    cache_key = symbol.upper()
    if cache_key in float_cache:
        return float_cache[cache_key], "CACHE", True

    float_shares = None
    source = "NONE"

    try:
        fundamentals = ib.reqFundamentalData(contract, "ReportSnapshot")
        if fundamentals:
            for line in fundamentals.splitlines():
                if "Float" in line and ">" in line:
                    parts = line.split(">")
                    value = parts[-1].split("<")[0].strip().replace(",", "")
                    if value.isdigit():
                        float_shares = int(value)
                        source = "IB_FUNDAMENTALS"
                        break
    except Exception:
        pass

    if float_shares is None and yf is not None:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            if isinstance(info, dict):
                float_val = info.get("floatShares") or info.get("sharesFloat")
                if float_val:
                    float_shares = int(float_val)
                    source = "YFINANCE"
        except Exception:
            pass

    if float_shares is not None:
        float_cache[cache_key] = float_shares

    return float_shares, source, False
