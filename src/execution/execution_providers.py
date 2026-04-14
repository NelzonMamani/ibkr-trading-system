from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Optional, Protocol, runtime_checkable, TYPE_CHECKING

from src.brokers.base_broker import BrokerOrderRequest
from src.brokers.sim_broker import SimBroker
from src.config.runtime_config import RunMode
from src.core.active_trade_registry import ActiveTradeRegistry
from src.core.event_collector import EventCollector
from src.execution.order_gateway import OrderGateway
from src.models.execution_result import ExecutionResult
from src.sim.price_feed import PriceFeed

if TYPE_CHECKING:
    from src.brokers.ibkr_live_broker import IbkrLiveBroker

@dataclass(frozen=True)
class CancelReport:
    order_id: str
    status: str
    rationale: str


@dataclass(frozen=True)
class OrderSnapshot:
    order_id: str
    symbol: str
    status: str


@dataclass(frozen=True)
class PositionSnapshot:
    positions: list
    as_of: str


@runtime_checkable
class ExecutionProvider(Protocol):
    def name(self) -> str:
        ...

    def is_live(self) -> bool:
        ...

    def place_order(self, request: BrokerOrderRequest) -> ExecutionResult:
        ...

    def cancel(self, order_id: str) -> CancelReport:
        ...

    def get_positions(self) -> PositionSnapshot:
        ...

    def get_open_orders(self) -> List[OrderSnapshot]:
        ...

    def place_stop_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: int,
        stop_price: float,
        trade_id: str,
        parent_order_id: str | None = None,
    ) -> dict[str, Any]:
        ...

    def place_target_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: int,
        limit_price: float,
        trade_id: str,
        parent_order_id: str | None = None,
    ) -> dict[str, Any]:
        ...

    def modify_stop_order(
        self,
        *,
        broker_order_id: str,
        symbol: str,
        side: str,
        quantity: int,
        new_stop_price: float,
        trade_id: str,
    ) -> dict[str, Any]:
        ...

    def cancel_order(self, *, broker_order_id: str) -> dict[str, Any]:
        ...


@dataclass
class PaperExecutionProvider(ExecutionProvider):
    price_feed: PriceFeed
    trade_registry: ActiveTradeRegistry
    event_collector: EventCollector
    run_mode: RunMode = RunMode.PAPER
    broker: Optional[SimBroker] = None
    _protective_seq: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.broker is None:
            self.broker = SimBroker(
                gateway=OrderGateway(),
                price_feed=self.price_feed,
                trade_registry=self.trade_registry,
                event_collector=self.event_collector,
                run_mode=self.run_mode,
            )

    def name(self) -> str:
        return "PAPER_EXECUTION_PROVIDER"

    def is_live(self) -> bool:
        return False

    def place_order(self, request: BrokerOrderRequest) -> ExecutionResult:
        return self.broker.place_order(request)

    def cancel(self, order_id: str) -> CancelReport:
        return CancelReport(
            order_id=order_id,
            status="NOT_SUPPORTED",
            rationale="Paper provider does not track cancelable open orders.",
        )

    def get_positions(self) -> PositionSnapshot:
        timestamp = datetime.now(timezone.utc).isoformat()
        return PositionSnapshot(positions=self.trade_registry.snapshot(), as_of=timestamp)

    def get_open_orders(self) -> List[OrderSnapshot]:
        return []

    def _next_protective_id(self, prefix: str) -> str:
        self._protective_seq += 1
        return f"{prefix}-{self._protective_seq}"

    def place_stop_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: int,
        stop_price: float,
        trade_id: str,
        parent_order_id: str | None = None,
    ) -> dict[str, Any]:
        order_id = self._next_protective_id("PAPER-STP")
        print(
            "[IBKR][ORDER_SUBMITTED] "
            f"type=STP mode=PAPER order_id={order_id} trade_id={trade_id} symbol={symbol} qty={quantity} stop={stop_price:.4f}"
        )
        return {
            "broker_order_id": order_id,
            "status": "Submitted",
            "order_type": "STP",
            "parent_order_id": parent_order_id,
        }

    def place_target_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: int,
        limit_price: float,
        trade_id: str,
        parent_order_id: str | None = None,
    ) -> dict[str, Any]:
        order_id = self._next_protective_id("PAPER-LMT")
        print(
            "[IBKR][ORDER_SUBMITTED] "
            f"type=LMT mode=PAPER order_id={order_id} trade_id={trade_id} symbol={symbol} qty={quantity} limit={limit_price:.4f}"
        )
        return {
            "broker_order_id": order_id,
            "status": "Submitted",
            "order_type": "LMT",
            "parent_order_id": parent_order_id,
        }

    def modify_stop_order(
        self,
        *,
        broker_order_id: str,
        symbol: str,
        side: str,
        quantity: int,
        new_stop_price: float,
        trade_id: str,
    ) -> dict[str, Any]:
        print(
            "[IBKR][ORDER_MODIFIED] "
            f"mode=PAPER order_id={broker_order_id} trade_id={trade_id} symbol={symbol} qty={quantity} stop={new_stop_price:.4f}"
        )
        return {"broker_order_id": broker_order_id, "status": "Submitted", "order_type": "STP"}

    def cancel_order(self, *, broker_order_id: str) -> dict[str, Any]:
        print(f"[IBKR][ORDER_CANCELLED] mode=PAPER order_id={broker_order_id}")
        return {"broker_order_id": broker_order_id, "status": "Cancelled"}


