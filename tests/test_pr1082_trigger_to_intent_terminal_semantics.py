from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import RunMode
from src.core.engines.decision_engine import DecisionEngine
from src.core.engines.trigger_engine import TriggerEngine
from src.domain.market_snapshot import MarketSnapshot
from src.setup_engine.setup_families.pullbacks import SecondPullbackPattern, ThreeBarPullbackPattern
from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.triggers import trigger_registry
from src.strategies.common.triggers.trigger_pullback_variants import (
    evaluate_second_pullback_trigger,
    evaluate_three_bar_pullback_trigger,
)
from src.strategies.common.triggers.trigger_registry import resolve_trigger_evaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    build_authoritative_pattern_inputs,
)
from src.strategies.ross_momentum.patterns.pattern_trace import (
    RossPatternFailureTraceCollector,
    RossPatternTrace,
)
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.ross_momentum.patterns.setup_fidelity import blocking_input_reason
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


@dataclass
class FakeRegistry:
    results: list[PatternResult]
    inactive_pattern_ids: set[str] = field(default_factory=set)

    @property
    def pattern_ids(self) -> list[str]:
        return [result.setup_id for result in self.results]

    def run(self, inputs, *, trace_context=None, trace_collector=None):
        context = dict(trace_context or {})
        for result in self.results:
            trace = RossPatternTrace(
                symbol=inputs.symbol,
                cycle_id=context.get("cycle_id"),
                strategy_key=context.get("strategy_key", "ross_momentum"),
                session_label=context.get("session_label"),
                session_phase=context.get("session_phase"),
                runtime_mode=context.get("runtime_mode"),
                symbol_source=context.get("symbol_source", "watchlist"),
                pattern_id=result.setup_id,
                pattern_name=result.pattern_name,
                setup_family_id=result.setup_family_id,
                invoked=True,
                detected=result.detected,
                rejection_reason=result.rejection_reason,
                input_summary=dict(context.get("input_summary") or {}),
            )
            trace.confidence = result.confidence
            if trace_collector is not None:
                trace_collector(trace)
        return list(self.results)


@pytest.fixture(autouse=True)
def _reset_config(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FORCE_SESSION", raising=False)
    set_config_overrides(
        {
            "RUN_MODE": "READ_ONLY",
            "RUN_MODE_EFFECTIVE": "READ_ONLY",
            "EXECUTION_ENABLED": False,
            "IBKR_FALLBACK_ENABLED": False,
            "ROSS_MOMENTUM_STRATEGY_ENABLED": True,
            "SELECTED_STRATEGY": "ross_momentum",
            "ROSS_VALIDATION_OVERRIDE_ENABLED": False,
            "MANUAL_FOCUS_ENABLED": False,
        }
    )
    yield
    set_config_overrides(None)

def _tail_rows(state: str) -> list[tuple[float, float, float, float, float]]:
    if state == "second_ready":
        return [
            (10.00, 10.55, 9.98, 10.50, 3000),
            (10.48, 10.52, 10.26, 10.30, 1200),
            (10.30, 10.62, 10.28, 10.58, 2400),
            (10.56, 10.59, 10.40, 10.45, 1000),
            (10.45, 10.61, 10.44, 10.60, 1600),
        ]
    trigger_by_state = {
        "ready": (10.32, 10.50, 10.20, 10.48, 1200),
        "not_ready": (10.12, 10.36, 10.10, 10.32, 1000),
        "invalidated": (10.12, 10.30, 10.04, 10.10, 1000),
        "failed_volume": (10.32, 10.50, 10.20, 10.48, 500),
    }
    if state not in trigger_by_state:
        raise AssertionError(f"unknown state={state}")
    return [
        (10.00, 10.50, 9.95, 10.45, 3000),
        (10.42, 10.44, 10.22, 10.30, 1000),
        (10.31, 10.35, 10.15, 10.20, 900),
        (10.20, 10.34, 10.08, 10.12, 800),
        trigger_by_state[state],
    ]

def _rows(state: str = "ready") -> list[tuple[float, float, float, float, float]]:
    prefix = []
    for index in range(45):
        open_price = 9.20 + (index * 0.01)
        prefix.append((open_price, open_price + 0.07, open_price - 0.03, open_price + 0.04, 1500 + index))
    return prefix + _tail_rows(state)

def _candles(
    rows: list[tuple[float, float, float, float, float]],
    *,
    end: datetime | None = None,
    step_seconds: int = 60,
) -> list[Candle]:
    end = end or datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = end - timedelta(seconds=step_seconds * (len(rows) - 1))
    return [
        Candle(open=o, high=h, low=l, close=c, volume=v, timestamp=start + timedelta(seconds=index * step_seconds))
        for index, (o, h, l, c, v) in enumerate(rows)
    ]

def _execution_bars(primary):
    # Aligned 10s fixtures covering the same structural interval, with per-10s volume.
    bars = []
    for candle in primary[:-1]:
        for offset in range(0, 60, 10):
            bars.append(replace(candle, volume=candle.volume / 6,
                                timestamp=candle.timestamp + timedelta(seconds=offset)))
    bars.append(replace(primary[-1], volume=primary[-1].volume / 6))
    return bars


def _bars(state: str = "ready", timeframe: str = "1m", *, end: datetime | None = None) -> list[Candle]:
    if timeframe == "10s":
        return _execution_bars(_candles(_rows(state), end=end))
    step_seconds = {"1m": 60, "5m": 300}.get(timeframe, 60)
    return _candles(_rows(state), end=end, step_seconds=step_seconds)

def _inputs(state: str = "ready", *, now: datetime | None = None, omit_timeframes: set[str] | None = None):
    now = now or datetime.now(timezone.utc).replace(second=0, microsecond=0)
    omit_timeframes = set(omit_timeframes or set())
    timeframe_candles = {
        timeframe: _bars(state, timeframe, end=now)
        for timeframe in ("10s", "1m", "5m")
        if timeframe not in omit_timeframes
    }
    return build_authoritative_pattern_inputs(
        symbol="UPC",
        session_label="RTH_OPEN",
        session_phase="RTH_OPEN",
        timeframe_candles=timeframe_candles,
        indicators=IndicatorSet(ema9=10.35, ema20=10.10, vwap=10.05),
        levels=LevelSet(premarket_high=10.30, premarket_low=9.70, prior_close=8.50),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=8.0, rvol=145.1, volume=1_800_000),
        now=now,
    )

