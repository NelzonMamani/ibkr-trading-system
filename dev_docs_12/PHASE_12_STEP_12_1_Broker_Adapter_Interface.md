PHASE_12_STEP_12_1_Broker_Adapter_Interface.md
PHASE 12 · STEP 12.1 — Broker Adapter Interface (SIM-ready, LIVE-capable contract)
Codex Instructions — SINGLE BLOCK (copy/paste everything). END marker included.

GOAL
Create a broker abstraction so ExecutionEngine can route to SIM or LIVE without changing business logic.
This step introduces:
- BaseBroker interface (contract)
- SimBroker (teaching-safe) that reuses current deterministic gateway/liquidity behaviour
- IbkrBroker (stub) with correct method shapes + placeholders (no real IB calls yet)
- ExecutionEngine refactor to call broker.place_order() instead of direct internal submit flow
- Minimal wiring in composition root (orchestrator/bootstrap) to select broker by RUN_MODE

RULES (DO NOT DEVIATE)
- Keep everything deterministic in SIM.
- LIVE broker must NOT place real trades in this step (stub only).
- Preserve current event emission semantics (ORDER_SUBMITTED, ORDER_GATEWAY_DECISION, etc.) even if schema registry is incomplete.
- Do not change strategy/risk logic. Only execution routing changes.
- Ensure all new code is formatted, import-safe, and mypy-friendly where feasible.
- Add END at end of this block (already included).

FILE PLAN
Create/modify the following files:

1) src/brokers/__init__.py                         (NEW)
2) src/brokers/base_broker.py                      (NEW)
3) src/brokers/sim_broker.py                       (NEW)
4) src/brokers/ibkr_broker.py                      (NEW, stub only)
5) src/execution/execution_engine.py               (MODIFY)
6) src/core/composition_root.py OR src/core/orchestrator_factory.py (MODIFY IF EXISTS)
   - Choose the correct location in your repo that currently wires ExecutionEngine.
   - If no such file exists, modify the nearest bootstrap location (likely src/main.py or where Orchestrator is built).

===============================================================================
1) CREATE: src/brokers/__init__.py
===============================================================================
Paste:

from .base_broker import BaseBroker
from .sim_broker import SimBroker
from .ibkr_broker import IbkrBroker

__all__ = ["BaseBroker", "SimBroker", "IbkrBroker"]

===============================================================================
2) CREATE: src/brokers/base_broker.py
===============================================================================
Paste:

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

# NOTE:
# We intentionally keep this contract small for Phase 12.1.
# It must be enough for ExecutionEngine to request an order placement and receive an ExecutionResult.


@dataclass(frozen=True)
class BrokerOrderRequest:
    """
    System-language order request (NOT broker-specific).
    direction: "LONG" or "SHORT"
    order_type: e.g. "MKT" for now (teaching)
    """
    client_order_id: str
    symbol: str
    direction: str            # "LONG" or "SHORT" (system language)
    quantity: int
    order_type: str = "MKT"   # teaching default
    trader_type: Optional[str] = None
    strategy_name: Optional[str] = None
    attempt_number: int = 1
    created_tick: Optional[int] = None


@runtime_checkable
class BaseBroker(Protocol):
    """
    Broker adapter contract.
    SIM and LIVE implementations must conform so ExecutionEngine remains unchanged.
    """

    def name(self) -> str:
        ...

    def is_live(self) -> bool:
        ...

    def place_order(self, request: BrokerOrderRequest):
        """
        Place an order and return an ExecutionResult-like object.
        We avoid importing ExecutionResult here to prevent circular imports.
        SIM broker will return the system ExecutionResult from execution domain.
        LIVE stub will return a system ExecutionResult marked as NOT_ATTEMPTED / STUBBED.
        """
        ...

===============================================================================
3) CREATE: src/brokers/sim_broker.py
===============================================================================
Paste:

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.brokers.base_broker import BaseBroker, BrokerOrderRequest

