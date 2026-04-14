from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExitDecision:
    action: str
    reason: str
    new_stop_price: float | None = None
    scale_quantity: int | None = None


class RossExitIntelligence:
    """Ross-owned exit intelligence for momentum management decisions."""

    def __init__(
        self,
        *,
        max_hold_time_seconds: int,
        fast_failure_seconds: int,
        fast_failure_min_progress: float,
        stall_candles_without_high: int,
        stall_rejections_threshold: int,
    ) -> None:
        self._max_hold_time_seconds = int(max_hold_time_seconds)
        self._fast_failure_seconds = int(fast_failure_seconds)
        self._fast_failure_min_progress = float(fast_failure_min_progress)
        self._stall_candles_without_high = int(stall_candles_without_high)
        self._stall_rejections_threshold = int(stall_rejections_threshold)

    def evaluate(
        self,
        *,
        trade: Any,
        current_price: float,
        current_volume: float | None,
        time_in_trade_sec: float,
        market_state: dict[str, Any] | None = None,
    ) -> ExitDecision:
        del current_volume  # Volume is optional input; current Ross logic is state-driven.
        state = market_state or {}

        if current_price <= float(trade.stop_loss_price):
            return ExitDecision(action="EXIT_MARKET", reason="STOP_LOSS_HIT")

        first_target_price = float(trade.first_target_price)
        hod_price_raw = state.get("hod_price")
        if hod_price_raw is not None:
            hod_price = float(hod_price_raw)
            if trade.entry_price < hod_price <= first_target_price:
                first_target_price = hod_price

        if current_price >= first_target_price:
            if (not bool(trade.partial_taken)) and int(trade.quantity) > 1:
                return ExitDecision(
                    action="SCALE_OUT",
                    reason="TARGET_HIT",
                    scale_quantity=max(1, int(trade.quantity) // 2),
                )
            return ExitDecision(action="EXIT_MARKET", reason="TARGET_HIT")

        profit_per_share = float(current_price) - float(trade.entry_price)
        if time_in_trade_sec >= self._fast_failure_seconds and profit_per_share <= self._fast_failure_min_progress:
            return ExitDecision(action="EXIT_MARKET", reason="NO_IMMEDIATE_FOLLOW_THROUGH")

        no_new_high_candles = int(state.get("candles_since_new_high", 0) or 0)
        rejection_count = int(state.get("rejection_count", 0) or 0)
        if no_new_high_candles >= self._stall_candles_without_high or rejection_count >= self._stall_rejections_threshold:
            return ExitDecision(action="EXIT_MARKET", reason="STALL_AT_LEVEL")

        weakness = bool(state.get("large_upper_wick", False)) or bool(state.get("stall_near_hod", False)) or bool(
            state.get("failed_new_high", False)
        )
        red_vs_green = float(state.get("red_volume_ratio", 0.0) or 0.0) > float(state.get("green_volume_ratio", 0.0) or 0.0)
        if weakness or red_vs_green:
            if bool(trade.partial_taken):
                return ExitDecision(action="EXIT_MARKET", reason="MOMENTUM_WEAKNESS")
            return ExitDecision(
                action="SCALE_OUT",
                reason="MOMENTUM_WEAKNESS",
                scale_quantity=max(1, int(trade.quantity) // 2),
            )

        if bool(trade.trailing_active) and current_price < float(trade.last_trail_price):
            return ExitDecision(action="EXIT_MARKET", reason="TRAILING_STOP_BROKEN")

        if time_in_trade_sec > self._max_hold_time_seconds:
            return ExitDecision(action="EXIT_MARKET", reason="MAX_HOLD_TIME_EXCEEDED")

        if bool(trade.partial_taken) and float(trade.stop_loss_price) < float(trade.break_even_price):
            return ExitDecision(
                action="MOVE_STOP",
                reason="PROTECT_BREAK_EVEN",
                new_stop_price=float(trade.break_even_price),
            )

        near_key_level = bool(state.get("key_level_hit", False)) or bool(state.get("near_resistance", False))
        if bool(trade.partial_taken) and near_key_level and not bool(trade.trailing_active):
            return ExitDecision(action="ACTIVATE_TRAILING", reason="TRAILING_ARMED_AT_KEY_LEVEL")

        return ExitDecision(action="HOLD", reason="NO_EXIT_CONDITION")