def _detected_three(state: str = "ready") -> PatternResult:
    result = ThreeBarPullbackPattern().evaluate(_inputs(state))
    assert result.detected is True
    return result

def _detected_pullback(pattern_id: str = "P_THREE_BAR_PULLBACK") -> PatternResult:
    setup_family_id = "THREE_BAR_PULLBACK" if pattern_id == "P_THREE_BAR_PULLBACK" else "SECOND_PULLBACK"
    return PatternResult(
        setup_id=pattern_id,
        pattern_name=pattern_id,
        pattern_family=PatternFamily.PULLBACK,
        detected=True,
        direction=Direction.LONG,
        confidence=0.58,
        setup_quality_tags=["natural_pullback"],
        setup_family_id=setup_family_id,
        setup_semantic="CONTINUATION",
        trigger_type="PULLBACK_HIGH_BREAK",
        trigger_level=10.44,
        stop_level=10.08,
        invalidation_level=10.08,
        trigger_mode="NONE",
        signal_class="ENTRY",
        setup_metadata={
            "pullback_high": 10.44,
            "pullback_low": 10.08,
            "breakout_volume_confirmed": True,
        },
    )

def _trigger_payload(result: PatternResult, *, volume_confirmation=...) -> dict[str, object]:
    metadata = dict(result.setup_metadata or {})
    if volume_confirmation is not ...:
        if volume_confirmation == "missing":
            metadata.pop("breakout_volume_confirmed", None)
        else:
            metadata["breakout_volume_confirmed"] = volume_confirmation
    return {
        "setup_family_id": result.setup_family_id,
        "setup_family": result.setup_family_id,
        "setup_name": result.pattern_name,
        "pattern_id": result.setup_id,
        "pattern_name": result.pattern_name,
        "direction": "LONG",
        "confidence": result.confidence,
        "quality_flags": list(result.setup_quality_tags),
        "blocking_flags": [],
        "invalidation_anchor": "pullback_low",
        "invalidation_level": result.invalidation_level,
        "stop_level": result.stop_level,
        "required_trigger_types": [result.trigger_type or "PULLBACK_HIGH_BREAK"],
        "trigger_level": result.trigger_level,
        "setup_detected": True,
        "source": "canonical_pattern_result",
        "setup_metadata": metadata,
        "execution_refinement_mode": result.trigger_mode or "NONE",
    }

def _watchlist_row(state: str = "ready", symbol: str = "UPC") -> dict:
    last = _rows(state)[-1][3]
    return {
        "symbol": symbol,
        "promotion_reason": "LIVE_SCAN",
        "watchlist_source": "LIVE_SCAN",
        "session_label": "RTH",
        "session_phase": "RTH_OPEN",
        "last_price": last,
        "bid": round(last - 0.01, 2),
        "ask": round(last + 0.01, 2),
        "spread": 0.02,
        "volume": 1_800_000,
        "rvol": 145.1,
        "float_millions": 8.0,
        "premarket_high": 10.30,
        "premarket_low": 9.70,
        "prior_close": 8.50,
    }

def _snapshot(state: str = "ready", symbol: str = "UPC") -> MarketSnapshot:
    last = _rows(state)[-1][3]
    return MarketSnapshot(
        symbol=symbol,
        bid=round(last - 0.01, 2),
        ask=round(last + 0.01, 2),
        last=last,
        volume=1_800_000,
        asof_utc=datetime.now(timezone.utc),
    )

def _base_strategy(monkeypatch: pytest.MonkeyPatch, tmp_path, *, state: str) -> RossMomentumStrategyV1:
    bars_by_timeframe = {timeframe: _bars(state, timeframe) for timeframe in ("10s", "1m", "5m")}

    def _get_intraday_bars(*, symbol, timeframe="1m", limit=50, **_kwargs):
        return list(bars_by_timeframe[str(timeframe)])[-int(limit):]

    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        _get_intraday_bars,
    )
    strategy = RossMomentumStrategyV1()
    strategy._failure_trace_collector = RossPatternFailureTraceCollector(evidence_root=tmp_path)
    return strategy

def test_three_bar_and_second_pullback_triggers_have_family_specific_registry_entries() -> None:
    assert resolve_trigger_evaluator("THREE_BAR_PULLBACK") is evaluate_three_bar_pullback_trigger
    assert resolve_trigger_evaluator("SECOND_PULLBACK") is evaluate_second_pullback_trigger

