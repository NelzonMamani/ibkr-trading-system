from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from utils.price_math import D, quantize_money


@dataclass
class ExecutionResult:
    """
    Decimal-safe execution record used for deterministic replay.
    """

    symbol: str
    trader_type: str
    attempted: bool
    status: str  # "SKIPPED" or "SIMULATED" to reinforce safety.
    rationale: str
    direction: str = "UNKNOWN"
    quantity: int = 1
    entry_price: Optional[Decimal] = None
    exit_price: Optional[Decimal] = None
    raw_price: Optional[Decimal] = None
    slippage_applied: Decimal = Decimal("0.00")
    entry_tick: Optional[int] = None
    exit_tick: Optional[int] = None
    stop_loss_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None
    gross_realised_pnl: Decimal = Decimal("0.00")
    commission: Decimal = Decimal("0.00")
    net_realised_pnl: Decimal = Decimal("0.00")
    requested_quantity: int = 0
    filled_quantity: int = 0
    remaining_quantity: int = 0
    fill_status: str = "UNKNOWN"  # "FULL" | "PARTIAL" | "NONE"
    average_fill_price: Optional[Decimal] = None
    note: Optional[str] = None
    gateway_decision: Optional[str] = None
    attempt_number: int = 0
    client_order_id: Optional[str] = None
    retry_scheduled: bool = False
    next_retry_tick: Optional[int] = None
    rejection_reason: Optional[str] = None

    def __post_init__(self) -> None:
        self.entry_price = self._maybe_quantize(self.entry_price)
        self.exit_price = self._maybe_quantize(self.exit_price)
        self.raw_price = self._maybe_quantize(self.raw_price)
        self.average_fill_price = self._maybe_quantize(self.average_fill_price)
        self.slippage_applied = quantize_money(D(self.slippage_applied))
        self.gross_realised_pnl = quantize_money(D(self.gross_realised_pnl))
        self.commission = quantize_money(D(self.commission))
        self.net_realised_pnl = quantize_money(D(self.net_realised_pnl))
        self.stop_loss_price = self._maybe_quantize(self.stop_loss_price)
        self.take_profit_price = self._maybe_quantize(self.take_profit_price)

    @staticmethod
    def _maybe_quantize(value: Optional[Decimal]) -> Optional[Decimal]:
        if value is None:
            return None
        return quantize_money(D(value))
