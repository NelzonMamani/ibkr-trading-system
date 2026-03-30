from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.core.engines.trigger_engine import TriggerEngine
from src.setup_engine.setup_families.ross_families import GapGoPattern
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext


def _candles() -> list[dict]:
    base = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)
    rows: list[dict] = []
    prices = [5.10, 5.30, 5.55, 5.80, 6.05]
    for idx, close in enumerate(prices):
        rows.append(
            {
                "timestamp": base + timedelta(minutes=idx),
                "open": close - 0.06,
                "high": close + 0.08,
                "low": close - 0.10,
                "close": close,
                "volume": 30_000 + idx * 2_000,
            }
        )
    return rows


def _pattern_inputs(*, rvol: float, spread: float, session: SessionContext = SessionContext.PRE) -> PatternInputs:
    candles = [
        Candle(
            timestamp=row["timestamp"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
        )
        for row in _candles()
    ]
    return PatternInputs(
        symbol="GAPX",
        timeframe="M1",
        candles=candles,
        session_context=session,
        levels=LevelSet(premarket_high=5.7, hod=6.0, prior_close=4.8, key_levels={}),
        indicators=IndicatorSet(vwap=5.6, ema9=5.55),
        liquidity_context=LiquidityContext(spread=spread, float_millions=20.0, rvol=rvol),
        news_context={"trend_up": True, "impulse_active": True, "compression_active": True},
    )


def test_gap_go_pre_rvol_threshold_allows_tradeable_setup() -> None:
    result = GapGoPattern().evaluate(_pattern_inputs(rvol=0.4, spread=0.02))
    assert result.detected is True
    assert str(result.setup_family_id).upper() == "GAP_GO"


def test_gap_go_spread_absolute_values_are_normalized_to_pct() -> None:
    result = GapGoPattern().evaluate(_pattern_inputs(rvol=0.9, spread=0.60))
    assert result.detected is False
    assert str(result.rejection_reason).upper() == "WIDE_SPREAD"


def test_trigger_engine_gap_go_pmh_break_uses_premarket_high() -> None:
    triggers = TriggerEngine().evaluate_triggers(
        symbol="GAPX",
        candles=_candles(),
        setups=[
            {"setup_family_id": "GAP_GO", "required_trigger_types": ["PMH_BREAK"], "trigger_level": 5.7},
        ],
        levels={"premarket_high": 5.7, "hod": 6.0},
        structure={},
    )
    assert triggers[0]["trigger_ready_now"] is True
    assert triggers[0]["trigger_event_emitted"] is True


def test_trigger_engine_gap_go_break_and_hold_requires_hold_confirmation() -> None:
    candles = _candles()
    candles[-2]["close"] = 5.60
    candles[-1]["close"] = 5.90
    triggers = TriggerEngine().evaluate_triggers(
        symbol="GAPX",
        candles=candles,
        setups=[
            {"setup_family_id": "GAP_GO", "required_trigger_types": ["BREAK_AND_HOLD"], "trigger_level": 5.8},
        ],
        levels={"premarket_high": 5.7, "hod": 6.0},
        structure={},
    )
    assert triggers[0]["trigger_ready_now"] is False
