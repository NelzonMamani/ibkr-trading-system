from src.config.runtime_config import RunMode
from src.strategies.power_hour.strategy import PowerHourStrategy


def _watchlist(symbol: str = "AAPL") -> list[dict]:
    return [{"symbol": symbol}]


def test_strategy_deterministic_outputs_in_sim_and_paper() -> None:
    strategy = PowerHourStrategy()
    kwargs = dict(
        watchlist=_watchlist(),
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T19:30:00+00:00",
        session_phase="MORNING",
    )
    sim = strategy.process_watchlist(mode=RunMode.SIM, **kwargs)
    paper = strategy.process_watchlist(mode=RunMode.PAPER, **kwargs)
    assert sim == paper


def test_strategy_returns_empty_in_read_only_and_live() -> None:
    strategy = PowerHourStrategy()
    kwargs = dict(
        watchlist=_watchlist(),
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T19:30:00+00:00",
        session_phase="MORNING",
    )
    assert strategy.process_watchlist(mode=RunMode.READ_ONLY, **kwargs) == []
    assert strategy.process_watchlist(mode=RunMode.LIVE, **kwargs) == []


def test_strategy_handles_empty_watchlist() -> None:
    strategy = PowerHourStrategy()
    intents = strategy.process_watchlist(
        watchlist=[],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T19:30:00+00:00",
        mode=RunMode.SIM,
        session_phase="MORNING",
    )
    assert intents == []
