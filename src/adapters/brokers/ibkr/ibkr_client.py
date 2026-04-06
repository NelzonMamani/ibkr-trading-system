from __future__ import annotations

import threading
import time
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Dict, List, Optional, Tuple

from ibapi.client import EClient
from ibapi.common import TickerId
from ibapi.contract import Contract, ContractDetails
from ibapi.order import Order
from ibapi.wrapper import EWrapper

from src.domain.market_snapshot import MarketSnapshot
from src.ibkr.market_data_client import MarketDataSnapshot
from src.ibkr.read_only_guard import assert_read_only_allows


def _market_data_type_code(market_data_type: str) -> int:
    value = market_data_type.upper()
    if value == "FROZEN":
        return 2
    if value == "DELAYED":
        return 3
    if value == "DELAYED_FROZEN":
        return 4
    return 1


class IbkrClient(EWrapper, EClient):
    MAX_CLIENT_ID_RETRIES = 10
    NON_REJECTING_ORDER_WARNING_CODES = {2109}

    """
    Thin wrapper around ibapi for read-only operations.

    Responsibilities:
    - Connect/disconnect safely
    - Resolve contracts
    - Request market data snapshots
    - Report simple health status
    """

    def __init__(
        self,
        host: str,
        port: int,
        client_id: int,
        snapshot_timeout_seconds: int,
        market_data_type: str,
        readonly_enabled: bool,
    ):
        EWrapper.__init__(self)
        EClient.__init__(self, wrapper=self)
        self.host = host
        self.port = port
        self.client_id = client_id
        self.snapshot_timeout_seconds = snapshot_timeout_seconds
        self.market_data_type = market_data_type.upper()
        self.readonly_enabled = readonly_enabled
        self._req_id = 0
        self._lock = threading.Lock()
        self._contract_events: Dict[int, threading.Event] = {}
        self._contract_details: Dict[int, List[ContractDetails]] = {}
        self._market_events: Dict[int, threading.Event] = {}
        self._market_data: Dict[int, Dict[str, Optional[float]]] = {}
        self._historical_events: Dict[int, threading.Event] = {}
        self._historical_data: Dict[int, List[object]] = {}
        self._errors: Dict[int, Tuple[int, str]] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._connection_event = threading.Event()
        self._last_disconnect_reason: Optional[str] = None
        self._next_order_id: Optional[int] = None
        self._next_valid_order_id: Optional[int] = None
        self._last_reserved_order_id: Optional[int] = self._load_last_reserved_order_id()
        self._order_status_events: Dict[int, threading.Event] = {}
        self._order_status: Dict[int, Dict[str, Optional[float | int | str]]] = {}
        self._order_errors: Dict[int, Tuple[int, str]] = {}
        self._order_warnings: Dict[int, Tuple[int, str]] = {}
        self._exec_details_by_order: Dict[int, List[dict]] = {}
        self._commission_by_exec_id: Dict[str, float] = {}
        self._account_summary_events: Dict[int, threading.Event] = {}
        self._account_summary_rows: Dict[int, Dict[str, str]] = {}
        self._managed_accounts_event = threading.Event()
        self._managed_accounts: list[str] = []
        self._scanner_events: Dict[int, threading.Event] = {}
        self._scanner_rows: Dict[int, List[object]] = {}
        self._ticker_by_req_id: Dict[int, object] = {}
        self._req_id_by_contract_key: Dict[tuple, int] = {}
        self._market_update_event = threading.Event()
        self._request_type_by_req_id: Dict[int, str] = {}
        self._active_market_req_ids: set[int] = set()
        self._order_state_registry: Dict[int, dict] = {}
        self._execution_callbacks: list = []
        self._open_orders_snapshot: Dict[int, object] = {}
        self._open_orders_event = threading.Event()
        self._executions_snapshot: list[object] = []
        self._executions_event = threading.Event()
        self._positions_snapshot: Dict[str, object] = {}
        self._positions_event = threading.Event()
        self._open_order_count = 0
        self._order_status_count = 0
        self._exec_details_count = 0

    def _order_id_state_path(self) -> Path:
        return Path(os.environ.get("IBKR_ORDER_ID_STATE_PATH", Path.home() / ".ibkr_order_id_state.json"))

    def _load_last_reserved_order_id(self) -> Optional[int]:
        try:
            path = self._order_id_state_path()
            if not path.exists():
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
            value = int(payload.get("last_reserved_order_id"))
            return value if value > 0 else None
        except Exception:
            return None

    def _persist_last_reserved_order_id(self, order_id: int) -> None:
        try:
            path = self._order_id_state_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"last_reserved_order_id": int(order_id)}), encoding="utf-8")
        except Exception as exc:
            print(f"[IBKR][ORDER_ID_PERSIST_WARN] reason={exc}")


    def _ensure_order_state_registry(self) -> None:
        if not hasattr(self, "_order_state_registry") or self._order_state_registry is None:
            self._order_state_registry = {}

    def register_execution_callback(self, callback) -> None:
        if callback is None:
            return
        if callback in self._execution_callbacks:
            return
        self._execution_callbacks.append(callback)

    def _emit_execution_callback(self, payload: dict) -> None:
        for callback in list(self._execution_callbacks):
            try:
                callback(payload)
            except Exception as exc:
                print(f"[IBKR][CALLBACK_ERROR] reason={exc}")

    # --- Connection management ---
    def connect(self) -> None:  # type: ignore[override]
        if not self.host or self.port is None or int(self.port) <= 0:
            raise RuntimeError(
                "INVALID_RETRY_CONFIGURATION: host/port must be configured before IBKR connect"
            )

        print(
            "[IBKR][CLIENT] connect "
            f"host={self.host} port={self.port} client_id={self.client_id} "
            f"timeout={self.snapshot_timeout_seconds} market_data_type={self.market_data_type} "
            f"readonly={self.readonly_enabled}"
        )
        self._connection_event.clear()
        super().connect(self.host, self.port, int(self.client_id))

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        if not self._connection_event.wait(timeout=self.snapshot_timeout_seconds):
            self.disconnect()
            raise RuntimeError("IBKR connection timeout waiting for handshake")

        data_type_code = _market_data_type_code(self.market_data_type)
        print(f"[IBKR] Setting market data type={self.market_data_type} code={data_type_code}")
        self.reqMarketDataType(data_type_code)
        print(f"[IBKR] connection_status={self.isConnected()}")
        print(f"[IBKR][CONNECTED] Connected client_id={self.client_id}")

    def disconnect(self) -> None:  # type: ignore[override]
        print(f"[IBKR] Disconnecting client_id={self.client_id}")
        self._stop_event.set()
        try:
            super().disconnect()
        finally:
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2)
                if self._thread.is_alive():  # pragma: no cover - defensive
                    print("[IBKR] Warning: network thread still alive after disconnect.")
            print("[IBKR][DISCONNECTED] client disconnected")

    def ensure_connection(self) -> None:
        if not self.is_connected():
            print("[IBKR] Connection lost. Reconnecting.")
            self.connect()

    def is_connected(self) -> bool:
        return self.isConnected()

    def health(self) -> dict:
        last_error = None
        if self._errors:
            _, last_error = sorted(self._errors.items())[-1]
        return {
            "connected": self.is_connected(),
            "last_error": last_error,
            "last_disconnect_reason": self._last_disconnect_reason,
            "market_data_type": self.market_data_type,
            "connection_event_set": self._connection_event.is_set(),
        }

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                super().run()
            except Exception as exc:  # pragma: no cover - defensive
                print(f"[IBKR] Network loop error: {exc}")
                time.sleep(0.1)
            else:
                break

    # --- Request/response helpers ---
    def _next_req_id(self) -> int:
        with self._lock:
            self._req_id += 1
            return self._req_id

    def _register_request(self, req_id: int, request_type: str) -> None:
        if not hasattr(self, "_request_type_by_req_id"):
            self._request_type_by_req_id = {}
        with self._lock:
            self._request_type_by_req_id[req_id] = request_type

    def _cleanup_market_request(self, req_id: int) -> None:
        if not hasattr(self, "_active_market_req_ids"):
            self._active_market_req_ids = set()
        if not hasattr(self, "_request_type_by_req_id"):
            self._request_type_by_req_id = {}
        with self._lock:
            self._active_market_req_ids.discard(req_id)
            self._request_type_by_req_id.pop(req_id, None)
            self._market_events.pop(req_id, None)
            self._market_data.pop(req_id, None)
            self._ticker_by_req_id.pop(req_id, None)
            stale_keys = [key for key, value in self._req_id_by_contract_key.items() if value == req_id]
            for key in stale_keys:
                self._req_id_by_contract_key.pop(key, None)

    @staticmethod
    def _contract_key(contract) -> tuple:
        return (
            getattr(contract, "conId", None),
            getattr(contract, "symbol", None),
            getattr(contract, "secType", None),
            getattr(contract, "exchange", None),
            getattr(contract, "currency", None),
        )

    def _build_ticker(self, contract) -> object:
        return SimpleNamespace(
            contract=contract,
            bid=None,
            ask=None,
            last=None,
            close=None,
            volume=None,
            bidSize=None,
            askSize=None,
            lastSize=None,
        )

    def reserve_order_id(self) -> int:
        with self._lock:
            if self._next_valid_order_id is None:
                print("[CRITICAL] IBKR_NEXT_VALID_ID_NOT_READY")
                raise RuntimeError("IBKR order id not yet initialized.")
            order_id = int(self._next_valid_order_id)
            self._next_valid_order_id = int(order_id) + 1
            self._next_order_id = self._next_valid_order_id
            self._last_reserved_order_id = int(order_id)
            self._persist_last_reserved_order_id(int(order_id))
            print(f"[IBKR][ORDER_ID_SOURCE] source=IBKR_NEXT_VALID_ID order_id={order_id}")
            print(f"[IBKR][ORDER_ID_SEQUENCE] reserved={order_id} next={self._next_valid_order_id}")
            return order_id

    def submit_order(self, contract: Contract, order) -> int:
        if not self.is_connected():
            raise RuntimeError("IBKR client is not connected.")
        assert_read_only_allows("PLACE_ORDER")
        try:
            order.eTradeOnly = False
        except Exception:
            pass
        try:
            order.firmQuoteOnly = False
        except Exception:
            pass
        order_id = self.reserve_order_id()
        self._order_status_events[order_id] = threading.Event()
        self._exec_details_by_order[order_id] = []
        print(
            "[ORDER][SUBMIT] "
            f"symbol={getattr(contract, 'symbol', None)} order_id={order_id} "
            f"qty={getattr(order, 'totalQuantity', None)} side={getattr(order, 'action', None)} "
            f"order_type={getattr(order, 'orderType', None)}"
        )
        print("[EXECUTION][ORDER_OBJECT]")
        print(f"type={type(order)}")
        print(f"action={getattr(order, 'action', None)}")
        print(f"qty={getattr(order, 'totalQuantity', None)}")
        print(f"orderType={getattr(order, 'orderType', None)}")
        print(f"outsideRth={getattr(order, 'outsideRth', None)}")
        if not isinstance(order, Order):
            raise RuntimeError(f"INVALID_ORDER_OBJECT_TYPE: {type(order)}")
        if getattr(order, "action", None) not in ("BUY", "SELL"):
            raise RuntimeError("ORDER_OBJECT_CONTAMINATION_DETECTED")
        assert order.action in ("BUY", "SELL")
        assert int(order.totalQuantity) > 0
        assert order.orderType in ("MKT", "LMT")
        try:
            self.placeOrder(order_id, contract, order)
        except Exception as exc:
            print(f"[IBKR][PLACE_ORDER][ERROR] symbol={getattr(contract, 'symbol', None)} order_id={order_id} error={exc}")
            raise
        return order_id

    def wait_for_order_status(
        self, order_id: int, timeout_seconds: int
    ) -> Optional[Dict[str, Optional[float | int | str]]]:
        event = self._order_status_events.setdefault(order_id, threading.Event())
        event.wait(timeout=timeout_seconds)
        return self._order_status.get(order_id)

    def commission_for_order(self, order_id: int) -> Optional[float]:
        exec_details = self._exec_details_by_order.get(order_id, [])
        if not exec_details:
            return None
        total_commission = 0.0
        found = False
        for detail in exec_details:
            exec_id = detail.get("execId")
            if exec_id is None:
                continue
            commission = self._commission_by_exec_id.get(exec_id)
            if commission is None:
                continue
            found = True
            total_commission += commission
        return round(total_commission, 2) if found else None

    def get_order_error(self, order_id: int) -> Optional[Tuple[int, str]]:
        return self._order_errors.get(order_id)

    def get_order_warning(self, order_id: int) -> Optional[Tuple[int, str]]:
        return self._order_warnings.get(order_id)

    def openOrders(self, timeout_seconds: Optional[int] = None) -> list[object]:
        if not self.is_connected():
            return list(self._open_orders_snapshot.values())
        self._open_orders_event.clear()
        self._open_orders_snapshot = {}
        self.reqOpenOrders()
        self._open_orders_event.wait(timeout=timeout_seconds or self.snapshot_timeout_seconds)
        return list(self._open_orders_snapshot.values())

    def executions(self, timeout_seconds: Optional[int] = None) -> list[object]:
        if not self.is_connected():
            return list(self._executions_snapshot)
        from ibapi.execution import ExecutionFilter

        req_id = self._next_req_id()
        self._executions_event.clear()
        self._executions_snapshot = []
        self._register_request(req_id, "EXECUTIONS")
        self.reqExecutions(req_id, ExecutionFilter())
        self._executions_event.wait(timeout=timeout_seconds or self.snapshot_timeout_seconds)
        return list(self._executions_snapshot)

    def positions(self, timeout_seconds: Optional[int] = None) -> list[object]:
        if not self.is_connected():
            return list(self._positions_snapshot.values())
        self._positions_event.clear()
        self._positions_snapshot = {}
        self.reqPositions()
        self._positions_event.wait(timeout=timeout_seconds or self.snapshot_timeout_seconds)
        return list(self._positions_snapshot.values())


    def get_account_summary(self, timeout_seconds: Optional[int] = None) -> Dict[str, str]:
        if not self.is_connected():
            raise RuntimeError("IBKR client is not connected.")

        req_id = self._next_req_id()
        event = threading.Event()
        self._account_summary_events[req_id] = event
        self._account_summary_rows[req_id] = {}
        self._register_request(req_id, "ACCOUNT_SUMMARY")

        self.reqAccountSummary(req_id, "All", "AvailableFunds,NetLiquidation,BuyingPower")

        timeout = timeout_seconds or self.snapshot_timeout_seconds
        event.wait(timeout=timeout)
        self.cancelAccountSummary(req_id)
        return dict(self._account_summary_rows.get(req_id, {}))

    def get_primary_account(self, timeout_seconds: Optional[int] = None) -> Optional[str]:
        if not self.is_connected():
            raise RuntimeError("IBKR client is not connected.")

        self._managed_accounts_event.clear()
        self._managed_accounts = []
        self.reqManagedAccts()
        timeout = timeout_seconds or self.snapshot_timeout_seconds
        self._managed_accounts_event.wait(timeout=timeout)
        return self._managed_accounts[0] if self._managed_accounts else None

    # --- Contract resolution ---
    def resolve_contract(
        self, symbol: str, exchange: str = "SMART", currency: str = "USD"
    ) -> ContractDetails:
        if not self.is_connected():
            raise RuntimeError("IBKR client is not connected.")

        req_id = self._next_req_id()
        print(f"[IBKR] Resolving contract for symbol={symbol} req_id={req_id}")

        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = exchange
        contract.currency = currency

        event = threading.Event()
        self._contract_events[req_id] = event
        self._contract_details[req_id] = []
        self._register_request(req_id, "CONTRACT_DETAILS")

        self.reqContractDetails(req_id, contract)

        if not event.wait(timeout=self.snapshot_timeout_seconds):
            raise RuntimeError(f"Contract resolution failed for symbol={symbol} (timeout).")

        details = self._contract_details.get(req_id, [])
        if not details:
            raise RuntimeError(f"Contract resolution failed for symbol={symbol}")

        resolved = details[0]
        print(
            f"[IBKR] Resolved contract symbol={symbol} req_id={req_id} conId={resolved.contract.conId}"
        )
        return resolved

    def qualifyContracts(self, *contracts):
        """
        Compatibility wrapper for ib_insync-style APIs used by snapshot enrichment.
        """
        qualified = []
        for contract in contracts:
            symbol = getattr(contract, "symbol", None)
            if not symbol:
                continue
            try:
                details = self.resolve_contract(
                    symbol=symbol,
                    exchange=getattr(contract, "exchange", "SMART") or "SMART",
                    currency=getattr(contract, "currency", "USD") or "USD",
                )
                resolved_contract = details.contract
                for attr in ("conId", "primaryExchange", "tradingClass", "localSymbol"):
                    if hasattr(resolved_contract, attr):
                        setattr(contract, attr, getattr(resolved_contract, attr))
                qualified.append(contract)
            except Exception:
                continue
        return qualified

    def reqMktData(self, *args, **kwargs):  # type: ignore[override]
        """
        Compatibility wrapper supporting both:
        - ib_insync-style: reqMktData(contract, genericTickList="", snapshot=True, regulatorySnapshot=False)
        - raw ibapi-style: reqMktData(reqId, contract, genericTickList, snapshot, regulatorySnapshot, mktDataOptions)
        """
        if args and not isinstance(args[0], int):
            contract = args[0]
            generic_tick_list = kwargs.pop("genericTickList", "") if "genericTickList" in kwargs else (
                args[1] if len(args) > 1 else ""
            )
            snapshot = kwargs.pop("snapshot", True) if "snapshot" in kwargs else (
                args[2] if len(args) > 2 else True
            )
            regulatory_snapshot = (
                kwargs.pop("regulatorySnapshot", False)
                if "regulatorySnapshot" in kwargs
                else (args[3] if len(args) > 3 else False)
            )
            if kwargs:
                raise TypeError(f"Unexpected reqMktData kwargs: {sorted(kwargs.keys())}")

            req_id = self._next_req_id()
            self._market_events[req_id] = threading.Event()
            self._market_data[req_id] = {"bid": None, "ask": None, "last": None, "volume": None}
            ticker = self._build_ticker(contract)
            self._ticker_by_req_id[req_id] = ticker
            self._req_id_by_contract_key[self._contract_key(contract)] = req_id
            self._register_request(req_id, "MARKET_DATA")
            self._active_market_req_ids.add(req_id)
            super().reqMktData(
                req_id,
                contract,
                generic_tick_list,
                bool(snapshot),
                bool(regulatory_snapshot),
                [],
            )
            return ticker

        if args and isinstance(args[0], int):
            req_id = int(args[0])
            if len(args) >= 2 and not isinstance(args[1], int):
                contract = args[1]
                self._req_id_by_contract_key[self._contract_key(contract)] = req_id
                self._ticker_by_req_id.setdefault(req_id, self._build_ticker(contract))
            self._register_request(req_id, "MARKET_DATA")
            self._active_market_req_ids.add(req_id)
            return super().reqMktData(*args, **kwargs)

        raise TypeError("reqMktData requires either (contract, ...) or (reqId, contract, ...)")

    def cancelMktData(self, *args, **kwargs):  # type: ignore[override]
        req_id: Optional[int] = None
        active_market_req_ids = getattr(self, "_active_market_req_ids", set())
        if args and not isinstance(args[0], int):
            contract = args[0]
            req_id = self._req_id_by_contract_key.get(self._contract_key(contract))
            if req_id is None or req_id not in active_market_req_ids:
                return None
            result = super().cancelMktData(req_id)
            self._cleanup_market_request(req_id)
            return result
        if args and isinstance(args[0], int):
            req_id = int(args[0])
            if req_id not in active_market_req_ids:
                return None
            result = super().cancelMktData(req_id)
            self._cleanup_market_request(req_id)
            return result
        return super().cancelMktData(*args, **kwargs)

    def reqHistoricalData(self, *args, **kwargs):  # type: ignore[override]
        """
        Compatibility wrapper supporting:

        - ib_insync-style:
            reqHistoricalData(contract, endDateTime="", durationStr="25 D", ...)

        - ibapi-style:
            reqHistoricalData(reqId, contract, ...)
        """
        if args and not isinstance(args[0], int):
            contract = args[0]
            end_date_time = kwargs.pop("endDateTime", args[1] if len(args) > 1 else "")
            duration_str = kwargs.pop("durationStr", args[2] if len(args) > 2 else "25 D")
            bar_size_setting = kwargs.pop("barSizeSetting", args[3] if len(args) > 3 else "1 day")
            what_to_show = kwargs.pop("whatToShow", args[4] if len(args) > 4 else "TRADES")
            use_rth = kwargs.pop("useRTH", args[5] if len(args) > 5 else True)
            format_date = kwargs.pop("formatDate", args[6] if len(args) > 6 else 1)
            keep_up_to_date = kwargs.pop("keepUpToDate", args[7] if len(args) > 7 else False)
            chart_options = kwargs.pop("chartOptions", args[8] if len(args) > 8 else [])
            if kwargs:
                raise TypeError(f"Unexpected reqHistoricalData kwargs: {sorted(kwargs.keys())}")

            req_id = self._next_req_id()
            self._historical_events[req_id] = threading.Event()
            self._historical_data[req_id] = []
            self._register_request(req_id, "HISTORICAL_DATA")
            print(
                f"[IBKR][HIST_REQ] req_id={req_id} symbol={getattr(contract, 'symbol', None)}"
            )

            super().reqHistoricalData(
                req_id,
                contract,
                end_date_time,
                duration_str,
                bar_size_setting,
                what_to_show,
                int(bool(use_rth)),
                int(format_date),
                bool(keep_up_to_date),
                chart_options,
            )

            event = self._historical_events[req_id]
            start = time.time()
            timeout = self.snapshot_timeout_seconds

            while True:
                if event.is_set():
                    break

                data = self._historical_data.get(req_id, [])
                if data:
                    break

                if time.time() - start > timeout:
                    break

                time.sleep(0.01)

            data = self._historical_data.get(req_id, [])
            if not data:
                print(f"[IBKR][HIST_EMPTY_FINAL] req_id={req_id}")
            else:
                print(f"[IBKR][HIST_RETURN] req_id={req_id} bars={len(data)}")

            return list(data)

        if args and isinstance(args[0], int):
            req_id = int(args[0])
            self._historical_events.setdefault(req_id, threading.Event())
            self._historical_data.setdefault(req_id, [])
            self._register_request(req_id, "HISTORICAL_DATA")
            return super().reqHistoricalData(*args, **kwargs)

        raise TypeError(
            "reqHistoricalData requires either (contract, ...) or (reqId, contract, ...)"
        )

    def waitOnUpdate(self, timeout: float = 0.0) -> bool:
        updated = self._market_update_event.wait(timeout=timeout)
        if updated:
            self._market_update_event.clear()
        return bool(updated)

    def contractDetails(self, reqId: int, contractDetails: ContractDetails):  # type: ignore[override]
        self._contract_details.setdefault(reqId, []).append(contractDetails)

    def contractDetailsEnd(self, reqId: int):  # type: ignore[override]
        event = self._contract_events.get(reqId)
        if event:
            event.set()
        getattr(self, "_request_type_by_req_id", {}).pop(reqId, None)

    # --- Market data snapshot ---
    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        details = self.resolve_contract(symbol)
        contract = details.contract
        req_id = self._next_req_id()
        print(f"[IBKR] Requesting market snapshot symbol={symbol} req_id={req_id} conId={contract.conId}")

        event = threading.Event()
        self._market_events[req_id] = event
        self._market_data[req_id] = {
            "bid": None,
            "ask": None,
            "last": None,
            "volume": None,
        }
        self._register_request(req_id, "MARKET_SNAPSHOT")
        self._active_market_req_ids.add(req_id)

        self.reqMktData(
            req_id,
            contract,
            "",
            True,
            False,
            [],
        )

        event.wait(timeout=self.snapshot_timeout_seconds)
        self.cancelMktData(req_id)

        prices = self._market_data.get(req_id, {})
        snapshot = MarketSnapshot(
            symbol=symbol,
            bid=prices.get("bid"),
            ask=prices.get("ask"),
            last=prices.get("last"),
            volume=prices.get("volume"),
            asof_utc=datetime.now(timezone.utc),
            market_data_type=self.market_data_type,
        )
        if event.is_set():
            print(
                f"[IBKR] Snapshot symbol={symbol} req_id={req_id} bid={snapshot.bid} ask={snapshot.ask} last={snapshot.last}"
            )
        else:
            print(
                f"[IBKR] Snapshot timeout symbol={symbol} req_id={req_id} (bid/ask/last may be None)"
            )
        return snapshot

    def snapshot_stock(self, symbol: str) -> MarketDataSnapshot:
        """Compatibility wrapper matching MarketDataClient snapshot contract."""
        snapshot = self.get_market_snapshot(symbol)
        return MarketDataSnapshot(
            symbol=symbol,
            bid=snapshot.bid,
            ask=snapshot.ask,
            last=snapshot.last,
            bid_size=None,
            ask_size=None,
            last_size=None,
            volume=snapshot.volume,
            vwap=None,
            open=None,
            high=None,
            low=None,
            close=snapshot.last,
            change_percent=None,
            spread=(snapshot.ask - snapshot.bid)
            if snapshot.ask is not None and snapshot.bid is not None
            else None,
            timestamp_utc=snapshot.asof_utc.isoformat(),
            data_quality_flags=[],
        )

    def snapshot_for_symbol(self, symbol: str) -> MarketDataSnapshot:
        return self.snapshot_stock(symbol)


    def reqScannerData(self, subscription):
        """
        Forward scanner request to underlying IB client.
        """
        if hasattr(self, "ib") and self.ib is not None:
            return self.ib.reqScannerData(subscription)

        if not self.is_connected():
            raise RuntimeError("IBKR client is not connected.")

        req_id = self._next_req_id()
        event = threading.Event()
        self._scanner_events[req_id] = event
        self._scanner_rows[req_id] = []
        self._register_request(req_id, "SCANNER_DATA")

        self.reqScannerSubscription(req_id, subscription, [], [])
        event.wait(timeout=self.snapshot_timeout_seconds)
        self.cancelScannerSubscription(req_id)
        return list(self._scanner_rows.get(req_id, []))

    def cancelScannerSubscription(self, reqId):
        """
        Forward scanner cancellation to underlying IB client.
        """
        if hasattr(self, "ib") and self.ib is not None:
            return self.ib.cancelScannerSubscription(reqId)
        return super().cancelScannerSubscription(reqId)

    def tickPrice(
        self,
        reqId: TickerId,
        tickType: int,
        price: float,
        attrib,
    ):  # type: ignore[override]
        prices = self._market_data.setdefault(
            reqId, {"bid": None, "ask": None, "last": None, "volume": None}
        )
        if tickType == 1:
            prices["bid"] = price
        elif tickType == 2:
            prices["ask"] = price
        elif tickType == 4:
            prices["last"] = price
        elif tickType == 9:
            prices["last"] = prices.get("last") if prices.get("last") is not None else price

        ticker = self._ticker_by_req_id.get(reqId)
        if ticker is not None:
            if tickType == 1:
                ticker.bid = price
            elif tickType == 2:
                ticker.ask = price
            elif tickType == 4:
                ticker.last = price
            elif tickType == 9:
                ticker.close = price

        if any(value is not None for value in prices.values()):
            event = self._market_events.get(reqId)
            if event:
                event.set()
            self._market_update_event.set()

    def tickSize(
        self,
        reqId: TickerId,
        tickType: int,
        size: float,
    ):  # type: ignore[override]
        prices = self._market_data.setdefault(
            reqId, {"bid": None, "ask": None, "last": None, "volume": None}
        )
        if tickType in (8, 37):
            prices["volume"] = float(size)

        ticker = self._ticker_by_req_id.get(reqId)
        if ticker is not None:
            if tickType in (0, 66):
                ticker.bidSize = size
            elif tickType in (3, 69):
                ticker.askSize = size
            elif tickType in (5, 71):
                ticker.lastSize = size
            elif tickType in (8, 37):
                ticker.volume = float(size)

        if any(value is not None for value in prices.values()):
            event = self._market_events.get(reqId)
            if event:
                event.set()
            self._market_update_event.set()

    def historicalData(self, reqId: int, bar):  # type: ignore[override]
        self._historical_data.setdefault(reqId, []).append(bar)

    def historicalDataEnd(self, reqId: int, start: str, end: str):  # type: ignore[override]
        print(
            f"[IBKR][HIST_DONE] req_id={reqId} bars={len(self._historical_data.get(reqId, []))}"
        )
        event = self._historical_events.get(reqId)
        if event:
            event.set()
        getattr(self, "_request_type_by_req_id", {}).pop(reqId, None)

    def accountSummary(
        self,
        reqId: int,
        account: str,
        tag: str,
        value: str,
        currency: str,
    ):  # type: ignore[override]
        rows = self._account_summary_rows.setdefault(reqId, {})
        rows[tag] = value

    def accountSummaryEnd(self, reqId: int):  # type: ignore[override]
        event = self._account_summary_events.get(reqId)
        if event:
            event.set()
        getattr(self, "_request_type_by_req_id", {}).pop(reqId, None)

    def managedAccounts(self, accountsList: str):  # type: ignore[override]
        self._managed_accounts = [
            account.strip() for account in accountsList.split(",") if account.strip()
        ]
        self._managed_accounts_event.set()


    def scannerData(
        self,
        reqId: int,
        rank: int,
        contractDetails: ContractDetails,
        distance: str,
        benchmark: str,
        projection: str,
        legsStr: str,
    ):  # type: ignore[override]
        from types import SimpleNamespace

        self._scanner_rows.setdefault(reqId, []).append(
            SimpleNamespace(
                rank=rank,
                contractDetails=contractDetails,
                distance=distance,
                benchmark=benchmark,
                projection=projection,
                legsStr=legsStr,
            )
        )

    def scannerDataEnd(self, reqId: int):  # type: ignore[override]
        event = self._scanner_events.get(reqId)
        if event:
            event.set()
        getattr(self, "_request_type_by_req_id", {}).pop(reqId, None)

    # --- Error handling ---
    def error(self, reqId: int, errorCode: int, errorString: str):  # type: ignore[override]
        request_type_by_req_id = getattr(self, "_request_type_by_req_id", {})
        request_type = request_type_by_req_id.get(reqId)
        unknown_market_req = int(errorCode) == 300 and reqId >= 0 and request_type is None
        if unknown_market_req:
            print(
                "[IBKR][WARN] "
                f"code=300 reqId={reqId} request_type=UNKNOWN reason={errorString} action=downgraded"
            )
            return
        fractional_unsupported_warning = int(errorCode) == 2176
        is_non_rejecting_order_warning = (
            errorCode in self.NON_REJECTING_ORDER_WARNING_CODES and reqId in self._order_status_events
        )
        if reqId >= 0:
            self._errors[reqId] = (errorCode, errorString)
            if reqId in self._order_status_events:
                existing = self._order_status.get(reqId, {})
                if is_non_rejecting_order_warning:
                    self._order_warnings[reqId] = (errorCode, errorString)
                    self._order_status[reqId] = {
                        **existing,
                        "broker_warning_code": str(errorCode),
                        "broker_warning_message": errorString,
                    }
                else:
                    self._order_errors[reqId] = (errorCode, errorString)
                    self._order_status[reqId] = {
                        **existing,
                        "status": existing.get("status", "REJECTED"),
                        "broker_error_code": str(errorCode),
                        "broker_error_message": errorString,
                    }
                    self._order_status_events[reqId].set()
            if reqId in self._contract_events:
                self._contract_events[reqId].set()
            if reqId in self._market_events:
                self._market_events[reqId].set()
                self._market_update_event.set()
            if reqId in self._historical_events:
                self._historical_events[reqId].set()
            if reqId in self._account_summary_events:
                self._account_summary_events[reqId].set()
            if reqId in self._scanner_events:
                self._scanner_events[reqId].set()
        if fractional_unsupported_warning:
            print(
                "[IBKR][WARN] "
                f"type=FRACTIONAL_SHARE_UNSUPPORTED order_id={reqId} code={errorCode} message={errorString}"
            )
            message = (
                "[IBKR][WARN] "
                f"type=FRACTIONAL_SHARE_UNSUPPORTED reqId={reqId} code={errorCode} msg={errorString}"
            )
        elif is_non_rejecting_order_warning:
            print(f"[IBKR][WARN] order_id={reqId} code={errorCode} message={errorString}")
            message = f"[IBKR] Warning reqId={reqId} code={errorCode} msg={errorString}"
        else:
            message = f"[IBKR] Error reqId={reqId} code={errorCode} msg={errorString}"
        if not fractional_unsupported_warning:
            print(
                "[ORDER][ERROR] "
                f"order_id={reqId} code={errorCode} message={errorString}"
            )
            print(
                "[IBKR][ORDER_ERROR] "
                f"order_id={reqId} code={errorCode} message={errorString}"
            )
        print(message)
        if errorCode == 326:
            print("[IBKR][CONNECT_FAIL] code=326 client id already in use")
        if errorCode in (1100, 1300):  # connection/pacing
            self._last_disconnect_reason = f"code={errorCode} msg={errorString}"
            self._connection_event.clear()

    def nextValidId(self, orderId: int):  # type: ignore[override]
        broker_next = int(orderId)
        chosen = broker_next
        if self._last_reserved_order_id is not None and broker_next <= int(self._last_reserved_order_id):
            chosen = int(self._last_reserved_order_id) + 1
            print(
                "[IBKR][ORDER_ID_REBASE] "
                f"broker_next={broker_next} local_last={self._last_reserved_order_id} chosen={chosen}"
            )
        self._next_valid_order_id = chosen
        self._next_order_id = chosen
        print(f"[IBKR][NEXT_VALID_ID] order_id={chosen}")
        self._connection_event.set()

    def orderStatus(
        self,
        orderId: int,
        status: str,
        filled: float,
        remaining: float,
        avgFillPrice: float,
        permId: int,
        parentId: int,
        lastFillPrice: float,
        clientId: int,
        whyHeld: str,
        mktCapPrice: float,
    ):  # type: ignore[override]
        if not hasattr(self, "_order_status_count"):
            self._order_status_count = 0
        self._order_status_count += 1
        print(
            "[IBKR][CALLBACK_RAW] "
            f"event=orderStatus order_id={orderId} status={status} filled={filled} remaining={remaining}"
        )
        print(
            "[IBKR][ORDER_STATUS] "
            f"order_id={orderId} "
            f"status={status} "
            f"filled={filled} "
            f"remaining={remaining}"
        )
        self._ensure_order_state_registry()
        existing = self._order_status.get(orderId, {})
        self._order_status[orderId] = {
            **existing,
            "status": status,
            "filled": int(filled),
            "remaining": int(remaining),
            "avgFillPrice": avgFillPrice,
            "lastFillPrice": lastFillPrice,
        }
        print(
            "[ORDER][STATUS] "
            f"order_id={orderId} status={status} filled={int(filled)} remaining={int(remaining)}"
        )
        print(
            "[IBKR][ORDER_STATUS] "
            f"order_id={orderId} status={status} filled={int(filled)} remaining={int(remaining)} "
            f"avg_fill_price={avgFillPrice} last_fill_price={lastFillPrice}"
        )
        print(
            "[EXECUTION][ORDER_TRACK] "
            f"order_id={orderId} status={status} filled={int(filled)} remaining={int(remaining)}"
        )
        open_order_row = self._open_orders_snapshot.get(orderId)
        ack_order = getattr(open_order_row, "order", None) if open_order_row is not None else None
        outside_rth = getattr(ack_order, "outsideRth", None)
        outside_rth_label = outside_rth if outside_rth is not None else "<unknown>"
        print(
            "[EXECUTION][ACK_CONFIRMED] "
            f"order_id={orderId} symbol={getattr(getattr(open_order_row, 'contract', None), 'symbol', None)} "
            f"outsideRth={outside_rth_label} status={status}"
        )
        self._emit_execution_callback(
            {
                "event_type": "orderStatus",
                "orderId": orderId,
                "status": status,
                "filled": int(filled),
                "remaining": int(remaining),
                "avgFillPrice": avgFillPrice,
                "lastFillPrice": lastFillPrice,
            }
        )
        event = self._order_status_events.setdefault(orderId, threading.Event())
        event.set()

    def execDetails(self, reqId, contract, execution):  # type: ignore[override]
        if not hasattr(self, "_exec_details_count"):
            self._exec_details_count = 0
        self._exec_details_count += 1
        self._ensure_order_state_registry()
        print(
            "[IBKR][CALLBACK_RAW] "
            f"event=execDetails order_id={getattr(execution, 'orderId', None)} "
            f"exec_id={getattr(execution, 'execId', None)} symbol={getattr(contract, 'symbol', None)}"
        )
        print(
            "[IBKR][EXEC_DETAILS] "
            f"symbol={getattr(contract, 'symbol', None)} "
            f"exec_id={getattr(execution, 'execId', None)} "
            f"order_id={getattr(execution, 'orderId', None)} "
            f"shares={getattr(execution, 'shares', None)} "
            f"price={getattr(execution, 'price', None)}"
        )
        order_id = getattr(execution, "orderId", None)
        if order_id is None:
            return
        details = {
            "execId": getattr(execution, "execId", None),
            "time": getattr(execution, "time", None),
            "price": getattr(execution, "price", None),
            "shares": getattr(execution, "shares", None),
        }
        print(
            "[ORDER][FILL] "
            f"symbol={getattr(contract, 'symbol', None)} order_id={order_id} "
            f"shares={getattr(execution, 'shares', None)} avg_price={getattr(execution, 'price', None)}"
        )
        print(
            "[IBKR][ORDER_FILL] "
            f"symbol={getattr(contract, 'symbol', None)} order_id={order_id} "
            f"shares={getattr(execution, 'shares', None)} avg_price={getattr(execution, 'price', None)}"
        )
        print(
            "[EXECUTION][ORDER_TRACK] "
            f"order_id={order_id} status=Filled shares={getattr(execution, 'shares', None)}"
        )
        self._exec_details_by_order.setdefault(order_id, []).append(details)
        self._executions_snapshot.append(
            SimpleNamespace(contract=contract, execution=execution, orderId=order_id)
        )
        self._emit_execution_callback(
            {
                "event_type": "execDetails",
                "orderId": order_id,
                "contract": contract,
                "execution": execution,
                "shares": getattr(execution, "shares", None),
                "price": getattr(execution, "price", None),
                "time": getattr(execution, "time", None),
            }
        )

    def openOrder(self, orderId, contract, order, orderState):  # type: ignore[override]
        if not hasattr(self, "_open_order_count"):
            self._open_order_count = 0
        self._open_order_count += 1
        self._ensure_order_state_registry()
        print(f"[ORDER][OPEN] order_id={orderId} symbol={getattr(contract, 'symbol', None)}")
        print(
            "[IBKR][CALLBACK_RAW] "
            f"event=openOrder order_id={orderId} symbol={getattr(contract, 'symbol', None)} "
            f"status={getattr(orderState, 'status', None)}"
        )
        outside_rth = getattr(order, "outsideRth", None)
        print(
            "[IBKR][ACK] "
            f"order_id={orderId} symbol={getattr(contract, 'symbol', None)} "
            f"orderType={getattr(order, 'orderType', None)} tif={getattr(order, 'tif', None)} outsideRth={outside_rth}"
        )
        outside_rth_label = outside_rth if outside_rth is not None else "<unknown>"
        print(
            "[EXECUTION][ACK_CONFIRMED] "
            f"order_id={orderId} symbol={getattr(contract, 'symbol', None)} "
            f"outsideRth={outside_rth_label} status={getattr(orderState, 'status', None)}"
        )
        row = SimpleNamespace(orderId=orderId, contract=contract, order=order, orderState=orderState)
        self._open_orders_snapshot[orderId] = row
        self._emit_execution_callback(
            {
                "event_type": "openOrder",
                "orderId": orderId,
                "contract": contract,
                "order": order,
                "orderState": orderState,
            }
        )

    def commissionReport(self, commissionReport):  # type: ignore[override]
        exec_id = getattr(commissionReport, "execId", None)
        commission = getattr(commissionReport, "commission", None)
        print(
            "[IBKR][CALLBACK_RAW] "
            f"event=commissionReport exec_id={exec_id} commission={commission}"
        )
        if exec_id is None or commission is None:
            return
        self._commission_by_exec_id[exec_id] = float(commission)
        self._emit_execution_callback(
            {
                "event_type": "commissionReport",
                "execId": exec_id,
                "commission": float(commission),
                "commissionReport": commissionReport,
            }
        )

    def openOrderEnd(self):  # type: ignore[override]
        print("[IBKR][CALLBACK_RAW] event=openOrderEnd")
        self._open_orders_event.set()

    def execDetailsEnd(self, reqId):  # type: ignore[override]
        print(f"[IBKR][CALLBACK_RAW] event=execDetailsEnd req_id={reqId}")
        self._executions_event.set()
        getattr(self, "_request_type_by_req_id", {}).pop(reqId, None)

    def position(self, account, contract, pos, avgCost):  # type: ignore[override]
        symbol = str(getattr(contract, "symbol", "") or "").upper()
        print(
            "[IBKR][CALLBACK_RAW] "
            f"event=position account={account} symbol={symbol} pos={pos} avg_cost={avgCost}"
        )
        if not symbol:
            return
        self._positions_snapshot[symbol] = SimpleNamespace(
            account=account, contract=contract, symbol=symbol, position=pos, avgCost=avgCost
        )
        self._emit_execution_callback(
            {
                "event_type": "position",
                "account": account,
                "contract": contract,
                "symbol": symbol,
                "position": pos,
                "avgCost": avgCost,
            }
        )

    def positionEnd(self):  # type: ignore[override]
        print("[IBKR][CALLBACK_RAW] event=positionEnd")
        self._positions_event.set()
        self._emit_execution_callback({"event_type": "positionEnd"})

    def connectionClosed(self):  # type: ignore[override]
        self._last_disconnect_reason = "connectionClosed"
        self._connection_event.clear()
        print("[IBKR] Connection closed by broker.")
