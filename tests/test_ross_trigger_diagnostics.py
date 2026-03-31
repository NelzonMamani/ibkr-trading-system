from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

from src.config.runtime_config import RunMode
from src.core.engines.trigger_quality_engine import TriggerQualityEngine
from src.domain.market_snapshot import MarketSnapshot
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_evaluator import PatternEvaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.ross_momentum.patterns.pattern_trace import RossPatternFailureTraceCollector, RossPatternTrace
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1
from src.strategies.strategy_contracts import SessionContext


@dataclass
class FakeRegistry:
    traces: list[RossPatternTrace]
    results: list[PatternResult]
    inactive_pattern_ids: set[str]

    @property
    def pattern_ids(self) -> list[str]:
        return [trace.pattern_id for trace in self.traces]

    def run(self, inputs, *, trace_context=None, trace_collector=None):
        if trace_collector is not None:
            for trace in self.traces:
                trace_collector(trace)
        return self.results


class _EvalRegistry:
    def __init__(self, results: list[PatternResult]):
        self._results = results

    def run(self, _inputs):
        return self._results


def _watchlist_row(symbol: str = "TEST") -> dict:
    return {
        "symbol": symbol,
        "promotion_reason": "manual_focus",
        "session_label": "PRE",
        "last_price": 11.1,
        "bid": 11.09,
        "ask": 11.11,
        "volume": 900000,
        "rvol": 3.0,
        "float_millions": 20.0,
        "premarket_high": 10.95,
        "prior_close": 10.0,
    }


def _snapshot(symbol: str = "TEST") -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        bid=11.09,
        ask=11.11,
        last=11.1,
        volume=900000,
        asof_utc=datetime.now(timezone.utc),
    )


def _bars(count: int = 24) -> list[Candle]:
    return [
        Candle(
            open=10.0 + idx * 0.05,
            high=10.15 + idx * 0.05,
            low=9.95 + idx * 0.05,
            close=10.1 + idx * 0.05,
            volume=2000 + idx * 20,
        )
        for idx in range(count)
    ]


def _detected_result(pattern_id: str, confidence: float = 0.82) -> PatternResult:
    return PatternResult(
        setup_id=pattern_id,
        pattern_name=pattern_id,
        pattern_family=PatternFamily.BREAKOUT,
        detected=True,
        direction=Direction.LONG,
        confidence=confidence,
        setup_quality_tags=["test"],
    )


def _rejected_result(pattern_id: str, reason: str) -> PatternResult:
    return PatternResult(
        setup_id=pattern_id,
        pattern_name=pattern_id,
        pattern_family=PatternFamily.BREAKOUT,
        detected=False,
        direction=Direction.LONG,
        confidence=0.0,
        setup_quality_tags=[],
        rejection_reason=reason,
    )


def _inputs(symbol: str = "TEST") -> PatternInputs:
    return PatternInputs(
        symbol=symbol,
        timeframe="1m",
        candles=[
            Candle(open=10.0, high=10.3, low=9.9, close=10.2, volume=1000),
            Candle(open=10.2, high=10.4, low=10.1, close=10.35, volume=1300),
        ],
        session_context=SessionContext.PRE,
        levels=LevelSet(premarket_high=10.25, hod=10.30, prior_close=9.8),
        indicators=IndicatorSet(ema9=10.1, ema20=10.0, vwap=10.05),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=12.0, rvol=2.4),
    )


def _base_strategy(monkeypatch, tmp_path) -> RossMomentumStrategyV1:
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: _bars(),
    )
    strategy = RossMomentumStrategyV1()
    strategy._failure_trace_collector = RossPatternFailureTraceCollector(evidence_root=tmp_path)
    strategy._data_contract_block_reasons = lambda **kwargs: []
    return strategy


def test_pattern_fail_emits_log(capsys) -> None:
    evaluator = PatternEvaluator()
    evaluator._registry = _EvalRegistry([_rejected_result("P_TEST", "no_pullback")])

    evaluator.evaluate([_inputs()])

    out = capsys.readouterr().out
    assert "[ROSS][PATTERN][START] symbol=TEST" in out
    assert "[ROSS][PATTERN][FAIL] symbol=TEST pattern=P_TEST reason=no_pullback" in out