# Import system execution types (these should already exist in your repo).
# Adjust import paths if your project structure differs.
from src.execution.execution_types import ExecutionResult
from src.execution.sim_deterministic_gateway import DeterministicGateway
from src.execution.sim_liquidity_model import DeterministicLiquidityModel
from src.execution.sim_price_feed import DeterministicPriceFeed
from src.execution.execution_events import (
    emit_order_submitted,
    emit_order_gateway_decision,
    emit_order_rejected_hard,
    emit_order_retry_scheduled,
    emit_trade_opened,
    emit_trade_not_filled,
)

from src.registry.trade_registry import TradeRegistry


@dataclass
class SimBroker(BaseBroker):
    """
    Teaching-safe SIM broker.
    Reuses the existing deterministic gateway + liquidity + price feed.
    The goal is to make ExecutionEngine broker-agnostic without changing behaviour.
    """
    gateway: DeterministicGateway
    liquidity: DeterministicLiquidityModel
    price_feed: DeterministicPriceFeed
    registry: TradeRegistry

    def name(self) -> str:
        return "SIM_BROKER"

    def is_live(self) -> bool:
        return False

    def place_order(self, request: BrokerOrderRequest) -> ExecutionResult:
        """
        Mirror current SIM execution flow:
        - Emit ORDER_SUBMITTED
        - Gateway decision: ACCEPT / REJECT / SOFT_REJECT
        - If REJECT => emit ORDER_REJECTED_HARD
        - If SOFT_REJECT => emit ORDER_RETRY_SCHEDULED and return RETRY_SCHEDULED result
        - If ACCEPT => consult price + liquidity; if fill => emit TRADE_OPENED; else TRADE_NOT_FILLED
        """
        # Ensure tick exists for deterministic models
        tick = request.created_tick if request.created_tick is not None else 0

        emit_order_submitted(
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            trader_type=request.trader_type,
            strategy_name=request.strategy_name,
            direction=request.direction,
            requested_quantity=request.quantity,
            created_tick=tick,
            attempt_number=request.attempt_number,
        )

        decision = self.gateway.decide(
            symbol=request.symbol,
            tick=tick,
            trader_type=request.trader_type or "UNKNOWN",
            attempt_number=request.attempt_number,
            client_order_id=request.client_order_id,
        )

        emit_order_gateway_decision(
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            trader_type=request.trader_type,
            tick=tick,
            attempt_number=request.attempt_number,
            decision=decision.decision,
            deterministic_key=decision.deterministic_key,
            mapping_r=decision.mapping_r,
        )

        # Always get a reference price for context (mirrors previous prints)
        price_snapshot = self.price_feed.get_price(symbol=request.symbol, tick=tick)
        raw_price = price_snapshot.last

        # HARD REJECT
        if decision.decision == "REJECT":
            emit_order_rejected_hard(
                client_order_id=request.client_order_id,
                symbol=request.symbol,
                trader_type=request.trader_type,
                tick=tick,
                attempt_number=request.attempt_number,
                reason="GATEWAY_HARD_REJECT",
            )
            return ExecutionResult(
                symbol=request.symbol,
                trader_type=request.trader_type or "UNKNOWN",
                attempted=False,
                status="REJECTED",
                rationale="Deterministic gateway hard rejected the order.",
                direction=request.direction,
                quantity=0,
                entry_price=None,
                exit_price=None,
                raw_price=raw_price,
                slippage_applied=0,
                entry_tick=tick,
                exit_tick=None,
                stop_loss_price=None,
                take_profit_price=None,
                gross_realised_pnl=0,
                commission=0,
                net_realised_pnl=0,
                requested_quantity=request.quantity,
                filled_quantity=0,
                remaining_quantity=request.quantity,
                fill_status="NONE",
                average_fill_price=None,
                note="Gateway hard reject — no liquidity attempted.",
                gateway_decision="REJECT",
                attempt_number=request.attempt_number,
                client_order_id=request.client_order_id,
                retry_scheduled=False,
                next_retry_tick=None,
                rejection_reason="GATEWAY_HARD_REJECT",
                spread=price_snapshot.spread,
                bid_price=price_snapshot.bid,
                ask_price=price_snapshot.ask,
                reference_price=price_snapshot.ask,  # teaching reference
                execution_price=None,
            )

        # SOFT REJECT => schedule retry deterministically (next tick)
        if decision.decision == "SOFT_REJECT":
            next_tick = tick + 1
            next_attempt = request.attempt_number + 1
            emit_order_retry_scheduled(
                client_order_id=request.client_order_id,
                symbol=request.symbol,
                trader_type=request.trader_type,
                from_tick=tick,
                next_retry_tick=next_tick,
                next_attempt_number=next_attempt,
            )
            return ExecutionResult(
                symbol=request.symbol,
                trader_type=request.trader_type or "UNKNOWN",
                attempted=False,
                status="RETRY_SCHEDULED",
                rationale="Gateway soft reject — retry scheduled.",
                direction=request.direction,
                quantity=0,
                entry_price=None,
                exit_price=None,
                raw_price=raw_price,
                slippage_applied=0,
                entry_tick=tick,
                exit_tick=None,
                stop_loss_price=None,
                take_profit_price=None,
                gross_realised_pnl=0,
                commission=0,
                net_realised_pnl=0,
                requested_quantity=request.quantity,
                filled_quantity=0,
                remaining_quantity=request.quantity,
                fill_status="NONE",
                average_fill_price=None,
                note="Gateway soft reject; will retry deterministically.",
                gateway_decision="SOFT_REJECT",
                attempt_number=request.attempt_number,
                client_order_id=request.client_order_id,
                retry_scheduled=True,
                next_retry_tick=next_tick,
                rejection_reason="GATEWAY_SOFT_REJECT",
                spread=price_snapshot.spread,
                bid_price=price_snapshot.bid,
                ask_price=price_snapshot.ask,
                reference_price=price_snapshot.ask,
                execution_price=None,
            )

        # ACCEPT => consult liquidity
        liq = self.liquidity.get_available(
            symbol=request.symbol,
            tick=tick,
            trader_type=request.trader_type or "UNKNOWN",
            requested=request.quantity,
        )

        filled_qty = min(request.quantity, liq.available)
        remaining = request.quantity - filled_qty

        # No fill
        if filled_qty <= 0:
            emit_trade_not_filled(
                symbol=request.symbol,
                trader_type=request.trader_type,
                tick=tick,
                requested_quantity=request.quantity,
                available_liquidity=liq.available,
                filled_quantity=0,
                remaining_quantity=request.quantity,
                reason="LIQUIDITY_ZERO",
                fill_status="NONE",
                client_order_id=request.client_order_id,
                attempt_number=request.attempt_number,
                gateway_decision="ACCEPT",
            )
            return ExecutionResult(
                symbol=request.symbol,
                trader_type=request.trader_type or "UNKNOWN",
                attempted=True,
                status="NOT_FILLED",
                rationale="Deterministic liquidity returned zero available volume.",
                direction=request.direction,
                quantity=0,
                entry_price=None,
                exit_price=None,
                raw_price=raw_price,
                slippage_applied=0,
                entry_tick=tick,
                exit_tick=None,
                stop_loss_price=None,
                take_profit_price=None,
                gross_realised_pnl=0,
                commission=0,
                net_realised_pnl=0,
                requested_quantity=request.quantity,
                filled_quantity=0,
                remaining_quantity=request.quantity,
                fill_status="NONE",
                average_fill_price=None,
                note="No fill: liquidity zero for this tick/symbol combination.",
                gateway_decision="ACCEPT",
                attempt_number=request.attempt_number,
                client_order_id=request.client_order_id,
                retry_scheduled=False,
                next_retry_tick=None,
                rejection_reason=None,
                spread=price_snapshot.spread,
                bid_price=price_snapshot.bid,
                ask_price=price_snapshot.ask,
                reference_price=price_snapshot.ask,
                execution_price=None,
            )

        # Fill => apply teaching slippage and register trade
        exec_price = self.price_feed.apply_slippage(
            symbol=request.symbol,
            tick=tick,
            direction=request.direction,
            base_price=price_snapshot.ask,
        )

        # Register in system registry (this should mirror existing registry behaviour)
        self.registry.register(
            symbol=request.symbol,
            trader_type=request.trader_type or "UNKNOWN",
            entry_tick=tick,
            entry_price=float(exec_price),
            direction=request.direction,
            quantity=filled_qty,
            strategy_name=request.strategy_name or "UNKNOWN",
        )

        emit_trade_opened(
            symbol=request.symbol,
            trader_type=request.trader_type,
            strategy_name=request.strategy_name,
            entry_tick=tick,
            opened_at_tick=tick,
            entry_price=float(exec_price),
            raw_price=float(raw_price),
            slippage_applied=float(exec_price - price_snapshot.ask),
            execution_price=float(exec_price),
            mode="SIM",
            direction=request.direction,
            quantity=filled_qty,
            stop_loss_price=None,
            take_profit_price=None,
            requested_quantity=request.quantity,
            filled_quantity=filled_qty,
            remaining_quantity=remaining,
            fill_status="FULL" if remaining == 0 else "PARTIAL",
            client_order_id=request.client_order_id,
            attempt_number=request.attempt_number,
            gateway_decision="ACCEPT",
        )

        return ExecutionResult(
            symbol=request.symbol,
            trader_type=request.trader_type or "UNKNOWN",
            attempted=True,
            status="SIMULATED",
            rationale="Teaching-only: routed by trader_type with deterministic gateway and liquidity.",
            direction=request.direction,
            quantity=filled_qty,
            entry_price=exec_price,
            exit_price=None,
            raw_price=raw_price,
            slippage_applied=exec_price - price_snapshot.ask,
            entry_tick=tick,
            exit_tick=None,
            stop_loss_price=None,
            take_profit_price=None,
            gross_realised_pnl=0,
            commission=0,
            net_realised_pnl=0,
            requested_quantity=request.quantity,
            filled_quantity=filled_qty,
            remaining_quantity=remaining,
            fill_status="FULL" if remaining == 0 else "PARTIAL",
            average_fill_price=exec_price,
            note=None,
            gateway_decision="ACCEPT",
            attempt_number=request.attempt_number,
            client_order_id=request.client_order_id,
            retry_scheduled=False,
            next_retry_tick=None,
            rejection_reason=None,
            spread=price_snapshot.spread,
            bid_price=price_snapshot.bid,
            ask_price=price_snapshot.ask,
            reference_price=price_snapshot.ask,
            execution_price=exec_price,
        )

