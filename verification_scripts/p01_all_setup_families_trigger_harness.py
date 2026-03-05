"""Deterministic trigger harness for all canonical P01 setup families."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import datetime, timezone
from src.setup_engine.registry import CANONICAL_SETUP_REGISTRY, SetupImplementationStatus
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.ross_momentum.patterns.pattern_evaluator import PatternEvaluator
from src.strategies.ross_momentum.strategy import RossMomentumStrategy
from src.strategies.ross_momentum.decision_policy import IntentPolicyConfig
from src.strategies.strategy_contracts import MarketContext, ScannerContext, SessionContext, StrategyInput


def _c(o: float, h: float, l: float, cl: float, v: float = 1000.0) -> Candle:
    return Candle(open=o, high=h, low=l, close=cl, volume=v)


def _base_inputs(symbol: str = "P01") -> PatternInputs:
    candles = [_c(10.0 + i * 0.1, 10.15 + i * 0.1, 9.95 + i * 0.1, 10.08 + i * 0.1, 1000 + i * 100) for i in range(12)]
    return PatternInputs(
        symbol=symbol,
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(premarket_high=10.8, prior_close=10.0, hod=11.0, key_levels={"k1": 10.9}),
        indicators=IndicatorSet(ema9=11.0, ema20=10.9, vwap=10.95),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=20.0, rvol=2.0),
    )


def _inputs_for_setup(setup_id: str) -> PatternInputs:
    b = _base_inputs(symbol=f"{setup_id[:4]}T")
    if setup_id in {"GAP_GO", "GAP_CONTINUATION"}:
        return PatternInputs(**{**b.__dict__, "candles": [_c(10.6, 10.8, 10.5, 10.7), _c(10.7, 10.9, 10.6, 10.8), _c(10.8, 11.2, 10.75, 11.1, 2400)]})
    if setup_id == "ORB":
        candles = [_c(10.0, 10.1, 9.95, 10.02) for _ in range(5)] + [_c(10.03, 10.5, 10.0, 10.45, 2500)]
        return PatternInputs(**{**b.__dict__, "candles": candles})
    if setup_id == "FIRST_PULLBACK":
        candles = [_c(10.0, 10.3, 9.95, 10.25), _c(10.25, 10.55, 10.2, 10.5), _c(10.5, 10.85, 10.45, 10.8), _c(10.8, 10.82, 10.7, 10.74), _c(10.74, 10.76, 10.66, 10.69), _c(10.7, 10.9, 10.68, 10.88)]
        return PatternInputs(**{**b.__dict__, "candles": candles})
    if setup_id == "MICRO_PULLBACK":
        candles = [_c(10.9, 11.0, 10.85, 10.96), _c(10.96, 11.02, 10.92, 10.95), _c(10.95, 10.99, 10.9, 10.93), _c(10.93, 10.97, 10.88, 10.91), _c(10.92, 11.15, 10.91, 11.1, 2400)]
        return PatternInputs(**{**b.__dict__, "candles": candles, "indicators": IndicatorSet(ema9=10.9, ema20=10.8, vwap=10.85)})
    if setup_id == "BULL_FLAG":
        candles = [_c(10.0, 10.4, 9.98, 10.35), _c(10.35, 10.75, 10.3, 10.7), _c(10.7, 11.0, 10.65, 10.95), _c(10.95, 11.0, 10.85, 10.9), _c(10.9, 10.98, 10.84, 10.88), _c(10.88, 10.97, 10.83, 10.86), _c(10.86, 10.96, 10.84, 10.89), _c(10.89, 11.02, 10.87, 10.98, 2500)]
        return PatternInputs(**{**b.__dict__, "candles": candles, "indicators": IndicatorSet(ema20=10.7, ema9=10.8, vwap=10.75)})
    if setup_id == "KEY_LEVEL_BREAK":
        return PatternInputs(**{**b.__dict__, "candles": [_c(10.8, 10.95, 10.75, 10.92), _c(10.92, 11.05, 10.9, 11.01)], "levels": LevelSet(premarket_high=10.95, hod=11.1, key_levels={"k1": 10.97})})
    if setup_id == "ABCD":
        candles = [_c(10.0, 10.2, 9.9, 10.1), _c(10.1, 10.3, 10.0, 10.2), _c(10.2, 10.35, 10.1, 10.3), _c(10.3, 10.8, 10.25, 10.75), _c(10.75, 10.78, 10.3, 10.4), _c(10.4, 10.5, 10.2, 10.3), _c(10.3, 10.95, 10.28, 10.85), _c(10.85, 11.05, 10.82, 11.0)]
        return PatternInputs(**{**b.__dict__, "candles": candles})
    if setup_id == "CUP_HANDLE":
        candles = [_c(11.0, 11.1, 10.95, 11.05), _c(11.05, 11.08, 10.98, 11.0), _c(11.0, 11.07, 10.96, 10.99), _c(10.99, 11.06, 10.95, 11.0), _c(10.95, 10.98, 10.7, 10.78), _c(10.78, 10.86, 10.72, 10.82), _c(10.82, 10.94, 10.8, 10.9), _c(10.9, 11.0, 10.88, 10.97), _c(10.97, 11.05, 10.95, 11.01), _c(11.01, 11.04, 10.97, 11.0), _c(10.99, 11.0, 10.93, 10.97), _c(10.98, 11.15, 10.97, 11.12)]
        return PatternInputs(**{**b.__dict__, "candles": candles})
    if setup_id == "MOMENTUM_RECLAIM":
        candles = [_c(10.9, 10.95, 10.82, 10.84), _c(10.84, 10.89, 10.78, 10.8), _c(10.8, 10.87, 10.76, 10.82), _c(10.82, 11.05, 10.8, 11.0)]
        return PatternInputs(**{**b.__dict__, "candles": candles, "indicators": IndicatorSet(ema9=10.9, vwap=10.85, ema20=10.8)})
    if setup_id == "PREMARKET_HIGH_BREAK":
        return PatternInputs(**{**b.__dict__, "candles": [_c(10.7, 10.85, 10.68, 10.82), _c(10.82, 11.1, 10.8, 11.05, 2500)]})
    if setup_id == "HALT_RESUME":
        return b
    if setup_id == "PARABOLIC_EXHAUSTION":
        candles = [_c(10.0, 10.2, 9.98, 10.1), _c(10.1, 10.35, 10.05, 10.28), _c(10.28, 10.6, 10.25, 10.52), _c(10.52, 10.95, 10.5, 10.9), _c(10.9, 11.45, 10.88, 11.35), _c(11.3, 11.8, 11.0, 11.15, 5000)]
        return PatternInputs(**{**b.__dict__, "candles": candles})
    if setup_id == "GAP_FILL":
        candles = [_c(10.6, 10.65, 10.45, 10.5), _c(10.5, 10.55, 10.35, 10.4), _c(10.4, 10.45, 10.2, 10.3), _c(10.3, 10.35, 9.95, 10.05), _c(10.05, 10.5, 10.0, 10.48)]
        return PatternInputs(**{**b.__dict__, "candles": candles, "levels": LevelSet(prior_close=10.0)})
    if setup_id == "OPENING_DRIVE":
        return PatternInputs(**{**b.__dict__, "candles": [_c(10.0, 10.2, 9.98, 10.1), _c(10.1, 10.3, 10.05, 10.22), _c(10.22, 10.35, 10.2, 10.3), _c(10.3, 10.42, 10.28, 10.38), _c(10.38, 10.55, 10.36, 10.5)]})
    if setup_id == "CONSOLIDATION_BREAKOUT":
        candles = [_c(10.00, 10.02, 9.99, 10.01), _c(10.01, 10.03, 10.00, 10.02), _c(10.02, 10.03, 10.00, 10.01), _c(10.01, 10.02, 9.99, 10.00), _c(10.00, 10.02, 9.99, 10.01), _c(10.01, 10.03, 10.00, 10.02), _c(10.02, 10.03, 10.00, 10.01), _c(10.01, 10.2, 10.0, 10.12, 2400)]
        return PatternInputs(**{**b.__dict__, "candles": candles})
    if setup_id in {"FLAT_TOP_BREAKOUT", "ASCENDING_TRIANGLE", "PENNANT", "RANGE_BREAK", "HOD_BREAK", "EMA_PULLBACK", "VWAP_PULLBACK", "THREE_BAR_PULLBACK", "TREND_CONTINUATION_STAIR_STEP", "SECOND_PULLBACK"}:
        candles = [_c(10.0, 10.1, 9.95, 10.02), _c(10.02, 10.12, 10.0, 10.05), _c(10.05, 10.15, 10.02, 10.08), _c(10.08, 10.18, 10.05, 10.1), _c(10.1, 10.22, 10.08, 10.2), _c(10.2, 10.35, 10.18, 10.3), _c(10.3, 10.45, 10.28, 10.4), _c(10.4, 10.55, 10.35, 10.5)]
        return PatternInputs(**{**b.__dict__, "candles": candles})
    if setup_id == "OPENING_FAKEOUT":
        candles = [_c(10.0, 10.1, 9.95, 10.02), _c(10.02, 10.08, 9.97, 10.0), _c(10.0, 10.05, 9.94, 9.98), _c(9.98, 10.06, 9.95, 10.01), _c(10.01, 10.09, 9.99, 10.03), _c(10.02, 10.4, 9.96, 10.01)]
        return PatternInputs(**{**b.__dict__, "candles": candles})
    if setup_id == "FAILED_ORB_FAKEOUT":
        candles = [_c(10.0, 10.1, 9.95, 10.02), _c(10.02, 10.08, 9.97, 10.0), _c(10.0, 10.05, 9.94, 9.98), _c(9.98, 10.06, 9.95, 10.01), _c(10.01, 10.09, 9.99, 10.03), _c(10.03, 10.35, 10.0, 10.05), _c(10.05, 10.08, 9.9, 9.97)]
        return PatternInputs(**{**b.__dict__, "candles": candles})
    raise KeyError(f"Unhandled setup_id: {setup_id}")


class _SinglePatternRegistry:
    def __init__(self, pattern) -> None:
        self.pattern = pattern

    @property
    def patterns(self):
        return [self.pattern]

    def run(self, inputs: PatternInputs):
        return [self.pattern.evaluate(inputs)]


def _strategy_intent_count(inputs: PatternInputs, pattern) -> int:
    strategy = RossMomentumStrategy(policy_config=IntentPolicyConfig(min_confidence=0.0))
    strategy._evaluator = PatternEvaluator(registry=_SinglePatternRegistry(pattern=pattern))
    decision = strategy.evaluate(
        symbol=inputs.symbol,
        inputs=StrategyInput(
            symbol=inputs.symbol,
            session_context=inputs.session_context,
            scanner_context=ScannerContext(score=1.0, rank=1),
            market_context=MarketContext(price=inputs.candles[-1].close, spread=inputs.liquidity_context.spread, volume=inputs.candles[-1].volume, rvol=inputs.liquidity_context.rvol or 0.0),
            pattern_inputs=[inputs],
        ),
    )
    return len(decision.intents)


def main() -> int:
    out_path = Path("AUDIT_EVIDENCE/p01_setup_family_sprint/all_families_trigger_harness.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict[str, object]] = {}
    overall_pass = True
    try:
        for setup_id, spec in CANONICAL_SETUP_REGISTRY.items():
            pattern = spec.pattern_cls()
            inputs = _inputs_for_setup(setup_id)
            outcome = pattern.evaluate(inputs)
            intents_emitted = _strategy_intent_count(inputs, pattern) if spec.status == SetupImplementationStatus.TRADE_READY else 0
            reason = outcome.rejection_reason or outcome.rationale_text
            if spec.status == SetupImplementationStatus.DISABLED:
                assert not outcome.detected, f"{setup_id} is DISABLED but detected=True"
                reason = f"skipped_disabled: {spec.reason}"
            else:
                assert outcome.detected, f"{setup_id} failed deterministic trigger: {reason}"
                assert intents_emitted >= 1, f"{setup_id} expected >=1 intent, got {intents_emitted}"
            results[setup_id] = {
                "status": spec.status.value,
                "detected": outcome.detected,
                "intents_emitted": intents_emitted,
                "reason": reason,
                "pattern_cls": spec.pattern_cls.__name__,
            }
    except Exception as exc:
        overall_pass = False
        error_message = str(exc)
    else:
        error_message = ""

    evidence = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "setup_ids": sorted(CANONICAL_SETUP_REGISTRY.keys()),
        "results": results,
        "pass": overall_pass,
    }
    if error_message:
        evidence["error"] = error_message
    out_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    if not overall_pass:
        raise AssertionError(error_message)

    print("PASS: p01_all_setup_families_trigger_harness")
    print(f"evidence={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