def test_confirmation_fail_emits_log(monkeypatch, tmp_path, capsys) -> None:
    strategy = _base_strategy(monkeypatch, tmp_path)
    strategy._pattern_registry = FakeRegistry(
        traces=[
            RossPatternTrace(
                symbol="TEST",
                cycle_id="cycle-confirm-fail",
                strategy_key="ross_momentum",
                session_label="PRE",
                session_phase="PRE",
                runtime_mode="LIVE",
                symbol_source="manual_focus",
                pattern_id="P_ORB",
                pattern_name="Opening Range Breakout",
                setup_family_id="P_ORB",
                invoked=True,
                detected=True,
            )
        ],
        results=[_detected_result("P_ORB")],
        inactive_pattern_ids=set(),
    )

    strategy.process_watchlist(
        watchlist=[_watchlist_row()],
        snapshots={"TEST": _snapshot()},
        session_label="PRE",
        timestamp_utc="cycle-confirm-fail",
        mode=RunMode.LIVE,
        session_phase="PRE",
    )

    out = capsys.readouterr().out
    assert "[ROSS][TRIGGER_FAIL] symbol=TEST" in out
    assert any(reason in out for reason in ("TRIGGER_BLOCKED", "invalid_session_for_pattern", "CONFIRMATION_BLOCKED"))


def test_trigger_fail_emits_log(monkeypatch, tmp_path, capsys) -> None:
    strategy = _base_strategy(monkeypatch, tmp_path)
    strategy._pattern_registry = FakeRegistry(
        traces=[
            RossPatternTrace(
                symbol="TEST",
                cycle_id="cycle-trigger-fail",
                strategy_key="ross_momentum",
                session_label="PRE",
                session_phase="PRE",
                runtime_mode="LIVE",
                symbol_source="manual_focus",
                pattern_id="P_ORB",
                pattern_name="Opening Range Breakout",
                setup_family_id="P_ORB",
                invoked=True,
                detected=True,
                rejection_reason="no_breakout_above_opening_range",
            )
        ],
        results=[_detected_result("P_ORB")],
        inactive_pattern_ids=set(),
    )

    strategy.process_watchlist(
        watchlist=[_watchlist_row()],
        snapshots={"TEST": _snapshot()},
        session_label="PRE",
        timestamp_utc="cycle-trigger-fail",
        mode=RunMode.LIVE,
        session_phase="PRE",
    )

    out = capsys.readouterr().out
    assert "[ROSS][TRIGGER_FAIL] symbol=TEST" in out
    assert any(reason in out for reason in ("TRIGGER_BLOCKED", "invalid_session_for_pattern", "CONFIRMATION_BLOCKED"))


def test_no_silent_drop_logs_pipeline_no_decision(monkeypatch, tmp_path, capsys) -> None:
    strategy = _base_strategy(monkeypatch, tmp_path)
    strategy._pattern_registry = FakeRegistry(traces=[], results=[], inactive_pattern_ids=set())

    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row()],
        snapshots={"TEST": _snapshot()},
        session_label="PRE",
        timestamp_utc="cycle-no-decision",
        mode=RunMode.LIVE,
        session_phase="PRE",
    )

    assert intents
    out = capsys.readouterr().out
    assert "[ROSS][SETUP_RESULT] symbol=TEST source=setup_engine" in out
    assert "[ROSS][INTENT_GENERATED] symbol=TEST" in out


def test_trade_ready_still_works_and_emits_terminal_log(monkeypatch, tmp_path, capsys) -> None:
    strategy = _base_strategy(monkeypatch, tmp_path)
    strategy._pattern_registry = FakeRegistry(
        traces=[
            RossPatternTrace(
                symbol="TEST",
                cycle_id="cycle-ready",
                strategy_key="ross_momentum",
                session_label="PRE",
                session_phase="PRE",
                runtime_mode="LIVE",
                symbol_source="manual_focus",
                pattern_id="P_PREMKT_BREAK",
                pattern_name="Premarket High Break",
                setup_family_id="P_PREMKT_BREAK",
                invoked=True,
                detected=True,
            )
        ],
        results=[_detected_result("P_PREMKT_BREAK")],
        inactive_pattern_ids=set(),
    )

    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row()],
        snapshots={"TEST": _snapshot()},
        session_label="PRE",
        timestamp_utc="cycle-ready",
        mode=RunMode.LIVE,
        session_phase="PRE",
    )

    assert intents
    assert intents[0].decision == "TRADE_READY"
    out = capsys.readouterr().out
    assert "[ROSS][INTENT_GENERATED] symbol=TEST" in out
    assert "[ROSS][DECISION] symbol=TEST outcome=TRADE_READY pattern=P_PREMKT_BREAK" in out
    assert intents[0].trigger_id.endswith(":TRIGGER") or bool(intents[0].trigger_id)
    assert intents[0].entry_price is not None
    assert intents[0].stop_loss_price is not None


