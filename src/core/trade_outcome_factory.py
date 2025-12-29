from models.data_models import ExecutionResult
from domain.trade_outcome import TradeOutcome


class TradeOutcomeFactory:
    """Pure utility for constructing TradeOutcome records from closed trades."""

    @staticmethod
    def from_execution_result(
        execution_result: ExecutionResult,
        strategy_name: str,
        trader_type: str,
    ) -> TradeOutcome:
        direction = (getattr(execution_result, "direction", "") or "").upper()
        quantity = getattr(execution_result, "quantity", 1) or 0
        entry_price = getattr(execution_result, "entry_price", 0.0) or 0.0
        exit_price = getattr(execution_result, "exit_price", 0.0) or 0.0

        if direction == "SHORT":
            gross_realised_pnl = (entry_price - exit_price) * quantity
        else:
            gross_realised_pnl = (exit_price - entry_price) * quantity

        gross_realised_pnl = round(gross_realised_pnl, 2)
        commission = getattr(execution_result, "commission", 0.0) or 0.0
        try:
            commission_value = float(commission)
        except (TypeError, ValueError):
            commission_value = 0.0
        commission_value = round(commission_value, 4)

        net_realised_pnl = round(gross_realised_pnl - commission_value, 2)

        entry_tick = getattr(execution_result, "entry_tick", None)
        exit_tick = getattr(execution_result, "exit_tick", None)
        if entry_tick is None or exit_tick is None:
            duration_ticks = 0
        else:
            duration_ticks = exit_tick - entry_tick

        if net_realised_pnl > 0:
            outcome = "WIN"
        elif net_realised_pnl < 0:
            outcome = "LOSS"
        else:
            outcome = "FLAT"

        return TradeOutcome(
            symbol=getattr(execution_result, "symbol", "UNKNOWN"),
            trader_type=trader_type,
            strategy_name=strategy_name,
            direction=direction or "UNKNOWN",
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=quantity,
            gross_realised_pnl=gross_realised_pnl,
            commission=commission_value,
            net_realised_pnl=net_realised_pnl,
            duration_ticks=duration_ticks,
            outcome=outcome,
        )
