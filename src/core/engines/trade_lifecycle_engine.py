from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


TRADE_STATUS_NEW = "NEW"
TRADE_STATUS_OPEN = "OPEN"
TRADE_STATUS_PARTIAL = "PARTIAL"
TRADE_STATUS_CLOSED = "CLOSED"
TRADE_STATUS_CANCELLED = "CANCELLED"
TRADE_STATUS_REJECTED = "REJECTED"


@dataclass(frozen=True)
class LifecycleEvent:
    timestamp: datetime
    event_type: str
    quantity: int
    price: float | None = None
    note: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TradeLifecycleState:
    trade_id: str
    symbol: str
    strategy_name: str
    setup_family_id: str | None
    trigger_id: str | None
    side: str
    status: str
    entry_timestamp: datetime | None
    exit_timestamp: datetime | None
    entry_price: float
    current_price: float
    stop_price: float
    initial_quantity: int
    current_quantity: int
    realized_quantity: int
    average_entry_price: float
    average_exit_price: float | None
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    initial_risk_per_share: float
    realized_r_multiple: float
    unrealized_r_multiple: float
    max_favorable_excursion: float
    max_adverse_excursion: float
    execution_mode: str
    execution_primary_timeframe: str
    execution_refinement_timeframe: str | None
    add_count: int
    partial_count: int
    exit_reason: str | None
    broker_order_ids: list[str]
    lifecycle_events: list[LifecycleEvent] = field(default_factory=list)


@dataclass(frozen=True)
class ClosedTradeRecord:
    trade_id: str
    symbol: str
    strategy_name: str
    setup_family_id: str | None
    trigger_id: str | None
    side: str
    entry_price: float
    average_exit_price: float
    initial_quantity: int
    realized_quantity: int
    realized_pnl: float
    realized_r_multiple: float
    mfe: float
    mae: float
    holding_time_seconds: float
    add_count: int
    partial_count: int
    exit_reason: str | None
    execution_mode: str
    primary_timeframe: str
    refinement_timeframe: str | None


