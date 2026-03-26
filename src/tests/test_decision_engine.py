from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.config.runtime_config import RunMode
from src.core.engines.decision_engine import DecisionEngine
from src.domain.market_snapshot import MarketSnapshot
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_trace import RossPatternFailureTraceCollector, RossPatternTrace
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


@dataclass
class _FakeRegistry:
    traces: list[RossPatternTrace]
    results: list[PatternResult]
    inactive_pattern_ids: set[str] = None

    def __post_init__(self) -> None:
        if self.inactive_pattern_ids is None:
            self.inactive_pattern_ids = set()

    @property
    def pattern_ids(self) -> list[str]:
        return [trace.pattern_id for trace in self.traces]

    def run(self, _inputs, *, trace_context=None, trace_collector=None):
        if trace_collector is not None:
            for trace in self.traces:
                trace_collector(trace)
        return self.results


def _result(
    pattern_id: str,
    *,
    confidence: float,
    detected: bool = True,
    direction: Direction = Direction.LONG,
    setup_family_id: str | None = None,
    trigger_level: float | None = 10.5,
    invalidation_level: float | None = 10.0,
    non_entry_signal: bool = False,
    tags: list[str] | None = None,
    session_valid: bool = True,
) -> PatternResult:
    return PatternResult(
        setup_id=pattern_id,
        pattern_name=pattern_id,
        pattern_family=PatternFamily.BREAKOUT,
        detected=detected,
        direction=direction,
        confidence=confidence,
        setup_quality_tags=["test"],
        setup_family_id=setup_family_id,
        trigger_level=trigger_level,
        invalidation_level=invalidation_level,
        non_entry_signal=non_entry_signal,
        tags=tags or [],
        session_valid=session_valid,
    )


def test_decision_engine_returns_no_candidate_when_nothing_detected() -> None:
    decision = DecisionEngine().compute_decision(
        symbol="TEST",
        levels={},
        structure={"trend": "UP"},
        setups=[],
        pattern_results=[_result("P_ORB", confidence=0.8, detected=False)],
        session_context="PRE",
    )

    assert decision["decision_state"] == "NO_CANDIDATE"
    assert decision["selected_pattern_id"] is None


def test_decision_engine_selects_orb_over_unrelated_lower_quality_candidate() -> None:
    decision = DecisionEngine().compute_decision(
        symbol="TEST",
        levels={"hod": 11.0},
        structure={"trend": "UP"},
        setups=[{"setup_family": "ORB"}],
        pattern_results=[
            _result("P_ORB", confidence=0.72, setup_family_id="ORB", trigger_level=11.0),
            _result("P_EMA_PULLBACK", confidence=0.35, setup_family_id="EMA_PULLBACK", trigger_level=None),
        ],
        session_context="RTH",
    )

    assert decision["selected_pattern_id"] == "P_ORB"
    assert any(item["pattern_id"] == "P_EMA_PULLBACK" for item in decision["rejected_candidates"])


def test_decision_engine_rejects_non_entry_candidates_for_entry_selection() -> None:
    decision = DecisionEngine().compute_decision(
        symbol="TEST",
        levels={},
        structure={"trend": "UP"},
        setups=[{"setup_family": "HOD_BREAK"}],
        pattern_results=[
            _result("P_HOD_BREAK", confidence=0.5, non_entry_signal=True, tags=["EXIT"]),
        ],
        session_context="RTH",
    )

    assert decision["decision_state"] == "CANDIDATE_REJECTED_INSUFFICIENT_QUALITY"
    assert decision["selected_pattern_id"] is None
    assert decision["rejected_candidates"][0]["reason"] == "non_entry_signal"


def test_decision_engine_prefers_setup_compatible_candidate() -> None:
    decision = DecisionEngine().compute_decision(
        symbol="TEST",
        levels={"vwap": 10.1},
        structure={"trend": "UP"},
        setups=[{"setup_family": "VWAP_RECLAIM"}],
        pattern_results=[
            _result("P_VWAP_PULLBACK", confidence=0.55, setup_family_id="VWAP_RECLAIM"),
            _result("P_ORB", confidence=0.75, setup_family_id="ORB"),
        ],
        session_context="RTH",
    )

    assert decision["selected_pattern_id"] == "P_VWAP_PULLBACK"


