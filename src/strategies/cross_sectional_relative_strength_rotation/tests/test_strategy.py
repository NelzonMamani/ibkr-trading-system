from src.config.runtime_config import RunMode
from src.strategies.cross_sectional_relative_strength_rotation.strategy import (
    CrossSectionalRelativeStrengthRotationStrategy,
)


def test_sim_outputs_deterministic_intents() -> None:
    strategy = CrossSectionalRelativeStrengthRotationStrategy()
    watchlist = [{"symbol": "AAPL"}, {"symbol": "MSFT"}, {"symbol": "NVDA"}]
    first = strategy.process_watchlist(
        watchlist=watchlist,
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T15:00:00+00:00",
        mode=RunMode.SIM,
        session_phase="MORNING",
    )
    second = strategy.process_watchlist(
        watchlist=watchlist,
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T15:00:00+00:00",
        mode=RunMode.SIM,
        session_phase="MORNING",
    )
    assert [i.symbol for i in first] == [i.symbol for i in second]


def test_live_returns_empty() -> None:
    strategy = CrossSectionalRelativeStrengthRotationStrategy()
    intents = strategy.process_watchlist(
        watchlist=[{"symbol": "AAPL"}],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T15:00:00+00:00",
        mode=RunMode.LIVE,
        session_phase="MORNING",
    )
    assert intents == []
