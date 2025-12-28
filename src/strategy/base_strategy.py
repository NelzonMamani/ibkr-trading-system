"""
Base strategy contract for teaching-first, pluggable strategy modules.

Strategies are isolated modules so StrategyRunner can dispatch them without
embedding pattern-specific logic. Each strategy stays stateless per evaluation
cycle and consumes PatternResult objects (not raw scanner data) to keep the
responsibilities clear: scanners discover candidates, pattern engines label
behaviors, and strategies translate those labels into TradeIntent objects.
"""

from abc import ABC, abstractmethod
from typing import List

from models.data_models import PatternResult, TradeIntent
from strategy.exit_signal import ExitSignal


class BaseStrategy(ABC):
    """
    Minimal contract all strategy plugins must follow.

    Statelessness ensures deterministic, repeatable outputs for every cycle
    given the same PatternResults.
    """

    name: str = "BaseStrategy"

    @abstractmethod
    def evaluate(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
        """Translate pattern results into zero or more TradeIntents."""
        raise NotImplementedError

    def evaluate_exit_signals(self, active_trades: List, current_tick: int) -> List[ExitSignal]:
        """
        Optional hook for strategies to suggest exits for their active trades.

        Default: no exit signals emitted. Strategies override to provide
        advisory exit requests while TradeExitEngine remains authoritative.
        """

        return []
