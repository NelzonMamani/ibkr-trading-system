# FILE: verification_scripts/verify_ibkr_spot_check.py
# TITLE: Optional IBKR spot check (connectivity + snapshot sanity). Only run with --ibkr.

from typing import Dict, Any

def verify_ibkr_spot_check() -> Dict[str, Any]:
    out: Dict[str, Any] = {"status": "PASS", "details": {}}
    try:
        # We do NOT assume provider class names. We introspect by importing the market data client.
        from src.ibkr.market_data_client import IBKRMarketDataClient  # type: ignore

        client = IBKRMarketDataClient()
        client.connect()

        symbol = "NVDA"
        snap = client.snapshot_stock(symbol)

        out["details"] = {
            "symbol": symbol,
            "last": getattr(snap, "last", None),
            "bid": getattr(snap, "bid", None),
            "ask": getattr(snap, "ask", None),
            "volume": getattr(snap, "volume", None),
        }

        client.disconnect()
        return out

    except Exception as e:
        out["status"] = "ERROR"
        out["details"] = {"error": repr(e), "hint": "IBKR must be running + API port open + correct port (7497 paper / 7496 live)."}
        return out
# END
