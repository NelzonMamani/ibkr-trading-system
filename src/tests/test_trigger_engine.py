from __future__ import annotations

from datetime import datetime, timezone

from src.config.runtime_config import RunMode
from src.core.engines.trigger_engine import TriggerEngine
from src.domain.market_snapshot import MarketSnapshot
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_trace import RossPatternFailureTraceCollector, RossPatternTrace
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


def _snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        symbol="TEST",
        bid=10.98,
        ask=11.00,
        last=10.99,
        volume=500_000,
        asof_utc=datetime.now(timezone.utc),
    )


def _decision(**overrides) -> dict:
    payload = {
        "symbol": "TEST",
        "selected_setup_family": "PREMARKET_HIGH_BREAK",
        "selected_pattern_id": "P_PREMKT_BREAK",
        "selected_pattern_name": "P_PREMKT_BREAK",
        "decision_state": "CANDIDATE_SELECTED",
        "confidence": 0.77,
        "entry_bias": "LONG",
        "trigger_level": 10.95,
        "invalidation_level": 10.70,
        "supporting_factors": ["detected"],
        "rejected_candidates": [],
        "decision_reason": "best_compatible_detected_candidate",
    }
    payload.update(overrides)
    return payload


def test_trigger_engine_valid_decision_is_ready() -> None:
    trigger = TriggerEngine().compute_trigger(
        symbol="TEST",
        decision=_decision(),
        market_snapshot=_snapshot(),
        session_context="PRE",
    )
    assert trigger["trigger_state"] == "TRIGGER_READY"
    assert trigger["entry_price"] == 11.0
    assert trigger["stop_loss_price"] == 10.7
    assert trigger["quantity_hint"] == 1


def test_trigger_engine_missing_trigger_level_blocks() -> None:
    trigger = TriggerEngine().compute_trigger(
        symbol="TEST",
        decision=_decision(trigger_level=None),
        market_snapshot=_snapshot(),
        session_context="PRE",
    )
    assert trigger["trigger_state"] == "TRIGGER_BLOCKED"
    assert "missing_trigger_level" in trigger["blocking_factors"]


def test_trigger_engine_missing_invalidation_blocks() -> None:
    trigger = TriggerEngine().compute_trigger(
        symbol="TEST",
        decision=_decision(invalidation_level=None),
        market_snapshot=_snapshot(),
        session_context="PRE",
    )
    assert trigger["trigger_state"] == "TRIGGER_BLOCKED"
    assert "missing_invalidation_level" in trigger["blocking_factors"]


def test_trigger_engine_no_decision_blocks() -> None:
    trigger = TriggerEngine().compute_trigger(
        symbol="TEST",
        decision={},
        market_snapshot=_snapshot(),
        session_context="PRE",
    )
    assert trigger["trigger_state"] == "TRIGGER_BLOCKED"
    assert "decision_not_candidate_selected" in trigger["blocking_factors"]


class _FakeRegistry:
    def __init__(self, traces: list[RossPatternTrace], results: list[PatternResult]) -> None:
        self.traces = traces
        self.results = results
        self.inactive_pattern_ids: set[str] = set()

    @property
    def pattern_ids(self) -> list[str]:
        return [trace.pattern_id for trace in self.traces]

    def run(self, _inputs, *, trace_context=None, trace_collector=None):
        if trace_collector is not None:
            for trace in self.traces:
                trace_collector(trace)
        return self.results


def _result(pattern_id: str = "P_PREMKT_BREAK") -> PatternResult:
    return PatternResult(
        setup_id=pattern_id,
        pattern_name=pattern_id,
        pattern_family=PatternFamily.BREAKOUT,
        detected=True,
        direction=Direction.LONG,
        confidence=0.81,
        setup_quality_tags=["test"],
        trigger_level=10.95,
        invalidation_level=10.70,
    )


def _watchlist_row() -> dict:
    return {
        "symbol": "TEST",
        "promotion_reason": "manual_focus",
        "session_label": "PRE",
        "last_price": 10.99,
        "bid": 10.98,
        "ask": 11.00,
        "volume": 500_000,
        "rvol": 3.0,
        "float_millions": 20.0,
        "premarket_high": 10.95,
        "prior_close": 10.0,
    }


def _bars() -> list[Candle]:
    return [
        Candle(open=10.0, high=10.2, low=9.9, close=10.1, volume=1800),
        Candle(open=10.1, high=10.4, low=10.0, close=10.3, volume=2100),
        Candle(open=10.3, high=10.7, low=10.25, close=10.6, volume=2400),
    ]


def _strategy(monkeypatch, tmp_path) -> RossMomentumStrategyV1:
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: _bars(),
    )
    strategy = RossMomentumStrategyV1()
    strategy._failure_trace_collector = RossPatternFailureTraceCollector(evidence_root=tmp_path)
    strategy._data_contract_block_reasons = lambda **kwargs: []
    return strategy


def test_ross_integration_emits_trade_intent_when_trigger_ready(monkeypatch, tmp_path) -> None:
    strategy = _strategy(monkeypatch, tmp_path)
    strategy._pattern_registry = _FakeRegistry(
        traces=[
            RossPatternTrace(
                symbol="TEST",
                cycle_id="trigger-ready",
                strategy_key="ross_momentum",
                session_label="PRE",
                session_phase="PRE",
                runtime_mode="LIVE",
                symbol_source="manual_focus",
                pattern_id="P_PREMKT_BREAK",
                pattern_name="Premarket Break",
                setup_family_id="PREMARKET_HIGH_BREAK",
                invoked=True,
                detected=True,
            )
        ],
        results=[_result()],
    )
    strategy._decision_engine.compute_decision = lambda **kwargs: _decision()

    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row()],
        snapshots={"TEST": _snapshot()},
        session_label="PRE",
        timestamp_utc="trigger-ready",
        mode=RunMode.LIVE,
        session_phase="PRE",
    )
    assert len(intents) == 1
    assert intents[0].decision == "TRADE_READY"
    assert intents[0].entry_price == 11.0
    assert intents[0].trigger_id


def test_ross_integration_emits_no_intent_when_trigger_blocked(monkeypatch, tmp_path) -> None:
    strategy = _strategy(monkeypatch, tmp_path)
    strategy._pattern_registry = _FakeRegistry(
        traces=[
            RossPatternTrace(
                symbol="TEST",
                cycle_id="trigger-blocked",
                strategy_key="ross_momentum",
                session_label="PRE",
                session_phase="PRE",
                runtime_mode="LIVE",
                symbol_source="manual_focus",
                pattern_id="P_PREMKT_BREAK",
                pattern_name="Premarket Break",
                setup_family_id="PREMARKET_HIGH_BREAK",
                invoked=True,
                detected=True,
            )
        ],
        results=[_result()],
    )
    strategy._decision_engine.compute_decision = lambda **kwargs: _decision(trigger_level=None)

    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row()],
        snapshots={"TEST": _snapshot()},
        session_label="PRE",
        timestamp_utc="trigger-blocked",
        mode=RunMode.LIVE,
        session_phase="PRE",
    )
    assert intents == []