===============================================================================
4) CREATE: src/brokers/ibkr_broker.py  (STUB ONLY — NO REAL TRADING)
===============================================================================
Paste:

from __future__ import annotations

from dataclasses import dataclass

from src.brokers.base_broker import BaseBroker, BrokerOrderRequest

# Import system ExecutionResult for consistent downstream handling.
from src.execution.execution_types import ExecutionResult


@dataclass
class IbkrBroker(BaseBroker):
    """
    LIVE-capable broker adapter (stub in Phase 12.1).
    In later steps this will wrap ibapi/ib_insync or your IBKR client.
    For now: return a safe stub result and emit NO broker-side actions.
    """
    def name(self) -> str:
        return "IBKR_BROKER"

    def is_live(self) -> bool:
        return True

    def place_order(self, request: BrokerOrderRequest) -> ExecutionResult:
        # IMPORTANT SAFETY: do not place real orders in Phase 12.1
        return ExecutionResult(
            symbol=request.symbol,
            trader_type=request.trader_type or "UNKNOWN",
            attempted=False,
            status="LIVE_STUB",
            rationale="LIVE broker stub: Phase 12.1 does not submit to IBKR.",
            direction=request.direction,
            quantity=0,
            entry_price=None,
            exit_price=None,
            raw_price=None,
            slippage_applied=0,
            entry_tick=request.created_tick,
            exit_tick=None,
            stop_loss_price=None,
            take_profit_price=None,
            gross_realised_pnl=0,
            commission=0,
            net_realised_pnl=0,
            requested_quantity=request.quantity,
            filled_quantity=0,
            remaining_quantity=request.quantity,
            fill_status="UNKNOWN",
            average_fill_price=None,
            note="No broker interaction performed.",
            gateway_decision=None,
            attempt_number=request.attempt_number,
            client_order_id=request.client_order_id,
            retry_scheduled=False,
            next_retry_tick=None,
            rejection_reason=None,
            spread=None,
            bid_price=None,
            ask_price=None,
            reference_price=None,
            execution_price=None,
        )