@dataclass
class IbkrExecutionProvider(ExecutionProvider):
    broker: "IbkrLiveBroker"
    trade_registry: ActiveTradeRegistry
    run_mode: RunMode = RunMode.LIVE

    def name(self) -> str:
        return "IBKR_EXECUTION_PROVIDER"

    def is_live(self) -> bool:
        return True

    def place_order(self, request: BrokerOrderRequest) -> ExecutionResult:
        if self.run_mode == RunMode.READ_ONLY:
            return ExecutionResult(
                symbol=request.symbol,
                trader_type=request.trader_type or "UNKNOWN",
                attempted=False,
                status="BLOCKED",
                rationale="LIVE_READ_ONLY_BLOCK",
                direction=request.direction,
                quantity=request.quantity,
                stop_loss_price=request.stop_loss_price,
                take_profit_price=request.take_profit_price,
                requested_quantity=request.quantity,
                filled_quantity=0,
                remaining_quantity=request.quantity,
                fill_status="NONE",
                note="LIVE_READ_ONLY_BLOCK",
                rejection_reason="LIVE_READ_ONLY_BLOCK",
                client_order_id=request.client_order_id,
                attempt_number=request.attempt_number,
            )
        return self.broker.place_order(request)

    def cancel(self, order_id: str) -> CancelReport:
        return CancelReport(
            order_id=order_id,
            status="NOT_IMPLEMENTED",
            rationale="IBKR cancel integration not yet implemented.",
        )

    def get_positions(self) -> PositionSnapshot:
        timestamp = datetime.now(timezone.utc).isoformat()
        return PositionSnapshot(positions=self.trade_registry.snapshot(), as_of=timestamp)

    def get_open_orders(self) -> List[OrderSnapshot]:
        try:
            rows = self.broker.open_orders()
        except Exception as exc:
            print(f"[IBKR][OPEN_ORDERS][ERROR] reason={exc}")
            return []
        snapshots: list[OrderSnapshot] = []
        for row in rows:
            contract = getattr(row, "contract", None)
            order_state = getattr(row, "orderState", None)
            snapshots.append(
                OrderSnapshot(
                    order_id=str(getattr(row, "orderId", "")),
                    symbol=str(getattr(contract, "symbol", "") or "").upper(),
                    status=str(getattr(order_state, "status", "") or ""),
                )
            )
        return snapshots

    def place_stop_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: int,
        stop_price: float,
        trade_id: str,
        parent_order_id: str | None = None,
    ) -> dict[str, Any]:
        if self.run_mode == RunMode.READ_ONLY:
            raise RuntimeError("READ_ONLY_NO_ORDER_MUTATION")
        return self.broker.place_stop_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            stop_price=stop_price,
            trade_id=trade_id,
            parent_order_id=parent_order_id,
        )

    def place_target_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: int,
        limit_price: float,
        trade_id: str,
        parent_order_id: str | None = None,
    ) -> dict[str, Any]:
        if self.run_mode == RunMode.READ_ONLY:
            raise RuntimeError("READ_ONLY_NO_ORDER_MUTATION")
        return self.broker.place_target_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            limit_price=limit_price,
            trade_id=trade_id,
            parent_order_id=parent_order_id,
        )

    def modify_stop_order(
        self,
        *,
        broker_order_id: str,
        symbol: str,
        side: str,
        quantity: int,
        new_stop_price: float,
        trade_id: str,
    ) -> dict[str, Any]:
        if self.run_mode == RunMode.READ_ONLY:
            raise RuntimeError("READ_ONLY_NO_ORDER_MUTATION")
        return self.broker.modify_stop_order(
            broker_order_id=broker_order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            new_stop_price=new_stop_price,
            trade_id=trade_id,
        )

    def cancel_order(self, *, broker_order_id: str) -> dict[str, Any]:
        if self.run_mode == RunMode.READ_ONLY:
            raise RuntimeError("READ_ONLY_NO_ORDER_MUTATION")
        return self.broker.cancel_order(broker_order_id=broker_order_id)
