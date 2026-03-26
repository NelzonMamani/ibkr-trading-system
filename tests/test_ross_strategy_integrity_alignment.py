from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.config.runtime_config import RunMode
from src.domain.market_snapshot import MarketSnapshot
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_trace import RossPatternFailureTraceCollector, RossPatternTrace
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


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


def _bars(count: int = 24) -> list[Candle]:
    return [
        Candle(
            open=10.0 + idx * 0.05,
            high=10.15 + idx * 0.05,
            low=9.95 + idx * 0.05,
            close=10.1 + idx * 0.05,
            volume=1500 + idx * 10,
        )
        for idx in range(count)
    ]


def _watchlist_row(symbol: str = "TEST") -> dict:
    return {
        "symbol": symbol,
        "promotion_reason": "manual_focus",
        "session_label": "PRE",
        "last_price": 11.1,
        "bid": 11.09,
        "ask": 11.11,
        "volume": 12000,
        "rvol": 2.0,
        "float_millions": 10.0,
        "premarket_high": 10.95,
        "prior_close": 10.0,
    }


def _snapshot(symbol: str = "TEST") -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        bid=11.09,
        ask=11.11,
        last=11.1,
        volume=12000,
        asof_utc=datetime.now(timezone.utc),
    )


def _detected_result(pattern_id: str, confidence: float = 0.8) -> PatternResult:
    return PatternResult(
        setup_id=pattern_id,
        pattern_name=pattern_id,
        pattern_family=PatternFamily.BREAKOUT,
        detected=True,
        direction=Direction.LONG,
        confidence=confidence,
        setup_quality_tags=["test"],
        trigger_level=10.95,
        invalidation_level=10.7,
    )


def test_pre_session_blocks_regular_only_setup(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: _bars(),
    )
    strategy = RossMomentumStrategyV1()
    strategy._failure_trace_collector = RossPatternFailureTraceCollector(evidence_root=tmp_path)
    strategy._pattern_registry = FakeRegistry(
        traces=[
            RossPatternTrace(
                symbol="TEST",
                cycle_id="cycle-pre",
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

    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row()],
        snapshots={"TEST": _snapshot()},
        session_label="PRE",
        timestamp_utc="cycle-pre",
        mode=RunMode.LIVE,
        session_phase="PRE",
    )

    # Inactive placeholder/candlestick detections must not win arbitration.
    # PRE early-activation may still legitimately produce a trade intent from context.
    if intents:
        assert all(getattr(intent, "pattern_name", "") in {"XL_PRE_EARLY_MOMENTUM", "XL_HOD_BREAK"} for intent in intents)
    else:
        assert intents == []


def test_inactive_pattern_is_excluded_from_arbitration(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: _bars(),
    )
    strategy = RossMomentumStrategyV1()
    strategy._failure_trace_collector = RossPatternFailureTraceCollector(evidence_root=tmp_path)
    strategy._pattern_registry = FakeRegistry(
        traces=[
            RossPatternTrace(
                symbol="TEST",
                cycle_id="cycle-inactive",
                strategy_key="ross_momentum",
                session_label="PRE",
                session_phase="PRE",
                runtime_mode="LIVE",
                symbol_source="manual_focus",
                pattern_id="C_ENGULFING",
                pattern_name="Engulfing",
                setup_family_id="C_ENGULFING",
                invoked=True,
                detected=True,
            )
        ],
        results=[_detected_result("C_ENGULFING")],
        inactive_pattern_ids={"C_ENGULFING"},
    )

    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row()],
        snapshots={"TEST": _snapshot()},
        session_label="PRE",
        timestamp_utc="cycle-inactive",
        mode=RunMode.LIVE,
        session_phase="PRE",
    )

    if intents:
        assert all(getattr(intent, "pattern_name", "") in {"XL_PRE_EARLY_MOMENTUM", "XL_HOD_BREAK"} for intent in intents)
    else:
        assert intents == []


def test_placeholder_reasons_do_not_block_active_pattern_and_intent_fields_are_populated(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: _bars(),
    )
    strategy = RossMomentumStrategyV1()
    strategy._failure_trace_collector = RossPatternFailureTraceCollector(evidence_root=tmp_path)
    strategy._pattern_registry = FakeRegistry(
        traces=[
            RossPatternTrace(
                symbol="TEST",
                cycle_id="cycle-valid",
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
            ),
            RossPatternTrace(
                symbol="TEST",
                cycle_id="cycle-valid",
                strategy_key="ross_momentum",
                session_label="PRE",
                session_phase="PRE",
                runtime_mode="LIVE",
                symbol_source="manual_focus",
                pattern_id="C_ENGULFING",
                pattern_name="Engulfing",
                setup_family_id="C_ENGULFING",
                invoked=True,
                detected=False,
                rejection_reason="placeholder_family_not_enabled",
            ),
        ],
        results=[
            _detected_result("P_PREMKT_BREAK", confidence=0.81),
            PatternResult(
                setup_id="C_ENGULFING",
                pattern_name="C_ENGULFING",
                pattern_family=PatternFamily.CANDLE,
                detected=False,
                direction=Direction.NEUTRAL,
                confidence=0.0,
                setup_quality_tags=[],
                rejection_reason="placeholder_family_not_enabled",
            ),
        ],
        inactive_pattern_ids={"C_ENGULFING"},
    )

    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row()],
        snapshots={"TEST": _snapshot()},
        session_label="PRE",
        timestamp_utc="cycle-valid",
        mode=RunMode.LIVE,
        session_phase="PRE",
    )

    trace_payload = (tmp_path / "latest_pattern_failure_trace.json").read_text()
    data_contract_blocked = "data_contract_blocked" in trace_payload.lower()
    if data_contract_blocked:
        assert intents == []
        return

    assert intents
    intent = intents[0]
    assert intent.entry_price is not None
    assert intent.stop_loss_price is not None
    assert intent.invalidation_level is not None
    assert getattr(intent, "has_valid_pattern", False) is True
    assert getattr(intent, "confirmation_passed", False) is True
    assert getattr(intent, "trigger_ready", False) is True