def test_decision_engine_produces_rejected_candidate_explanations() -> None:
    decision = DecisionEngine().compute_decision(
        symbol="TEST",
        levels={},
        structure={"trend": "UP"},
        setups=[{"setup_family": "ORB"}],
        pattern_results=[
            _result("P_ORB", confidence=0.8),
            _result("P_OPENING_DRIVE", confidence=0.8),
        ],
        session_context="RTH",
    )

    assert decision["decision_state"] == "CANDIDATE_SELECTED"
    assert decision["decision_reason"] == "selected_best_compatible_candidate"
    assert decision["rejected_candidates"]
    assert all("reason" in item for item in decision["rejected_candidates"])
    assert {
        item["reason"] for item in decision["rejected_candidates"]
    } <= {"dropped_lower_priority_compatible_candidate", "rejected_true_conflict_incompatible_execution_semantics"}


def test_decision_engine_rejects_true_conflict_opposing_direction() -> None:
    decision = DecisionEngine().compute_decision(
        symbol="TEST",
        levels={},
        structure={"trend": "UP"},
        setups=[{"setup_family": "ORB"}],
        pattern_results=[
            _result("P_ORB", confidence=0.8, direction=Direction.LONG),
            _result("P_FAILED_ORB_FAKEOUT", confidence=0.7, direction=Direction.SHORT),
        ],
        session_context="RTH",
    )

    assert decision["decision_state"] == "CANDIDATE_REJECTED_CONFLICT"
    assert decision["selected_pattern_id"] is None
    assert decision["decision_reason"] == "rejected_true_conflict_opposing_direction"
    assert all(
        item["reason"] == "rejected_true_conflict_opposing_direction"
        for item in decision["rejected_candidates"]
    )


def test_decision_engine_prefers_registry_candidate_over_fallback_candidate() -> None:
    decision = DecisionEngine().compute_decision(
        symbol="TEST",
        levels={},
        structure={"trend": "UP"},
        setups=[{"setup_family": "HOD_BREAK"}],
        pattern_results=[
            _result("FALLBACK_HOD_BREAK", confidence=0.95, setup_family_id="HOD_BREAK"),
            _result("P_HOD_BREAK", confidence=0.78, setup_family_id="HOD_BREAK"),
        ],
        session_context="RTH",
    )

    assert decision["decision_state"] == "CANDIDATE_SELECTED"
    assert decision["selected_pattern_id"] == "P_HOD_BREAK"
    assert any(
        item["pattern_id"] == "FALLBACK_HOD_BREAK"
        and item["reason"] == "dropped_lower_priority_compatible_candidate"
        for item in decision["rejected_candidates"]
    )


def test_ross_process_watchlist_uses_decision_engine_selection(monkeypatch, tmp_path) -> None:
    bars = [
        Candle(open=10.0, high=10.2, low=9.95, close=10.15, volume=2000),
        Candle(open=10.15, high=10.35, low=10.1, close=10.3, volume=2200),
        Candle(open=10.3, high=10.55, low=10.25, close=10.5, volume=2500),
        Candle(open=10.5, high=10.8, low=10.45, close=10.72, volume=2800),
        Candle(open=10.72, high=11.0, low=10.7, close=10.95, volume=3000),
    ]
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: bars,
    )

    strategy = RossMomentumStrategyV1()
    strategy._failure_trace_collector = RossPatternFailureTraceCollector(evidence_root=tmp_path)
    strategy._data_contract_block_reasons = lambda **kwargs: []

    traces = [
        RossPatternTrace(
            symbol="TEST",
            cycle_id="decision-cycle",
            strategy_key="ross_momentum",
            session_label="PRE",
            session_phase="PRE",
            runtime_mode="LIVE",
            symbol_source="manual_focus",
            pattern_id="P_PREMKT_BREAK",
            pattern_name="Premarket High Break",
            setup_family_id="PREMARKET_HIGH_BREAK",
            invoked=True,
            detected=True,
        ),
        RossPatternTrace(
            symbol="TEST",
            cycle_id="decision-cycle",
            strategy_key="ross_momentum",
            session_label="PRE",
            session_phase="PRE",
            runtime_mode="LIVE",
            symbol_source="manual_focus",
            pattern_id="P_ORB",
            pattern_name="Opening Range Breakout",
            setup_family_id="ORB",
            invoked=True,
            detected=True,
        ),
    ]
    results = [
        _result("P_PREMKT_BREAK", confidence=0.62, setup_family_id="PREMARKET_HIGH_BREAK"),
        _result("P_ORB", confidence=0.91, setup_family_id="ORB"),
    ]
    strategy._pattern_registry = _FakeRegistry(traces=traces, results=results)
    strategy._decision_engine.compute_decision = lambda **kwargs: {
        "symbol": "TEST",
        "selected_setup_family": "PREMARKET_HIGH_BREAK",
        "selected_pattern_id": "P_PREMKT_BREAK",
        "selected_pattern_name": "P_PREMKT_BREAK",
        "decision_state": "CANDIDATE_SELECTED",
        "confidence": 0.62,
        "entry_bias": "LONG",
        "trigger_level": 10.95,
        "invalidation_level": 10.6,
        "supporting_factors": ["detected", "setup_compatible"],
        "rejected_candidates": [{"pattern_id": "P_ORB", "reason": "session_incompatible"}],
        "decision_reason": "best_compatible_detected_candidate",
    }

    intents = strategy.process_watchlist(
        watchlist=[{
            "symbol": "TEST",
            "promotion_reason": "manual_focus",
            "session_label": "PRE",
            "last_price": 11.1,
            "bid": 11.09,
            "ask": 11.11,
            "volume": 600_000,
            "rvol": 3.0,
            "float_millions": 20.0,
            "premarket_high": 10.95,
            "prior_close": 10.0,
        }],
        snapshots={"TEST": MarketSnapshot(symbol="TEST", bid=11.09, ask=11.11, last=11.1, volume=600_000, asof_utc=datetime.now(timezone.utc))},
        session_label="PRE",
        timestamp_utc="decision-cycle",
        mode=RunMode.LIVE,
        session_phase="PRE",
    )

    assert intents
    assert intents[0].pattern_name == "P_PREMKT_BREAK"
    assert intents[0].trigger_id == "confirmation_gate"


