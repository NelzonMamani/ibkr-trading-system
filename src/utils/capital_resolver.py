from __future__ import annotations

from src.config.runtime_config import get_default_capital


def resolve_available_capital(ibkr_client) -> float:
    try:
        summary = ibkr_client.get_account_summary()
        available = summary.get("AvailableFunds")
        if available is not None:
            print(f"[CAPITAL] source=IBKR available_funds={available}")
            return float(available)
    except Exception as exc:  # pragma: no cover - diagnostic fallback path
        print(f"[CAPITAL] ibkr_fetch_failed reason={exc}")

    default_capital = get_default_capital()
    print(f"[CAPITAL] source=CONFIG_DEFAULT fallback={default_capital}")
    return float(default_capital)