===============================================================================
5) MODIFY: src/execution/execution_engine.py
===============================================================================
INSTRUCTION
Refactor ExecutionEngine to depend on BaseBroker and route all order placement through broker.place_order().

A) Add imports near top:

from src.brokers.base_broker import BrokerOrderRequest
from src.brokers.base_broker import BaseBroker

B) Update ExecutionEngine __init__ signature to accept broker:

class ExecutionEngine:
    def __init__(self, ..., broker: BaseBroker, ...):
        self._broker = broker

Keep existing deterministic components in ExecutionEngine ONLY if other parts still reference them;
otherwise move them into SimBroker (preferred) and keep ExecutionEngine clean.

C) Locate the method that currently does:
- generate client_order_id
- gateway decision
- liquidity
- registry registration
- returns ExecutionResult

Replace that internal flow with:
- Build BrokerOrderRequest
- Call self._broker.place_order(request)
- Keep the existing “SIM mode active — no broker calls” log ONLY if broker.is_live() is False; otherwise log that LIVE stub returned.

Pseudo-pattern:

client_order_id = <existing deterministic id creation>
req = BrokerOrderRequest(
    client_order_id=client_order_id,
    symbol=risk_decision.symbol,
    direction=risk_decision.direction,
    quantity=risk_decision.max_position_size,
    order_type="MKT",
    trader_type=risk_decision.trader_type,
    strategy_name=risk_decision.strategy_name,
    attempt_number=<existing attempt>,
    created_tick=current_tick,
)

