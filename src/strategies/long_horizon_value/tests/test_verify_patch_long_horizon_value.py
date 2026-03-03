from src.config.runtime_config import RunMode
from src.strategies.long_horizon_value.runner import LongHorizonValueRunner
from src.strategies.long_horizon_value.strategy import LongHorizonValueStrategy
from src.strategies.long_horizon_value.strategy_policy import (
    MAX_SINGLE_POSITION_PCT,
    MIN_OPERATING_YEARS,
    portfolio_allows,
    required_margin_of_safety,
)


def test_long_horizon_policy_loads_with_invariants() -> None:
    assert MIN_OPERATING_YEARS >= 5
    assert 0.0 < MAX_SINGLE_POSITION_PCT <= 0.2
    assert required_margin_of_safety("LOW") > required_margin_of_safety("HIGH")
    assert portfolio_allows(MAX_SINGLE_POSITION_PCT)


def test_long_horizon_deterministic_evaluation_path() -> None:
    strategy = LongHorizonValueStrategy()
    kwargs = dict(
        watchlist=[{"symbol": "AAPL"}],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T14:50:00+00:00",
        mode=RunMode.SIM,
        session_phase="MORNING",
    )
    first = strategy.process_watchlist(**kwargs)
    second = strategy.process_watchlist(**kwargs)
    assert [i.direction for i in first] == ["LONG"]
    assert [i.direction for i in second] == ["LONG"]


def test_long_horizon_respects_mode_execution_gate_in_paper() -> None:
    strategy = LongHorizonValueStrategy()
    intents = strategy.process_watchlist(
        watchlist=[{"symbol": "AAPL"}],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T14:55:00+00:00",
        mode=RunMode.PAPER,
        session_phase="MORNING",
    )
    assert [intent.direction for intent in intents] == ["LONG"]


def test_long_horizon_runner_fallback_is_long_only_in_sim_and_paper() -> None:
    strategy = LongHorizonValueStrategy()
    kwargs = dict(
        watchlist=[{"symbol": "AAPL"}],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T14:55:00+00:00",
        session_phase="MORNING",
    )

    sim_intents = strategy.process_watchlist(mode=RunMode.SIM, **kwargs)
    paper_intents = strategy.process_watchlist(mode=RunMode.PAPER, **kwargs)

    assert all(intent.direction == "LONG" for intent in sim_intents)
    assert all(intent.direction == "LONG" for intent in paper_intents)


def test_long_horizon_fallback_disabled_in_live_and_read_only() -> None:
    strategy = LongHorizonValueStrategy()
    kwargs = dict(
        watchlist=[{"symbol": "AAPL"}],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T14:55:00+00:00",
        session_phase="MORNING",
    )

    assert strategy.process_watchlist(mode=RunMode.LIVE, **kwargs) == []
    assert strategy.process_watchlist(mode=RunMode.READ_ONLY, **kwargs) == []


def test_long_horizon_underwriting_batch_is_skipped_during_rth() -> None:
    runner = LongHorizonValueRunner()

    def _should_not_run(**kwargs):
        raise AssertionError(f"underwriting batch should be skipped during RTH: {kwargs}")

    runner._run_underwriting_batch = _should_not_run  # type: ignore[method-assign]
    result = runner.run(
        {
            "watchlist": [{"symbol": "AAPL"}],
            "mode": RunMode.SIM.value,
            "session_label": "RTH",
        }
    )
    statuses = [report.get("status") for report in result.get("reports", [])]
    assert "UNDERWRITING_SKIPPED_SESSION_GUARD" in statuses