def test_canonical_three_bar_pullback_detector_exports_trigger_contract() -> None:
    result = _detected_three("ready")

    assert result.setup_id == "P_THREE_BAR_PULLBACK"
    assert result.setup_family_id == "THREE_BAR_PULLBACK"
    assert result.setup_semantic == "CONTINUATION"
    assert result.trigger_type == "PULLBACK_HIGH_BREAK"
    assert result.trigger_mode == "NONE"
    assert result.trigger_level == pytest.approx(10.44)
    assert result.stop_level == pytest.approx(10.08)
    assert result.invalidation_level == pytest.approx(10.08)
    assert result.setup_metadata["breakout_volume_confirmed"] is True

def test_second_pullback_uses_its_own_structure_not_three_bar_shape() -> None:
    inputs = _inputs("second_ready")
    second = SecondPullbackPattern().evaluate(inputs)
    three = ThreeBarPullbackPattern().evaluate(inputs)

    assert second.detected is True
    assert second.setup_id == "P_SECOND_PULLBACK"
    assert second.setup_family_id == "SECOND_PULLBACK"
    assert second.trigger_type == "PULLBACK_HIGH_BREAK"
    assert second.trigger_mode == "NONE"
    assert second.setup_metadata["breakout_volume_confirmed"] is True
    assert three.detected is False
    assert three.rejection_reason == "three_bar_pullback_not_orderly"

def test_three_bar_pullback_trigger_transitions_not_ready_to_ready_and_invalidated() -> None:
    not_ready_payload = _trigger_payload(_detected_three("not_ready"))
    ready_payload = _trigger_payload(_detected_three("ready"))

    armed = evaluate_three_bar_pullback_trigger(not_ready_payload, {"candles": _bars("not_ready"), "rvol": 145.1})
    assert armed["trigger_state"] == "ARMED"
    assert armed["trigger_ready_now"] is False
    assert armed["trigger_reason"] == "awaiting_pullback_break"
    assert armed["execution_refinement_mode"] == "NONE"

    fired = evaluate_three_bar_pullback_trigger(ready_payload, {"candles": _bars("ready"), "rvol": 145.1})
    assert fired["trigger_state"] == "FIRED"
    assert fired["trigger_ready_now"] is True
    assert fired["trigger_reason"] == "pullback_high_broken"
    assert fired["trigger_type"] == "PULLBACK_HIGH_BREAK"

    invalidated = evaluate_three_bar_pullback_trigger(not_ready_payload, {"candles": _bars("invalidated"), "rvol": 145.1})
    assert invalidated["trigger_state"] == "BLOCKED"
    assert invalidated["trigger_ready_now"] is False
    assert invalidated["trigger_reason"] == "structural_invalidation_breached"


def test_trigger_engine_normalizes_pullback_pattern_alias_before_registered_evaluator() -> None:
    payload = _trigger_payload(_detected_three("not_ready"))
    payload["setup_family_id"] = "P_THREE_BAR_PULLBACK"
    payload["setup_family"] = "P_THREE_BAR_PULLBACK"

    triggers = TriggerEngine().evaluate_triggers(
        symbol="UPC",
        candles=_bars("not_ready"),
        setups=[payload],
        levels={"rvol": 145.1},
        structure={"trend": "UP", "is_actionable": True},
    )

    assert triggers[0]["setup_family_id"] == "THREE_BAR_PULLBACK"
    assert triggers[0]["trigger_type"] == "PULLBACK_HIGH_BREAK"
    assert triggers[0]["trigger_ready_now"] is False
    assert triggers[0]["trigger_reason"] == "awaiting_pullback_break"


def test_missing_structural_fields_and_pattern_inputs_block_without_intent_authority() -> None:
    missing_data = evaluate_three_bar_pullback_trigger(
        _trigger_payload(_detected_three("ready")),
        {"candles": [], "rvol": 145.1},
    )
    assert missing_data["trigger_state"] == "BLOCKED"
    assert missing_data["trigger_reason"] == "missing_candles"

    missing_levels = evaluate_three_bar_pullback_trigger(
        {"setup_family_id": "THREE_BAR_PULLBACK", "setup_detected": True},
        {"candles": _bars("ready"), "rvol": 145.1},
    )
    assert missing_levels["trigger_state"] == "BLOCKED"
    assert missing_levels["trigger_reason"] == "missing_fields"

def test_missing_or_failed_required_breakout_volume_confirmation_blocks_ready_breakout() -> None:
    result = _detected_three("ready")

    missing = evaluate_three_bar_pullback_trigger(
        _trigger_payload(result, volume_confirmation="missing"),
        {"candles": _bars("ready"), "rvol": 145.1},
    )
    assert missing["trigger_state"] == "BLOCKED"
    assert missing["trigger_reason"] == "breakout_volume_confirmation_missing"
    assert "PATTERN_VOLUME_CONFIRMATION_MISSING" in missing["quality_flags"]

    failed = evaluate_three_bar_pullback_trigger(
        _trigger_payload(result, volume_confirmation=False),
        {"candles": _bars("ready"), "rvol": 145.1},
    )
    assert failed["trigger_state"] == "BLOCKED"
    assert failed["trigger_reason"] == "breakout_volume_confirmation_failed"
    assert "PATTERN_VOLUME_CONFIRMATION_FAILED" in failed["quality_flags"]

