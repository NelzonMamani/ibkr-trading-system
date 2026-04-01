from __future__ import annotations

from dataclasses import replace

from src.setup_engine.registry import CANONICAL_SETUP_REGISTRY, SetupImplementationStatus
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.strategy_contracts import SessionContext


def _candles(vals: list[tuple[float,float,float,float,int]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o,h,l,c,v in vals]


def _inputs(setup_id: str, positive: bool) -> PatternInputs:
    base = PatternInputs(
        symbol=setup_id,
        timeframe='1m',
        candles=_candles([(10,10.2,9.9,10.1,1000)]*12),
        session_context=SessionContext.PRE,
        levels=LevelSet(premarket_high=10.5, premarket_low=9.7, hod=10.9, prior_close=9.8, key_levels={'pivot':10.4}),
        indicators=IndicatorSet(ema9=10.3, ema20=10.2, vwap=10.25),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=12.0, rvol=2.5),
    )
    positive_map = {
        'GAP_GO': replace(base, candles=_candles([(10,10.1,9.95,10.0,900),(10.0,10.4,9.98,10.35,1000),(10.35,10.7,10.3,10.65,1500),(10.65,10.85,10.6,10.8,1700)])),
        'ORB': replace(
            base,
            session_context=SessionContext.REGULAR,
            candles=_candles([(10.1,10.2,10.1,10.15,1000),(10.15,10.25,10.12,10.2,1000),(10.2,10.28,10.16,10.24,1000),(10.24,10.32,10.2,10.28,1000),(10.28,10.35,10.24,10.3,1000),(10.3,10.6,10.28,10.58,1400)]),
            levels=LevelSet(premarket_high=10.5, premarket_low=10.0, hod=10.9, prior_close=9.8, key_levels={'OPENING_RANGE_HIGH':10.35,'OPENING_RANGE_LOW':10.1}),
            indicators=IndicatorSet(ema9=10.3, ema20=10.2, vwap=10.25),
            liquidity_context=LiquidityContext(spread=0.005, float_millions=12.0, rvol=2.5),
            news_context={"macd": 0.5, "session_phase": "RTH_OPEN"},
        ),
        'FIRST_PULLBACK': replace(base, candles=_candles([(10,10.3,9.95,10.25,1000),(10.25,10.6,10.2,10.55,1200),(10.55,10.9,10.5,10.85,1500),(10.85,10.86,10.72,10.75,900),(10.75,10.78,10.68,10.7,850),(10.72,10.95,10.71,10.92,1300)])),
        'MICRO_PULLBACK': replace(base, candles=_candles([(10,10.2,9.95,10.15,900),(10.15,10.35,10.1,10.3,1000),(10.3,10.32,10.2,10.24,800),(10.24,10.25,10.16,10.18,780),(10.18,10.2,10.1,10.12,760),(10.15,10.42,10.14,10.4,1200)]), indicators=IndicatorSet(ema9=10.2, ema20=10.1, vwap=10.18)),
        'BULL_FLAG': replace(base, candles=_candles([(10,10.4,9.98,10.35,1000),(10.35,10.8,10.3,10.75,1300),(10.75,11.0,10.72,10.95,1500),(10.95,10.98,10.82,10.9,800),(10.9,10.94,10.8,10.86,780),(10.86,10.9,10.79,10.84,760),(10.84,10.92,10.8,10.88,770),(10.9,11.05,10.88,11.02,1400)]), indicators=IndicatorSet(ema9=10.9, ema20=10.8, vwap=10.85)),
        'KEY_LEVEL_BREAK': replace(base, candles=_candles([(10.2,10.25,10.1,10.18,900),(10.18,10.55,10.16,10.5,1200)])),
        'ABCD': replace(base, candles=_candles([(10.2,10.30,10.10,10.20,1000),(10.1,10.25,9.90,10.15,1100),(10.2,10.50,10.15,10.40,1200),(10.5,11.00,10.40,10.90,1400),(10.8,10.80,10.50,10.60,900),(10.6,10.70,10.35,10.45,950),(10.5,10.95,10.45,10.90,1300),(10.9,11.05,10.90,11.02,1500)])),
        'CUP_HANDLE': replace(base, candles=_candles([(10.0,10.6,9.98,10.5,900),(10.5,10.62,10.4,10.55,920),(10.55,10.65,10.48,10.6,930),(10.6,10.64,10.5,10.58,940),(10.58,10.6,10.35,10.4,800),(10.4,10.45,10.25,10.3,780),(10.3,10.38,10.22,10.32,790),(10.32,10.48,10.3,10.45,820),(10.45,10.6,10.42,10.56,880),(10.56,10.62,10.5,10.6,900),(10.6,10.61,10.52,10.56,760),(10.58,10.72,10.57,10.7,1200)])),
        'MOMENTUM_RECLAIM': replace(base, candles=_candles([(10.3,10.34,10.2,10.22,900),(10.22,10.24,10.08,10.12,880),(10.12,10.18,10.05,10.08,850),(10.08,10.36,10.06,10.33,1200)]), indicators=IndicatorSet(ema9=10.2, ema20=10.1, vwap=10.18)),
        'PREMARKET_HIGH_BREAK': replace(base, candles=_candles([(10.2,10.25,10.15,10.22,900),(10.22,10.7,10.2,10.66,1300)])),
        'PARABOLIC_EXHAUSTION': replace(base, candles=_candles([(10,10.2,9.98,10.18,900),(10.18,10.45,10.16,10.4,1000),(10.4,10.78,10.38,10.7,1200),(10.7,11.2,10.68,11.05,1500),(11.05,11.8,11.0,11.65,1900),(11.65,12.4,11.5,11.75,3200)])),
        'GAP_FILL': replace(base, candles=_candles([(10.5,10.52,10.2,10.28,900),(10.28,10.3,9.78,9.9,1100),(9.9,10.0,9.76,9.88,1000),(9.88,10.18,9.86,10.12,1400),(10.12,10.35,10.1,10.3,1300)])),
        'GAP_CONTINUATION': replace(base, candles=_candles([(10,10.1,9.95,10.0,900),(10.0,10.4,9.98,10.35,1000),(10.35,10.7,10.3,10.65,1500),(10.65,10.85,10.6,10.8,1700)])),
        'OPENING_DRIVE': replace(base, candles=_candles([(10,10.1,9.98,10.05,900),(10.05,10.12,10.0,10.08,900),(10.08,10.18,10.05,10.16,910),(10.16,10.25,10.12,10.22,920),(10.22,10.35,10.2,10.32,1100)])),
        'OPENING_FAKEOUT': replace(base, session_context=SessionContext.REGULAR, candles=_candles([(10,10.1,9.95,10.02,900),(10.02,10.12,9.98,10.08,910),(10.08,10.16,10.02,10.1,920),(10.1,10.18,10.04,10.12,930),(10.12,10.2,10.06,10.15,940),(10.15,10.42,10.0,10.1,1300)])),
        'CONSOLIDATION_BREAKOUT': replace(base, candles=_candles([(10,10.4,9.98,10.3,1200),(10.3,10.42,10.28,10.36,1000),(10.36,10.38,10.31,10.35,850),(10.35,10.39,10.32,10.36,840),(10.36,10.4,10.33,10.37,830),(10.37,10.39,10.34,10.38,820),(10.38,10.4,10.35,10.39,810),(10.4,10.55,10.39,10.53,1400)])),
        'FLAT_TOP_BREAKOUT': replace(base, candles=_candles([(10,10.1,9.98,10.02,800),(10.02,10.15,10.0,10.1,820),(10.1,10.18,10.06,10.14,840),(10.14,10.19,10.1,10.16,860),(10.16,10.28,10.15,10.26,1100)])),
        'ASCENDING_TRIANGLE': replace(base, candles=_candles([(10.0,10.15,9.98,10.08,800),(10.08,10.2,10.04,10.14,820),(10.14,10.2,10.1,10.16,830),(10.16,10.22,10.12,10.18,840),(10.18,10.3,10.16,10.28,1100)])),
        'PENNANT': replace(base, candles=_candles([(10,10.45,9.98,10.38,1200),(10.38,10.4,10.25,10.32,900),(10.32,10.36,10.24,10.3,850),(10.3,10.34,10.26,10.31,840),(10.31,10.5,10.3,10.48,1300)])),
        'RANGE_BREAK': replace(base, candles=_candles([(10,10.12,9.98,10.02,800),(10.02,10.1,10.0,10.04,810),(10.04,10.11,10.01,10.05,820),(10.05,10.12,10.02,10.06,830),(10.06,10.2,10.05,10.18,1100)])),
        'HOD_BREAK': replace(base, candles=_candles([(10.0,10.1,9.98,10.02,800),(10.02,10.2,10.0,10.16,850),(10.16,10.24,10.12,10.2,860),(10.2,10.32,10.18,10.28,900),(10.28,11.02,10.26,10.96,1400)]), levels=LevelSet(premarket_high=10.5, hod=10.9, prior_close=9.8)),
        'EMA_PULLBACK': replace(base, candles=_candles([(10,10.1,9.98,10.02,800),(10.02,10.18,10.0,10.16,850),(10.16,10.2,10.08,10.1,820),(10.1,10.14,10.05,10.08,800),(10.08,10.22,10.07,10.2,1100)])),
        'VWAP_PULLBACK': replace(base, candles=_candles([(10.0,10.08,9.98,10.06,900),(10.06,10.24,10.04,10.22,1100),(10.22,10.54,10.2,10.5,1650),(10.5,10.56,10.3,10.22,900),(10.22,10.38,10.2,10.22,850),(10.22,10.58,10.21,10.52,1500)]), indicators=IndicatorSet(ema9=10.48, ema20=10.32, vwap=10.25)),
        'THREE_BAR_PULLBACK': replace(base, candles=_candles([(10,10.18,9.98,10.16,900),(10.16,10.17,10.1,10.12,820),(10.12,10.13,10.05,10.08,800),(10.08,10.09,10.02,10.04,790),(10.04,10.22,10.03,10.2,1200)])),
        'TREND_CONTINUATION_STAIR_STEP': replace(base, candles=_candles([(10,10.1,9.99,10.04,800),(10.04,10.2,10.03,10.16,850),(10.16,10.18,10.1,10.12,820),(10.12,10.25,10.1,10.22,900),(10.22,10.35,10.2,10.32,1100)])),
        'SECOND_PULLBACK': replace(base, candles=_candles([(10,10.18,9.98,10.16,900),(10.16,10.14,10.06,10.08,820),(10.08,10.24,10.07,10.2,900),(10.2,10.18,10.1,10.12,800),(10.12,10.3,10.11,10.28,1200)])),
        'FAILED_ORB_FAKEOUT': replace(base, session_context=SessionContext.REGULAR, candles=_candles([(10,10.1,9.95,10.0,900),(10.0,10.15,9.98,10.08,910),(10.08,10.2,10.02,10.12,920),(10.12,10.22,10.08,10.18,930),(10.18,10.24,10.14,10.2,940),(10.2,10.4,10.18,10.3,1100),(10.3,10.31,10.05,10.12,1300)])),
    }
    candidate = positive_map[setup_id]
    if positive:
        return candidate
    if setup_id == "ABCD":
        return replace(candidate, candles=candidate.candles[:5])
    return replace(candidate, candles=candidate.candles[:-1])


def _trade_ready_ids() -> list[str]:
    return [setup_id for setup_id, spec in CANONICAL_SETUP_REGISTRY.items() if spec.status == SetupImplementationStatus.TRADE_READY]


def test_every_trade_ready_setup_has_positive_trigger_proof() -> None:
    missing: list[str] = []
    for setup_id in _trade_ready_ids():
        pattern = CANONICAL_SETUP_REGISTRY[setup_id].pattern_cls()
        result = pattern.evaluate(_inputs(setup_id, True))
        if not result.detected:
            missing.append(f"{setup_id}:{result.rejection_reason}")
    assert not missing, f"Missing trigger proof: {missing}"


def test_every_trade_ready_setup_has_rejection_proof() -> None:
    missing: list[str] = []
    for setup_id in _trade_ready_ids():
        pattern = CANONICAL_SETUP_REGISTRY[setup_id].pattern_cls()
        result = pattern.evaluate(_inputs(setup_id, False))
        if result.detected or not result.rejection_reason:
            missing.append(f"{setup_id}:{result}")
    assert not missing, f"Missing rejection proof: {missing}"
