from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.config.runtime_config import (
    get_ibkr_client_id,
    get_ibkr_host,
    get_ibkr_market_data_type,
    get_ibkr_port,
    get_ibkr_readonly_enabled,
    get_ibkr_snapshot_timeout_seconds,
)
from src.utils.capital_resolver import resolve_available_capital


def main() -> int:
    print("[VERIFY][CAPITAL]")
    client = IbkrClient(
        host=get_ibkr_host(),
        port=get_ibkr_port(),
        client_id=get_ibkr_client_id(),
        snapshot_timeout_seconds=get_ibkr_snapshot_timeout_seconds(),
        market_data_type=get_ibkr_market_data_type(),
        readonly_enabled=get_ibkr_readonly_enabled(),
    )

    source = "CONFIG_DEFAULT"
    try:
        client.connect()
        summary = client.get_account_summary()
        if summary.get("AvailableFunds") is not None:
            source = "IBKR"
        capital = resolve_available_capital(client)
    except Exception:
        capital = resolve_available_capital(client)
    finally:
        try:
            if client.is_connected():
                client.disconnect()
        except Exception:
            pass

    if source == "IBKR":
        print("source=IBKR")
        print(f"available_funds={capital}")
    else:
        print("source=CONFIG_DEFAULT")
        print(f"fallback={capital}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