def test_pattern_input_policy_blocks_missing_or_stale_required_timeframes() -> None:
    now = datetime.now(timezone.utc)
    missing_10s = _inputs("ready", now=now, omit_timeframes={"10s"})
    assert blocking_input_reason(missing_10s, "P_THREE_BAR_PULLBACK") == (
        "pr4_input_block:THREE_BAR_PULLBACK:timeframe:10s=MISSING"
    )

    stale_10s = build_authoritative_pattern_inputs(
        symbol="UPC",
        session_label="RTH_OPEN",
        session_phase="RTH_OPEN",
        timeframe_candles={
            "10s": _bars("ready", "10s", end=now - timedelta(seconds=90)),
            "1m": _bars("ready", "1m", end=now),
            "5m": _bars("ready", "5m", end=now),
        },
        indicators=IndicatorSet(ema9=10.35, ema20=10.10, vwap=10.05),
        levels=LevelSet(premarket_high=10.30, premarket_low=9.70, prior_close=8.50),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=8.0, rvol=145.1, volume=1_800_000),
        now=now,
    )
    assert blocking_input_reason(stale_10s, "P_THREE_BAR_PULLBACK") == (
        "pr4_input_block:THREE_BAR_PULLBACK:timeframe:10s=STALE"
    )

    missing_5m = _inputs("ready", now=now, omit_timeframes={"5m"})
    assert blocking_input_reason(missing_5m, "P_SECOND_PULLBACK") == (
        "pr4_input_block:SECOND_PULLBACK:timeframe:5m=MISSING"
    )

def test_registered_pmh_trigger_does_not_clobber_structural_invalidation() -> None:
    triggers = TriggerEngine().evaluate_triggers(
        symbol="PREX",
        candles=_candles(
            [
                (10.45, 10.58, 10.40, 10.55, 1000),
                (10.55, 10.64, 10.50, 10.62, 1300),
            ]
        ),
        setups=[
            {
                "setup_family_id": "PREMARKET_HIGH_BREAK",
                "setup_family": "PREMARKET_HIGH_BREAK",
                "setup_detected": True,
                "trigger_level": 10.60,
                "required_trigger_types": ["PMH_BREAK"],
            }
        ],
        levels={"premarket_high": 10.60},
        structure={"trend": "UP", "is_actionable": True},
    )

    assert triggers[0]["trigger_ready_now"] is True
    assert triggers[0]["trigger_type"] == "XL_PREMARKET_HIGH_BREAK"
    assert triggers[0]["trigger_price_reference"] == pytest.approx(10.60)
    assert triggers[0]["invalidation_price_reference"] == pytest.approx(10.50)


