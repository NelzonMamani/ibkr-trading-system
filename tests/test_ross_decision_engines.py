from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.config.runtime_config import RunMode
from src.core.engines.pattern_engine import PatternEngine
from src.core.engines.setup_engine import SetupEngine
from src.core.engines.trigger_engine import TriggerEngine
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


def _candle(open_: float, high: float, low: float, close: float, minute: int, volume: float) -> Candle:
    base = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    return Candle(
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        timestamp=base + timedelta(minutes=minute),
    )


def _bullish_candles() -> list[Candle]:
    return [
        _candle(10.0, 10.4, 9.95, 10.3, 0, 200_000),
        _candle(10.3, 10.6, 10.15, 10.55, 1, 280_000),
        _candle(10.55, 10.58, 10.32, 10.4, 2, 120_000),
        _candle(10.4, 10.48, 10.33, 10.45, 3, 105_000),
        _candle(10.45, 10.72, 10.44, 10.7, 4, 310_000),
    ]


def test_setup_engine_returns_explicit_rejection_when_no_valid_setup() -> None:
    engine = SetupEngine()
    output = engine.evaluate_setup(
        symbol="TEST",
        session_context="RTH",
        structure_output={"trend": "DOWN", "pullback_active": False, "compression_active": False},
        candles=_bullish_candles(),
        levels={},
    )

    assert output["setup_valid"] is False
    assert output["rejection_reason"] == "no_ross_setup_from_structure"


def test_pattern_engine_rejects_break_below_pullback_low() -> None:
    candles = _bullish_candles()
    setup_output = {
        "setup_valid": True,
        "setup_family": "FIRST_PULLBACK",
        "candidate_entry_level": 10.6,
        "pullback_high": 10.58,
        "pullback_low": 10.5,
    }
    output = PatternEngine().evaluate_pattern(
        symbol="TEST",
        setup_output=setup_output,
        candles=candles,
    )

    assert output["pattern_valid"] is False
    assert "BROKE_BELOW_PULLBACK_LOW" in output["disqualifying_flags"]


def test_trigger_engine_fires_only_when_breakout_clears_entry() -> None:
    setup_output = {
        "setup_valid": True,
        "setup_family": "FIRST_PULLBACK",
        "candidate_entry_level": 10.6,
        "pullback_high": 10.58,
    }
    pattern_output = {"pattern_valid": True, "pattern_reason": "pattern_confirmed"}
    fired = TriggerEngine().evaluate_trigger(
        symbol="TEST",
        setup_output=setup_output,
        pattern_output=pattern_output,
        live_bar={"high": 10.7, "close": 10.68},
    )
    rejected = TriggerEngine().evaluate_trigger(
        symbol="TEST",
        setup_output=setup_output,
        pattern_output=pattern_output,
        live_bar={"high": 10.59, "close": 10.58},
    )

    assert fired["trigger_fired"] is True
    assert fired["trigger_type"] == "FIRST_NEW_HIGH_BREAK"
    assert rejected["trigger_fired"] is False


def test_ross_runtime_calls_setup_pattern_and_trigger_engines(monkeypatch) -> None:
    calls = {"setup": 0, "pattern": 0, "trigger": 0}

    original_setup = SetupEngine.evaluate_setup
    original_pattern = PatternEngine.evaluate_pattern
    original_trigger = TriggerEngine.evaluate_trigger

    def wrapped_setup(self, **kwargs):
        calls["setup"] += 1
        return original_setup(self, **kwargs)

    def wrapped_pattern(self, **kwargs):
        calls["pattern"] += 1
        return original_pattern(self, **kwargs)

    def wrapped_trigger(self, **kwargs):
        calls["trigger"] += 1
        return original_trigger(self, **kwargs)

    monkeypatch.setattr(SetupEngine, "evaluate_setup", wrapped_setup)
    monkeypatch.setattr(PatternEngine, "evaluate_pattern", wrapped_pattern)
    monkeypatch.setattr(TriggerEngine, "evaluate_trigger", wrapped_trigger)
    candles = _bullish_candles()

    def _fake_build_runtime_pattern_inputs(**kwargs):
        return (
            SimpleNamespace(
                candles=candles,
                levels=SimpleNamespace(key_levels={}, prior_close=10.0),
                indicators=SimpleNamespace(ema9=10.4, ema20=10.2, ema50=9.9, ema200=9.5),
                liquidity_context=SimpleNamespace(rvol=3.1, float_millions=12.0),
                session_context="RTH",
            ),
            [],
        )

    class _Summary:
        candle_count = len(candles)
        last_price = candles[-1].close
        rvol = 3.1
        float_millions = 12.0
        levels_present = []
        indicators_present = []
        pct_change = 8.5
        session_context = "RTH"
        has_indicators = True
        has_levels = True
        missing_fields = []
        volume = 2_000_000
        spread = 0.03
        quality_flags = []

        def to_dict(self):
            return {
                "candle_count": self.candle_count,
                "last_price": self.last_price,
                "rvol": self.rvol,
                "float_millions": self.float_millions,
                "session_context": self.session_context,
            }

    monkeypatch.setattr(
        "src.strategies.ross_momentum_strategy_v1.build_runtime_pattern_inputs",
        _fake_build_runtime_pattern_inputs,
    )
    monkeypatch.setattr(
        "src.strategies.ross_momentum_strategy_v1.build_input_snapshot_summary",
        lambda **kwargs: _Summary(),
    )

    strategy = RossMomentumStrategyV1()
    strategy._pattern_registry = SimpleNamespace(
        pattern_ids=[],
        inactive_pattern_ids=set(),
        run=lambda *args, **kwargs: [],
    )
    strategy.process_watchlist(
        watchlist=[
            {
                "symbol": "TEST",
                "session_label": "RTH",
                "volume": 2_000_000,
                "pct_change": 8.5,
                "rvol": 3.1,
                "price": 10.7,
            }
        ],
        snapshots={},
        session_label="RTH",
        timestamp_utc="2026-01-05T15:00:00Z",
        mode=RunMode.PAPER,
        session_phase="RTH_OPEN",
    )

    assert calls["setup"] >= 1
    assert calls["pattern"] >= 1
    assert calls["trigger"] >= 1
