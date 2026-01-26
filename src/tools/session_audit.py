"""CLI tool to audit session classification and percent-change/RVOL baselines."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, Optional

from src.scanner.providers.factory import build_provider
from src.scanner.providers.base import ProviderConnectionError
from src.scanner.providers.mock_provider import MockScannerProvider
from src.scanner.scanner_runner import _resolve_price
from src.utils.session_classifier import SessionClassifier


_CACHE_PATH = Path("data/cache/session_close_cache.json")


def _load_close_cache() -> Dict[str, Any]:
    if not _CACHE_PATH.exists():
        return {}
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_close_cache(cache: Dict[str, Any]) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(cache, sort_keys=True, indent=2), encoding="utf-8")


def _baseline_summary(
    state: str,
    last_price: Optional[float],
    prev_close: Optional[float],
    rth_close: Optional[float],
    close_cache: Dict[str, Any],
    ny_date: str,
) -> Dict[str, Any]:
    if state in {"PRE", "RTH"}:
        return {
            "baseline_type": "prior_close",
            "baseline_price": prev_close,
            "compare_price": last_price,
        }
    if state == "AH":
        baseline = rth_close or prev_close
        return {
            "baseline_type": "rth_close" if rth_close else "prior_close_fallback",
            "baseline_price": baseline,
            "compare_price": last_price,
        }
    if state in {"WEEKEND", "HOLIDAY"}:
        last_trading_close = close_cache.get("last_trading_close")
        prev_trading_close = close_cache.get("previous_trading_close")
        return {
            "baseline_type": "last_vs_prev_trading_close",
            "baseline_price": last_trading_close,
            "compare_price": prev_trading_close,
        }
    return {
        "baseline_type": "closed",
        "baseline_price": prev_close,
        "compare_price": last_price,
    }


def _rvol_summary(volume: Optional[int], avg_20d: Optional[int]) -> Dict[str, Any]:
    rvol_20d = None
    if volume is not None and avg_20d:
        rvol_20d = round(volume / avg_20d, 4)
    return {"rvol_20d": rvol_20d, "rvol_1d": None}


def main() -> int:
    parser = argparse.ArgumentParser(description="Session audit tool")
    parser.add_argument("--symbol", default="AAPL")
    args = parser.parse_args()

    classifier = SessionClassifier()
    now_utc = datetime.now(timezone.utc)
    classification = classifier.classify(now_utc)
    try:
        provider = build_provider()
        provider.connect()
    except ProviderConnectionError:
        provider = MockScannerProvider()
        provider.connect()
    try:
        quote = provider.get_quote(args.symbol)
        last_price = _resolve_price(quote)
        prev_close = provider.get_prev_close(args.symbol)
        rth_close = quote.close
        intraday = provider.get_intraday_stats(args.symbol)
    finally:
        provider.disconnect()

    close_cache = _load_close_cache()
    close_cache["last_trading_close"] = prev_close
    close_cache["previous_trading_close"] = close_cache.get("previous_trading_close") or prev_close
    _save_close_cache(close_cache)

    baseline = _baseline_summary(
        classification.session_state,
        last_price,
        prev_close,
        rth_close,
        close_cache,
        classification.now_ny.date().isoformat(),
    )
    rvol = _rvol_summary(
        intraday.current_intraday_volume if intraday else None,
        intraday.average_daily_volume_20d if intraday else None,
    )

    print("[SESSION_AUDIT] now_utc:", classification.now_utc.isoformat())
    print("[SESSION_AUDIT] now_ny:", classification.now_ny.isoformat())
    print("[SESSION_AUDIT] now_uk:", classification.now_uk.isoformat())
    print("[SESSION_AUDIT] session_state:", classification.session_state)
    print("[SESSION_AUDIT] ross_trading_mode:", classification.ross_trading_mode.value)
    print("[SESSION_AUDIT] percent_change_baseline:", baseline)
    print("[SESSION_AUDIT] rvol_baseline:", rvol)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