def test_registered_trade_ready_setup_without_trigger_mapping_is_internal_fault(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.delitem(trigger_registry.TRIGGER_EVALUATOR_REGISTRY, "THREE_BAR_PULLBACK", raising=False)

    triggers = TriggerEngine().evaluate_triggers(
        symbol="UPC",
        candles=_bars("ready"),
        setups=[_trigger_payload(_detected_three("ready"))],
        levels={"rvol": 145.1},
        structure={"trend": "UP", "is_actionable": True},
    )

    assert triggers[0]["trigger_type"] == "UNMAPPED"
    assert triggers[0]["trigger_ready_now"] is False
    assert triggers[0]["trigger_reason"] == "setup_trigger_mapping_missing"
    assert "SETUP_TRIGGER_MAPPING_MISSING setup_family=THREE_BAR_PULLBACK" in capsys.readouterr().out

def test_selected_setup_family_cannot_inherit_unrelated_micro_pullback_trigger() -> None:
    selected = RossMomentumStrategyV1._select_trigger_candidate(
        setup_family_id="P_THREE_BAR_PULLBACK",
        trigger_candidates=[
            {"setup_family_id": "MICRO_PULLBACK", "trigger_type": "FAST_MICRO_PULLBACK", "trigger_ready_now": True},
            {"setup_family_id": "THREE_BAR_PULLBACK", "trigger_type": "PULLBACK_HIGH_BREAK", "trigger_ready_now": False},
        ],
    )
    assert selected is not None
    assert selected["setup_family_id"] == "THREE_BAR_PULLBACK"

    assert RossMomentumStrategyV1._select_trigger_candidate(
        setup_family_id="P_THREE_BAR_PULLBACK",
        trigger_candidates=[{"setup_family_id": "MICRO_PULLBACK", "trigger_type": "FAST_MICRO_PULLBACK", "trigger_ready_now": True}],
    ) is None

def test_decision_engine_normalizes_natural_pullback_families() -> None:
    decision = DecisionEngine().compute_decision(
        symbol="UPC",
        levels={},
        structure={"trend": "UP"},
        setups=[{"setup_family": "THREE_BAR_PULLBACK"}],
        pattern_results=[_detected_pullback("P_THREE_BAR_PULLBACK")],
        session_context="RTH_OPEN",
    )

    assert decision["decision_state"] == "CANDIDATE_SELECTED"
    assert decision["selected_pattern_id"] == "P_THREE_BAR_PULLBACK"
    assert decision["selected_setup_family"] == "THREE_BAR_PULLBACK"

def test_canonical_pattern_result_creates_trigger_candidate_without_setup_promotion() -> None:
    strategy = RossMomentumStrategyV1()
    result = _detected_pullback("P_THREE_BAR_PULLBACK")
    existing_setups = [{"setup_family_id": "MICRO_PULLBACK", "setup_detected": True}]

    candidates = strategy._canonical_pattern_trigger_candidates(
        [result],
        symbol="UPC",
        existing_triggers=[],
    )

    assert [setup["setup_family_id"] for setup in existing_setups] == ["MICRO_PULLBACK"]
    assert candidates == [
        {
            "setup_family_id": "THREE_BAR_PULLBACK",
            "setup_family": "THREE_BAR_PULLBACK",
            "setup_name": "P_THREE_BAR_PULLBACK",
            "pattern_id": "P_THREE_BAR_PULLBACK",
            "pattern_name": "P_THREE_BAR_PULLBACK",
            "direction": "LONG",
            "confidence": pytest.approx(0.58),
            "quality_flags": ["natural_pullback", "CANONICAL_PATTERN_TRIGGER_AUTHORITY"],
            "blocking_flags": [],
            "invalidation_anchor": "pullback_low",
            "invalidation_level": pytest.approx(10.08),
            "stop_level": pytest.approx(10.08),
            "required_trigger_types": ["PULLBACK_HIGH_BREAK"],
            "trigger_level": pytest.approx(10.44),
            "setup_detected": True,
            "source": "canonical_pattern_result",
            "setup_metadata": result.setup_metadata,
            "execution_refinement_mode": "NONE",
        }
    ]

def test_canonical_pattern_adapter_rejects_incomplete_trigger_contract() -> None:
    strategy = RossMomentumStrategyV1()
    result = PatternResult(
        setup_id="P_THREE_BAR_PULLBACK",
        pattern_name="P_THREE_BAR_PULLBACK",
        pattern_family=PatternFamily.PULLBACK,
        detected=True,
        direction=Direction.LONG,
        confidence=0.58,
        setup_quality_tags=["natural_pullback"],
        setup_family_id="THREE_BAR_PULLBACK",
        trigger_type="PULLBACK_HIGH_BREAK",
    )

    assert strategy._canonical_pattern_trigger_candidates([result], symbol="UPC", existing_triggers=[]) == []

def test_natural_three_bar_pullback_ready_trigger_reaches_readonly_intent(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys) -> None:
    strategy = _base_strategy(monkeypatch, tmp_path, state="ready")
    strategy._pattern_registry = FakeRegistry([_detected_three("ready")])

    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row("ready")],
        snapshots={"UPC": _snapshot("ready")},
        session_label="RTH",
        timestamp_utc="cycle-pr1082-trigger-ready",
        mode=RunMode.READ_ONLY,
        session_phase="RTH_OPEN",
    )

    assert len(intents) == 1
    assert intents[0].symbol == "UPC"
    assert intents[0].setup_family_id == "THREE_BAR_PULLBACK"
    assert intents[0].trigger_id == "PULLBACK_HIGH_BREAK"
    assert intents[0].trigger_ready is True
    assert getattr(intents[0], "synthetic_forced_intent", False) is False
    terminal = strategy.last_symbol_terminal_outcomes["UPC"]
    assert terminal["outcome"] == "INTENT_CREATED"
    assert terminal["intent_emitted"] is True
    assert terminal["trigger_ready_now"] is True
    assert terminal["selected_setup_family"] == "THREE_BAR_PULLBACK"
    assert terminal["trigger_type"] == "PULLBACK_HIGH_BREAK"
    out = capsys.readouterr().out
    assert "[ROSS][CANONICAL_PATTERN_TRIGGER] symbol=UPC setup_family=THREE_BAR_PULLBACK" in out
    assert "[ROSS][TRIGGER_MAP] symbol=UPC setup_family=THREE_BAR_PULLBACK trigger_id=PULLBACK_HIGH_BREAK" in out
    assert "[ROSS][INTENT_GENERATED] symbol=UPC" in out
    assert "[ORDER_ROUTER]" not in out

def test_cycle_selection_marks_only_returned_intent_as_emitted(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    strategy = _base_strategy(monkeypatch, tmp_path, state="ready")
    strategy._pattern_registry = FakeRegistry([_detected_three("ready")])

    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row("ready", symbol="AAA"), _watchlist_row("ready", symbol="BBB")],
        snapshots={"AAA": _snapshot("ready", symbol="AAA"), "BBB": _snapshot("ready", symbol="BBB")},
        session_label="RTH",
        timestamp_utc="cycle-pr1089-selection",
        mode=RunMode.READ_ONLY,
        session_phase="RTH_OPEN",
    )

    assert [intent.symbol for intent in intents] == ["AAA"]
    winner = strategy.last_symbol_terminal_outcomes["AAA"]
    loser = strategy.last_symbol_terminal_outcomes["BBB"]
    assert winner["outcome"] == "INTENT_CREATED"
    assert winner["intent_emitted"] is True
    assert winner["terminal_stage"] == "intent"
    assert loser["outcome"] == "SETUP_FOUND_CYCLE_SELECTION_BLOCKED"
    assert loser["reason"] == "max_trades_per_cycle"
    assert loser["trigger_ready_now"] is True
    assert loser["intent_emitted"] is False
    assert loser["terminal_stage"] == "cycle_selection"


