from __future__ import annotations

from src.market_data.market_snapshot_enricher import MarketSnapshotEnricher
from src.scanner.providers.ibkr_provider import IbkrScannerProvider


def main() -> None:
    provider = IbkrScannerProvider()
    provider.connect()
    try:
        symbols = provider.get_top_gainers(limit=10)
        enricher = MarketSnapshotEnricher(
            connection_manager=getattr(provider, "connection_manager", None),
            batch_timeout_seconds=5.0,
        )
        snapshots = enricher.fetch_snapshots(symbols)
        for symbol in symbols:
            snap = snapshots.get(symbol, {})
            print(
                f"{symbol} "
                f"last_price={snap.get('last_price')} "
                f"volume={snap.get('volume')} "
                f"bid={snap.get('bid')} "
                f"ask={snap.get('ask')}"
            )
    finally:
        provider.disconnect()


if __name__ == "__main__":
    main()
