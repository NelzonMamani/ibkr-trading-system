"""Trade intent generation policy for Ross Momentum."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_evaluator import (
    PatternEvaluationSummary,
    PatternEvaluator,
)
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.ross_momentum.patterns.pattern_types import Direction
from src.strategies.ross_momentum.setup_rules import allow_session_trade
from src.strategies.strategy_contracts import Direction as IntentDirection
from src.strategies.strategy_contracts import SessionContext
from src.strategies.strategy_contracts import TimeInForcePolicy, TradeIntent


@dataclass(frozen=True)
class IntentPolicyConfig:
    min_confidence: float = 0.6
    allow_after_hours: bool = False


def build_trade_intents(
    strategy_id: str,
    symbol: str,
    summary: PatternEvaluationSummary,
    session: SessionContext,
    config: IntentPolicyConfig | None = None,
) -> List[TradeIntent]:
    config = config or IntentPolicyConfig()
    intents: List[TradeIntent] = []
    if summary.conflict_flag:
        return intents

    if not allow_session_trade(session, config.allow_after_hours):
        return intents

    for setup in [summary.best_long_setup, summary.best_short_setup]:
        if setup is None:
            continue
        if setup.confidence < config.min_confidence:
            continue
        direction = (
            IntentDirection.LONG if setup.direction == Direction.LONG else IntentDirection.SHORT
        )
        setup_id = setup.setup_id or setup.pattern_name or "setup"
        intent_id = f"{strategy_id}:{symbol}:{setup_id}"
        invalidations = []
        if summary.veto_flags:
            invalidations.append("veto_flags_present")
        intents.append(
            TradeIntent(
                intent_id=intent_id,
                symbol=symbol,
                direction=direction,
                entry_model=setup.entry_zone or "Breakout trigger",
                stop_model=setup.stop_suggestion or "Structure-based stop",
                target_model=setup.target_suggestion,
                time_in_force_policy=TimeInForcePolicy.DAY,
                invalidations=invalidations,
                rationale_text=f"{setup.rationale_text} | session={session.value}",
                risk_flags=setup.risk_flags,
            )
        )

    return intents


def _sample_inputs(symbol: str) -> PatternInputs:
    candles = [
        Candle(open=10.0, high=10.2, low=9.9, close=10.15, volume=900),
        Candle(open=10.15, high=10.5, low=10.1, close=10.45, volume=1500),
        Candle(open=10.45, high=10.7, low=10.4, close=10.65, volume=1800),
        Candle(open=10.65, high=10.68, low=10.55, close=10.6, volume=800),
        Candle(open=10.6, high=10.9, low=10.55, close=10.85, volume=1900),
    ]
    indicators = IndicatorSet(ema9=10.4, ema20=10.2, vwap=10.35)
    levels = LevelSet(premarket_high=10.6, hod=10.9, prior_close=9.8)
    liquidity = LiquidityContext(spread=0.02, float_millions=14.0, rvol=2.0)
    return PatternInputs(
        symbol=symbol,
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=levels,
        indicators=indicators,
        liquidity_context=liquidity,
        data_quality_flags=[],
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Ross Momentum decision policy harness")
    parser.add_argument("--mode", default="SIM")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--symbol", default="TEST")
    args = parser.parse_args()

    print(f"[STRATEGY] mode={args.mode} cycles={args.cycles}")
    evaluator = PatternEvaluator()
    inputs = _sample_inputs(args.symbol)
    summary = evaluator.evaluate([inputs])
    intents = build_trade_intents(
        strategy_id="RossMomentum",
        symbol=args.symbol,
        summary=summary,
        session=inputs.session_context,
    )
    if intents:
        print(f"[STRATEGY] Generated intents={len(intents)}")
        for intent in intents:
            print(
                "[STRATEGY][INTENT] "
                f"symbol={intent.symbol} setup={intent.intent_id} "
                f"side={intent.direction.value} stop={intent.stop_model} "
                f"rationale={intent.rationale_text}"
            )
    else:
        print("[STRATEGY] 0 intents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
