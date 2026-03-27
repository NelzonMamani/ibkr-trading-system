from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.config.runtime_config import RunMode
from src.domain.market_snapshot import MarketSnapshot
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_trace import RossPatternFailureTraceCollector
from src.strategies.ross_momentum.patterns.pattern_types import PatternResult
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


@dataclass
class EmptyRegistry:
    inactive_pattern_ids: set[str]

    @property
    def pattern_ids(self) -> list[str]:
        return []

    def run(self, inputs, *, trace_context=None, trace_collector=None) -> list[PatternResult]:
        return []


def _watchlist_row(symbol: str = "TEST") -> dict:
    return {
        "symbol": symbol,
        "promotion_reason": "manual_focus",
        "session_label": "PRE",
        "last_price": 11.6,
        "bid": 11.59,
        "ask": 11.61,
        "volume": 950000,
        "rvol": 3.4,
        "float_millions": 18.0,
        "premarket_high": 11.55,
        "prior_close": 10.8,
    }


def _snapshot(symbol: str = "TEST") -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        bid=11.59,
        ask=11.61,
        last=11.6,
        volume=950000,
        asof_utc=datetime.now(timezone.utc),
    )


def _base_strategy(monkeypatch, tmp_path, bars: list[Candle]) -> RossMomentumStrategyV1:
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: bars,
    )
    strategy = RossMomentumStrategyV1()
    strategy._failure_trace_collector = RossPatternFailureTraceCollector(evidence_root=tmp_path)
    strategy._pattern_registry = EmptyRegistry(inactive_pattern_ids=set())
    strategy._data_contract_block_reasons = lambda **kwargs: []
    return strategy


def _hod_break_bars() -> list[Candle]:
    return [
        Candle(open=10.8, high=10.9, low=10.75, close=10.88, volume=1200),
        Candle(open=10.88, high=11.0, low=10.84, close=10.98, volume=1500),
        Candle(open=10.98, high=11.15, low=10.95, close=11.10, volume=1900),
        Candle(open=11.10, high=11.28, low=11.05, close=11.22, volume=2400),
        Candle(open=11.22, high=11.42, low=11.18, close=11.36, volume=2900),
        Candle(open=11.36, high=11.60, low=11.32, close=11.58, volume=3600),
    ]


def _micro_pullback_bars() -> list[Candle]:
    return [
        Candle(open=10.0, high=10.2, low=9.95, close=10.15, volume=1000),
        Candle(open=10.15, high=10.4, low=10.1, close=10.35, volume=1300),
        Candle(open=10.35, high=10.6, low=10.3, close=10.52, volume=1500),
        Candle(open=10.52, high=10.68, low=10.45, close=10.60, volume=1700),
        Candle(open=10.60, high=10.64, low=10.50, close=10.54, volume=1450),
        Candle(open=10.54, high=10.62, low=10.48, close=10.57, volume=1500),
    ]


def test_real_setup_engine_setup_triggers_when_no_patterns(monkeypatch, tmp_path, capsys) -> None:
    strategy = _base_strategy(monkeypatch, tmp_path, _hod_break_bars())

    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row()],
        snapshots={"TEST": _snapshot()},
        session_label="PRE",
        timestamp_utc="cycle-fallback",
        mode=RunMode.LIVE,
        session_phase="PRE",
    )

    assert intents
    out = capsys.readouterr().out
    assert "[ROSS][SETUP_RESULT] symbol=TEST source=setup_engine" in out
    assert "[ROSS][INTENT_GENERATED] symbol=TEST" in out


def test_setup_engine_hod_break_produces_trigger(monkeypatch, tmp_path) -> None:
    strategy = _base_strategy(monkeypatch, tmp_path, _hod_break_bars())

    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row()],
        snapshots={"TEST": _snapshot()},
        session_label="PRE",
        timestamp_utc="cycle-fallback-hod",
        mode=RunMode.LIVE,
        session_phase="PRE",
    )

    assert intents
    assert intents[0].pattern_name.endswith("HOD_BREAK") or intents[0].pattern_name.endswith("RANGE_BREAKOUT") or intents[0].pattern_name.endswith("PREMARKET_HIGH_BREAK")
    assert intents[0].trigger_ready is True
    assert intents[0].trigger_id.endswith(":TRIGGER") or bool(intents[0].trigger_id)
    assert intents[0].entry_price is not None
    assert intents[0].stop_loss_price is not None


def test_no_synthetic_lightweight_setup_detector_available(monkeypatch, tmp_path) -> None:
    strategy = _base_strategy(monkeypatch, tmp_path, _micro_pullback_bars())
    assert not hasattr(strategy, "_detect_lightweight_setups")


def test_pipeline_not_blocked_by_missing_patterns(monkeypatch, tmp_path) -> None:
    strategy = _base_strategy(monkeypatch, tmp_path, _hod_break_bars())

    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row()],
        snapshots={"TEST": _snapshot()},
        session_label="PRE",
        timestamp_utc="cycle-not-blocked",
        mode=RunMode.LIVE,
        session_phase="PRE",
    )

    assert intents
    assert intents[0].decision in {"TRADE_READY", "ARMED_WAITING_TRIGGER", "TRIGGER_FIRED_INTENT_EMITTED"}
