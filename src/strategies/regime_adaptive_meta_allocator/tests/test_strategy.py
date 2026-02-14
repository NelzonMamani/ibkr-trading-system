from src.config.runtime_config import RunMode
from src.strategies.regime_adaptive_meta_allocator.strategy import (
    RegimeAdaptiveMetaAllocatorStrategy,
)


def test_regime_allocation_is_deterministic() -> None:
    strategy = RegimeAdaptiveMetaAllocatorStrategy()
    watchlist = [{"symbol": "AAPL"}, {"symbol": "XLP"}, {"symbol": "MSFT"}]
    intents_first = strategy.process_watchlist(
        watchlist=watchlist,
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T15:00:00+00:00",
        mode=RunMode.SIM,
        session_phase="MORNING",
    )
    intents_second = strategy.process_watchlist(
        watchlist=watchlist,
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T15:00:00+00:00",
        mode=RunMode.SIM,
        session_phase="MORNING",
    )
    assert [i.symbol for i in intents_first] == [i.symbol for i in intents_second]


def test_live_returns_empty() -> None:
    strategy = RegimeAdaptiveMetaAllocatorStrategy()
    intents = strategy.process_watchlist(
        watchlist=[{"symbol": "AAPL"}],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T15:00:00+00:00",
        mode=RunMode.LIVE,
        session_phase="MORNING",
    )
    assert intents == []
