# strategy.py
"""Ross Cameron Retail Confirmation Momentum strategy."""

from __future__ import annotations

from dataclasses import replace
from typing import List

from src.config.config_resolver import get_config
from src.strategies.ross_momentum.decision_policy import (
    IntentPolicyConfig,
    build_trade_intents,
)
from src.strategies.ross_momentum.patterns.pattern_evaluator import PatternEvaluator
from src.strategies.ross_momentum.patterns.pattern_types import (
    Direction as PatternDirection,
    PatternFamily,
    PatternResult,
)
from src.strategies.strategy_base import StrategyBase
from src.strategies.strategy_contracts import (
    DecisionType,
    ExecutionMode,
    StrategyDecision,
    StrategyExecutionProfile,
    StrategyFoundationComponents,
    StrategyInput,
)
from src.utils.teacher_logs import (
    log_decision,
    log_intent_summary,
    log_pattern_summary,
    log_strategy_header,
)



def _resolve_ross_pattern_cadence(phase: str) -> tuple[str | None, str | None, bool]:
    normalized = (phase or "").upper()
    mapping = {
        "RTH_OPEN": ("1m", "10s", True),
        "RTH_MID": ("1m", "10s", True),
        "RTH_LATE": ("5m", "1m", True),
        "PRE": ("1m", "10s", True),
        "AH": ("5m", "1m", False),
        "OVN": (None, None, False),
        "CLOSED": (None, None, False),
        "WEEKEND": (None, None, False),
    }
    return mapping.get(normalized, ("1m", "10s", False))


def _resolve_session_phase(inputs: StrategyInput) -> str:
    if inputs.news_context and isinstance(inputs.news_context, dict):
        phase = inputs.news_context.get("session_phase")
        if phase:
            return str(phase).upper()
    session = getattr(inputs, "session_context", None)
    if session and hasattr(session, "value"):
        value = str(session.value).upper()
        if value == "REGULAR":
            return "RTH_OPEN"
        if value == "AFTER":
            return "AH"
        return value
    return "PRE"



def _reason_code(raw_reason: str | None) -> str:
    reason = (raw_reason or "").upper()
    if "HOD" in reason and ("NOT" in reason or "FAIL" in reason or "REJECT" in reason):
        return "HOD_NOT_BROKEN"
    if "VOLUME" in reason:
        return "INSUFFICIENT_VOLUME"
    if "SPREAD" in reason:
        return "SPREAD_TOO_WIDE"
    if "RVOL" in reason or "RELATIVE VOLUME" in reason:
        return "RVOL_TOO_LOW"
    return "STRUCTURE_INVALID"


def _log_setup_eval(
    *,
    symbol: str,
    pattern_name: str,
    scanner_rvol: float | None,
    gap_pct: float | None,
    hod_pct: float | None,
    volume: float | None,
    decision: str,
    reason: str,
    phase: str,
    structure_tf: str,
    trigger_tf: str,
) -> None:
    print(
        "[ROSS][SETUP_EVAL] "
        f"symbol={symbol} "
        f"pattern={pattern_name} "
        f"scanner_rvol={scanner_rvol} "
        f"gap_pct={gap_pct} "
        f"hod_pct={hod_pct} "
        f"volume={volume} "
        f"phase={phase} "
        f"structure_tf={structure_tf} "
        f"trigger_tf={trigger_tf} "
        f"decision={decision} "
        f"reason={reason}"
    )


