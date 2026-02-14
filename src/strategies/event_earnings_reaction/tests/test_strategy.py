from src.config.runtime_config import RunMode
from src.strategies.event_earnings_reaction.strategy import EventEarningsReactionStrategy


def _entry(**overrides):
    base = {"symbol": "AAPL"}
    base.update({'earnings_surprise': 0.1, 'gap_pct': 3.0, 'relative_volume': 2.0})
    base.update(overrides)
    return base


def test_strategy_generates_intent_in_sim() -> None:
    strategy = EventEarningsReactionStrategy()
    intents = strategy.process_watchlist(
        watchlist=[_entry()],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T15:00:00+00:00",
        mode=RunMode.SIM,
        session_phase="MORNING",
    )
    assert len(intents) == 1


def test_strategy_generates_intent_in_paper() -> None:
    strategy = EventEarningsReactionStrategy()
    intents = strategy.process_watchlist(
        watchlist=[_entry()],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T15:00:00+00:00",
        mode=RunMode.PAPER,
        session_phase="MORNING",
    )
    assert len(intents) == 1


def test_strategy_returns_empty_in_live() -> None:
    strategy = EventEarningsReactionStrategy()
    intents = strategy.process_watchlist(
        watchlist=[_entry(symbol="")],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T15:00:00+00:00",
        mode=RunMode.LIVE,
        session_phase="MORNING",
    )
    assert intents == []


def test_strategy_handles_dict_watchlist_rows() -> None:
    strategy = EventEarningsReactionStrategy()
    intents = strategy.process_watchlist(
        watchlist=[_entry()],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T15:00:00+00:00",
        mode=RunMode.SIM,
        session_phase="MORNING",
    )
    assert intents and intents[0].symbol == "AAPL"
