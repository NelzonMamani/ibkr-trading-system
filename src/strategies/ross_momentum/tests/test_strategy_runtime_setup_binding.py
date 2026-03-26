from __future__ import annotations

from datetime import datetime, timezone

from src.config.runtime_config import RunMode
from src.domain.market_snapshot import MarketSnapshot
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


class _EmptyRegistry:
    inactive_pattern_ids: set[str] = set()

    @property
    def pattern_ids(self) -> list[str]:
        return []

    def run(self, inputs, *, trace_context=None, trace_collector=None):
        return []


def _bars(**kwargs):
    return [
        Candle(open=10.0, high=10.3, low=9.9, close=10.2, volume=2000),
        Candle(open=10.2, high=10.5, low=10.1, close=10.4, volume=2600),
        Candle(open=10.4, high=10.7, low=10.3, close=10.65, volume=3200),
        Candle(open=10.65, high=10.9, low=10.55, close=10.85, volume=3800),
        Candle(open=10.85, high=11.1, low=10.8, close=11.0, volume=4500),
    ]


def test_runtime_setup_binding_emits_terminal_for_non_detected(monkeypatch, capsys):
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        _bars,
    )
    strategy = RossMomentumStrategyV1()
    strategy._pattern_registry = _EmptyRegistry()
    strategy._data_contract_block_reasons = lambda **kwargs: []

    intents = strategy.process_watchlist(
        watchlist=[{
            "symbol": "BIND",
            "promotion_reason": "watchlist",
            "session_label": "PRE",
            "last_price": 11.0,
            "bid": 10.99,
            "ask": 11.01,
            "volume": 200000,
            "rvol": 2.0,
            "float_millions": 12.0,
            "premarket_high": 11.05,
            "prior_close": 10.0,
            "pct_change": 6.2,
        }],
        snapshots={"BIND": MarketSnapshot(symbol="BIND", bid=10.99, ask=11.01, last=11.0, volume=200000, asof_utc=datetime.now(timezone.utc))},
        session_label="PRE",
        timestamp_utc="binding-test",
        mode=RunMode.PAPER,
        session_phase="PRE",
    )

    out = capsys.readouterr().out
    assert intents == []
    assert "[ROSS][TERMINAL] symbol=BIND category=SETUP_NOT_FOUND" in out
