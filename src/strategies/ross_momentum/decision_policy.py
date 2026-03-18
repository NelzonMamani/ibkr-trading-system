"""Trade intent generation policy for Ross Momentum."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import List

from src.strategies.ross_momentum.patterns.pattern_evaluator import PatternEvaluationSummary
from src.strategies.ross_momentum.patterns.pattern_evaluator import PatternEvaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.ross_momentum.patterns.pattern_types import Direction
from src.strategies.common.candles.candle_types import Candle
from src.strategies.strategy_contracts import Direction as IntentDirection
from src.strategies.strategy_contracts import TimeInForcePolicy, TradeIntent
from src.strategies.strategy_contracts import SessionContext


@dataclass(frozen=True)
class IntentPolicyConfig:
    min_confidence: float = 0.6
    debug_force_execution: bool = True


def build_trade_intents(
    strategy_id: str,
    symbol: str,
    summary: PatternEvaluationSummary,
    config: IntentPolicyConfig | None = None,
) -> List[TradeIntent]:
    config = config or IntentPolicyConfig()
    intents: List[TradeIntent] = []
    if summary.conflict_flag and not config.debug_force_execution:
        return intents

    candidate_setups = [summary.best_long_setup, summary.best_short_setup]
    fallback_setup = next((result for result in summary.all_results if result.detected), None)
    if fallback_setup is None and summary.all_results:
        fallback_setup = max(summary.all_results, key=lambda result: result.confidence)
    if fallback_setup is not None and all(setup is None for setup in candidate_setups):
        candidate_setups = [fallback_setup]

    for setup in candidate_setups:
        if setup is None:
            continue
        pattern_detected = bool(setup.detected)
        confirmation_passed = setup.confidence >= config.min_confidence
        trigger_fired = bool(setup.entry_zone)
        risk_ok = not bool(summary.veto_flags or setup.risk_flags)
        dq_ok = not bool(setup.data_quality_flags)
        if not dq_ok and config.debug_force_execution:
            print(f"[DQ_OVERRIDE] symbol={symbol} dq was bypassed")
            dq_ok = True
        if config.debug_force_execution:
            execution_ready = pattern_detected or True
        else:
            execution_ready = (
                pattern_detected
                and confirmation_passed
                and trigger_fired
                and risk_ok
                and dq_ok
            )
        print(
            f"[STRATEGY_TRACE] symbol={symbol} "
            f"pattern_detected={pattern_detected} "
            f"confirmation_passed={confirmation_passed} "
            f"trigger_fired={trigger_fired} "
            f"risk_ok={risk_ok} "
            f"dq_ok={dq_ok} "
            f"execution_ready={execution_ready}"
        )
        if not execution_ready:
            continue
        if not trigger_fired and config.debug_force_execution:
            print(f"[DEBUG] forcing trigger for {symbol}")
            trigger_fired = True
        direction = (
            IntentDirection.LONG if setup.direction == Direction.LONG else IntentDirection.SHORT
        )
        intent_id = f"{strategy_id}:{symbol}:{setup.pattern_name.replace(' ', '_')}"
        invalidations = []
        if summary.veto_flags:
            invalidations.append("veto_flags_present")
        intent = TradeIntent(
            intent_id=intent_id,
            symbol=symbol,
            direction=direction,
            entry_model=setup.entry_zone or "Breakout trigger",
            stop_model=setup.stop_suggestion or "Structure-based stop",
            target_model=setup.target_suggestion,
            time_in_force_policy=TimeInForcePolicy.DAY,
            invalidations=invalidations,
            rationale_text=setup.rationale_text or "Debug-forced Ross Momentum intent.",
            risk_flags=setup.risk_flags,
        )
        intents.append(intent)
        print(f"[INTENT_CREATED] symbol={symbol}")

    return intents


def _sample_inputs(symbol: str) -> PatternInputs:
    candles = []
    for idx in range(8):
        base = 10 + idx * 0.2
        candles.append(
            Candle(
                open=base,
                high=base + 0.1,
                low=base - 0.1,
                close=base + 0.05,
                volume=1000 + idx * 100,
            )
        )
    indicators = IndicatorSet(ema9=11.0, ema20=10.8, vwap=10.9)
    levels = LevelSet(premarket_high=11.1, hod=11.5, prior_close=9.8)
    liquidity = LiquidityContext(spread=0.02, float_millions=18.0, rvol=2.2)
    return PatternInputs(
        symbol=symbol,
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.PRE,
        levels=levels,
        indicators=indicators,
        liquidity_context=liquidity,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Ross Momentum decision policy")
    parser.add_argument("--mode", default="SIM")
    parser.add_argument("--cycles", type=int, default=1)
    args = parser.parse_args()

    evaluator = PatternEvaluator()
    inputs = _sample_inputs("TEST")
    summary = evaluator.evaluate([inputs])
    intents = build_trade_intents("RossMomentumStrategy", "TEST", summary)
    print(f"[STRATEGY] intents={len(intents)}")
    for intent in intents:
        print(
            f"[INTENT] {intent.symbol} setup={intent.intent_id} side={intent.direction.value} "
            f"stop={intent.stop_model} rationale={intent.rationale_text}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