def test_existing_positions_exhaust_capacity_records_ready_no_intent_terminal(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    strategy = _base_strategy(monkeypatch, tmp_path, state="ready")
    strategy._pattern_registry = FakeRegistry([_detected_three("ready")])
    strategy._infer_open_positions_count = lambda _watchlist: strategy._max_concurrent_positions

    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row("ready")],
        snapshots={"UPC": _snapshot("ready")},
        session_label="RTH",
        timestamp_utc="cycle-pr1089-capacity",
        mode=RunMode.READ_ONLY,
        session_phase="RTH_OPEN",
    )

    assert intents == []
    terminal = strategy.last_symbol_terminal_outcomes["UPC"]
    assert terminal["outcome"] == "SETUP_FOUND_CAPACITY_BLOCKED"
    assert terminal["reason"] == "max_concurrent_positions_reached"
    assert terminal["trigger_ready_now"] is True
    assert terminal["intent_emitted"] is False
    assert terminal["terminal_stage"] == "capacity"


@pytest.mark.parametrize(
    "reason",
    [
        "LOW_CONFIDENCE",
        "SPREAD_UNAVAILABLE",
        "SPREAD_TOO_WIDE",
        "ENTRY_EXTENSION_TOO_WIDE",
        "MOMENTUM_CONTEXT_INVALID",
    ],
)
def test_fired_trigger_tradeability_block_records_valid_no_intent_terminal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    reason: str,
) -> None:
    strategy = _base_strategy(monkeypatch, tmp_path, state="ready")
    strategy._pattern_registry = FakeRegistry([_detected_three("ready")])
    strategy.evaluate_tradeable_entry = lambda **_kwargs: {
        "tradeable": False,
        "blocking_reasons": [reason],
        "spread_pct": 0.02,
        "extension_pct": 0.02,
    }

    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row("ready")],
        snapshots={"UPC": _snapshot("ready")},
        session_label="RTH",
        timestamp_utc=f"cycle-pr1089-tradeability-{reason.lower()}",
        mode=RunMode.READ_ONLY,
        session_phase="RTH_OPEN",
    )

    assert intents == []
    terminal = strategy.last_symbol_terminal_outcomes["UPC"]
    assert terminal["outcome"] == "SETUP_FOUND_TRADEABILITY_BLOCKED"
    assert terminal["reason"] == reason
    assert terminal["trigger_ready_now"] is True
    assert terminal["intent_emitted"] is False
    assert terminal["terminal_stage"] == "tradeability"
    assert terminal["trigger_type"] == "PULLBACK_HIGH_BREAK"

def test_natural_three_bar_pullback_not_ready_is_enriched_terminal_no_trade(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys) -> None:
    strategy = _base_strategy(monkeypatch, tmp_path, state="not_ready")
    strategy._pattern_registry = FakeRegistry([_detected_three("not_ready")])

    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row("not_ready")],
        snapshots={"UPC": _snapshot("not_ready")},
        session_label="RTH",
        timestamp_utc="cycle-pr1082-trigger-not-ready",
        mode=RunMode.READ_ONLY,
        session_phase="RTH_OPEN",
    )

    assert intents == []
    terminal = strategy.last_symbol_terminal_outcomes["UPC"]
    assert terminal["symbol"] == "UPC"
    assert terminal["cycle_id"] == "cycle-pr1082-trigger-not-ready"
    assert terminal["outcome"] == "SETUP_FOUND_BUT_NO_TRIGGER"
    assert terminal["reason"] == "awaiting_pullback_break"
    assert terminal["selected_setup_family"] == "THREE_BAR_PULLBACK"
    assert terminal["selected_pattern_id"] == "P_THREE_BAR_PULLBACK"
    assert terminal["trigger_type"] == "PULLBACK_HIGH_BREAK"
    assert terminal["trigger_ready_now"] is False
    assert terminal["intent_emitted"] is False
    assert terminal["pattern_inputs_ready"] is True
    assert terminal["pattern_detected"] is True
    assert terminal["trigger_evaluated"] is True
    assert terminal["terminal_stage"] == "trigger"
    assert "PIPELINE_BREAK_SETUP_TO_INTENT" not in capsys.readouterr().out

def test_missing_mapping_records_internal_fault_terminal_without_killing_strategy(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys) -> None:
    monkeypatch.delitem(trigger_registry.TRIGGER_EVALUATOR_REGISTRY, "THREE_BAR_PULLBACK", raising=False)
    strategy = _base_strategy(monkeypatch, tmp_path, state="ready")
    strategy._pattern_registry = FakeRegistry([_detected_three("ready")])

    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row("ready")],
        snapshots={"UPC": _snapshot("ready")},
        session_label="RTH",
        timestamp_utc="cycle-pr1082-missing-mapping",
        mode=RunMode.READ_ONLY,
        session_phase="RTH_OPEN",
    )

    assert intents == []
    terminal = strategy.last_symbol_terminal_outcomes["UPC"]
    assert terminal["outcome"] == "SETUP_TRIGGER_MAPPING_MISSING"
    assert terminal["reason"] == "setup_trigger_mapping_missing"
    assert terminal["selected_setup_family"] == "THREE_BAR_PULLBACK"
    assert terminal["trigger_type"] == "UNMAPPED"
    assert terminal["trigger_ready_now"] is False
    out = capsys.readouterr().out
    assert "[ROSS][INTERNAL_FAULT] symbol=UPC setup_family=THREE_BAR_PULLBACK reason=SETUP_TRIGGER_MAPPING_MISSING" in out


