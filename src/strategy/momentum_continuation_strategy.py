"""
Momentum Continuation strategy plugin.

This module translates detected "Momentum Continuation" patterns into
TradeIntent objects without applying thresholds, sizing, or risk logic. It
keeps the system deterministic and SIM-only while demonstrating coexistence
with other strategy modules like GapAndGoStrategy.
"""

from typing import List

from config.trading_config import MIN_HOLD_TICKS
from models.data_models import PatternResult, TradeIntent
from strategy.exit_signal import ExitSignal
from strategy.base_strategy import BaseStrategy


class MomentumContinuationStrategy(BaseStrategy):
    """Pure translation from Momentum Continuation pattern into a long MOMENTUM intent."""

    name = "MomentumContinuationStrategy"

    def evaluate(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
        print(
            f"[STRATEGY:Momentum] Evaluation start — received {len(pattern_results)} pattern(s) for review"
        )
        trade_intents: List[TradeIntent] = []
        for pattern in pattern_results:
            if "Momentum Continuation" in pattern.pattern_name:
                rationale = (
                    f"{pattern.rationale} | Teaching note: translating 'Momentum Continuation' detection into a long MOMENTUM intent."
                )
                print(
                    "[STRATEGY:Momentum] Matched pattern — creating TradeIntent "
                    f"for symbol={pattern.symbol} with confidence={pattern.confidence}"
                )
                trade_intents.append(
                    TradeIntent(
                        symbol=pattern.symbol,
                        direction="LONG",
                        strategy_name=self.name,
                        confidence=pattern.confidence,
                        rationale=rationale,
                        trader_type="MOMENTUM",
                        gap_percent=getattr(pattern, "gap_percent", None),
                        rvol=getattr(pattern, "rvol", None),
                        float_millions=getattr(pattern, "float_millions", None),
                    )
                )
            else:
                print(
                    "[STRATEGY:Momentum] Skipped pattern — not a Momentum Continuation label "
                    f"for symbol={pattern.symbol} (pattern='{pattern.pattern_name}')"
                )
        print(
            f"[STRATEGY:Momentum] Evaluation complete — generated {len(trade_intents)} TradeIntent(s)"
        )
        return trade_intents

    def evaluate_exit_signals(self, active_trades: List, current_tick: int) -> List[ExitSignal]:
        print(
            f"[STRATEGY:Momentum] Exit review start — evaluating {len(active_trades)} active trade(s)"
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
                    "[STRATEGY:Momentum] Exit request deferred — min hold not met "
                    f"(symbol={symbol} hold_duration={hold_duration} min_hold={MIN_HOLD_TICKS})"
                )
                continue

            rationale = (
                f"Teaching exit request after {hold_duration} tick(s); "
                "Momentum Continuation is ready to secure progress once minimum hold is satisfied."
            )
            exit_signal = ExitSignal(
                symbol=symbol,
                trader_type=trader_type,
                strategy_name=self.name,
                reason=rationale,
            )
            exit_signals.append(exit_signal)
            print(
                "[STRATEGY:Momentum] ExitSignal created "
                f"symbol={symbol} trader_type={trader_type} hold_duration={hold_duration}"
            )

        print(
            f"[STRATEGY:Momentum] Exit review complete — requested {len(exit_signals)} exit(s)"
        )
        return exit_signals
