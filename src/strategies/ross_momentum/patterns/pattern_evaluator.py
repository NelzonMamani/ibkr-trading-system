"""Pattern evaluation and conflict resolution for Ross Momentum."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext

from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternResult


@dataclass(frozen=True)
class PatternEvaluationSummary:
    all_results: List[PatternResult]
    best_long_setup: Optional[PatternResult]
    best_short_setup: Optional[PatternResult]
    conflict_flag: bool
    combined_rationale_text: str
    veto_flags: List[str]


class PatternEvaluator:
    def __init__(self, registry: Optional[RossPatternRegistry] = None) -> None:
        self._registry = registry or RossPatternRegistry()

    def evaluate(self, inputs_list: List[PatternInputs]) -> PatternEvaluationSummary:
        all_results: List[PatternResult] = []
        veto_flags: List[str] = []
        for inputs in inputs_list:
            all_results.extend(self._registry.run(inputs))
            if inputs.liquidity_context.spread > 0.05:
                veto_flags.append("wide_spread")
            if inputs.data_quality_flags:
                veto_flags.append("data_quality")
            if inputs.liquidity_context.float_millions is not None:
                if inputs.liquidity_context.float_millions < 5:
                    veto_flags.append("low_float")

        best_long = self._best_setup(all_results, Direction.LONG)
        best_short = self._best_setup(all_results, Direction.SHORT)
        conflict_flag = bool(best_long and best_short)

        rationale_lines: List[str] = []
        if best_long:
            rationale_lines.append(
                f"Best long: {best_long.pattern_name} conf={best_long.confidence:.2f}"
            )
        if best_short:
            rationale_lines.append(
                f"Best short: {best_short.pattern_name} conf={best_short.confidence:.2f}"
            )
        if conflict_flag:
            rationale_lines.append("Conflict: long and short setups coexist")
        if veto_flags:
            rationale_lines.append(f"Veto flags: {', '.join(sorted(set(veto_flags)))}")
        combined = " | ".join(rationale_lines) if rationale_lines else "No setups detected"

        return PatternEvaluationSummary(
            all_results=all_results,
            best_long_setup=best_long,
            best_short_setup=best_short,
            conflict_flag=conflict_flag,
            combined_rationale_text=combined,
            veto_flags=sorted(set(veto_flags)),
        )

    @staticmethod
    def _best_setup(
        results: List[PatternResult], direction: Direction
    ) -> Optional[PatternResult]:
        candidates = [
            result
            for result in results
            if result.detected and result.direction == direction
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda result: result.confidence)


def _sample_inputs(symbol: str) -> PatternInputs:
    candles = [
        Candle(open=10.0, high=10.3, low=9.9, close=10.2, volume=1200),
        Candle(open=10.2, high=10.6, low=10.1, close=10.5, volume=1400),
        Candle(open=10.5, high=10.8, low=10.4, close=10.7, volume=1600),
        Candle(open=10.7, high=10.75, low=10.6, close=10.65, volume=900),
        Candle(open=10.65, high=10.9, low=10.6, close=10.85, volume=1800),
    ]
    indicators = IndicatorSet(ema9=10.4, ema20=10.2, vwap=10.35)
    levels = LevelSet(
        premarket_high=10.6,
        hod=10.9,
        prior_close=9.8,
        key_levels={"orb_high": 10.6},
    )
    liquidity = LiquidityContext(spread=0.02, float_millions=12.5, rvol=2.2)
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

    parser = argparse.ArgumentParser(description="Ross Momentum pattern evaluator")
    parser.add_argument("--symbol", default="TEST")
    parser.add_argument("--mode", default="SIM")
    args = parser.parse_args()

    print(f"[PATTERN_EVAL] mode={args.mode} symbol={args.symbol}")
    evaluator = PatternEvaluator()
    inputs_list = [_sample_inputs(args.symbol)]
    summary = evaluator.evaluate(inputs_list)

    print("[PATTERN_EVAL] Summary:")
    if summary.best_long_setup:
        best = summary.best_long_setup
        print(
            f"  Best setup: {best.pattern_name} conf={best.confidence:.2f} "
            f"rationale={best.rationale_text.splitlines()[0]}"
        )
    else:
        print("  Best setup: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
