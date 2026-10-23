from __future__ import annotations

from src.core.acquisition import AcquisitionCancelled, AcquisitionDeadlineExceeded, checkpoint, wait_event, bounded_timeout

import threading
import math
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

from src.ibkr.quote_diagnostics import QuoteDiagnostics
from src.ibkr.position_snapshot import BrokerPositionResult
from src.domain.market_snapshot import MarketSnapshot
from src.ibkr.market_data_client import (
    MarketDataSnapshot,
    _clean,
    _market_data_type_flags,
    _returned_market_data_type,
    _resolve_snapshot_timestamp,
    _record_field_receipt,
    _snapshot_authority_metadata,
)
from src.ibkr.read_only_guard import assert_read_only_allows
from src.ibkr.evidence_safety import register_account, sanitize


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
    ORDER_ONLY_CALLBACK_CODES = {201, 202, 399}

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
        self._quote_trace = QuoteDiagnostics(client_id)
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
        self._broker_error_events: list[dict] = []
        self._request_context_by_req_id: dict[int, dict] = {}
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
        self._position_queries: dict[int, dict] = {}
        self._position_connection_epoch = 0
        self._position_transport_available = False
        self._position_upstream_lost = False
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

    def cached_order_status(self, order_id: int) -> dict:
        """Read callback-owned facts only; does not request data or connect."""
        return dict(self._order_status.get(int(order_id), {}))

    def register_execution_callback(self, callback, *, internal_reconciliation=False) -> None:
        if callback is None:
            return
        if callback in self._execution_callbacks:
            return
        self._execution_callbacks.append(callback)
        if internal_reconciliation:
            if not hasattr(self, "_internal_execution_callbacks"):
                self._internal_execution_callbacks = set()
            self._internal_execution_callbacks.add(callback)

    def register_reconciliation_callback(self, callback) -> None:
        self.register_execution_callback(callback, internal_reconciliation=True)

    def _emit_execution_callback(self, payload: dict) -> None:
        for callback in list(self._execution_callbacks):
            try:
                callback(payload if callback in getattr(self, "_internal_execution_callbacks", set()) else sanitize(payload))
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
        self._position_upstream_lost = False
        super().connect(self.host, self.port, int(self.client_id))

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        if not wait_event(self._connection_event, self.snapshot_timeout_seconds):
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
        self._invalidate_position_queries()
        try:
            try:
                with self._lock:
                    for context in self._request_context_by_req_id.values():
                        context.pop("reference_response", None)
                        context.pop("reference_deadline", None)
            finally:
                # Metadata cleanup must never prevent socket disconnection.
                super().disconnect()
        finally:
            thread = self._thread
            if thread and thread.is_alive():
                if thread is threading.current_thread():
                    print("[IBKR] Disconnect called from network thread; skipping self-join.")
                else:
                    thread.join(timeout=2)
                    if thread.is_alive():  # pragma: no cover - defensive
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
                if self._stop_event.is_set() and "cannot join current thread" in str(exc):
                    break
                print(f"[IBKR] Network loop error: {exc}")
                time.sleep(0.1)
            else:
                break

    # --- Request/response helpers ---
    def _next_req_id(self) -> int:
        with self._lock:
            # IBKR errors carry one numeric ID for both requests and orders.
            # Allocate both through the existing authorities under this lock,
            # always above IDs already reserved by either side. Positive gaps in
            # order IDs are legal; no guessed error-code ownership is needed.
            self._req_id = max(self._req_id, self._last_reserved_order_id or 0,
                               self._next_valid_order_id or 0,
                               max(self._order_status_events, default=0),
                               max(self._order_state_registry, default=0)) + 1
            return self._req_id

    def _register_request(self, req_id: int, request_type: str, contract=None) -> None:
        if not hasattr(self, "_request_type_by_req_id"):
            self._request_type_by_req_id = {}
        with self._lock:
            if (req_id in self._order_status_events or req_id in self._order_state_registry
                    or req_id == self._last_reserved_order_id):
                raise RuntimeError("Request ID is already reserved for an order.")
            # Raw compatibility calls may supply their own positive request ID.
            # Registration must reserve that ID before a concurrent order can.
            self._req_id = max(self._req_id, req_id)
            if request_type == "CONTRACT_DETAILS" and self._stop_event.is_set():
                raise RuntimeError("Contract resolution stopped during disconnect.")
            self._request_type_by_req_id[req_id] = request_type
            if not hasattr(self, "_request_context_by_req_id"):
                self._request_context_by_req_id = {}
            self._request_context_by_req_id[req_id] = {
                "request_type": request_type,
                "symbol": getattr(contract, "symbol", None),
                "con_id": getattr(contract, "conId", None),
            }
            if request_type == "CONTRACT_DETAILS":
                # Register eligibility atomically with the context that disconnect
                # invalidates under this same lock. Never re-arm it after cleanup.
                self._request_context_by_req_id[req_id]["reference_deadline"] = (
                    time.monotonic() + self.snapshot_timeout_seconds
                )
            # Retain bounded context for broker errors arriving after cleanup.
            if len(self._request_context_by_req_id) > 1024:
                self._request_context_by_req_id.pop(next(iter(self._request_context_by_req_id)))

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
            open=None,
            high=None,
            low=None,
            requestedMarketDataType=getattr(self, "_requested_market_data_type_code", _market_data_type_code(self.market_data_type)),
            marketDataType=None,
            marketDataTypeConfirmed=False,
            marketDataTypeReceivedAt=None,
            reqId=None,
            snapshotEnd=False,
            receivedAt=None,
            lastTime=None,
            requestStartedAt=datetime.now(timezone.utc),
            snapshotEndedAt=None,
            fieldReceivedAt={},
            brokerErrors=[],
        )

    def _request_id_conflicted(self, req_id: int) -> bool:
        return bool(getattr(self, "_order_state_registry", {}).get(req_id, {}).get("request_id_conflict"))

    def _raise_if_request_id_conflicted(self, req_id: int) -> None:
        if self._request_id_conflicted(req_id):
            raise RuntimeError("Request/order ID ownership is ambiguous.")

    def _observe_order_id(self, order_id: int) -> None:
        """Reserve observed IDs; quarantine collisions without inventing error ownership."""
        self._ensure_order_state_registry()
        with self._lock:
            known_order = order_id in self._order_status_events
            self._order_status_events.setdefault(order_id, threading.Event())
            request_type = getattr(self, "_request_type_by_req_id", {}).pop(order_id, None)
            position_query = self._position_queries.get(order_id)
            context = getattr(self, "_request_context_by_req_id", {}).get(order_id, {})
            # Completed request metadata and still-held request maps also expose
            # ambiguity. An unseen lower ID may be a retired request whose bounded
            # context has already been evicted; keep that case conservative.
            possible_request = (request_type is not None or position_query is not None
                                or bool(context.get("request_type"))
                                or (not known_order and order_id <= self._req_id))
            if not possible_request:
                return
            # Generic IBKR errors have no request-vs-order discriminator. Retain
            # this ambiguity in the existing order-ID registry even after request
            # metadata is evicted; never attribute a late shared-ID error to either.
            self._order_state_registry.setdefault(order_id, {})["request_id_conflict"] = True
            context = self._request_context_by_req_id.get(order_id, {})
            context["reference_error"] = (-1, "Request/order ID ownership is ambiguous.")
            context.pop("reference_response", None)
            context.pop("reference_deadline", None)
            if position_query is not None:
                position_query["status"] = "FAILED"
                position_query["event"].set()
            for events in (self._market_events, self._historical_events, self._contract_events,
                           self._scanner_events, self._account_summary_events):
                event = events.pop(order_id, None)
                if event is not None:
                    event.set()  # Release waiters to raise unavailable, not complete.
            for rows in (self._market_data, self._historical_data, self._contract_details,
                         self._scanner_rows, self._account_summary_rows):
                rows.pop(order_id, None)
            self._active_market_req_ids.discard(order_id)
            ticker = self._ticker_by_req_id.get(order_id)
            if ticker is not None:
                ticker.snapshotEnd = False
                for field in ("bid", "ask", "last", "close", "open", "high", "low", "volume"):
                    setattr(ticker, field, None)
                ticker.brokerErrors.append({"code": -1, "message": "REQUEST_ORDER_ID_CONFLICT"})
            if request_type == "EXECUTIONS":
                self._executions_snapshot = []
                self._executions_event.set()

    def reserve_order_id(self) -> int:
        with self._lock:
            if self._next_valid_order_id is None:
                print("[CRITICAL] IBKR_NEXT_VALID_ID_NOT_READY")
                raise RuntimeError("IBKR order id not yet initialized.")
            order_id = max(int(self._next_valid_order_id), self._req_id + 1,
                           (self._last_reserved_order_id or 0) + 1,
                           max(self._order_status_events, default=0) + 1)
            self._next_valid_order_id = int(order_id) + 1
            self._next_order_id = self._next_valid_order_id
            self._last_reserved_order_id = int(order_id)
            self._order_status_events.setdefault(order_id, threading.Event())
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
        assert order.orderType in ("MKT", "LMT", "STP")
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
        with self._lock:
            self._raise_if_request_id_conflicted(req_id)
            return list(self._executions_snapshot)

    def position_snapshot(self, timeout_seconds: Optional[float] = None) -> BrokerPositionResult:
        # The legacy reqPositions stream has no correlation token. Never cancel or
        # reassign its subscription here. reqPositionsMulti has request-scoped end
        # markers and cancellation, on the SAME canonical socket/account authority.
        with self._lock:
            accounts = tuple(self._managed_accounts)
            if not self.is_connected() or self._stop_event.is_set() or not self._position_transport_available:
                return BrokerPositionResult(status="DISCONNECTED")
            if len(accounts) != 1 or not accounts[0]:
                return BrokerPositionResult(status="ACCOUNT_SCOPE_UNAVAILABLE")
            epoch = self._position_connection_epoch
        req_id = self._next_req_id()
        timeout = self.snapshot_timeout_seconds if timeout_seconds is None else timeout_seconds
        context = {"account": accounts[0], "rows": {}, "event": threading.Event(),
                   "status": "PARTIAL", "completed_at": None, "epoch": epoch,
                   "deadline": time.monotonic() + max(0, timeout)}
        with self._lock:
            if (epoch != self._position_connection_epoch or not self.is_connected()
                    or self._stop_event.is_set() or not self._position_transport_available):
                return BrokerPositionResult(status="DISCONNECTED")
            self._position_queries[req_id] = context
        try:
            self._register_request(req_id, "POSITIONS_MULTI")
            self.reqPositionsMulti(req_id, accounts[0], "")
            context["event"].wait(timeout=max(0, timeout))
            with self._lock:
                if epoch != self._position_connection_epoch or not self.is_connected():
                    context["status"] = "DISCONNECTED"
                elif tuple(self._managed_accounts) != accounts:
                    context["status"] = "WRONG_ACCOUNT"
                elif context["status"] == "PARTIAL":
                    context["status"] = "TIMEOUT"
                elif context["status"] == "COMPLETE":
                    from src.config.runtime_config import get_ibkr_snapshot_max_age_seconds
                    age = (datetime.now(timezone.utc) - context["completed_at"]).total_seconds()
                    if not 0 <= age <= get_ibkr_snapshot_max_age_seconds():
                        context["status"] = "STALE"
                return BrokerPositionResult(tuple(context["rows"].values()), context["status"],
                                            context["account"], context["completed_at"])
        except Exception:
            return BrokerPositionResult(status="FAILED", account=accounts[0])
        finally:
            # Retire before cancellation: even synchronous/late callbacks cannot
            # mutate returned evidence or complete another query.
            with self._lock:
                self._position_queries.pop(req_id, None)
                self._request_type_by_req_id.pop(req_id, None)
            try:
                self.cancelPositionsMulti(req_id)
            except Exception:
                pass

    def positions(self, timeout_seconds: Optional[int] = None) -> list[object]:
        result = self.position_snapshot(timeout_seconds)
        if result.status != "COMPLETE":
            raise RuntimeError(f"Broker position truth unavailable: {result.status}")
        return list(result.rows)

    def _invalidate_position_queries(self, *, clear_account_scope: bool = True) -> None:
        with self._lock:
            self._position_connection_epoch += 1
            self._position_transport_available = False
            self._position_upstream_lost = True
            if clear_account_scope:
                self._managed_accounts = []
            for context in self._position_queries.values():
                context["status"] = "DISCONNECTED"
                context["event"].set()

    def positionMulti(self, reqId, account, modelCode, contract, pos, avgCost):
        with self._lock:
            context = self._position_queries.get(reqId)
            if context is None or context["status"] != "PARTIAL":
                return
            if account != context["account"] or modelCode:
                context["status"] = "WRONG_ACCOUNT"
                context["event"].set()
                return
            try:
                valid_quantity = math.isfinite(float(pos))
            except (TypeError, ValueError, OverflowError):
                valid_quantity = False
            if not valid_quantity:
                context["status"] = "FAILED"
                context["event"].set()
                return
            symbol = str(getattr(contract, "symbol", "") or "").strip().upper()
            if not symbol:
                context["status"] = "FAILED"
                context["event"].set()
                return
            context["rows"][(account, getattr(contract, "conId", 0), symbol)] = SimpleNamespace(
                account=account, contract=contract, symbol=symbol, position=pos, avgCost=avgCost)

    def positionMultiEnd(self, reqId):
        with self._lock:
            context = self._position_queries.get(reqId)
            if context is None or context["status"] != "PARTIAL":
                return
            if (context["epoch"] != self._position_connection_epoch or not self.is_connected()
                    or self._stop_event.is_set()):
                context["status"] = "DISCONNECTED"
            elif time.monotonic() > context["deadline"]:
                context["status"] = "TIMEOUT"
            else:
                context["status"] = "COMPLETE"
                context["completed_at"] = datetime.now(timezone.utc)
            context["event"].set()


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
        with self._lock:
            self._raise_if_request_id_conflicted(req_id)
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
        self._register_request(req_id, "CONTRACT_DETAILS", contract)
        if self._stop_event.is_set():
            raise RuntimeError("Contract resolution stopped during disconnect.")

        self.reqContractDetails(req_id, contract)

        if not wait_event(event, self.snapshot_timeout_seconds):
            raise RuntimeError(f"Contract resolution failed for symbol={symbol} (timeout).")

        with self._lock:
            self._raise_if_request_id_conflicted(req_id)
            details = list(self._contract_details.get(req_id, []))
        if not details:
            raise RuntimeError(f"Contract resolution failed for symbol={symbol}")

        resolved = details[0]
        print(
            f"[IBKR] Resolved contract symbol={symbol} req_id={req_id} conId={resolved.contract.conId}"
        )
        return resolved

    def get_contract_reference_metadata(self, contract) -> dict:
        """Reuse completed qualification evidence; never request or reconnect.

        Qualification's first-row choice is not name authority. Require a single
        response matching the caller's retained positive security identity.
        """
        con_id = getattr(contract, "conId", None)
        if type(con_id) is not int or con_id <= 0 or not self.is_connected():
            return {}
        for req_id, context in reversed(tuple(self._request_context_by_req_id.items())):
            if context.get("request_type") != "CONTRACT_DETAILS" or context.get("symbol") != getattr(contract, "symbol", None):
                continue
            # The latest attempt is authoritative even when it failed or timed out.
            response = context.get("reference_response")
            if not response or context.get("reference_error"):
                return {}
            completed, rows = response
            if completed > context.get("reference_deadline", float("-inf")) or len(rows) != 1:
                return {}
            row = rows[0]
            if type(row.get("conId")) is not int or row["conId"] != con_id:
                return {}
            for field in ("symbol", "secType", "currency", "primaryExchange", "localSymbol", "tradingClass", "exchange"):
                expected = getattr(contract, field, None)
                if field == "exchange" and expected == "SMART":
                    continue  # SMART is a routing instruction, not a listing venue.
                if expected and row.get(field) != expected:
                    return {}
            name = row.get("longName")
            if not isinstance(name, str) or not name.strip():
                return {}
            return {"longName": name, "conId": con_id, "request_id": req_id,
                    "source": "IBKR_CONTRACT_DETAILS", "completed_at_utc": context["reference_completed_at_utc"]}
        return {}

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

    def reqMarketDataType(self, marketDataType: int):  # type: ignore[override]
        self._requested_market_data_type_code = int(marketDataType)
        return super().reqMarketDataType(marketDataType)

    def _send_quote(self, *args, **kwargs):
        names = ("reqId", "contract", "genericTickList", "snapshot", "regulatorySnapshot", "mktDataOptions")
        values = {name: args[index] if len(args) > index else kwargs.get(name)
                  for index, name in enumerate(names)}
        req_id = values["reqId"]
        self._quote_trace.start(req_id, values["contract"],
            getattr(self, "_requested_market_data_type_code", _market_data_type_code(self.market_data_type)),
            values["genericTickList"], values["snapshot"], values["regulatorySnapshot"], values["mktDataOptions"])
        try:
            result = super().reqMktData(*args, **kwargs)
        except BaseException:
            self._quote_trace.sent(req_id, "SDK_RAISED")
            self._quote_trace.finish(req_id, "send_error")
            try:
                self.cancelMktData(req_id)
            except Exception:
                pass  # cancel owns finally-cleanup; retain the original exception.
            raise
        self._quote_trace.sent(req_id, "SDK_RETURNED_NOT_BROKER_ACK")
        return result

    def _quote_callback_ticker(self, req_id, kind, *, supported=True, valid=True, returned_type=None, tick_type=None):
        # Caller holds the native lock. Diagnostic counts are not authority.
        # Order-only/partially initialized callback consumers have no quote owner.
        if not hasattr(self, "_quote_trace"):
            return None
        owner = getattr(self, "_request_type_by_req_id", {}).get(req_id)
        ticker = self._ticker_by_req_id.get(req_id)
        if self._request_id_conflicted(req_id):
            reason = "conflicted"
        elif req_id not in self._active_market_req_ids:
            reason = "inactive" if req_id in self._quote_trace.requests else "unknown_request"
        elif owner != "MARKET_DATA":
            reason = "wrong_owner"
        elif ticker is None:
            reason = "missing_ticker"
        elif not supported:
            reason = "unsupported_tick"
        elif not valid:
            reason = "invalid_value"
        else:
            reason = "accepted"
        self._quote_trace.callback(req_id, kind, reason, owner=owner, returned_type=returned_type, tick_type=tick_type)
        return ticker if reason == "accepted" else None

    def record_quote_completion(self, req_id, reason):
        self._quote_trace.finish(req_id, reason)

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
            ticker.reqId = req_id
            self._ticker_by_req_id[req_id] = ticker
            self._req_id_by_contract_key[self._contract_key(contract)] = req_id
            self._register_request(req_id, "MARKET_DATA", contract)
            self._active_market_req_ids.add(req_id)
            self._send_quote(
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
            contract = args[1] if len(args) >= 2 else kwargs.get("contract")
            self._register_request(req_id, "MARKET_DATA", contract)
            if contract is not None and not isinstance(contract, int):
                self._req_id_by_contract_key[self._contract_key(contract)] = req_id
                self._ticker_by_req_id.setdefault(req_id, self._build_ticker(contract)).reqId = req_id
            self._market_events.setdefault(req_id, threading.Event())
            self._market_data.setdefault(req_id, {"bid": None, "ask": None, "last": None, "volume": None})
            self._active_market_req_ids.add(req_id)
            return self._send_quote(*args, **kwargs)

        raise TypeError("reqMktData requires either (contract, ...) or (reqId, contract, ...)")

    def cancelMktData(self, *args, **kwargs):  # type: ignore[override]
        if args and not isinstance(args[0], int):
            req_id = self._req_id_by_contract_key.get(self._contract_key(args[0]))
        elif args:
            req_id = int(args[0])
        else:
            return super().cancelMktData(*args, **kwargs)
        with self._lock:
            if req_id not in self._active_market_req_ids:
                return None
            ticker = self._ticker_by_req_id.get(req_id)
            completed = bool(getattr(ticker, "snapshotEnd", False))
            # Stop accepting ticks before sending a cancellation over the wire.
            self._active_market_req_ids.discard(req_id)
        outcome = "NOT_SENT_ALREADY_COMPLETE" if completed else "SDK_CANCEL_RAISED"
        try:
            # SDK return is not broker cancellation acknowledgement.
            if completed:
                return None
            result = super().cancelMktData(req_id)
            outcome = "SDK_CANCEL_RETURNED_NOT_BROKER_ACK"
            return result
        finally:
            self._cleanup_market_request(req_id)
            self._quote_trace.cleanup(req_id, outcome,
                active=req_id in self._active_market_req_ids,
                ticker_present=req_id in self._ticker_by_req_id,
                event_present=req_id in self._market_events)

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
            event = threading.Event()
            self._historical_events[req_id] = event
            self._historical_data[req_id] = []
            self._register_request(req_id, "HISTORICAL_DATA", contract)
            print(
                f"[IBKR][HIST_REQ] req_id={req_id} symbol={getattr(contract, 'symbol', None)}"
            )

            checkpoint()
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

            self._raise_if_request_id_conflicted(req_id)
            start = time.time()
            timeout = self.snapshot_timeout_seconds

            try:
                while True:
                    checkpoint()
                    if event.is_set():
                        break

                    data = self._historical_data.get(req_id, [])
                    if data:
                        break

                    if time.time() - start > timeout:
                        break

                    time.sleep(bounded_timeout(0.01))
            except (AcquisitionCancelled, AcquisitionDeadlineExceeded):
                # Market-data cancellation only; never an order cancellation.
                self.cancelHistoricalData(req_id)
                raise

            with self._lock:
                self._raise_if_request_id_conflicted(req_id)
                data = list(self._historical_data.get(req_id, []))
            if not data:
                print(f"[IBKR][HIST_EMPTY_FINAL] req_id={req_id}")
            else:
                print(f"[IBKR][HIST_RETURN] req_id={req_id} bars={len(data)}")

            return list(data)

        if args and isinstance(args[0], int):
            req_id = int(args[0])
            contract = args[1] if len(args) > 1 else kwargs.get("contract")
            self._register_request(req_id, "HISTORICAL_DATA", contract)
            self._historical_events.setdefault(req_id, threading.Event())
            self._historical_data.setdefault(req_id, [])
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
        with self._lock:
            if self._request_id_conflicted(reqId):
                return
            self._contract_details.setdefault(reqId, []).append(contractDetails)

    def contractDetailsEnd(self, reqId: int):  # type: ignore[override]
        with self._lock:
            if self._request_id_conflicted(reqId):
                return
            context = getattr(self, "_request_context_by_req_id", {}).get(reqId, {})
            if "reference_deadline" in context and "reference_response" not in context:
                # Freeze only fields received by the genuine end callback. Late rows
                # cannot be promoted; error wakeups are not successful completion.
                rows = tuple({**{field: getattr(detail.contract, field, None) for field in
                             ("conId", "symbol", "secType", "currency", "exchange", "primaryExchange", "localSymbol", "tradingClass")},
                             "longName": getattr(detail, "longName", None)}
                             for detail in self._contract_details.get(reqId, ()))
                context["reference_completed_at_utc"] = datetime.now(timezone.utc).isoformat()
                context["reference_response"] = (time.monotonic(), rows)
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
        self._market_data[req_id] = {"bid": None, "ask": None, "last": None, "volume": None}
        try:
            self.reqMktData(req_id, contract, "", True, False, [])
            wait_event(event, self.snapshot_timeout_seconds)
            completed_at = datetime.now(timezone.utc)
            with self._lock:
                self._raise_if_request_id_conflicted(req_id)
                # Cancellation owns cleanup; retain all values before it runs.
                ticker = SimpleNamespace(**vars(self._ticker_by_req_id[req_id]))
            self.record_quote_completion(req_id, "snapshot_end" if ticker.snapshotEnd else
                                         "broker_error" if ticker.brokerErrors else "timeout")
        except BaseException:
            self.record_quote_completion(req_id, "interrupted")
            raise
        finally:
            self.cancelMktData(req_id)
        returned_type = _returned_market_data_type(ticker)
        requested_type = {1: "LIVE", 2: "FROZEN", 3: "DELAYED", 4: "DELAYED_FROZEN"}.get(ticker.requestedMarketDataType, "UNKNOWN")
        timestamp = _resolve_snapshot_timestamp(ticker)
        flags = _market_data_type_flags(returned_type)
        completion_reason = "snapshot_end" if ticker.snapshotEnd else ("broker_error" if ticker.brokerErrors else "timeout")
        if completion_reason == "timeout":
            flags.append("MD_TIMEOUT")
        if not ticker.snapshotEnd:
            flags.append("MD_SNAPSHOT_INCOMPLETE")
        if any(event["code"] == 10197 for event in ticker.brokerErrors):
            flags.append("MD_CONFLICT_10197")
        if timestamp is None:
            flags.append("MD_TIMESTAMP_UNKNOWN")
        fields = {name: _clean(getattr(ticker, name, None)) for name in ("bid", "ask", "last", "volume", "close", "open", "high", "low")}
        for name in ("bid", "ask", "last", "close", "open", "high", "low"):
            if fields[name] is not None and fields[name] <= 0:
                fields[name] = None
        if fields["volume"] is not None and fields["volume"] < 0:
            fields["volume"] = None
        for name in ("bid", "ask", "last", "close", "volume"):
            if fields[name] is None:
                flags.append(f"MD_MISSING_{name.upper()}")
        if all(fields[name] is None for name in ("bid", "ask", "last")):
            flags.append("MD_EMPTY")
        snapshot = MarketSnapshot(
            symbol=symbol,
            **fields,
            bid_size=_clean(ticker.bidSize),
            ask_size=_clean(ticker.askSize),
            last_size=_clean(ticker.lastSize),
            asof_utc=datetime.now(timezone.utc),
            market_data_type=returned_type,
            requested_market_data_type=requested_type,
            returned_market_data_type=returned_type,
            market_data_type_confirmed=ticker.marketDataTypeConfirmed,
            market_timestamp_utc=timestamp,
            timestamp_source="LAST_TRADE" if timestamp else "UNKNOWN",
            market_data_type_received_at_utc=ticker.marketDataTypeReceivedAt,
            request_id=req_id,
            snapshot_complete=ticker.snapshotEnd,
            received_at_utc=ticker.receivedAt,
            data_quality_flags=tuple(flags),
            **_snapshot_authority_metadata(ticker, fields, completed_at=completed_at, completion_reason=completion_reason),
        )
        print(f"[IBKR] Snapshot symbol={symbol} req_id={req_id} requested_type={requested_type} returned_type={returned_type} complete={ticker.snapshotEnd} bid={snapshot.bid} ask={snapshot.ask} last={snapshot.last}")
        return snapshot

    def snapshot_stock(self, symbol: str) -> MarketDataSnapshot:
        """Compatibility wrapper matching MarketDataClient snapshot contract."""
        snapshot = self.get_market_snapshot(symbol)
        return MarketDataSnapshot(
            symbol=symbol,
            bid=snapshot.bid,
            ask=snapshot.ask,
            last=snapshot.last,
            bid_size=snapshot.bid_size,
            ask_size=snapshot.ask_size,
            last_size=snapshot.last_size,
            volume=snapshot.volume,
            vwap=None,
            open=snapshot.open,
            high=snapshot.high,
            low=snapshot.low,
            close=snapshot.close,
            change_percent=None,
            spread=(snapshot.ask - snapshot.bid) if snapshot.ask is not None and snapshot.bid is not None else None,
            timestamp_utc=snapshot.market_timestamp_utc.isoformat() if snapshot.market_timestamp_utc else None,
            data_quality_flags=list(snapshot.data_quality_flags),
            requested_market_data_type=snapshot.requested_market_data_type,
            returned_market_data_type=snapshot.returned_market_data_type,
            market_data_type_confirmed=snapshot.market_data_type_confirmed,
            timestamp_source="LAST_TRADE" if snapshot.market_timestamp_utc else "UNKNOWN",
            received_at_utc=snapshot.received_at_utc.isoformat() if snapshot.received_at_utc else None,
            market_data_type_received_at_utc=snapshot.market_data_type_received_at_utc.isoformat() if snapshot.market_data_type_received_at_utc else None,
            request_id=snapshot.request_id,
            snapshot_complete=snapshot.snapshot_complete,
            **{key: getattr(snapshot, key) for key in (
                "market_data_type_confirmation_source", "request_started_at_utc",
                "request_completed_at_utc", "snapshot_completed_at_utc", "completion_reason",
                "field_availability", "field_received_at_utc", "missing_fields_observed_at_utc",
                "broker_errors",
            )},
        )

    def snapshot_for_symbol(self, symbol: str) -> MarketDataSnapshot:
        return self.snapshot_stock(symbol)


    def reqScannerData(self, subscription):
        """
        Forward scanner request to underlying IB client.
        """
        self.last_scanner_request = {"completion_status": "UNAVAILABLE",
                                     "end_received": False, "wait_signalled": False,
                                     "row_count": None}
        if hasattr(self, "ib") and self.ib is not None:
            # ib_insync can return an empty ScanDataList on request errors without
            # scannerDataEnd. This branch has no native completion authority.
            raise RuntimeError("IBKR scanner response unavailable: unverified delegate; use native scanner client")

        if not self.is_connected():
            raise RuntimeError("IBKR client is not connected.")

        req_id = self._next_req_id()
        event = threading.Event()
        self._scanner_events[req_id] = event
        self._scanner_rows[req_id] = []
        self._register_request(req_id, "SCANNER_DATA")

        context = self._request_context_by_req_id[req_id]
        context["scanner_end_received"] = False
        started = time.monotonic()
        print(f"[IBKR][SCANNER_REQUEST] req_id={req_id} client_id={self.client_id} "
              f"scan={getattr(subscription, 'scanCode', None)} "
              f"location={getattr(subscription, 'locationCode', None)} "
              f"connected={self.is_connected()} timeout_seconds={self.snapshot_timeout_seconds}")
        try:
            self.reqScannerSubscription(req_id, subscription, [], [])
            signalled = wait_event(event, self.snapshot_timeout_seconds)
            with self._lock:
                self._raise_if_request_id_conflicted(req_id)
                rows = list(self._scanner_rows.get(req_id, []))
                error = self._errors.get(req_id)
                completed = bool(context["scanner_end_received"])
                receipt = {"req_id": req_id, "client_id": self.client_id,
                           "completion_status": "COMPLETE" if signalled and completed and not error else "UNAVAILABLE",
                           "end_received": completed, "wait_signalled": signalled,
                           "row_count": len(rows), "error": error,
                           "connected": self.is_connected(),
                           "elapsed_seconds": time.monotonic()-started}
                self.last_scanner_request = receipt
                print(f"[IBKR][SCANNER_RESULT] {json.dumps(sanitize(receipt), sort_keys=True)}")
            if error:
                raise RuntimeError(f"IBKR scanner request {req_id} failed: {error}")
            if not signalled or not completed:
                raise TimeoutError(f"IBKR scanner request {req_id}: scannerDataEnd missing within wait budget")
            return rows
        finally:
            try:
                self.cancelScannerSubscription(req_id)
            finally:
                with self._lock:
                    self._scanner_events.pop(req_id, None)
                    self._scanner_rows.pop(req_id, None)
                    self._request_type_by_req_id.pop(req_id, None)

    def cancelScannerSubscription(self, reqId):
        """
        Forward scanner cancellation to underlying IB client.
        """
        if hasattr(self, "ib") and self.ib is not None:
            return self.ib.cancelScannerSubscription(reqId)
        return super().cancelScannerSubscription(reqId)

    def marketDataType(self, reqId: TickerId, marketDataType: int):  # type: ignore[override]
        with self._lock:
            ticker = self._quote_callback_ticker(reqId, "marketDataType", returned_type=marketDataType)
            if ticker is None:
                return
            ticker.marketDataType = marketDataType if marketDataType in {1, 2, 3, 4} else None
            ticker.marketDataTypeConfirmed = ticker.marketDataType is not None
            ticker.marketDataTypeReceivedAt = datetime.now(timezone.utc)
            event = {
                "req_id": reqId,
                "symbol": getattr(ticker.contract, "symbol", None),
                "requested_market_data_type": ticker.requestedMarketDataType,
                "returned_market_data_type": ticker.marketDataType,
                "timestamp_utc": ticker.marketDataTypeReceivedAt.isoformat(),
            }
        print(f"[IBKR][MARKET_DATA_TYPE] {json.dumps(event, sort_keys=True)}")
        self._market_update_event.set()

    def tickSnapshotEnd(self, reqId: TickerId):  # type: ignore[override]
        with self._lock:
            ticker = self._quote_callback_ticker(reqId, "tickSnapshotEnd")
            if ticker is None:
                return
            ticker.snapshotEnd = True
            ticker.snapshotEndedAt = datetime.now(timezone.utc)
            event = self._market_events.get(reqId)
            if event:
                event.set()
        self._market_update_event.set()

    def tickPrice(self, reqId: TickerId, tickType: int, price: float, attrib):  # type: ignore[override]
        field = {1: "bid", 2: "ask", 4: "last", 6: "high", 7: "low", 9: "close", 14: "open",
                 66: "bid", 67: "ask", 68: "last", 72: "high", 73: "low", 75: "close", 76: "open"}.get(tickType)
        with self._lock:
            ticker = self._quote_callback_ticker(reqId, "tickPrice", supported=field is not None, tick_type=tickType)
            if ticker is None:
                return
            self._market_data[reqId][field] = price
            setattr(ticker, field, price)
            _record_field_receipt(ticker, [field])
        self._market_update_event.set()

    def tickSize(self, reqId: TickerId, tickType: int, size: float):  # type: ignore[override]
        field = {0: "bidSize", 3: "askSize", 5: "lastSize", 8: "volume",
                 69: "bidSize", 70: "askSize", 71: "lastSize", 74: "volume"}.get(tickType)
        with self._lock:
            ticker = self._quote_callback_ticker(reqId, "tickSize", supported=field is not None, tick_type=tickType)
            if ticker is None:
                return
            value = float(size)
            self._market_data[reqId][field] = value
            setattr(ticker, field, value)
            _record_field_receipt(ticker, [{"bidSize": "bid_size", "askSize": "ask_size", "lastSize": "last_size"}.get(field, field)])
        self._market_update_event.set()

    def tickString(self, reqId: TickerId, tickType: int, value: str):  # type: ignore[override]
        if tickType not in {45, 88}:
            with self._lock:
                self._quote_callback_ticker(reqId, "tickString", supported=False, tick_type=tickType)
            return
        try:
            timestamp = datetime.fromtimestamp(float(value), timezone.utc)
        except (TypeError, ValueError, OverflowError, OSError):
            with self._lock:
                self._quote_callback_ticker(reqId, "tickString", valid=False, tick_type=tickType)
            return
        with self._lock:
            ticker = self._quote_callback_ticker(reqId, "tickString", tick_type=tickType)
            if ticker is None:
                return
            ticker.lastTime = timestamp
            _record_field_receipt(ticker, ["market_timestamp"])
        self._market_update_event.set()

    def historicalData(self, reqId: int, bar):  # type: ignore[override]
        with self._lock:
            if self._request_id_conflicted(reqId):
                return
            self._historical_data.setdefault(reqId, []).append(bar)

    def historicalDataEnd(self, reqId: int, start: str, end: str):  # type: ignore[override]
        with self._lock:
            if self._request_id_conflicted(reqId):
                return
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
        with self._lock:
            if self._request_id_conflicted(reqId):
                return
            register_account(account)
            rows = self._account_summary_rows.setdefault(reqId, {})
            rows[tag] = value

    def accountSummaryEnd(self, reqId: int):  # type: ignore[override]
        with self._lock:
            if self._request_id_conflicted(reqId):
                return
            event = self._account_summary_events.get(reqId)
            if event:
                event.set()
            getattr(self, "_request_type_by_req_id", {}).pop(reqId, None)

    def managedAccounts(self, accountsList: str):  # type: ignore[override]
        register_account(accountsList)
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
        with self._lock:
            if self._request_id_conflicted(reqId):
                return
            from types import SimpleNamespace

            if reqId not in self._scanner_events:
                print(f"[IBKR][SCANNER_CALLBACK_IGNORED] req_id={reqId} event=scannerData reason=no_active_request")
                return
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
        with self._lock:
            if self._request_id_conflicted(reqId):
                return
            event = self._scanner_events.get(reqId)
            print(f"[IBKR][SCANNER_CALLBACK] req_id={reqId} event=scannerDataEnd active={event is not None}")
            if event:
                self._request_context_by_req_id[reqId]["scanner_end_received"] = True
                event.set()
            getattr(self, "_request_type_by_req_id", {}).pop(reqId, None)

    # --- Error handling ---
    def error(self, reqId: int, errorCode: int, errorString: str):  # type: ignore[override]
        timestamp_utc = datetime.now(timezone.utc).isoformat()
        request_type_by_req_id = getattr(self, "_request_type_by_req_id", {})
        context = getattr(self, "_request_context_by_req_id", {}).get(reqId, {})
        request_type = request_type_by_req_id.get(reqId) or context.get("request_type")
        with self._lock:
            ticker = self._quote_callback_ticker(reqId, "error")
        event = sanitize({
            "timestamp_utc": timestamp_utc,
            "req_id": reqId,
            "request_type": request_type,
            "symbol": getattr(getattr(ticker, "contract", None), "symbol", None) or context.get("symbol"),
            "con_id": context.get("con_id"),
            "code": int(errorCode),
            "message": errorString,
        })
        if not hasattr(self, "_broker_error_events"):
            self._broker_error_events = []
        if ticker is not None and reqId in self._active_market_req_ids:
            ticker.brokerErrors.append(event)
        self._broker_error_events.append(event)
        del self._broker_error_events[:-256]
        print(f"[IBKR][BROKER_ERROR] {json.dumps(event, sort_keys=True)}")
        self._update_position_transport(errorCode, errorString)
        with self._lock:
            if self._request_id_conflicted(reqId):
                print(f"[IBKR][ERROR][OWNERSHIP_AMBIGUOUS] id={reqId} code={errorCode}")
                return
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
            is_order_only_callback = (
                is_non_rejecting_order_warning or fractional_unsupported_warning
                or (errorCode in self.ORDER_ONLY_CALLBACK_CODES
                    and reqId in self._order_status_events)
            )
            if (request_type_by_req_id.get(reqId) == "CONTRACT_DETAILS"
                    and "reference_deadline" in context and "reference_response" not in context
                    and not is_order_only_callback):
                # Numeric order IDs share the legacy error map. Exclude known order
                # callbacks; only this active attempt can disqualify its response.
                context["reference_error"] = (errorCode, errorString)
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
                if reqId in self._contract_events and not is_order_only_callback:
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
                message = f"[IBKR] Error reqId={reqId} code={errorCode} msg={errorString} timestamp_utc={timestamp_utc}"
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
            context = self._position_queries.get(reqId)
            if context is not None and not is_order_only_callback:
                context["status"] = "FAILED"
                context["event"].set()

    def _update_position_transport(self, error_code: int, error_string: str) -> None:
        if error_code in (1100, 1300):  # connection/pacing
            self._invalidate_position_queries(clear_account_scope=error_code == 1300)
            self._last_disconnect_reason = f"code={error_code} msg={error_string}"
            self._connection_event.clear()
        elif error_code in (1101, 1102):
            # TWS restored the same upstream session without a new API handshake.
            # Retained account identity is scope, never position evidence. All
            # interrupted query epochs remain invalid; only a fresh query may pass.
            with self._lock:
                if self.is_connected() and not self._stop_event.is_set():
                    self._position_upstream_lost = False
                    self._position_transport_available = True
                    self._connection_event.set()


    def nextValidId(self, orderId: int):  # type: ignore[override]
        with self._lock:
            if not self._position_upstream_lost:
                self._position_transport_available = True
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
        self._observe_order_id(int(orderId))
        if not hasattr(self, "_order_status_count"):
            self._order_status_count = 0
        self._order_status_count += 1
        print(
            "[IBKR][CALLBACK_RAW] "
            f"event=orderStatus order_id={orderId} status={status} filled={filled} remaining={remaining} whyHeld={whyHeld}"
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
                "whyHeld": whyHeld,
            }
        )
        event = self._order_status_events.setdefault(orderId, threading.Event())
        event.set()

    def execDetails(self, reqId, contract, execution):  # type: ignore[override]
        if getattr(execution, "orderId", None) is not None:
            self._observe_order_id(int(execution.orderId))
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
        self._observe_order_id(int(orderId))
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
        with self._lock:
            if self._request_id_conflicted(reqId):
                return
            print(f"[IBKR][CALLBACK_RAW] event=execDetailsEnd req_id={reqId}")
            self._executions_event.set()
            getattr(self, "_request_type_by_req_id", {}).pop(reqId, None)

    def position(self, account, contract, pos, avgCost):  # type: ignore[override]
        register_account(account)
        symbol = str(getattr(contract, "symbol", "") or "").upper()
        print(
            "[IBKR][CALLBACK_RAW] "
            f"event=position account_id_redacted=REDACTED symbol={symbol} pos={pos} avg_cost={avgCost}"
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
        self._invalidate_position_queries()
        self._last_disconnect_reason = "connectionClosed"
        self._connection_event.clear()
        print("[IBKR] Connection closed by broker.")


from src.ibkr.mutation_audit import install_sdk, instrument_mutation
install_sdk(EClient, IbkrClient)
instrument_mutation(IbkrClient, "submit_order")
