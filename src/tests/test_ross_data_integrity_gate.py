from __future__ import annotations

from datetime import datetime, timezone

from src.domain.market_snapshot import MarketSnapshot
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_trace import (
    PatternInputSnapshotSummary,
    build_runtime_pattern_inputs,
)
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


def _bars(count: int = 25, volume: float = 1_500.0) -> list[Candle]:
    now = datetime.now(timezone.utc)
    return [
        Candle(
            open=10.0 + idx * 0.02,
            high=10.1 + idx * 0.02,
            low=9.9 + idx * 0.02,
            close=10.05 + idx * 0.02,
            volume=volume,
            timestamp=now,
        )
        for idx in range(count)
    ]


def test_runtime_inputs_prefers_intraday_volume_when_snapshot_volume_invalid(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **_: _bars(),
    )
    snapshot = MarketSnapshot(
        symbol="TEST",
        bid=10.0,
        ask=10.1,
        last=10.05,
        volume=1.0,
        asof_utc=datetime.now(timezone.utc),
    )
    row = {"symbol": "TEST", "avg_volume_20d": 1_000_000}
    inputs, flags = build_runtime_pattern_inputs(
        symbol="TEST",
        row=row,
        snapshot=snapshot,
        session_label="PRE",
        session_phase="PRE",
    )
    assert inputs is not None
    assert "INVALID_VOLUME" not in flags
    assert float(inputs.news_context["volume"]) >= 10_000.0


def test_ross_pre_pattern_data_block_reasons_include_spread_and_rvol() -> None:
    strategy = RossMomentumStrategyV1()
    summary = PatternInputSnapshotSummary(
        candle_count=25,
        last_price=10.1,
        bid=None,
        ask=None,
        spread=None,
        volume=75_000.0,
        pct_change=6.0,
        rvol=0.3,
        float_millions=20.0,
        has_levels=True,
        levels_present=["hod", "lod"],
        has_indicators=True,
        indicators_present=["EMA9", "EMA20"],
        session_context="RTH_OPEN",
        quality_flags=["SPREAD_UNKNOWN"],
        missing_fields=[],
    )
    reasons = strategy._data_contract_block_reasons(
        symbol="TEST",
        input_summary=summary,
        inputs=type("Inputs", (), {"candles": _bars(5, 5000.0)})(),
    )
    assert "RVOL_WEAK" in reasons
    assert "SPREAD_UNKNOWN" in reasons
