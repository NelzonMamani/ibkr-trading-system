"""Pattern evaluation and conflict resolution for Ross Momentum."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import List, Optional

from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternResult
from src.strategies.common.candles.candle_types import Candle
from src.strategies.strategy_contracts import SessionContext


@dataclass(frozen=True)
class PatternEvaluationSummary:
    all_results: List[PatternResult]
    best_long_setup: Optional[PatternResult]
    best_short_setup: Optional[PatternResult]
    conflict_flag: bool
    combined_rationale_text: str
    veto_flags: List[str]




def _apply_setup_exclusivity(results: List[PatternResult]) -> List[PatternResult]:
    detected = {str(r.setup_family_id or r.setup_id).upper() for r in results if r.detected}
    suppressed: set[str] = set()
    if "GAP_GO" in detected:
        suppressed.update({"MICRO_PULLBACK", "BULL_FLAG", "RANGE", "EMA_PULLBACK"})
    if "FIRST_PULLBACK" in detected:
        suppressed.update({"MICRO_PULLBACK", "BULL_FLAG"})
    if "ABCD" in detected:
        suppressed.update({"BULL_FLAG", "RANGE"})

    normalized: list[PatternResult] = []
    for result in results:
        setup_key = str(result.setup_family_id or result.setup_id).upper()
        if not result.detected or setup_key not in suppressed:
            normalized.append(result)
            continue
        normalized.append(
            PatternResult(
                setup_id=result.setup_id,
                pattern_name=result.pattern_name,
                pattern_family=result.pattern_family,
                detected=False,
                direction=result.direction,
                confidence=0.0,
                setup_quality_tags=list(result.setup_quality_tags),
                setup_family_id=result.setup_family_id,
                tags=list(result.tags),
                entry_zone=result.entry_zone,
                stop_suggestion=result.stop_suggestion,
                target_suggestion=result.target_suggestion,
                rationale_text=f"Suppressed by setup exclusivity: {setup_key}",
                risk_flags=list(result.risk_flags),
                data_quality_flags=list(result.data_quality_flags),
                rejection_reason="suppressed_by_setup_exclusivity",
                session_valid=result.session_valid,
                trigger_type=result.trigger_type,
                trigger_level=result.trigger_level,
                stop_level=result.stop_level,
                invalidation_level=result.invalidation_level,
            )
        )
    return normalized


class PatternEvaluator:
    def __init__(self, registry: Optional[RossPatternRegistry] = None) -> None:
        self._registry = registry or RossPatternRegistry()

    def evaluate(self, inputs_list: List[PatternInputs]) -> PatternEvaluationSummary:
        all_results: List[PatternResult] = []
        veto_flags: List[str] = []
        for inputs in inputs_list:
            symbol = inputs.symbol
            print(f"[ROSS][EVAL] symbol={symbol} stage=START")
            print(f"[ROSS][PATTERN][START] symbol={symbol}")
            try:
                symbol_results = self._registry.run(
                    inputs,
                    trace_context={
                        "strategy_key": "ross_momentum",
                        "session_label": inputs.session_context.value,
                        "input_summary": {
                            "symbol": inputs.symbol,
                            "timeframe": inputs.timeframe,
                        },
                    },
                )
            except TypeError:
                # Backward compatibility for test mocks
                symbol_results = self._registry.run(inputs)
            detected_pattern = next((result for result in symbol_results if result.detected), None)
            print(
                f"[ROSS][PATTERN] symbol={symbol} detected={bool(detected_pattern)} "
                f"pattern={detected_pattern.pattern_name if detected_pattern else None}"
            )
            confirmations_passed = bool(detected_pattern)
            print(f"[ROSS][CONFIRM] symbol={symbol} passed={confirmations_passed}")
            trigger_ready = bool(
                detected_pattern
                and detected_pattern.trigger_level is not None
                and detected_pattern.stop_suggestion is not None
            )
            print(f"[ROSS][TRIGGER_CHECK] symbol={symbol} ready={trigger_ready}")
            force_execution_window = str(os.getenv("FORCE_EXECUTION_WINDOW", "")).strip().lower() in {"1", "true", "yes", "on"}
            if detected_pattern and force_execution_window and (not confirmations_passed or not trigger_ready):
                trigger = {
                    "type": "FORCED_MARKET_ENTRY",
                    "reason": "DIAGNOSTIC_FORCE_TRIGGER",
                    "confidence": 0.1,
                }
                _ = trigger
                print(f"[ROSS][FORCED_TRIGGER] symbol={symbol} reason=NO_TRIGGER_PIPELINE")
            for result in symbol_results:
                if result.detected:
                    print(
                        "[ROSS][PATTERN][PASS] "
                        f"symbol={inputs.symbol} pattern={result.pattern_name}"
                    )
                else:
                    reason_code = result.rejection_reason or "unspecified_rejection"
                    print(
                        "[ROSS][PATTERN][FAIL] "
                        f"symbol={inputs.symbol} pattern={result.pattern_name} reason={reason_code}"
                    )
            all_results.extend(symbol_results)
            spread = inputs.liquidity_context.spread
            if spread is not None and spread > 0.05:
                veto_flags.append("wide_spread")
            if inputs.data_quality_flags:
                veto_flags.append("data_quality")
            if inputs.liquidity_context.float_millions is not None:
                if inputs.liquidity_context.float_millions < 5:
                    veto_flags.append("low_float")

        all_results = _apply_setup_exclusivity(all_results)

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
    candles = []
    for idx in range(10):
        base = 10 + idx * 0.2
        candles.append(
            Candle(
                open=base,
                high=base + 0.1,
                low=base - 0.1,
                close=base + (0.05 if idx % 2 == 0 else -0.03),
                volume=1000 + idx * 100,
            )
        )
    indicators = IndicatorSet(ema9=11.2, ema20=11.0, vwap=11.1)
    levels = LevelSet(premarket_high=11.3, hod=11.6, prior_close=10.0)
    liquidity = LiquidityContext(spread=0.02, float_millions=12.0, rvol=2.0)
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
    parser = argparse.ArgumentParser(description="Ross pattern evaluator")
    parser.add_argument("--symbol", default="TEST")
    parser.add_argument("--mode", default="SIM")
    args = parser.parse_args()
    evaluator = PatternEvaluator()
    summary = evaluator.evaluate([_sample_inputs(args.symbol)])
    best = summary.best_long_setup or summary.best_short_setup
    if best:
        print(
            f"[PATTERN][SUMMARY] best={best.pattern_name} conf={best.confidence:.2f} "
            f"rationale={best.rationale_text}"
        )
    else:
        print("[PATTERN][SUMMARY] No setups detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
