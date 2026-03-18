from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.runtime.async_runtime_bootstrap import safe_import_ib_insync
from src.config.runtime_config import resolve_ibkr_connection
from src.scanner.candidate_identity import CandidateIdentity
from src.scanner.reference_resolver import CanonicalReferenceResolver
from src.scanner.providers.ibkr_provider import IbkrScannerProvider


def _build_identity(symbol: str, details: dict) -> CandidateIdentity:
    return CandidateIdentity.from_mapping(
        {
            "symbol": symbol,
            "conId": details.get("conId"),
            "secType": details.get("secType") or "STK",
            "exchange": details.get("exchange") or details.get("primaryExchange") or "SMART",
            "primaryExchange": details.get("primaryExchange"),
            "tradingClass": details.get("tradingClass"),
            "currency": details.get("currency") or "USD",
            "localSymbol": details.get("localSymbol") or symbol,
        }
    )


def main() -> None:
    host, port, client_id, mode = resolve_ibkr_connection()
    print(f"[VERIFY] mode={mode} port={port}")
    provider = IbkrScannerProvider(
        host=host,
        port=port,
        client_id=client_id,
    )
    resolver = CanonicalReferenceResolver()
    failures: list[str] = []
    try:
        provider.connect()
        symbols = provider.get_top_gainers(limit=5)[:5]
        symbol_details = provider.last_scan_details.get("symbol_details") or {}
        ib = provider.market_data_client._resolve_ib_client()
        if not symbols:
            raise SystemExit("No scanner symbols returned from IBKR.")

        for symbol in symbols:
            details = symbol_details.get(symbol) or {"symbol": symbol}
            identity = _build_identity(symbol, details)
            history_identity, qualified_ok = resolver._qualify_history_identity(provider, identity)
            if not qualified_ok:
                print(f"FAIL symbol={symbol} reason=QUALIFY_FAILED")
                failures.append(f"{symbol}:QUALIFY_FAILED")
                continue

            _, Stock, _ = safe_import_ib_insync()
            contract = Stock(history_identity.symbol, history_identity.exchange or "SMART", history_identity.currency or "USD")
            contract.conId = history_identity.con_id
            contract.primaryExchange = history_identity.primary_exchange
            if history_identity.trading_class:
                contract.tradingClass = history_identity.trading_class
            if history_identity.local_symbol:
                contract.localSymbol = history_identity.local_symbol

            bars = ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr="25 D",
                barSizeSetting="1 day",
                whatToShow="TRADES",
                useRTH=True,
                formatDate=1,
            ) or []
            bar_count = len(bars)
            status = "PASS" if bar_count > 0 else "FAIL"
            print(
                f"{status} symbol={symbol} conId={history_identity.con_id} exchange={history_identity.exchange} "
                f"primaryExchange={history_identity.primary_exchange} bar_count={bar_count}"
            )
            if bar_count <= 0:
                failures.append(f"{symbol}:ZERO_BARS")
    finally:
        provider.disconnect()

    if failures:
        raise SystemExit(f"Verification failed: {failures}")


if __name__ == "__main__":
    main()