def test_ross_process_watchlist_compatible_candidates_emit_trade_ready(monkeypatch, tmp_path, capsys) -> None:
    bars = [
        Candle(open=10.0, high=10.2, low=9.95, close=10.15, volume=2000),
        Candle(open=10.15, high=10.35, low=10.1, close=10.3, volume=2200),
        Candle(open=10.3, high=10.55, low=10.25, close=10.5, volume=2500),
        Candle(open=10.5, high=10.8, low=10.45, close=10.72, volume=2800),
        Candle(open=10.72, high=11.0, low=10.7, close=10.95, volume=3200),
    ]
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: bars,
    )

    strategy = RossMomentumStrategyV1()
    strategy._failure_trace_collector = RossPatternFailureTraceCollector(evidence_root=tmp_path)
    strategy._data_contract_block_reasons = lambda **kwargs: []
    strategy._pattern_registry = _FakeRegistry(
        traces=[
            RossPatternTrace(
                symbol="TEST",
                cycle_id="decision-cycle",
                strategy_key="ross_momentum",
                session_label="PRE",
                session_phase="PRE",
                runtime_mode="LIVE",
                symbol_source="manual_focus",
                pattern_id="P_PREMKT_BREAK",
                pattern_name="Premarket High Break",
                setup_family_id="PREMARKET_HIGH_BREAK",
                invoked=True,
                detected=True,
            ),
            RossPatternTrace(
                symbol="TEST",
                cycle_id="decision-cycle",
                strategy_key="ross_momentum",
                session_label="PRE",
                session_phase="PRE",
                runtime_mode="LIVE",
                symbol_source="manual_focus",
                pattern_id="P_HOD_BREAK",
                pattern_name="HOD Break",
                setup_family_id="HOD_BREAK",
                invoked=True,
                detected=True,
            ),
        ],
        results=[
            _result("P_PREMKT_BREAK", confidence=0.68, setup_family_id="PREMARKET_HIGH_BREAK"),
            _result("P_HOD_BREAK", confidence=0.65, setup_family_id="HOD_BREAK"),
        ],
    )

    intents = strategy.process_watchlist(
        watchlist=[{
            "symbol": "TEST",
            "promotion_reason": "manual_focus",
            "session_label": "PRE",
            "last_price": 11.1,
            "bid": 11.09,
            "ask": 11.11,
            "volume": 600_000,
            "rvol": 3.0,
            "float_millions": 20.0,
            "premarket_high": 10.95,
            "prior_close": 10.0,
        }],
        snapshots={"TEST": MarketSnapshot(symbol="TEST", bid=11.09, ask=11.11, last=11.1, volume=600_000, asof_utc=datetime.now(timezone.utc))},
        session_label="PRE",
        timestamp_utc="decision-cycle",
        mode=RunMode.LIVE,
        session_phase="PRE",
    )

    assert intents
    assert intents[0].decision == "TRADE_READY"
    out = capsys.readouterr().out
    assert "state=CANDIDATE_SELECTED" in out
    assert "decision_not_candidate_selected" not in out
