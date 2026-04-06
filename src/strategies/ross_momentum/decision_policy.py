"""Trade intent generation policy for Ross Momentum."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import List

from src.scanner.session_pct_change import normalize_session_label

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

from .hierarchy_policy import select_dominant_setup

ALLOWED_SESSIONS = {
    "PRE",
    "RTH_OPEN",
    "RTH_MID",
    "RTH_LATE",
}


@dataclass(frozen=True)
class IntentPolicyConfig:
    min_confidence: float = 0.6
    debug_force_execution: bool = False
    validation_session_override: bool | None = None


def _env_flag_enabled(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def build_trade_intents(
    strategy_id: str,
    symbol: str,
    summary: PatternEvaluationSummary,
    config: IntentPolicyConfig | None = None,
    system_health_degraded: bool = False,
    trigger_ready_now: bool | None = None,
    session: str | None = None,
) -> List[TradeIntent]:
    _ = system_health_degraded
    config = config or IntentPolicyConfig()
    validation_session_override_enabled = (
        bool(config.validation_session_override)
        if config.validation_session_override is not None
        else _env_flag_enabled("VALIDATION_SESSION_OVERRIDE", default=False)
    )
    run_mode = str(
        os.getenv("RUN_MODE_EFFECTIVE")
        or os.getenv("RUN_MODE")
        or "UNKNOWN"
    ).upper()
    print(
        "[ROSS][INPUT] "
        f"symbol={symbol} strategy={strategy_id} setup_candidates={len(summary.all_results)} "
        f"conflict_flag={str(bool(summary.conflict_flag)).lower()} trigger_ready_override={trigger_ready_now}"
    )
    intents: List[TradeIntent] = []
    if summary.conflict_flag and not config.debug_force_execution:
        print(f"[ROSS][BLOCKER] symbol={symbol} blocker=NO_SETUP_DETECTED reason=CONFLICT_FLAG")
        return intents

    session_raw = session if session is not None else "RTH_OPEN"
    session = normalize_session_label(session_raw) or "RTH_OPEN"
    session_is_invalid = session not in ALLOWED_SESSIONS
    if session_is_invalid:
        if validation_session_override_enabled:
            print(
                "[ROSS][SESSION_OVERRIDE] "
                f"symbol={symbol} session={session} mode={run_mode} reason=VALIDATION_MODE override=ENABLED"
            )
        else:
            print(f"[ROSS][BLOCKER] symbol={symbol} blocker=SESSION_INVALID reason={session}")
            return intents
    effective_session = "PRE" if (session_is_invalid and validation_session_override_enabled) else session

    detected_setups = [
        setup for setup in summary.all_results
        if setup is not None and bool(getattr(setup, "detected", False))
    ]
    selection_session = (
        effective_session
        if session_is_invalid and validation_session_override_enabled
        else session
    )
    best_setup = select_dominant_setup(selection_session, detected_setups)
    print(
        "[ROSS][DEBUG][SETUP_SELECTION] "
        f"symbol={symbol} "
        f"original_session={session} "
        f"selection_session={selection_session} "
        f"override_session={effective_session} "
        f"selected={getattr(best_setup, 'pattern_name', None)}"
    )
    if best_setup is None:
        print(
            "[ROSS][SETUP_RESULT] "
            f"symbol={symbol} setup_families=[] detected=['NONE']"
        )
        print(f"[ROSS][INTENT_RESULT] symbol={symbol} outcome=NOT_CREATED reason=NO_TRIGGER_OR_SETUP")
        print(f"[ROSS][BLOCKER] symbol={symbol} blocker=NO_SETUP_DETECTED reason=NO_TRIGGER_OR_SETUP")
        return intents

    print(
        "[ROSS][HIERARCHY] "
        f"symbol={symbol} session={session} "
        f"selected={best_setup.pattern_name} "
        f"confidence={getattr(best_setup, 'confidence', None)}"
    )

    candidate_setups = [best_setup]
    guaranteed_intent_required = False
    detected_names = [setup.pattern_name for setup in candidate_setups if setup is not None and bool(setup.detected)]
    print(
        "[ROSS][SETUP_RESULT] "
        f"symbol={symbol} setup_families={[setup.pattern_name for setup in candidate_setups if setup is not None]} "
        f"detected={detected_names or ['NONE']}"
    )
    for setup in candidate_setups:
        if setup is None:
            continue
        pattern_detected = bool(setup.detected)
        confirmation_passed = setup.confidence >= config.min_confidence
        trigger_fired = bool(trigger_ready_now) if trigger_ready_now is not None else bool(setup.entry_zone)
        if trigger_fired:
            guaranteed_intent_required = True
        # `setup.risk_flags` can contain advisory warnings that do not block final
        # risk approval; only explicit veto flags should produce a risk-stage negative.
        risk_precheck_ok = not bool(summary.veto_flags)
        dq_ok = not bool(setup.data_quality_flags)
        if not dq_ok and config.debug_force_execution:
            print(f"[DQ_OVERRIDE] symbol={symbol} dq was bypassed")
            dq_ok = True
        pre_intent_execution_ready = (
            pattern_detected
            and trigger_fired
            and risk_precheck_ok
            and dq_ok
        )
        if not trigger_fired:
            print(f"[ROSS][TRIGGER_RESULT] symbol={symbol} outcome=NOT_FIRED reason=TRIGGER_NOT_READY")
            print(
                f"[STRATEGY_TRACE] symbol={symbol} "
                f"pattern_detected={pattern_detected} "
                f"confirmation_passed={confirmation_passed} "
                f"trigger_fired={trigger_fired} "
                f"risk_precheck_ok={risk_precheck_ok} "
                f"dq_ok={dq_ok} "
                "execution_candidate_ready=false"
            )
            continue
        if not pattern_detected:
            print(f"[ROSS][TRIGGER_RESULT] symbol={symbol} outcome=FIRED reason=PATTERN_NOT_DETECTED")
            print(
                f"[STRATEGY_TRACE] symbol={symbol} "
                "pattern_detected=false "
                f"confirmation_passed={confirmation_passed} "
                "trigger_fired=true "
                f"risk_precheck_ok={risk_precheck_ok} "
                f"dq_ok={dq_ok} "
                "execution_candidate_ready=false"
            )
            continue
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
            validation_override=bool(validation_session_override_enabled and session_is_invalid),
        )
        if intent.validation_override:
            print(
                "[INTENT][OVERRIDE] "
                f"symbol={symbol} session={session} reason=SESSION_OVERRIDE"
            )
        intents.append(intent)
        execution_ready = pre_intent_execution_ready and bool(intents)
        print(
            f"[STRATEGY_TRACE] symbol={symbol} "
            f"pattern_detected={pattern_detected} "
            f"confirmation_passed={confirmation_passed} "
            f"trigger_fired={trigger_fired} "
            f"risk_precheck_ok={risk_precheck_ok} "
            f"dq_ok={dq_ok} "
            f"execution_candidate_ready={execution_ready}"
        )
        print(f"[ROSS][TRIGGER_RESULT] symbol={symbol} outcome=FIRED reason=TRIGGER_READY")
        print(
            "[INTENT][CREATE] "
            f"symbol={symbol} "
            f"entry={setup.entry_zone or 'Breakout trigger'} "
            "trigger=TRUE"
        )
        print(
            f"[INTENT_CREATED] symbol={symbol} risk_precheck_ok={risk_precheck_ok} execution_candidate_ready={execution_ready}"
        )
        print(f"[ROSS][INTENT_RESULT] symbol={symbol} outcome=CREATED reason=INTENT_CREATED")

    if guaranteed_intent_required and not intents:
        print(f"[ROSS][INTENT_RESULT] symbol={symbol} outcome=NOT_CREATED reason=TRIGGER_WITHOUT_INTENT")
        print(f"[ROSS][BLOCKER] symbol={symbol} blocker=TRIGGER_FIRED_NO_INTENT reason=TRIGGER_WITHOUT_INTENT")
        print("[CRITICAL] TRIGGER WITHOUT INTENT — PIPELINE FAILURE")
    elif not intents:
        print(f"[ROSS][INTENT_RESULT] symbol={symbol} outcome=NOT_CREATED reason=NO_TRIGGER_OR_SETUP")
        print(f"[ROSS][BLOCKER] symbol={symbol} blocker=NO_SETUP_DETECTED reason=NO_TRIGGER_OR_SETUP")

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
