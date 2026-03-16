from __future__ import annotations

from src.market_data.market_snapshot_enricher import MarketSnapshotEnricher
from src.scanner.providers.ibkr_provider import IbkrScannerProvider


def _contract_details_from_provider(provider: IbkrScannerProvider) -> dict[str, dict[str, object]]:
    scan_details = getattr(provider, "last_scan_details", {}) or {}
    symbol_details = scan_details.get("symbol_details", {}) if isinstance(scan_details, dict) else {}
    payload: dict[str, dict[str, object]] = {}
    for symbol, meta in symbol_details.items():
        if not isinstance(meta, dict):
            continue
        normalized = str(symbol or "").upper().strip()
        if not normalized:
            continue
        payload[normalized] = {
            "symbol": normalized,
            "secType": "STK",
            "conId": meta.get("conId"),
            "primaryExchange": meta.get("primaryExchange"),
            "tradingClass": meta.get("tradingClass"),
            "exchange": "SMART",
            "currency": "USD",
        }
    return payload


def main() -> None:
    provider = IbkrScannerProvider()
    provider.connect()
    try:
        symbols = provider.get_top_gainers(limit=10)
        contract_details_by_symbol = _contract_details_from_provider(provider)
        enricher = MarketSnapshotEnricher(
            connection_manager=getattr(provider, "connection_manager", None),
            batch_timeout_seconds=5.0,
        )
        snapshots = enricher.fetch_snapshots(
            symbols,
            contract_details_by_symbol=contract_details_by_symbol,
        )
        diagnostics = getattr(enricher, "last_fetch_diagnostics", {}) or {}
        for symbol in symbols:
            snap = snapshots.get(symbol, {})
            diag = diagnostics.get(symbol, {})
            print(
                f"{symbol} "
                f"source={diag.get('contract_build_source')} "
                f"qualified_ok={diag.get('qualified_ok')} "
                f"snapshot_received={diag.get('snapshot_received')} "
                f"last_price={snap.get('last_price')} "
                f"bid={snap.get('bid')} "
                f"ask={snap.get('ask')} "
                f"volume={snap.get('volume')}"
            )

        with_last_price = sum(1 for snap in snapshots.values() if snap.get("last_price") is not None)
        with_bid_ask = sum(1 for snap in snapshots.values() if snap.get("bid") is not None and snap.get("ask") is not None)
        with_volume = sum(1 for snap in snapshots.values() if snap.get("volume") is not None)
        print(
            "SUMMARY "
            f"total={len(symbols)} "
            f"with_last_price={with_last_price} "
            f"with_bid_ask={with_bid_ask} "
            f"with_volume={with_volume}"
        )
    finally:
        provider.disconnect()


if __name__ == "__main__":
    main()
