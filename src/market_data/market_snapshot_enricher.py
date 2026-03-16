from __future__ import annotations

import math
import time
from typing import Any, Dict, Iterable, Optional

from src.runtime.async_runtime_bootstrap import safe_import_ib_insync


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        parsed = float(value)
    except Exception:
        return None
    if math.isnan(parsed) or not math.isfinite(parsed):
        return None
    return parsed


class MarketSnapshotEnricher:
    """Deterministic IBKR market snapshot fetcher for scanner symbols."""

    def __init__(
        self,
        *,
        connection_manager=None,
        default_exchange: str = "SMART",
        default_currency: str = "USD",
        batch_timeout_seconds: float = 5.0,
    ) -> None:
        self.connection_manager = connection_manager
        self.default_exchange = default_exchange
        self.default_currency = default_currency
        self.batch_timeout_seconds = float(batch_timeout_seconds)

    def _resolve_ib(self):
        if self.connection_manager is None:
            return None
        try:
            return self.connection_manager.get_client()
        except Exception:
            return None

    def fetch_snapshots(self, symbols: Iterable[str]) -> Dict[str, Dict[str, Optional[float]]]:
        resolved_symbols = [str(symbol or "").upper().strip() for symbol in symbols if str(symbol or "").strip()]
        snapshots: Dict[str, Dict[str, Optional[float]]] = {
            symbol: {
                "last_price": None,
                "bid": None,
                "ask": None,
                "volume": None,
                "close": None,
            }
            for symbol in resolved_symbols
        }
        if not resolved_symbols:
            return snapshots

        ib = self._resolve_ib()
        if ib is None:
            return snapshots

        _, Stock, _ = safe_import_ib_insync()
        requested_contracts: dict[str, Any] = {}
        for symbol in resolved_symbols:
            try:
                requested_contracts[symbol] = Stock(symbol, self.default_exchange, self.default_currency)
            except Exception:
                continue

        if not requested_contracts:
            return snapshots

        try:
            qualified_contracts = ib.qualifyContracts(*requested_contracts.values())
        except Exception:
            return snapshots

        contracts_by_symbol: dict[str, Any] = {
            str(getattr(contract, "symbol", "") or "").upper(): contract
            for contract in (qualified_contracts or [])
            if getattr(contract, "symbol", None)
        }
        ticker_by_symbol: dict[str, Any] = {}
        for symbol in resolved_symbols:
            contract = contracts_by_symbol.get(symbol)
            if contract is None:
                continue
            try:
                ticker = ib.reqMktData(contract, genericTickList="", snapshot=True, regulatorySnapshot=False)
                ticker_by_symbol[symbol] = ticker
            except Exception:
                continue

        deadline = time.time() + self.batch_timeout_seconds
        while time.time() < deadline and ticker_by_symbol:
            try:
                ib.waitOnUpdate(timeout=0.2)
            except Exception:
                break
            all_resolved = True
            for symbol, ticker in ticker_by_symbol.items():
                last_price = _safe_float(getattr(ticker, "last", None))
                bid = _safe_float(getattr(ticker, "bid", None))
                ask = _safe_float(getattr(ticker, "ask", None))
                volume = _safe_float(getattr(ticker, "volume", None))
                close = _safe_float(getattr(ticker, "close", None))
                snapshots[symbol] = {
                    "last_price": last_price,
                    "bid": bid,
                    "ask": ask,
                    "volume": volume,
                    "close": close,
                }
                if last_price is None and bid is None and ask is None and volume is None and close is None:
                    all_resolved = False
            if all_resolved:
                break

        for symbol, contract in contracts_by_symbol.items():
            if symbol not in ticker_by_symbol:
                continue
            try:
                ib.cancelMktData(contract)
            except Exception:
                pass

        return snapshots

