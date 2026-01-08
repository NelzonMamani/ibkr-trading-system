from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from ibapi.client import EClient
from ibapi.common import TickerId
from ibapi.contract import Contract, ContractDetails
from ibapi.wrapper import EWrapper

from domain.market_snapshot import MarketSnapshot
from ibkr.read_only_guard import assert_read_only_allows


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
        self._errors: Dict[int, Tuple[int, str]] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._connection_event = threading.Event()
        self._last_disconnect_reason: Optional[str] = None
        self._next_order_id: Optional[int] = None
        self._order_status_events: Dict[int, threading.Event] = {}
        self._order_status: Dict[int, Dict[str, Optional[float | int | str]]] = {}
        self._exec_details_by_order: Dict[int, List[dict]] = {}
        self._commission_by_exec_id: Dict[str, float] = {}

    # --- Connection management ---
    def connect(self) -> None:  # type: ignore[override]
        if not self.readonly_enabled:
            print("[IBKR] Read-only disabled; trading-enabled connection requested.")

        print(
            f"[IBKR] Connecting to host={self.host} port={self.port} client_id={self.client_id}"
        )
        try:
            super().connect(self.host, self.port, self.client_id)
        except Exception as exc:  # pragma: no cover - defensive
            raise RuntimeError(f"IBKR connection failed: {exc}") from exc

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        if not self._connection_event.wait(timeout=self.snapshot_timeout_seconds):
            self.disconnect()
            raise RuntimeError(
                "IBKR connection timeout waiting for next valid id handshake."
            )

        data_type_code = _market_data_type_code(self.market_data_type)
        print(f"[IBKR] Setting market data type={self.market_data_type} code={data_type_code}")
        self.reqMarketDataType(data_type_code)
        print("[IBKR] Connection established.")

    def disconnect(self) -> None:  # type: ignore[override]
        print("[IBKR] Disconnect requested.")
        self._stop_event.set()
        try:
            super().disconnect()
        finally:
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2)
                if self._thread.is_alive():  # pragma: no cover - defensive
                    print("[IBKR] Warning: network thread still alive after disconnect.")
            print("[IBKR] Disconnected.")

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

    def reserve_order_id(self) -> int:
        with self._lock:
            if self._next_order_id is None:
                raise RuntimeError("IBKR order id not yet initialized.")
            order_id = self._next_order_id
            self._next_order_id += 1
            return order_id

    def submit_order(self, contract: Contract, order) -> int:
        if not self.is_connected():
            raise RuntimeError("IBKR client is not connected.")
        assert_read_only_allows("PLACE_ORDER")
        order_id = self.reserve_order_id()
        self._order_status_events[order_id] = threading.Event()
        self._exec_details_by_order[order_id] = []
        self.placeOrder(order_id, contract, order)
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

    def contractDetails(self, reqId: int, contractDetails: ContractDetails):  # type: ignore[override]
        self._contract_details.setdefault(reqId, []).append(contractDetails)

    def contractDetailsEnd(self, reqId: int):  # type: ignore[override]
        event = self._contract_events.get(reqId)
        if event:
            event.set()

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

        self.reqMktData(
            reqId=req_id,
            contract=contract,
            genericTickList="",
            snapshot=True,
            regulatorySnapshot=False,
            mktDataOptions=[],
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

        if any(value is not None for value in prices.values()):
            event = self._market_events.get(reqId)
            if event:
                event.set()

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
        if any(value is not None for value in prices.values()):
            event = self._market_events.get(reqId)
            if event:
                event.set()

    # --- Error handling ---
    def error(self, reqId: int, errorCode: int, errorString: str):  # type: ignore[override]
        if reqId >= 0:
            self._errors[reqId] = (errorCode, errorString)
            if reqId in self._contract_events:
                self._contract_events[reqId].set()
            if reqId in self._market_events:
                self._market_events[reqId].set()
        message = f"[IBKR] Error reqId={reqId} code={errorCode} msg={errorString}"
        print(message)
        if errorCode in (1100, 1300):  # connection/pacing
            self._last_disconnect_reason = f"code={errorCode} msg={errorString}"
            self._connection_event.clear()

    def nextValidId(self, orderId: int):  # type: ignore[override]
        print(f"[IBKR] nextValidId received orderId={orderId}")
        self._next_order_id = orderId
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
        self._order_status[orderId] = {
            "status": status,
            "filled": int(filled),
            "remaining": int(remaining),
            "avgFillPrice": avgFillPrice,
            "lastFillPrice": lastFillPrice,
        }
        event = self._order_status_events.setdefault(orderId, threading.Event())
        event.set()

    def execDetails(self, reqId, contract, execution):  # type: ignore[override]
        order_id = getattr(execution, "orderId", None)
        if order_id is None:
            return
        details = {
            "execId": getattr(execution, "execId", None),
            "time": getattr(execution, "time", None),
            "price": getattr(execution, "price", None),
            "shares": getattr(execution, "shares", None),
        }
        self._exec_details_by_order.setdefault(order_id, []).append(details)

    def commissionReport(self, commissionReport):  # type: ignore[override]
        exec_id = getattr(commissionReport, "execId", None)
        commission = getattr(commissionReport, "commission", None)
        if exec_id is None or commission is None:
            return
        self._commission_by_exec_id[exec_id] = float(commission)

    def connectionClosed(self):  # type: ignore[override]
        self._last_disconnect_reason = "connectionClosed"
        self._connection_event.clear()
        print("[IBKR] Connection closed by broker.")