def _as_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_valid_fast_trigger(symbol: str, inputs: StrategyInput) -> PatternResult | None:
    """Prioritize first valid momentum break (PMH/HOD/first pullback high)."""

    price = _as_float(getattr(inputs.market_context, "price", None))
    rvol = _as_float(getattr(inputs.market_context, "rvol", None))
    pct_change = _as_float((inputs.news_context or {}).get("pct_change"))
    if pct_change is None:
        pct_change = _as_float((inputs.news_context or {}).get("gap_pct"))

    levels = getattr(inputs.market_context, "key_levels", {}) or {}
    pattern_levels = {}
    if inputs.pattern_inputs:
        first_levels = getattr(inputs.pattern_inputs[0], "levels", None)
        if first_levels is not None:
            pattern_levels = {
                "PREMARKET_HIGH": _as_float(getattr(first_levels, "premarket_high", None)),
                "HOD": _as_float(getattr(first_levels, "hod", None)),
                "PULLBACK_HIGH": _as_float((getattr(first_levels, "key_levels", {}) or {}).get("PULLBACK_HIGH")),
            }

    canonical_levels = {
        "HOD": _as_float(levels.get("HOD")) or pattern_levels.get("HOD"),
        "PREMARKET_HIGH": _as_float(levels.get("PREMARKET_HIGH")) or pattern_levels.get("PREMARKET_HIGH"),
        "PULLBACK_HIGH": _as_float(levels.get("PULLBACK_HIGH")) or pattern_levels.get("PULLBACK_HIGH"),
    }
    trigger_specs = (
        ("HOD", "HOD_BREAK_FAST", "XL_HOD_BREAK_FAST"),
        ("PREMARKET_HIGH", "PMH_BREAK_FAST", "XL_PREMARKET_HIGH_BREAK_FAST"),
        ("PULLBACK_HIGH", "PULLBACK_BREAK_FAST", "XL_FIRST_PULLBACK_BREAK_FAST"),
    )
    rvol_ok = (rvol or 0.0) >= 2.0

    if (
        pct_change is not None
        and pct_change >= 10.0
        and rvol_ok
        and price is not None
        and canonical_levels.get("HOD") is not None
        and price > float(canonical_levels["HOD"])
    ):
        hod_level = float(canonical_levels["HOD"])
        print(
            "[ROSS][TRIGGER_OVERRIDE] "
            "reason=HIGH_MOMENTUM_BREAK "
            f"symbol={symbol} level={hod_level} price={price} rvol={rvol} pct_change={pct_change}"
        )
        print(
            "[ROSS][TRIGGER] "
            f"symbol={symbol} trigger_type=HOD_BREAK_FAST level={hod_level} price={price} "
            f"rvol={rvol} pct_change={pct_change}"
        )
        return PatternResult(
            setup_id="XL_HOD_BREAK_FAST_OVERRIDE",
            pattern_name="HOD_BREAK_FAST",
            pattern_family=PatternFamily.BREAKOUT,
            detected=True,
            direction=PatternDirection.LONG,
            confidence=0.99,
            setup_quality_tags=["FAST_TRIGGER", "OVERRIDE", "K_VOLUME_CONFIRM"],
            tags=["HIGH_MOMENTUM_BREAK", "K_BREAK_AND_HOLD_CONFIRM_OPTIONAL"],
            entry_zone=f"Break above intraday high {hod_level:.4f}",
            stop_suggestion=f"Below intraday high {hod_level:.4f}",
            rationale_text="High momentum override activated despite incomplete pattern stack.",
        )

    for level_key, trigger_type, setup_id in trigger_specs:
        level = canonical_levels.get(level_key)
        if level is None or price is None:
            print(
                "[ROSS][TRIGGER_SKIP] "
                f"symbol={symbol} trigger_type={trigger_type} reason=MISSING_LEVEL_OR_PRICE"
            )
            continue
        if price <= level:
            print(
                "[ROSS][TRIGGER_SKIP] "
                f"symbol={symbol} trigger_type={trigger_type} reason=PRICE_NOT_ABOVE_LEVEL "
                f"level={level} price={price}"
            )
            continue
        if not rvol_ok:
            print(
                "[ROSS][TRIGGER_SKIP] "
                f"symbol={symbol} trigger_type={trigger_type} reason=RVOL_BELOW_THRESHOLD "
                f"rvol={rvol}"
            )
            continue
        print(
            "[ROSS][TRIGGER] "
            f"symbol={symbol} trigger_type={trigger_type} level={level} price={price} "
            f"rvol={rvol} pct_change={pct_change}"
        )
        return PatternResult(
            setup_id=setup_id,
            pattern_name=trigger_type,
            pattern_family=PatternFamily.BREAKOUT,
            detected=True,
            direction=PatternDirection.LONG,
            confidence=0.96,
            setup_quality_tags=["FAST_TRIGGER", "K_VOLUME_CONFIRM"],
            tags=["K_BREAK_AND_HOLD_CONFIRM_OPTIONAL", level_key],
            entry_zone=f"Break above {level_key} {level:.4f}",
            stop_suggestion=f"Below {level_key} {level:.4f}",
            rationale_text=f"Fast-trigger activation on first valid momentum break: {trigger_type}.",
        )

    print(
        "[ROSS][TRIGGER_SKIP] "
        f"symbol={symbol} trigger_type=FAST_PATH reason=NO_FAST_TRIGGER "
        f"price={price} rvol={rvol} pct_change={pct_change}"
    )
    return None

