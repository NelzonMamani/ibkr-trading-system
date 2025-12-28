"""
Deterministic Gap and Go strategy plugin.

This strategy simply translates PatternResults labeled with "Gap and Go" into
TradeIntent objects without thresholds, sizing, or broker integration.
"""

from typing import List

from config.trading_config import MIN_HOLD_TICKS
from models.data_models import PatternResult, TradeIntent
from strategy.exit_signal import ExitSignal
from strategy.base_strategy import BaseStrategy


class GapAndGoStrategy(BaseStrategy):
    """Pure translation from Gap and Go pattern into a long SCALPER intent."""

    name = "GapAndGoStrategy"

    def evaluate(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
        print(
            f"[STRATEGY:GapAndGo] Evaluation start — received {len(pattern_results)} pattern(s) for review"
        )
        trade_intents: List[TradeIntent] = []
        for pattern in pattern_results:
            if "Gap and Go" in pattern.pattern_name:
                rationale = (
                    f"{pattern.rationale} | Teaching note: translating 'Gap and Go' detection into a long SCALPER intent."
                )
                print(
                    "[STRATEGY:GapAndGo] Matched pattern — creating TradeIntent "
                    f"for symbol={pattern.symbol} with confidence={pattern.confidence}"
                )
                trade_intents.append(
                    TradeIntent(
                        symbol=pattern.symbol,
                        direction="LONG",
                        strategy_name=self.name,
                        confidence=pattern.confidence,
                        rationale=rationale,
                        trader_type="SCALPER",
                    )
                )
            else:
                print(
                    "[STRATEGY:GapAndGo] Skipped pattern — not a Gap and Go label "
                    f"for symbol={pattern.symbol} (pattern='{pattern.pattern_name}')"
                )
        print(
            f"[STRATEGY:GapAndGo] Evaluation complete — generated {len(trade_intents)} TradeIntent(s)"
        )
        return trade_intents

    def evaluate_exit_signals(self, active_trades: List, current_tick: int) -> List[ExitSignal]:
        print(
            f"[STRATEGY:GapAndGo] Exit review start — evaluating {len(active_trades)} active trade(s)"
        )
        exit_signals: List[ExitSignal] = []
        for trade in active_trades or []:
            if getattr(trade, "strategy_name", None) != self.name:
                continue

            symbol = getattr(trade, "symbol", None)
            trader_type = getattr(trade, "trader_type", "UNKNOWN")
            entry_tick = getattr(trade, "entry_tick", current_tick)
            hold_duration = current_tick - entry_tick

            if symbol is None:
                continue

            if hold_duration < MIN_HOLD_TICKS:
                print(
                    "[STRATEGY:GapAndGo] Exit request deferred — min hold not met "
                    f"(symbol={symbol} hold_duration={hold_duration} min_hold={MIN_HOLD_TICKS})"
                )
                continue

            rationale = (
                f"Teaching exit request after holding {hold_duration} tick(s); "
                "Gap and Go strategy would lock in gains once minimum visibility is met."
            )
            exit_signal = ExitSignal(
                symbol=symbol,
                trader_type=trader_type,
                strategy_name=self.name,
                reason=rationale,
            )
            exit_signals.append(exit_signal)
            print(
                "[STRATEGY:GapAndGo] ExitSignal created "
                f"symbol={symbol} trader_type={trader_type} hold_duration={hold_duration}"
            )

        print(
            f"[STRATEGY:GapAndGo] Exit review complete — requested {len(exit_signals)} exit(s)"
        )
        return exit_signals