result = self._broker.place_order(req)

Return result (and any list aggregation remains unchanged).

D) Ensure “blocked” decisions remain blocked (ExecutionEngine should still short-circuit when risk_decision.allowed is False).
That path should return an ExecutionResult with status="BLOCKED" exactly as you already have.

E) Ensure retry scheduling remains deterministic.
If your engine currently stores retry queue internally, keep it.
But only schedule retries when broker returns status="RETRY_SCHEDULED" and includes next_retry_tick.

If your ExecutionResult already contains:
- retry_scheduled
- next_retry_tick
- attempt_number
Use those fields to keep existing retry queue behaviour.

===============================================================================
6) WIRING: Compose the correct broker by RUN_MODE
===============================================================================
Find where ExecutionEngine is constructed (likely orchestrator / factory / main bootstrap).
Modify to:

- If RUN_MODE == SIM: use SimBroker(...) with deterministic gateway/liquidity/price_feed/registry
- If RUN_MODE == LIVE: use IbkrBroker() (stub)

Example (adapt to your actual file names and constructors):

from src.brokers import SimBroker, IbkrBroker
from src.execution.sim_deterministic_gateway import DeterministicGateway
from src.execution.sim_liquidity_model import DeterministicLiquidityModel
from src.execution.sim_price_feed import DeterministicPriceFeed
from src.registry.trade_registry import TradeRegistry

if run_mode == "SIM":
    broker = SimBroker(
        gateway=DeterministicGateway(),
        liquidity=DeterministicLiquidityModel(),
        price_feed=DeterministicPriceFeed(),
        registry=trade_registry,  # use the same registry instance the system uses
    )
else:
    broker = IbkrBroker()

execution_engine = ExecutionEngine(
    ...,
    broker=broker,
    ...,
)

IMPORTANT
- Use ONE TradeRegistry instance across system (risk uses it, execution uses it, exit uses it).
- Do not create a second registry in the broker unless you are passing the shared one.

===============================================================================
VALIDATION CHECKLIST
===============================================================================
Run `python src/main.py` in SIM mode.
Expected:
- Same logs as before for scanner/pattern/strategy/risk.
- Execution should still show deterministic outcomes: ACCEPT/REJECT/SOFT_REJECT and liquidity fills.
- Active trade registry should still register/unregister.
- Shutdown force-close should still work.
- Invariants OK.
- No real broker calls.

Optional sanity:
Set RUN_MODE=LIVE (if your config supports it).
Expected:
- Risk decisions still produced.
- Execution returns status LIVE_STUB and does NOT register trades.
- System continues cleanly.

END