def _detected_parabolic_exhaustion() -> PatternResult:
    return PatternResult(
        setup_id="P_PARABOLIC_EXHAUSTION",
        pattern_name="P_PARABOLIC_EXHAUSTION",
        pattern_family=PatternFamily.EXHAUSTION,
        detected=True,
        direction=Direction.SHORT,
        confidence=0.82,
        setup_quality_tags=["risk_off"],
        setup_family_id="PARABOLIC_EXHAUSTION",
        signal_class="RISK_OFF",
        non_entry_signal=True,
        rationale_text="parabolic exhaustion risk-off pattern",
    )


def _run_rejected_decision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    *,
    results: list[PatternResult],
    decision: dict[str, object],
    cycle_id: str,
) -> tuple[RossMomentumStrategyV1, list]:
    strategy = _base_strategy(monkeypatch, tmp_path, state="not_ready")
    strategy._pattern_registry = FakeRegistry(results)
    strategy._decision_engine = SimpleNamespace(compute_decision=lambda **_kwargs: dict(decision))

    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row("not_ready")],
        snapshots={"UPC": _snapshot("not_ready")},
        session_label="RTH",
        timestamp_utc=cycle_id,
        mode=RunMode.READ_ONLY,
        session_phase="RTH_OPEN",
    )
    return strategy, intents


