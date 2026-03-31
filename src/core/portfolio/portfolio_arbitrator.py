from __future__ import annotations

from src.application.arbitration.trade_intent_arbitrator import (
    ArbitrationContext,
    TradeIntentArbitrator,
)
from src.config.config_resolver import get_config
from src.core.portfolio.portfolio_state import PortfolioState
from src.models.data_models import TradeIntent


class PortfolioArbitrator:
    """Compatibility wrapper for the pure trade intent arbitration engine."""

    def __init__(self) -> None:
        self._arbitrator = TradeIntentArbitrator()

    def select_trades(
        self,
        trade_intents: list[TradeIntent],
        portfolio_state: PortfolioState,
    ) -> list[TradeIntent]:
        _ = portfolio_state  # Explicitly ignored: arbitration is stateless and read-only.
        context = ArbitrationContext(
            max_positions=int(get_config("E22_MAX_POSITIONS_PER_CYCLE") or 0),
            max_intents_per_cycle=int(get_config("E22_MAX_INTENTS_PER_CYCLE") or 0),
        )
        return self._arbitrator.arbitrate(trade_intents or [], context)
