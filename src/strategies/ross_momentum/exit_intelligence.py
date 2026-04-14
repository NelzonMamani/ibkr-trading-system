from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExitDecision:
    action: str
    reason: str
    new_stop_price: float | None = None
    scale_quantity: int | None = None

    @property
    def should_exit(self) -> bool:
        return str(self.action or "").upper() in {"EXIT_MARKET", "SCALE_OUT"}


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
        del current_volume
        state = market_state or {}
        current_price = float(current_price)
        pullback_low = float(state.get("pullback_low", state.get("last_pullback_low", trade.stop_loss_price)) or trade.stop_loss_price)

        if current_price < pullback_low:
            return ExitDecision(action="EXIT_MARKET", reason="STOP_LOSS_BREAK")

        candle_range = float(state.get("candle_range", 0.0) or 0.0)
        upper_wick = float(state.get("upper_wick", 0.0) or 0.0)
        no_continuation = bool(state.get("no_continuation", False)) or not bool(state.get("continuation", True))
        if candle_range > 0 and upper_wick >= 0.5 * candle_range and no_continuation:
            return ExitDecision(action="EXIT_MARKET", reason="MOMENTUM_WEAKNESS")

        red_volume_raw = state.get("red_volume")
        red_volume = float(red_volume_raw or 0.0)
        recent_green_volume = state.get("recent_green_volume")
        if isinstance(recent_green_volume, (list, tuple)):
            max_recent_green = max((float(v or 0.0) for v in recent_green_volume), default=0.0)
        else:
            max_recent_green = float(
                state.get("max_recent_green_volume", state.get("green_volume", state.get("green_volume_ratio", 0.0))) or 0.0
            )
        if red_volume_raw is not None and red_volume > max_recent_green:
            return ExitDecision(action="EXIT_MARKET", reason="VOLUME_REVERSAL")

        macd_value = state.get("macd", state.get("macd_histogram"))
        if macd_value is not None and float(macd_value) < 0:
            return ExitDecision(action="EXIT_MARKET", reason="MACD_INVALID")

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

        profit_per_share = current_price - float(trade.entry_price)
        no_progress = bool(state.get("no_progress", False)) or profit_per_share <= 0
        if time_in_trade_sec > self._max_hold_time_seconds and no_progress:
            return ExitDecision(action="EXIT_MARKET", reason="TIME_STOP")
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