def test_decision_rejection_terminal_records_single_family_provenance(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    result = _detected_pullback("P_THREE_BAR_PULLBACK")
    strategy, intents = _run_rejected_decision(
        monkeypatch,
        tmp_path,
        results=[result],
        cycle_id="cycle-pr1082-single-rejection",
        decision={
            "decision_state": "CANDIDATE_REJECTED_INSUFFICIENT_QUALITY",
            "selected_setup_family": None,
            "selected_pattern_id": None,
            "selected_pattern_name": None,
            "decision_reason": "all_detected_candidates_rejected",
            "rejected_candidates": [
                {"pattern_id": "P_THREE_BAR_PULLBACK", "setup_family": "THREE_BAR_PULLBACK", "reason": "quality_gate"}
            ],
        },
    )

    assert intents == []
    terminal = strategy.last_symbol_terminal_outcomes["UPC"]
    assert terminal["outcome"] == "SETUP_FOUND_DECISION_REJECTED"
    assert terminal["selected_setup_family"] == "THREE_BAR_PULLBACK"
    assert terminal["selected_pattern_id"] == "P_THREE_BAR_PULLBACK"
    assert "selected_setup_families" not in terminal


def test_decision_rejection_terminal_records_multi_family_conflict_provenance(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    strategy, intents = _run_rejected_decision(
        monkeypatch,
        tmp_path,
        results=[_detected_pullback("P_THREE_BAR_PULLBACK"), _detected_pullback("P_SECOND_PULLBACK")],
        cycle_id="cycle-pr1082-multi-rejection",
        decision={
            "decision_state": "CANDIDATE_REJECTED_CONFLICT",
            "selected_setup_family": None,
            "selected_pattern_id": None,
            "selected_pattern_name": None,
            "decision_reason": "rejected_true_conflict_opposing_direction",
            "rejected_candidates": [
                {"pattern_id": "P_THREE_BAR_PULLBACK", "setup_family": "THREE_BAR_PULLBACK", "reason": "conflict"},
                {"pattern_id": "P_SECOND_PULLBACK", "setup_family": "SECOND_PULLBACK", "reason": "conflict"},
            ],
        },
    )

    assert intents == []
    terminal = strategy.last_symbol_terminal_outcomes["UPC"]
    assert terminal["outcome"] == "SETUP_FOUND_DECISION_REJECTED"
    assert "selected_setup_family" not in terminal
    assert terminal["selected_setup_families"] == ["SECOND_PULLBACK", "THREE_BAR_PULLBACK"]
    assert terminal["selected_pattern_ids"] == ["P_SECOND_PULLBACK", "P_THREE_BAR_PULLBACK"]
    assert terminal["trigger_type"] == "DECISION_REJECTED"


def test_decision_rejection_terminal_records_parabolic_exhaustion_provenance(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    strategy, intents = _run_rejected_decision(
        monkeypatch,
        tmp_path,
        results=[_detected_parabolic_exhaustion()],
        cycle_id="cycle-pr1082-parabolic-rejection",
        decision={
            "decision_state": "CANDIDATE_REJECTED_INSUFFICIENT_QUALITY",
            "selected_setup_family": None,
            "selected_pattern_id": None,
            "selected_pattern_name": None,
            "decision_reason": "all_detected_candidates_rejected",
            "rejected_candidates": [
                {"pattern_id": "P_PARABOLIC_EXHAUSTION", "reason": "parabolic_exhaustion_non_entry"}
            ],
        },
    )

    assert intents == []
    terminal = strategy.last_symbol_terminal_outcomes["UPC"]
    assert terminal["outcome"] == "SETUP_FOUND_DECISION_REJECTED"
    assert terminal["selected_setup_family"] == "PARABOLIC_EXHAUSTION"
    assert terminal["selected_pattern_id"] == "P_PARABOLIC_EXHAUSTION"
    assert terminal["terminal_stage"] == "decision"


@pytest.mark.parametrize(
    "entry,stop,reason",
    [
        (None, 10.08, "missing_trigger_entry_or_stop"),
        (10.44, None, "missing_trigger_entry_or_stop"),
        (10.44, 10.44, "entry_stop_structure_invalid"),
        (10.44, 10.60, "entry_stop_structure_invalid"),
    ],
    ids=["missing_entry", "missing_stop", "equal_stop", "higher_stop"],
)
def test_trade_structure_block_preserves_fired_trigger(
    monkeypatch, tmp_path, entry, stop, reason,
) -> None:
    strategy = _base_strategy(monkeypatch, tmp_path, state="ready")
    strategy._pattern_registry = FakeRegistry([_detected_three("ready")])
    build_trade = strategy._build_trade_from_pattern

    def _invalid_structure(pattern, inputs, *, selected_trigger, rejection_reasons):
        assert selected_trigger["trigger_ready_now"] is True
        payload = dict(selected_trigger)
        payload.update(
            trigger_price_reference=entry, trigger_level=entry,
            invalidation_price_reference=stop, invalidation_level=stop, stop_level=stop,
        )
        return build_trade(pattern, inputs, selected_trigger=payload, rejection_reasons=rejection_reasons)

    monkeypatch.setattr(strategy, "_build_trade_from_pattern", _invalid_structure)
    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row("ready")],
        snapshots={"UPC": _snapshot("ready")},
        session_label="RTH", timestamp_utc="cycle-structure",
        mode=RunMode.READ_ONLY, session_phase="RTH_OPEN",
    )
    assert intents == []
    terminal = strategy.last_symbol_terminal_outcomes["UPC"]
    assert terminal["outcome"] == "SETUP_FOUND_TRADE_STRUCTURE_BLOCKED"
    assert terminal["reason"] == reason
    assert terminal["terminal_stage"] == "trade_structure"
    assert terminal["trigger_ready_now"] is True
    assert terminal["intent_emitted"] is False
    assert terminal["symbol"] == "UPC"
    assert terminal["cycle_id"] == "cycle-structure"
    assert terminal["selected_setup_family"] == "THREE_BAR_PULLBACK"
    assert terminal["selected_pattern_id"] == "P_THREE_BAR_PULLBACK"
    assert terminal["trigger_type"] == "PULLBACK_HIGH_BREAK"
    trace = strategy._failure_trace_collector._symbols[-1]
    assert trace.trigger_stage["status"] == "FIRED"
    assert trace.final_reason_code == reason


def test_trade_structure_mixed_cycle_preserves_valid_intent_without_broker_mutation(
    monkeypatch, tmp_path, capsys,
) -> None:
    from test_pr1082_rth_watchlist_continuity import _install_runtime_harness, _payload, _row
    from ibapi.client import EClient

    broker_calls = []

    def _forbid_broker_mutation(*args, **kwargs):
        broker_calls.append((args, kwargs))
        raise AssertionError("No broker mutation is allowed")

    monkeypatch.setattr(EClient, "placeOrder", _forbid_broker_mutation)
    monkeypatch.setattr(EClient, "cancelOrder", _forbid_broker_mutation)
    aaa, bbb = _row("AAA", catalyst=True), _row("BBB", catalyst=True)
    orchestrator, _, _ = _install_runtime_harness(monkeypatch, [_payload([aaa, bbb], focus=[aaa, bbb])])
    strategy = _base_strategy(monkeypatch, tmp_path, state="ready")
    strategy._pattern_registry = FakeRegistry([_detected_three("ready")])
    build_trade = strategy._build_trade_from_pattern

    def _build_with_invalid_b(pattern, inputs, *, selected_trigger, rejection_reasons):
        assert selected_trigger["trigger_ready_now"] is True
        payload = dict(selected_trigger)
        if inputs.symbol == "BBB":
            payload.update(invalidation_price_reference=20.0, invalidation_level=20.0, stop_level=20.0)
        return build_trade(pattern, inputs, selected_trigger=payload, rejection_reasons=rejection_reasons)

    monkeypatch.setattr(strategy, "_build_trade_from_pattern", _build_with_invalid_b)
    orchestrator.strategy_runner.strategies = [strategy]
    returned = []

    def _process(**kwargs):
        intents = strategy.process_watchlist(
            watchlist=[_watchlist_row("ready", symbol=s) for s in ("AAA", "BBB")],
            snapshots={s: _snapshot("ready", symbol=s) for s in ("AAA", "BBB")},
            session_label="RTH", timestamp_utc=kwargs["timestamp_utc"],
            mode=RunMode.READ_ONLY, session_phase="RTH_OPEN",
        )
        returned.extend(intents)
        return intents

    orchestrator.strategy_runner.process = _process
    assert orchestrator.run_once() is True
    assert [intent.symbol for intent in returned] == ["AAA"]
    assert strategy.last_symbol_terminal_outcomes["AAA"]["intent_emitted"] is True
    blocked = strategy.last_symbol_terminal_outcomes["BBB"]
    assert blocked["outcome"] == "SETUP_FOUND_TRADE_STRUCTURE_BLOCKED"
    assert blocked["reason"] == "entry_stop_structure_invalid"
    assert blocked["trigger_ready_now"] is True
    assert blocked["intent_emitted"] is False
    output = capsys.readouterr().out
    assert "PIPELINE_BREAK_SETUP_TO_INTENT" not in output
    assert "[PIPELINE][SYMBOL_TRACE] symbol=AAA strategy_detected=True intent_created=True" in output
    assert "[PIPELINE][SYMBOL_TRACE] symbol=BBB strategy_detected=True intent_created=False" in output
    assert broker_calls == []
