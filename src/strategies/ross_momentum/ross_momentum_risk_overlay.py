"""Ross Momentum-specific risk overlay enforced before global risk engine logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from src.config.config_resolver import get_config
from src.core.event_collector import EventCollector
from src.models.data_models import RiskDecision, TradeIntent
from src.models.risk_decision import (
    ROSS_BLOCK_COOLDOWN_ACTIVE,
    ROSS_BLOCK_FLOAT_TOO_HIGH,
    ROSS_BLOCK_GAP_OUT_OF_RANGE,
    ROSS_BLOCK_LOW_CONFIDENCE,
    ROSS_BLOCK_LOW_RVOL,
    ROSS_BLOCK_MAX_ATTEMPTS,
    ROSS_BLOCK_SHORT,
)


@dataclass(frozen=True)
class RiskContext:
    current_tick: int


class RossMomentumRiskOverlay:
    """Deterministic, strategy-scoped overlay for Ross Momentum trade intents."""

    def __init__(self, event_collector: Optional[EventCollector] = None) -> None:
        self._event_collector = event_collector or EventCollector()
        self._last_attempt_tick: Dict[str, int] = {}
        self._attempt_counts: Dict[str, int] = {}
        self.min_gap = float(get_config("ROSS_RISK_MIN_GAP"))
        self.max_gap = float(get_config("ROSS_RISK_MAX_GAP"))
        self.float_ceiling = float(get_config("ROSS_RISK_FLOAT_CEILING"))
        self.rvol_floor = float(get_config("ROSS_RISK_RVOL_FLOOR"))
        self.confidence_floor = float(get_config("ROSS_RISK_CONFIDENCE_FLOOR"))
        self.cooldown_ticks = int(get_config("ROSS_RISK_COOLDOWN_TICKS"))
        self.max_attempts_per_symbol = int(get_config("ROSS_RISK_MAX_ATTEMPTS_PER_SYMBOL"))

    def evaluate(
        self,
        trade_intent: TradeIntent,
        context: RiskContext,
    ) -> Optional[RiskDecision]:
        symbol = trade_intent.symbol
        current_tick = context.current_tick if context is not None else 0
        attempts = self._attempt_counts.get(symbol, 0)
        if attempts >= self.max_attempts_per_symbol:
            rationale = (
                f"Ross Momentum max attempts reached ({attempts}/"
                f"{self.max_attempts_per_symbol}) for {symbol}; blocking new intent."
            )
            return self._blocked_decision(trade_intent, ROSS_BLOCK_MAX_ATTEMPTS, rationale)

        last_attempt = self._last_attempt_tick.get(symbol)
        if last_attempt is not None and current_tick - last_attempt < self.cooldown_ticks:
            self._record_attempt(symbol, current_tick, update_last_tick=False)
            rationale = (
                f"Ross Momentum cooldown active for {symbol}: "
                f"last_attempt_tick={last_attempt} current_tick={current_tick} "
                f"cooldown_ticks={self.cooldown_ticks}."
            )
            return self._blocked_decision(trade_intent, ROSS_BLOCK_COOLDOWN_ACTIVE, rationale)

        direction = (trade_intent.direction or "").upper()
        if direction != "LONG":
            self._record_attempt(symbol, current_tick, update_last_tick=False)
            rationale = "Ross Momentum overlay only allows LONG intents; blocking short/neutral intent."
            return self._blocked_decision(trade_intent, ROSS_BLOCK_SHORT, rationale)

        gap_percent = getattr(trade_intent, "gap_percent", None)
        if gap_percent is None or not (self.min_gap <= gap_percent <= self.max_gap):
            self._record_attempt(symbol, current_tick, update_last_tick=False)
            rationale = (
                f"Ross Momentum gap filter failed: gap_percent={gap_percent} "
                f"not in range {self.min_gap}-{self.max_gap}."
            )
            return self._blocked_decision(trade_intent, ROSS_BLOCK_GAP_OUT_OF_RANGE, rationale)

        float_millions = getattr(trade_intent, "float_millions", None)
        if float_millions is None or float_millions > self.float_ceiling:
            self._record_attempt(symbol, current_tick, update_last_tick=False)
            rationale = (
                f"Ross Momentum float filter failed: float_millions={float_millions} "
                f"> {self.float_ceiling}."
            )
            return self._blocked_decision(trade_intent, ROSS_BLOCK_FLOAT_TOO_HIGH, rationale)

        rvol = getattr(trade_intent, "rvol", None)
        if rvol is None or rvol < self.rvol_floor:
            self._record_attempt(symbol, current_tick, update_last_tick=False)
            rationale = (
                f"Ross Momentum rVol filter failed: rvol={rvol} "
                f"< {self.rvol_floor}."
            )
            return self._blocked_decision(trade_intent, ROSS_BLOCK_LOW_RVOL, rationale)

        if trade_intent.confidence < self.confidence_floor:
            self._record_attempt(symbol, current_tick, update_last_tick=False)
            rationale = (
                f"Ross Momentum confidence filter failed: confidence={trade_intent.confidence:.2f} "
                f"< {self.confidence_floor:.2f}."
            )
            return self._blocked_decision(trade_intent, ROSS_BLOCK_LOW_CONFIDENCE, rationale)

        self._record_attempt(symbol, current_tick, update_last_tick=True)
        return None

    def _record_attempt(self, symbol: str, tick: int, update_last_tick: bool) -> None:
        self._attempt_counts[symbol] = self._attempt_counts.get(symbol, 0) + 1
        if update_last_tick:
            self._last_attempt_tick[symbol] = tick

    def _blocked_decision(
        self,
        trade_intent: TradeIntent,
        reason_code: str,
        rationale: str,
    ) -> RiskDecision:
        self._emit_block_event(trade_intent, reason_code, rationale)
        return RiskDecision(
            symbol=trade_intent.symbol,
            allowed=False,
            max_position_size=0,
            risk_level="BLOCKED",
            rationale=rationale,
            trader_type=trade_intent.trader_type,
            strategy_name=trade_intent.strategy_name,
            direction=trade_intent.direction,
            stop_loss_price=trade_intent.stop_loss_price,
            take_profit_price=trade_intent.take_profit_price,
            reason_code=reason_code,
        )

    def _emit_block_event(
        self,
        trade_intent: TradeIntent,
        reason_code: str,
        rationale: str,
    ) -> None:
        self._event_collector.emit(
            event_type="TRADE_BLOCKED",
            source="RossMomentumRiskOverlay",
            payload={
                "symbol": trade_intent.symbol,
                "trader_type": trade_intent.trader_type,
                "strategy_name": trade_intent.strategy_name,
                "reason": reason_code,
                "reason_code": reason_code,
                "human_readable_rationale": rationale,
            },
        )
