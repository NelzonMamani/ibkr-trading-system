"""Ross Momentum strategy with explicit profitability decision spine."""

from __future__ import annotations

from dataclasses import replace

from src.strategies.ross_momentum.decision_pipeline import (
    build_no_signal,
    evaluate_confirmations,
    summarize_cycle,
)
from src.strategies.ross_momentum.pattern_engine import PatternEngine
from src.strategies.ross_momentum.setup_engine import SetupEngine
from src.strategies.ross_momentum.trigger_engine import TriggerEngine
from src.strategies.strategy_base import StrategyBase
from src.strategies.strategy_contracts import (
    DecisionType,
    Direction,
    ExecutionMode,
    StrategyDecision,
    StrategyExecutionProfile,
    StrategyFoundationComponents,
    StrategyInput,
    TimeInForcePolicy,
    TradeIntent,
)


def _resolve_ross_pattern_cadence(phase: str) -> tuple[str | None, str | None, bool]:
    normalized = (phase or "").upper()
    mapping = {
        "RTH_OPEN": ("1m", "10s", True),
        "RTH_MID": ("3m", "30s", True),
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


class RossMomentumStrategy(StrategyBase):
    strategy_id = "ross_momentum"
    strategy_name = "Ross Momentum"
    version = "3.0"
    foundation_components = StrategyFoundationComponents()
    execution_profile = StrategyExecutionProfile(
        supported_modes=[ExecutionMode.SIM, ExecutionMode.PAPER, ExecutionMode.READ_ONLY, ExecutionMode.LIVE]
    )

    def __init__(self) -> None:
        self._setup_engine = SetupEngine()
        self._pattern_engine = PatternEngine()
        self._trigger_engine = TriggerEngine()

    def evaluate(self, symbol: str, inputs: StrategyInput) -> StrategyDecision:
        if not inputs.pattern_inputs:
            no_signal = build_no_signal(symbol, "ELIGIBILITY", "NO_PATTERN_INPUTS")
            print(f"[ROSS][NO_SIGNAL] symbol={symbol} stage={no_signal.failed_stage} reason={no_signal.reason}")
            return StrategyDecision(
                symbol=symbol,
                strategy_id=self.strategy_id,
                decision_type=DecisionType.NO_ACTION,
                confidence=0.0,
                rationale_text="No pattern inputs provided",
                risk_flags=["missing_pattern_inputs"],
                intents=[],
            )

        session_phase = _resolve_session_phase(inputs)
        structure_tf, _, _ = _resolve_ross_pattern_cadence(session_phase)
        pattern_input = inputs.pattern_inputs[0]
        if structure_tf is not None:
            pattern_input = replace(pattern_input, timeframe=structure_tf)

        print(f"[ROSS][SETUP][START] symbol={symbol} phase={session_phase}")
        setup = self._setup_engine.classify(symbol, pattern_input, inputs.market_context, inputs.news_context or {})
        print(
            f"[ROSS][SETUP][RESULT] symbol={symbol} detected={setup.detected} "
            f"family={setup.setup_family} rationale={setup.rationale} disqualifiers={setup.disqualifiers}"
        )

        pattern = self._pattern_engine.evaluate(setup, pattern_input)
        print(
            f"[ROSS][PATTERN][RESULT] symbol={symbol} detected={pattern.detected} pattern={pattern.pattern_name} "
            f"rejection={pattern.rejection_reason} pullback_high={pattern.pullback_high} pullback_low={pattern.pullback_low}"
        )

        confirmations = evaluate_confirmations(setup, pattern, inputs.market_context)
        print(
            f"[ROSS][CONFIRM][RESULT] symbol={symbol} passed={confirmations.confirmations_passed} "
            f"failed={confirmations.confirmations_failed} block_trade={confirmations.block_trade}"
        )

        current_candle = pattern_input.candles[-1]
        trigger = self._trigger_engine.evaluate(pattern, current_candle)
        print(
            f"[ROSS][TRIGGER][RESULT] symbol={symbol} trigger_name={trigger.trigger_name} triggered={trigger.triggered} "
            f"trigger_level={trigger.trigger_level} rejection={trigger.rejection_reason}"
        )

        intents: list[TradeIntent] = []
        no_signal = None
        if not setup.detected:
            no_signal = build_no_signal(symbol, "SETUP", "NO_ACTIVE_SETUP", {"setup": setup.setup_family})
        elif not pattern.detected:
            no_signal = build_no_signal(symbol, "PATTERN", pattern.rejection_reason or "PATTERN_NOT_VALID")
        elif confirmations.block_trade:
            no_signal = build_no_signal(symbol, "CONFIRMATION", ",".join(confirmations.confirmations_failed))
        elif not trigger.triggered:
            no_signal = build_no_signal(symbol, "TRIGGER", trigger.rejection_reason or "TRIGGER_NOT_FIRED")
        elif trigger.stop_anchor is None:
            no_signal = build_no_signal(symbol, "POST_TRIGGER_ACTIONABILITY", "MISSING_STOP_ANCHOR")
        else:
            intent = TradeIntent(
                intent_id=f"{self.strategy_id}:{symbol}:{trigger.trigger_name}",
                symbol=symbol,
                direction=Direction.LONG,
                entry_model=f"Break above {trigger.trigger_level}",
                stop_model=f"Stop below pullback low {trigger.stop_anchor}",
                target_model=None,
                time_in_force_policy=TimeInForcePolicy.DAY,
                invalidations=[f"loss_of_{setup.setup_family.lower()}", f"below_{trigger.invalidation_level}"],
                rationale_text=(
                    f"setup={setup.setup_family}; pattern={pattern.pattern_name}; trigger={trigger.trigger_name}; "
                    f"entry_thesis=first-new-high-after-pullback; invalidation={trigger.invalidation_level}"
                ),
                risk_flags=confirmations.warnings + trigger.post_trigger_warnings,
            )
            intents = [intent]
            print(
                f"[ROSS][INTENT][CREATED] symbol={symbol} setup={setup.setup_family} pattern={pattern.pattern_name} "
                f"trigger={trigger.trigger_name} stop_anchor={trigger.stop_anchor}"
            )

        if no_signal is not None:
            print(
                f"[ROSS][NO_SIGNAL] symbol={symbol} stage={no_signal.failed_stage} reason={no_signal.reason} details={no_signal.details}"
            )

        cycle_summary = summarize_cycle(
            [
                {
                    "setup_detected": setup.detected,
                    "pattern_detected": pattern.detected,
                    "triggered": trigger.triggered,
                    "intent_emitted": bool(intents),
                    "failed_stage": no_signal.failed_stage if no_signal else None,
                    "reason": no_signal.reason if no_signal else None,
                }
            ]
        )
        print(f"[ROSS][CYCLE][SUMMARY] {cycle_summary}")

        decision_type = DecisionType.EMIT_INTENT if intents else (DecisionType.WATCH if setup.detected else DecisionType.NO_ACTION)
        return StrategyDecision(
            symbol=symbol,
            strategy_id=self.strategy_id,
            decision_type=decision_type,
            confidence=pattern.confidence if intents else 0.0,
            rationale_text=(intents[0].rationale_text if intents else (no_signal.reason if no_signal else "NO_SIGNAL")),
            risk_flags=confirmations.confirmations_failed,
            intents=intents,
        )
