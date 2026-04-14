from __future__ import annotations

from dataclasses import dataclass

from src.execution.post_fill_lifecycle_engine import ManagedTradeLifecycle, PositionLifecycleState


@dataclass
class ExitDecision:
    action: str  # HOLD | EXIT_MARKET | SCALE_OUT | MOVE_STOP | ACTIVATE_TRAILING
    reason: str
    new_stop_price: float | None = None
    scale_quantity: int | None = None


class RossExitIntelligence:
    def evaluate(
        self,
        *,
        trade: ManagedTradeLifecycle,
        current_price: float,
        current_volume: float | None,
        time_in_trade_sec: float,
    ) -> ExitDecision:
        del current_volume
        price = float(current_price)
        entry = float(trade.avg_fill_price)

        trade.high_water_mark = max(float(trade.high_water_mark or entry), price)

        if bool(getattr(trade, "exit_triggered", False)):
            return ExitDecision(action="HOLD", reason="already_executed")

        if trade.stop is not None and price <= float(trade.stop.trigger_price):
            return ExitDecision(action="EXIT_MARKET", reason="hard_stop_breach")

        if price >= float(trade.break_even_activation) and trade.stop is not None and trade.stop.trigger_price < entry:
            return ExitDecision(action="MOVE_STOP", reason="break_even_protection", new_stop_price=entry)

        if (
            trade.high_water_mark is not None
            and trade.state in {
                PositionLifecycleState.TRAILING_ELIGIBLE,
                PositionLifecycleState.TRAILING_ACTIVE,
                PositionLifecycleState.TARGET_ACTIVE,
            }
            and price <= float(trade.high_water_mark) * 0.995
        ):
            return ExitDecision(action="EXIT_MARKET", reason="momentum_failure")

        if time_in_trade_sec > 180 and price < (entry * 1.003):
            return ExitDecision(action="EXIT_MARKET", reason="time_stop_no_momentum")

        if price >= (entry * 1.015) and not bool(getattr(trade, "scaled_out", False)):
            qty = max(1, int(trade.filled_qty) // 2)
            return ExitDecision(action="SCALE_OUT", reason="partial_profit_take", scale_quantity=qty)

        if price >= float(trade.trailing_activation) and not bool(trade.trailing_active):
            return ExitDecision(action="ACTIVATE_TRAILING", reason="trailing_activation")

        return ExitDecision(action="HOLD", reason="no_exit_condition")