class TradeLifecycleEngine:
    """Canonical lifecycle and PnL authority for active/closed trades."""

    def __init__(self) -> None:
        self._open_trades: dict[str, TradeLifecycleState] = {}
        self._closed_trades: list[ClosedTradeRecord] = []

    def open_trade(
        self,
        *,
        symbol: str,
        side: str,
        quantity: int,
        entry_price: float,
        stop_price: float,
        strategy_name: str = "UNKNOWN",
        setup_family_id: str | None = None,
        trigger_id: str | None = None,
        trade_id: str | None = None,
        execution_mode: str = "NORMAL",
        execution_primary_timeframe: str = "1m",
        execution_refinement_timeframe: str | None = None,
        broker_order_ids: list[str] | None = None,
        timestamp: datetime | None = None,
    ) -> TradeLifecycleState:
        if quantity <= 0:
            raise ValueError("open_trade requires positive quantity")
        if entry_price <= 0 or stop_price <= 0:
            raise ValueError("open_trade requires positive entry/stop")

        now = timestamp or datetime.now(timezone.utc)
        canonical_side = self._canonical_side(side)
        resolved_trade_id = trade_id or f"{symbol}-{uuid4().hex[:12]}"
        risk_per_share = abs(entry_price - stop_price)

        event = LifecycleEvent(
            timestamp=now,
            event_type="OPEN",
            quantity=quantity,
            price=entry_price,
            note="trade_opened",
        )
        state = TradeLifecycleState(
            trade_id=resolved_trade_id,
            symbol=symbol,
            strategy_name=strategy_name,
            setup_family_id=setup_family_id,
            trigger_id=trigger_id,
            side=canonical_side,
            status=TRADE_STATUS_OPEN,
            entry_timestamp=now,
            exit_timestamp=None,
            entry_price=entry_price,
            current_price=entry_price,
            stop_price=stop_price,
            initial_quantity=quantity,
            current_quantity=quantity,
            realized_quantity=0,
            average_entry_price=entry_price,
            average_exit_price=None,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            total_pnl=0.0,
            initial_risk_per_share=risk_per_share,
            realized_r_multiple=0.0,
            unrealized_r_multiple=0.0,
            max_favorable_excursion=0.0,
            max_adverse_excursion=0.0,
            execution_mode=execution_mode,
            execution_primary_timeframe=execution_primary_timeframe,
            execution_refinement_timeframe=execution_refinement_timeframe,
            add_count=0,
            partial_count=0,
            exit_reason=None,
            broker_order_ids=list(broker_order_ids or []),
            lifecycle_events=[event],
        )
        self._open_trades[resolved_trade_id] = state
        print(
            "[TRADE][OPEN] "
            f"symbol={symbol} trade_id={resolved_trade_id} qty={quantity} "
            f"entry={entry_price} stop={stop_price} strategy={strategy_name}"
        )
        return state

    def apply_fill(self, trade_id: str, *, quantity: int, price: float, note: str = "fill", metadata: dict[str, Any] | None = None) -> TradeLifecycleState:
        state = self._get_trade(trade_id)
        if quantity > 0:
            return self.apply_add(trade_id, add_quantity=quantity, add_price=price, note=note, metadata=metadata)
        if quantity < 0:
            return self.apply_partial_exit(trade_id, exit_quantity=abs(quantity), exit_price=price, note=note, metadata=metadata)
        return state

    def mark_to_market(self, trade_id: str, *, current_price: float, timestamp: datetime | None = None) -> TradeLifecycleState:
        state = self._get_trade(trade_id)
        state.current_price = current_price
        state.unrealized_pnl = self._pnl_delta(
            side=state.side,
            entry_price=state.average_entry_price,
            exit_price=current_price,
            quantity=state.current_quantity,
        )
        state.unrealized_r_multiple = self._to_r_multiple(
            pnl=state.unrealized_pnl,
            risk_per_share=state.initial_risk_per_share,
            initial_quantity=state.initial_quantity,
        )
        move = self._price_move_from_entry(state.side, state.average_entry_price, current_price)
        state.max_favorable_excursion = max(state.max_favorable_excursion, move)
        state.max_adverse_excursion = min(state.max_adverse_excursion, move)
        state.total_pnl = state.realized_pnl + state.unrealized_pnl

        state.lifecycle_events.append(
            LifecycleEvent(
                timestamp=timestamp or datetime.now(timezone.utc),
                event_type="UPDATE_MARK",
                quantity=state.current_quantity,
                price=current_price,
                note="mark_to_market",
            )
        )
        print(
            "[TRADE][MARK] "
            f"symbol={state.symbol} trade_id={state.trade_id} current={current_price} "
            f"unrealized_pnl={state.unrealized_pnl:.4f} unrealized_r={state.unrealized_r_multiple:.4f} "
            f"mfe={state.max_favorable_excursion:.4f} mae={state.max_adverse_excursion:.4f}"
        )
        return state

    def apply_partial_exit(
        self,
        trade_id: str,
        *,
        exit_quantity: int,
        exit_price: float,
        note: str = "partial_exit",
        metadata: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> TradeLifecycleState:
        state = self._get_trade(trade_id)
        if exit_quantity <= 0:
            raise ValueError("exit_quantity must be positive")
        if exit_quantity > state.current_quantity:
            raise ValueError("exit_quantity exceeds current quantity")

        incremental_realized = self._pnl_delta(
            side=state.side,
            entry_price=state.average_entry_price,
            exit_price=exit_price,
            quantity=exit_quantity,
        )
        prior_realized_qty = state.realized_quantity
        state.realized_pnl += incremental_realized
        state.realized_quantity += exit_quantity
        state.current_quantity -= exit_quantity
        if state.realized_quantity > 0:
            cumulative_exit_notional = (state.average_exit_price or 0.0) * prior_realized_qty + (exit_price * exit_quantity)
            state.average_exit_price = cumulative_exit_notional / state.realized_quantity
        state.partial_count += 1

        if state.current_quantity == 0:
            state.status = TRADE_STATUS_CLOSED
            state.unrealized_pnl = 0.0
            state.unrealized_r_multiple = 0.0
        else:
            state.status = TRADE_STATUS_PARTIAL
            state.unrealized_pnl = self._pnl_delta(
                side=state.side,
                entry_price=state.average_entry_price,
                exit_price=state.current_price,
                quantity=state.current_quantity,
            )
            state.unrealized_r_multiple = self._to_r_multiple(
                pnl=state.unrealized_pnl,
                risk_per_share=state.initial_risk_per_share,
                initial_quantity=state.initial_quantity,
            )
        state.realized_r_multiple = self._to_r_multiple(
            pnl=state.realized_pnl,
            risk_per_share=state.initial_risk_per_share,
            initial_quantity=state.initial_quantity,
        )
        state.total_pnl = state.realized_pnl + state.unrealized_pnl
        state.lifecycle_events.append(
            LifecycleEvent(
                timestamp=timestamp or datetime.now(timezone.utc),
                event_type="PARTIAL",
                quantity=exit_quantity,
                price=exit_price,
                note=note,
                metadata=dict(metadata or {}),
            )
        )
        print(
            "[TRADE][PARTIAL] "
            f"symbol={state.symbol} trade_id={state.trade_id} qty={exit_quantity} "
            f"realized_pnl={state.realized_pnl:.4f}"
        )
        return state

    def apply_add(
        self,
        trade_id: str,
        *,
        add_quantity: int,
        add_price: float,
        note: str = "add",
        metadata: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> TradeLifecycleState:
        state = self._get_trade(trade_id)
        if add_quantity <= 0:
            raise ValueError("add_quantity must be positive")

        old_qty = state.current_quantity
        new_qty = old_qty + add_quantity
        state.average_entry_price = (
            (state.average_entry_price * old_qty) + (add_price * add_quantity)
        ) / new_qty
        state.current_quantity = new_qty
        state.add_count += 1
        state.status = TRADE_STATUS_OPEN
        state.unrealized_pnl = self._pnl_delta(
            side=state.side,
            entry_price=state.average_entry_price,
            exit_price=state.current_price,
            quantity=state.current_quantity,
        )
        state.unrealized_r_multiple = self._to_r_multiple(
            pnl=state.unrealized_pnl,
            risk_per_share=state.initial_risk_per_share,
            initial_quantity=state.initial_quantity,
        )
        state.total_pnl = state.realized_pnl + state.unrealized_pnl
        state.lifecycle_events.append(
            LifecycleEvent(
                timestamp=timestamp or datetime.now(timezone.utc),
                event_type="ADD",
                quantity=add_quantity,
                price=add_price,
                note=note,
                metadata=dict(metadata or {}),
            )
        )
        print(
            "[TRADE][ADD] "
            f"symbol={state.symbol} trade_id={state.trade_id} qty={add_quantity} "
            f"avg_entry={state.average_entry_price:.4f} total_qty={state.current_quantity}"
        )
        return state

    def move_stop(self, trade_id: str, *, stop_price: float, note: str = "stop_move", metadata: dict[str, Any] | None = None, timestamp: datetime | None = None) -> TradeLifecycleState:
        state = self._get_trade(trade_id)
        state.stop_price = stop_price
        state.lifecycle_events.append(
            LifecycleEvent(
                timestamp=timestamp or datetime.now(timezone.utc),
                event_type="STOP_MOVE",
                quantity=state.current_quantity,
                price=stop_price,
                note=note,
                metadata=dict(metadata or {}),
            )
        )
        print(
            "[TRADE][STOP_MOVE] "
            f"symbol={state.symbol} trade_id={state.trade_id} stop={stop_price}"
        )
        return state

    def close_trade(
        self,
        trade_id: str,
        *,
        exit_price: float,
        exit_reason: str,
        timestamp: datetime | None = None,
    ) -> ClosedTradeRecord:
        state = self._get_trade(trade_id)
        now = timestamp or datetime.now(timezone.utc)
        if state.current_quantity > 0:
            self.apply_partial_exit(
                trade_id,
                exit_quantity=state.current_quantity,
                exit_price=exit_price,
                note="final_exit",
                timestamp=now,
            )

        state.status = TRADE_STATUS_CLOSED
        state.exit_reason = exit_reason
        state.exit_timestamp = now
        state.current_price = exit_price
        state.unrealized_pnl = 0.0
        state.unrealized_r_multiple = 0.0
        state.total_pnl = state.realized_pnl
        state.realized_r_multiple = self._to_r_multiple(
            pnl=state.realized_pnl,
            risk_per_share=state.initial_risk_per_share,
            initial_quantity=state.initial_quantity,
        )
        state.lifecycle_events.append(
            LifecycleEvent(
                timestamp=now,
                event_type="EXIT",
                quantity=state.realized_quantity,
                price=exit_price,
                note=exit_reason,
            )
        )
        closed = ClosedTradeRecord(
            trade_id=state.trade_id,
            symbol=state.symbol,
            strategy_name=state.strategy_name,
            setup_family_id=state.setup_family_id,
            trigger_id=state.trigger_id,
            side=state.side,
            entry_price=state.entry_price,
            average_exit_price=float(state.average_exit_price or exit_price),
            initial_quantity=state.initial_quantity,
            realized_quantity=state.realized_quantity,
            realized_pnl=state.realized_pnl,
            realized_r_multiple=state.realized_r_multiple,
            mfe=state.max_favorable_excursion,
            mae=state.max_adverse_excursion,
            holding_time_seconds=max(0.0, (now - (state.entry_timestamp or now)).total_seconds()),
            add_count=state.add_count,
            partial_count=state.partial_count,
            exit_reason=exit_reason,
            execution_mode=state.execution_mode,
            primary_timeframe=state.execution_primary_timeframe,
            refinement_timeframe=state.execution_refinement_timeframe,
        )
        self._closed_trades.append(closed)
        self._open_trades.pop(trade_id, None)
        print(
            "[TRADE][CLOSE] "
            f"symbol={state.symbol} trade_id={state.trade_id} realized_pnl={state.realized_pnl:.4f} "
            f"realized_r={state.realized_r_multiple:.4f} exit_reason={exit_reason}"
        )
        return closed

    def get_open_trades(self) -> list[TradeLifecycleState]:
        return list(self._open_trades.values())

    def get_closed_trades(self) -> list[ClosedTradeRecord]:
        return list(self._closed_trades)

    def summarize_session_metrics(self) -> dict[str, float]:
        open_trades = self.get_open_trades()
        closed_trades = self.get_closed_trades()
        realized_total = sum(trade.realized_pnl for trade in closed_trades)
        unrealized_total = sum(trade.unrealized_pnl for trade in open_trades)
        winners = sum(1 for trade in closed_trades if trade.realized_pnl > 0)
        losers = sum(1 for trade in closed_trades if trade.realized_pnl < 0)
        win_pnls = [trade.realized_pnl for trade in closed_trades if trade.realized_pnl > 0]
        loss_pnls = [trade.realized_pnl for trade in closed_trades if trade.realized_pnl < 0]
        avg_realized_r = sum(trade.realized_r_multiple for trade in closed_trades) / len(closed_trades) if closed_trades else 0.0
        summary = {
            "open_trade_count": float(len(open_trades)),
            "closed_trade_count": float(len(closed_trades)),
            "winners": float(winners),
            "losers": float(losers),
            "realized_pnl_total": realized_total,
            "unrealized_pnl_total": unrealized_total,
            "average_realized_r": avg_realized_r,
            "average_win": (sum(win_pnls) / len(win_pnls)) if win_pnls else 0.0,
            "average_loss": (sum(loss_pnls) / len(loss_pnls)) if loss_pnls else 0.0,
            "win_rate": (winners / len(closed_trades)) if closed_trades else 0.0,
        }
        print(
            "[TRADE][SUMMARY] "
            f"open={int(summary['open_trade_count'])} closed={int(summary['closed_trade_count'])} "
            f"realized_pnl={summary['realized_pnl_total']:.4f} unrealized_pnl={summary['unrealized_pnl_total']:.4f}"
        )
        return summary

    def _get_trade(self, trade_id: str) -> TradeLifecycleState:
        state = self._open_trades.get(trade_id)
        if state is None:
            raise KeyError(f"unknown trade_id={trade_id}")
        return state

    @staticmethod
    def _canonical_side(side: str) -> str:
        normalized = str(side or "LONG").upper()
        if normalized not in {"LONG", "SHORT"}:
            raise ValueError(f"invalid side={side}")
        return normalized

    @staticmethod
    def _pnl_delta(*, side: str, entry_price: float, exit_price: float, quantity: int) -> float:
        if side == "LONG":
            return (exit_price - entry_price) * quantity
        return (entry_price - exit_price) * quantity

    @staticmethod
    def _price_move_from_entry(side: str, entry_price: float, current_price: float) -> float:
        if side == "LONG":
            return current_price - entry_price
        return entry_price - current_price

    @staticmethod
    def _to_r_multiple(*, pnl: float, risk_per_share: float, initial_quantity: int) -> float:
        denominator = risk_per_share * initial_quantity
        if denominator <= 0:
            return 0.0
        return pnl / denominator
