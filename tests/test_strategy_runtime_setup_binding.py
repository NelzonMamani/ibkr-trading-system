from __future__ import annotations

from dataclasses import replace

from src.setup_engine.registry import CANONICAL_SETUP_REGISTRY, SetupImplementationStatus
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.strategy_contracts import SessionContext


def _candles(vals: list[tuple[float, float, float, float, int]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in vals]


def _inputs(setup_id: str) -> PatternInputs:
    base = PatternInputs(
        symbol=setup_id,
        timeframe="1m",
        candles=_candles([(10, 10.2, 9.9, 10.1, 1000)] * 12),
        session_context=SessionContext.PRE,
        levels=LevelSet(
            premarket_high=10.5,
            premarket_low=10.1,
            hod=10.9,
            lod=9.9,
            prior_close=9.8,
            key_levels={"PULLBACK_HIGH": 10.45, "PULLBACK_LOW": 10.2, "pivot": 10.4},
        ),
        indicators=IndicatorSet(ema9=10.3, ema20=10.2, vwap=10.25),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=12.0, rvol=2.5),
    )
    positive_map = {
        "GAP_GO": replace(base, candles=_candles([(10, 10.1, 9.95, 10.0, 900), (10.0, 10.4, 9.98, 10.35, 1000), (10.35, 10.7, 10.3, 10.65, 1500), (10.65, 10.85, 10.6, 10.8, 1700)])),
        "ORB": replace(base, session_context=SessionContext.REGULAR, candles=_candles([(10, 10.1, 9.9, 10.0, 1000), (10.0, 10.2, 9.95, 10.1, 1000), (10.1, 10.25, 10.0, 10.2, 1000), (10.2, 10.3, 10.1, 10.25, 1000), (10.25, 10.35, 10.2, 10.3, 1000), (10.3, 10.6, 10.28, 10.58, 1400)])),
        "FIRST_PULLBACK": replace(base, candles=_candles([(10, 10.3, 9.95, 10.25, 1000), (10.25, 10.6, 10.2, 10.55, 1200), (10.55, 10.9, 10.5, 10.85, 1500), (10.85, 10.86, 10.72, 10.75, 900), (10.75, 10.78, 10.68, 10.7, 850), (10.72, 10.95, 10.71, 10.92, 1300)])),
        "MICRO_PULLBACK": replace(base, candles=_candles([(10, 10.2, 9.95, 10.15, 900), (10.15, 10.35, 10.1, 10.3, 1000), (10.3, 10.32, 10.2, 10.24, 800), (10.24, 10.25, 10.16, 10.18, 780), (10.18, 10.2, 10.1, 10.12, 760), (10.15, 10.42, 10.14, 10.4, 1200)]), indicators=IndicatorSet(ema9=10.2, ema20=10.1, vwap=10.18)),
        "BULL_FLAG": replace(base, candles=_candles([(10, 10.4, 9.98, 10.35, 1000), (10.35, 10.8, 10.3, 10.75, 1300), (10.75, 11.0, 10.72, 10.95, 1500), (10.95, 10.98, 10.82, 10.9, 800), (10.9, 10.94, 10.8, 10.86, 780), (10.86, 10.9, 10.79, 10.84, 760), (10.84, 10.92, 10.8, 10.88, 770), (10.9, 11.05, 10.88, 11.02, 1400)]), indicators=IndicatorSet(ema9=10.9, ema20=10.8, vwap=10.85)),
        "KEY_LEVEL_BREAK": replace(base, candles=_candles([(10.2, 10.25, 10.1, 10.18, 900), (10.18, 10.55, 10.16, 10.5, 1200)])),
    }
    return positive_map.get(setup_id, base)


def test_all_setups_produce_actionable_fields() -> None:
    failures: list[str] = []
    for setup_id, spec in CANONICAL_SETUP_REGISTRY.items():
        if spec.status != SetupImplementationStatus.TRADE_READY:
            continue
        result = spec.pattern_cls().evaluate(_inputs(setup_id))
        if result.detected and not result.non_entry_signal:
            if not result.trigger_type:
                failures.append(f"{setup_id}:missing_trigger_type")
            if result.trigger_level is None:
                failures.append(f"{setup_id}:missing_trigger_level")
            if result.stop_level is None:
                failures.append(f"{setup_id}:missing_stop_level")
    assert not failures, f"Detected setups missing actionable fields: {failures}"
