from __future__ import annotations

import math
import time
from typing import Any, Dict, Iterable, Optional

from src.runtime.async_runtime_bootstrap import safe_import_ib_insync
from src.ibkr.contract_qualification import qualify_contracts_resilient
from src.scanner.candidate_identity import CandidateIdentity


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
        self.last_fetch_diagnostics: Dict[str, Dict[str, Any]] = {}

    def _resolve_ib(self):
        if self.connection_manager is None:
            return None
        try:
            return self.connection_manager.get_client()
        except Exception:
            return None

    def _build_contract_from_metadata(self, symbol: str, metadata: Any, stock_cls: Any) -> tuple[Any, str]:
        if metadata is None:
            return stock_cls(symbol, self.default_exchange, self.default_currency), "GENERIC_STOCK"

        if hasattr(metadata, "symbol"):
            contract = metadata
            if not getattr(contract, "symbol", None):
                contract.symbol = symbol
            return contract, "SCANNER_METADATA"

        if isinstance(metadata, dict):
            scanner_contract = metadata.get("contract")
            if scanner_contract is not None and hasattr(scanner_contract, "symbol"):
                if not getattr(scanner_contract, "symbol", None):
                    scanner_contract.symbol = symbol
                return scanner_contract, "SCANNER_METADATA"

            sec_type = str(metadata.get("secType") or "STK").upper()
            if sec_type == "STK":
                contract = stock_cls(
                    symbol,
                    metadata.get("exchange") or self.default_exchange,
                    metadata.get("currency") or self.default_currency,
                )
                for field in (
                    "conId",
                    "primaryExchange",
                    "tradingClass",
                    "localSymbol",
                ):
                    value = metadata.get(field)
                    if value is not None:
                        setattr(contract, field, value)
                return contract, "SCANNER_METADATA"

        return stock_cls(symbol, self.default_exchange, self.default_currency), "GENERIC_STOCK"

    def fetch_snapshots(
        self,
        symbols: Iterable[str],
        contract_details_by_symbol: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Optional[float]]]:
        resolved_symbols = [str(symbol or "").upper().strip() for symbol in symbols if str(symbol or "").strip()]
        metadata_lookup = {
            str(symbol or "").upper().strip(): details
            for symbol, details in (contract_details_by_symbol or {}).items()
            if str(symbol or "").strip()
        }
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
        diagnostics: Dict[str, Dict[str, Any]] = {
            symbol: {
                "contract_build_source": "GENERIC_STOCK",
                "qualified_ok": False,
                "snapshot_requested": False,
                "snapshot_received": False,
                "last_price": None,
                "bid": None,
                "ask": None,
                "volume": None,
                "close": None,
                "exception": None,
            }
            for symbol in resolved_symbols
        }
        self.last_fetch_diagnostics = diagnostics
        if not resolved_symbols:
            return snapshots

        ib = self._resolve_ib()
        if ib is None:
            return snapshots

        _, Stock, _ = safe_import_ib_insync()
        requested_contracts: dict[str, Any] = {}
        requested_identities: dict[str, CandidateIdentity] = {}
        for symbol in resolved_symbols:
            try:
                contract, source = self._build_contract_from_metadata(
                    symbol,
                    metadata_lookup.get(symbol),
                    Stock,
                )
                requested_contracts[symbol] = contract
                requested_identities[symbol] = CandidateIdentity.from_contract(contract, fallback_symbol=symbol)
                diagnostics[symbol]["contract_build_source"] = source
                print(f"[SNAPSHOT][REQUEST] symbol={symbol} source={source} identity_key={requested_identities[symbol].key}")
            except Exception as exc:
                diagnostics[symbol]["exception"] = str(exc)
                print(f"[SNAPSHOT][FAIL] symbol={symbol} reason=build_contract:{exc}")
                continue

        if not requested_contracts:
            return snapshots

        try:
            qualified_contracts = qualify_contracts_resilient(
                ib,
                *requested_contracts.values(),
                timeout_seconds=self.batch_timeout_seconds,
                log_prefix="[EXECUTION][QUALIFY]",
            )
        except Exception as exc:
            for symbol in requested_contracts:
                diagnostics[symbol]["exception"] = f"qualify:{exc}"
                print(f"[SNAPSHOT][FAIL] symbol={symbol} reason=qualify:{exc}")
            return snapshots

        contracts_by_symbol: dict[str, Any] = {}
        for contract in (qualified_contracts or []):
            identity = CandidateIdentity.from_contract(contract)
            for alias in identity.aliases:
                contracts_by_symbol.setdefault(alias, contract)
            if identity.con_id not in {None, 0}:
                for symbol, requested_identity in requested_identities.items():
                    if requested_identity.con_id == identity.con_id:
                        contracts_by_symbol.setdefault(symbol, contract)
        ticker_by_symbol: dict[str, Any] = {}
        for symbol in resolved_symbols:
            contract = contracts_by_symbol.get(symbol)
            if contract is None:
                print(f"[SNAPSHOT][FAIL] symbol={symbol} reason=qualify_missing_contract")
                continue
            diagnostics[symbol]["qualified_ok"] = True
            qualified_identity = CandidateIdentity.from_contract(contract, fallback_symbol=symbol)
            diagnostics[symbol]["identity_key"] = qualified_identity.key
            print(
                f"[SNAPSHOT][QUALIFY_OK] symbol={symbol} conId={getattr(contract, 'conId', None)} identity_key={qualified_identity.key}"
            )
            try:
                ticker = ib.reqMktData(contract, genericTickList="", snapshot=True, regulatorySnapshot=False)
                ticker_by_symbol[symbol] = ticker
                diagnostics[symbol]["snapshot_requested"] = True
            except Exception as exc:
                diagnostics[symbol]["exception"] = f"reqMktData:{exc}"
                print(f"[SNAPSHOT][FAIL] symbol={symbol} reason=reqMktData:{exc}")
                continue

        deadline = time.time() + self.batch_timeout_seconds
        result_logged: set[str] = set()
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
                diagnostics[symbol].update(snapshots[symbol])
                has_data = any(value is not None for value in snapshots[symbol].values())
                diagnostics[symbol]["snapshot_received"] = has_data
                if has_data and symbol not in result_logged:
                    result_logged.add(symbol)
                    print(
                        "[SNAPSHOT][RESULT] "
                        f"symbol={symbol} identity_key={diagnostics[symbol].get('identity_key')} last={last_price} bid={bid} ask={ask} volume={volume}"
                    )
                if last_price is None and bid is None and ask is None and volume is None and close is None:
                    all_resolved = False
            if all_resolved:
                break

        for symbol in resolved_symbols:
            if diagnostics[symbol]["snapshot_requested"] and not diagnostics[symbol]["snapshot_received"]:
                print("[SNAPSHOT][FAIL] symbol={} reason=snapshot_empty".format(symbol))

        for symbol, contract in contracts_by_symbol.items():
            if symbol not in ticker_by_symbol:
                continue
            try:
                ib.cancelMktData(contract)
            except Exception as exc:
                diagnostics[symbol]["cancel_exception"] = str(exc)

        self.last_fetch_diagnostics = diagnostics

        return snapshots