def test_select_trigger_candidate_normalizes_setup_family_aliases() -> None:
    selected = RossMomentumStrategyV1._select_trigger_candidate(
        setup_family_id="P_PREMKT_BREAK",
        trigger_candidates=[
            {
                "setup_family_id": "PREMARKET_HIGH_BREAK",
                "trigger_ready_now": True,
                "trigger_quality_flags": [],
                "trigger_type": "PMH_BREAK",
            }
        ],
    )
    assert selected is not None
    assert selected["trigger_type"] == "PMH_BREAK"


def test_trade_permission_allows_non_high_quality_when_trigger_fired() -> None:
    allow_trade, reason = RossMomentumStrategyV1._trade_permission(
        trigger_ready=True,
        setup_family_id="HOD_BREAK",
    )
    assert allow_trade is True
    assert reason == "trigger_fired"


def test_trade_permission_blocks_when_trigger_not_ready() -> None:
    allow_trade, reason = RossMomentumStrategyV1._trade_permission(
        trigger_ready=False,
        setup_family_id="HOD_BREAK",
    )
    assert allow_trade is False
    assert reason == "trigger_not_ready"


def test_trigger_quality_engine_scores_high_quality_ready_setup() -> None:
    quality = TriggerQualityEngine().evaluate_trigger_quality(
        trigger={
            "setup_family_id": "FIRST_PULLBACK",
            "trigger_quality_flags": [],
        },
        structure={
            "dominant_direction": "UP",
            "pullback_depth": {"depth_pct": 0.25},
            "compression_active": True,
            "structure_quality_flags": [],
        },
        session_context="RTH_OPEN",
        rvol=2.5,
    )
    assert quality["quality_score"] == 0.9


def test_quality_size_multiplier_and_open_position_helpers() -> None:
    assert RossMomentumStrategyV1._size_multiplier_for_quality(0.81) == 1.0
    assert RossMomentumStrategyV1._size_multiplier_for_quality(0.71) == 0.75
    assert RossMomentumStrategyV1._size_multiplier_for_quality(0.61) == 0.5
    assert RossMomentumStrategyV1._size_multiplier_for_quality(0.42) == 0.25

    assert RossMomentumStrategyV1._infer_open_positions_count(
        [
            {"symbol": "AAA", "position_qty": 10},
            {"symbol": "BBB", "position_size": 1},
            {"symbol": "CCC", "position_qty": 0},
        ]
    ) == 2


def test_tradeable_entry_gate_blocks_extension_and_spread(capsys) -> None:
    strategy = RossMomentumStrategyV1()
    summary = SimpleNamespace(last_price=10.0, spread=0.25, rvol=2.0, pct_change=8.0)
    result = strategy.evaluate_tradeable_entry(
        symbol="TEST",
        mode=RunMode.PAPER,
        setup_family="HOD_BREAK",
        pattern_confidence=0.9,
        entry_price=10.6,
        input_summary=summary,
        selected_trigger={"trigger_price_reference": 10.0},
        levels={"hod": 10.0},
    )
    assert result["tradeable"] is False
    assert "ENTRY_TOO_EXTENDED" in result["blocking_reasons"]
    assert "SPREAD_TOO_WIDE" in result["blocking_reasons"]
    assert "[ENTRY][EXTENSION_BLOCK] symbol=TEST" in capsys.readouterr().out


def test_tradeable_entry_gate_passes_clean_candidate(capsys) -> None:
    strategy = RossMomentumStrategyV1()
    summary = SimpleNamespace(last_price=10.0, spread=0.02, rvol=2.0, pct_change=8.0)
    result = strategy.evaluate_tradeable_entry(
        symbol="TEST",
        mode=RunMode.PAPER,
        setup_family="HOD_BREAK",
        pattern_confidence=0.9,
        entry_price=10.03,
        input_summary=summary,
        selected_trigger={"trigger_price_reference": 10.0},
        levels={"hod": 10.0},
    )
    assert result["tradeable"] is True
    assert result["blocking_reasons"] == []
    assert "[TRADEABLE][PASS] symbol=TEST" in capsys.readouterr().out
