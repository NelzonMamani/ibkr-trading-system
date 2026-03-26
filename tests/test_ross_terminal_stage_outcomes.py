from __future__ import annotations

from datetime import datetime, timezone

from src.config.runtime_config import RunMode
from src.domain.market_snapshot import MarketSnapshot
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_trace import RossPatternFailureTraceCollector
from src.strategies.ross_momentum.patterns.pattern_types import PatternResult
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


class EmptyRegistry:
    inactive_pattern_ids: set[str] = set()

    @property
    def pattern_ids(self) -> list[str]:
        return []

    def run(self, inputs, *, trace_context=None, trace_collector=None) -> list[PatternResult]:
        return []


def _bars() -> list[Candle]:
    return [
        Candle(open=9.8, high=10.0, low=9.7, close=9.95, volume=1_000),
        Candle(open=9.95, high=10.2, low=9.9, close=10.15, volume=1_500),
        Candle(open=10.15, high=10.4, low=10.1, close=10.35, volume=2_200),
        Candle(open=10.35, high=10.7, low=10.3, close=10.65, volume=2_900),
    ]


def _snapshot(symbol: str, last: float = 10.65) -> MarketSnapshot:
    return MarketSnapshot(symbol=symbol, bid=last - 0.01, ask=last + 0.01, last=last, volume=400_000, asof_utc=datetime.now(timezone.utc))


def _row(symbol: str, *, pct_change: float, rvol: float, volume: float = 400_000) -> dict:
    return {
        "symbol": symbol,
        "promotion_reason": "watchlist",
        "session_label": "PRE",
        "last_price": 10.65,
        "bid": 10.64,
        "ask": 10.66,
        "volume": volume,
        "rvol": rvol,
        "float_millions": 14.0,
        "premarket_high": 10.6,
        "prior_close": 9.7,
        "pct_change": pct_change,
    }


def _strategy(monkeypatch, tmp_path) -> RossMomentumStrategyV1:
    monkeypatch.setattr("src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars", lambda **kwargs: _bars())
    strategy = RossMomentumStrategyV1()
    strategy._pattern_registry = EmptyRegistry()
    strategy._failure_trace_collector = RossPatternFailureTraceCollector(evidence_root=tmp_path)
    return strategy


def test_every_evaluated_symbol_emits_terminal_stage(monkeypatch, tmp_path, capsys) -> None:
    strategy = _strategy(monkeypatch, tmp_path)
    watchlist = [_row("GOOD", pct_change=6.5, rvol=2.2), _row("BAD", pct_change=-1.0, rvol=0.2, volume=500)]
    snapshots = {"GOOD": _snapshot("GOOD"), "BAD": _snapshot("BAD")}

    intents = strategy.process_watchlist(
        watchlist=watchlist,
        snapshots=snapshots,
        session_label="PRE",
        timestamp_utc="cycle-terminal",
        mode=RunMode.SIM,
        session_phase="PRE",
    )

    out = capsys.readouterr().out
    assert intents
    assert "[ROSS][TERMINAL_STAGE] symbol=GOOD outcome=INTENT_GENERATED" in out
    assert "[ROSS][TERMINAL_STAGE] symbol=BAD outcome=CONTEXT_REJECTED" in out


def test_strong_candidates_emit_intent_by_phase(monkeypatch, tmp_path) -> None:
    strategy = _strategy(monkeypatch, tmp_path)

    for phase in ("PRE", "RTH_OPEN", "RTH_MID"):
        intents = strategy.process_watchlist(
            watchlist=[_row(f"{phase}X", pct_change=8.0 if phase != "RTH_MID" else 6.0, rvol=2.5)],
            snapshots={f"{phase}X": _snapshot(f"{phase}X")},
            session_label=phase,
            timestamp_utc=f"cycle-{phase}",
            mode=RunMode.SIM,
            session_phase=phase,
        )
        assert intents, f"expected intent for phase={phase}"
        assert intents[0].decision == "TRADE_READY"
