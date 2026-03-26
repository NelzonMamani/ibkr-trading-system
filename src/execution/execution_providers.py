from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Protocol, runtime_checkable, TYPE_CHECKING

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


@dataclass
class PaperExecutionProvider(ExecutionProvider):
    price_feed: PriceFeed
    trade_registry: ActiveTradeRegistry
    event_collector: EventCollector
    run_mode: RunMode = RunMode.PAPER
    broker: Optional[SimBroker] = None

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
        self.broker.verify_broker_protection()
        return PositionSnapshot(positions=self.trade_registry.snapshot(), as_of=timestamp)

    def get_open_orders(self) -> List[OrderSnapshot]:
        return []