class RossMomentumStrategy(StrategyBase):
    strategy_id = "ross_momentum"
    strategy_name = "Ross Momentum"
    version = "2.1"
    foundation_components = StrategyFoundationComponents()
    execution_profile = StrategyExecutionProfile(
        supported_modes=[
            ExecutionMode.SIM,
            ExecutionMode.PAPER,
            ExecutionMode.READ_ONLY,
            ExecutionMode.LIVE,
        ]
    )

    def __init__(self, policy_config: IntentPolicyConfig | None = None) -> None:
        self._evaluator = PatternEvaluator()
        self._policy_config = policy_config or IntentPolicyConfig()

    def evaluate(self, symbol: str, inputs: StrategyInput) -> StrategyDecision:
        log_strategy_header(self.strategy_name, symbol)

        mode_value = getattr(inputs, "execution_mode", None) or get_config("RUN_MODE_EFFECTIVE")
        try:
            execution_mode = mode_value if isinstance(mode_value, ExecutionMode) else ExecutionMode(str(mode_value))
        except ValueError:
            execution_mode = None
        if execution_mode == ExecutionMode.READ_ONLY:
            print(f"[ROSS][BLOCK] symbol={symbol} reason=READ_ONLY_MODE")
            decision = StrategyDecision(
                symbol=symbol,
                strategy_id=self.strategy_id,
                decision_type=DecisionType.BLOCK,
                confidence=0.0,
                rationale_text="Execution blocked in READ_ONLY mode",
                risk_flags=["READ_ONLY_MODE"],
                intents=[],
            )
            log_decision(decision)
            return decision

        if not inputs.pattern_inputs:
            decision = StrategyDecision(
                symbol=symbol,
                strategy_id=self.strategy_id,
                decision_type=DecisionType.NO_ACTION,
                confidence=0.0,
                rationale_text="No pattern inputs provided",
                risk_flags=["missing_pattern_inputs"],
                intents=[],
            )
            log_decision(decision)
            return decision

        session_phase = _resolve_session_phase(inputs)
        session_label = str(getattr(inputs.market_context, "session_label", session_phase) or session_phase).upper()
        print(f"[ROSS][SESSION] symbol={symbol} session={session_label}")
        structure_tf, trigger_tf, pattern_supported = _resolve_ross_pattern_cadence(session_label)
        print(
            "[ROSS][CADENCE] "
            f"phase={session_phase} structure_tf={structure_tf} trigger_tf={trigger_tf}"
        )
        if not pattern_supported:
            print(
                "[ROSS][CADENCE][WARN] "
                f"phase={session_phase} pattern_support=limited execution_disabled=true"
            )
        if structure_tf is None:
            pattern_inputs = []
        else:
            pattern_inputs = [replace(item, timeframe=structure_tf) for item in inputs.pattern_inputs]
        summary = self._evaluator.evaluate(pattern_inputs)
        fast_trigger_result = _first_valid_fast_trigger(symbol, inputs)
        if fast_trigger_result is not None:
            summary.all_results.append(fast_trigger_result)
            if summary.best_long_setup is None or fast_trigger_result.confidence >= summary.best_long_setup.confidence:
                summary = replace(summary, best_long_setup=fast_trigger_result)
        log_pattern_summary(summary)

        scanner_rvol = getattr(inputs.market_context, "rvol", None)
        gap_pct = None
        hod_pct = None
        volume = getattr(inputs.market_context, "volume", None)
        if inputs.news_context:
            gap_pct = inputs.news_context.get("gap_pct")
            hod_pct = inputs.news_context.get("hod_pct")

        for result in summary.all_results:
            decision = "TRIGGER" if result.detected else "REJECT"
            reason = "SETUP_DETECTED" if result.detected else _reason_code(result.rejection_reason)
            _log_setup_eval(
                symbol=symbol,
                pattern_name=result.pattern_name,
                scanner_rvol=scanner_rvol,
                gap_pct=gap_pct,
                hod_pct=hod_pct,
                volume=volume,
                decision=decision,
                reason=reason,
                phase=session_phase,
                structure_tf=structure_tf,
                trigger_tf=trigger_tf,
            )
            if result.detected:
                print(
                    "[ROSS][SETUP_TRIGGER] "
                    f"symbol={symbol} pattern={result.pattern_name} reason={reason}"
                )
            else:
                print(
                    "[ROSS][SETUP_REJECT] "
                    f"symbol={symbol} pattern={result.pattern_name} reason={reason}"
                )

        intents = build_trade_intents(
            strategy_id=self.strategy_id,
            symbol=symbol,
            summary=summary,
            config=self._policy_config,
        )
        confidence = max(
            [result.confidence for result in summary.all_results if result.detected],
            default=0.0,
        )
        decision_type = (
            DecisionType.EMIT_INTENT
            if intents
            else DecisionType.WATCH
            if summary.best_long_setup or summary.best_short_setup
            else DecisionType.NO_ACTION
        )
        rationale = summary.combined_rationale_text
        decision = StrategyDecision(
            symbol=symbol,
            strategy_id=self.strategy_id,
            decision_type=decision_type,
            confidence=confidence,
            rationale_text=rationale,
            risk_flags=summary.veto_flags,
            intents=intents,
        )
        log_intent_summary(intents)
        log_decision(decision)
        return decision
