from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from src.config.runtime_config import RunMode
from src.domain.market_snapshot import MarketSnapshot
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.ross_momentum.patterns.pattern_trace import (
    RossPatternFailureTraceCollector,
    RossPatternTrace,
    RossSymbolTrace,
    build_runtime_pattern_inputs,
)
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


class _EmptyRegistry:
    inactive_pattern_ids: set[str] = set()

    @property
    def pattern_ids(self) -> list[str]:
        return []

    def run(self, inputs, *, trace_context=None, trace_collector=None):
        return []


def _pre_bars() -> list[Candle]:
    return [
        Candle(open=10.0, high=10.2, low=9.98, close=10.15, volume=2500),
        Candle(open=10.15, high=10.35, low=10.12, close=10.30, volume=3200),
        Candle(open=10.30, high=10.48, low=10.26, close=10.42, volume=3900),
        Candle(open=10.42, high=10.55, low=10.38, close=10.50, volume=4500),
        Candle(open=10.50, high=10.62, low=10.45, close=10.61, volume=5200),
    ]


def test_pre_candidate_pre_activation_is_observable_and_can_promote_breakout_trigger(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: _pre_bars(),
    )
    strategy = RossMomentumStrategyV1()
    strategy._failure_trace_collector = RossPatternFailureTraceCollector(evidence_root=tmp_path)
    strategy._pattern_registry = _EmptyRegistry()
    strategy._data_contract_block_reasons = lambda **kwargs: []

    intents = strategy.process_watchlist(
        watchlist=[{
            "symbol": "PREX",
            "promotion_reason": "manual_focus",
            "session_label": "PRE",
            "last_price": 10.62,
            "bid": 10.61,
            "ask": 10.63,
            "spread": 0.02,
            "volume": 200_000,
            "pct_change": 3.2,
            "rvol": 1.8,
            "float_millions": 14.0,
            "premarket_high": 10.6,
            "previous_close": 9.9,
        }],
        snapshots={"PREX": MarketSnapshot(symbol="PREX", bid=10.61, ask=10.63, last=10.62, volume=200_000, asof_utc=datetime.now(timezone.utc))},
        session_label="PRE",
        timestamp_utc="cycle-pre-ready",
        mode=RunMode.LIVE,
        session_phase="PRE",
    )

    out = capsys.readouterr().out
    assert intents
    assert intents[0].trigger_ready is True
    assert "[ROSS][PRE_ACTIVATION] symbol=PREX" in out
    assert "[ROSS][PRE_TRIGGER_PROMOTION] symbol=PREX reason=PRE_ACTIVATION_BREAKOUT" in out
    assert "[ROSS][INTENT_GENERATED] symbol=PREX" in out


def test_registry_marks_session_incompatible_patterns_as_skipped(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: _pre_bars() * 5,
    )
    inputs, _flags = build_runtime_pattern_inputs(
        symbol="SKIP",
        row={"symbol": "SKIP", "session_label": "PRE", "last_price": 10.6, "volume": 100_000, "prior_close": 9.8, "premarket_high": 10.55},
        snapshot=MarketSnapshot(symbol="SKIP", bid=10.59, ask=10.6, last=10.6, volume=100_000, asof_utc=datetime.now(timezone.utc)),
        session_label="PRE",
        session_phase="PRE",
    )
    traces: list[RossPatternTrace] = []
    RossPatternRegistry().run(inputs, trace_collector=traces.append)
    assert any(t.pattern_id == "P_ORB" and t.skipped and t.skip_reason == "session_incompatible" for t in traces)


def test_pattern_inputs_normalize_level_aliases(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: _pre_bars() * 5,
    )
    inputs, _ = build_runtime_pattern_inputs(
        symbol="NORM",
        row={
            "symbol": "NORM",
            "session_label": "PRE",
            "last_price": 10.6,
            "volume": 120_000,
            "previous_close": 9.95,
            "PREMARKET_HIGH": 10.62,
            "PREMARKET_LOW": 9.9,
            "HOD": 10.65,
            "LOD": 9.85,
        },
        snapshot=MarketSnapshot(symbol="NORM", bid=10.59, ask=10.6, last=10.6, volume=120_000, asof_utc=datetime.now(timezone.utc)),
        session_label="PRE",
        session_phase="PRE",
    )
    assert inputs is not None
    assert inputs.levels.prior_close == 9.95
    assert inputs.levels.premarket_high == 10.62
    assert "LAST_RTH_CLOSE" in inputs.levels.key_levels


def test_rth_thresholds_remain_strict_for_fallback() -> None:
    strategy = RossMomentumStrategyV1()
    summary = SimpleNamespace(session_context="RTH", pct_change=3.0, rvol=1.6, volume=300_000, last_price=11.0)
    assert strategy._build_fallback_momentum_intent(symbol="RTHX", input_summary=summary) is None


def test_failure_summary_separates_skips_from_real_rejections(tmp_path) -> None:
    collector = RossPatternFailureTraceCollector(evidence_root=tmp_path)
    symbol_trace = RossSymbolTrace(
        symbol="SUMM",
        cycle_id="cycle-1",
        strategy_key="ross_momentum",
        session_label="PRE",
        session_phase="PRE",
        runtime_mode="LIVE",
        symbol_source="manual_focus",
    )
    symbol_trace.pattern_traces = [
        RossPatternTrace(symbol="SUMM", cycle_id="cycle-1", strategy_key="ross_momentum", session_label="PRE", session_phase="PRE", runtime_mode="LIVE", symbol_source="manual_focus", pattern_id="P_ORB", pattern_name="ORB", setup_family_id="P_ORB", invoked=True, skipped=True, skip_reason="session_incompatible"),
        RossPatternTrace(symbol="SUMM", cycle_id="cycle-1", strategy_key="ross_momentum", session_label="PRE", session_phase="PRE", runtime_mode="LIVE", symbol_source="manual_focus", pattern_id="C_ENGULFING", pattern_name="Engulfing", setup_family_id="C_ENGULFING", invoked=True, skipped=True, skip_reason="inactive_placeholder"),
        RossPatternTrace(symbol="SUMM", cycle_id="cycle-1", strategy_key="ross_momentum", session_label="PRE", session_phase="PRE", runtime_mode="LIVE", symbol_source="manual_focus", pattern_id="P_PREMKT_BREAK", pattern_name="Premarket High Break", setup_family_id="P_PREMKT_BREAK", invoked=True, detected=False, rejection_reason="price below premarket high"),
    ]
    cycle = collector.build_cycle_summary(
        cycle_id="cycle-1",
        strategy_key="ross_momentum",
        session_label="PRE",
        session_phase="PRE",
        runtime_mode="LIVE",
        symbol_traces=[symbol_trace],
        real_setup_trigger_count=0,
        synthetic_forced_intents=0,
    )
    assert cycle.dominant_skip_reasons.get("session_incompatible") == 1
    assert cycle.dominant_inactive_placeholder_reasons.get("inactive_placeholder") == 1
    assert cycle.dominant_real_pattern_rejections == {"price below premarket high": 1}
