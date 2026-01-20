"""
Teaching-first risk engine that deterministically converts intents to risk decisions.

Phase 4: Minimal live-capable scaffolding with highly constrained, conservative defaults.
"""

from typing import Optional, List

from src.core_engine.events import RiskDecisionRecord, TradeIntentRecord
from src.core_engine.health import HealthStatus
from src.core_engine.state import RunMode as Epoch5Mode

from src.config.config_resolver import get_config
from src.config.runtime_config import (
    RunMode,
    get_daily_loss_hard_limit,
    get_ibkr_readonly_enabled,
)
from src.core.active_trade_registry import ActiveTradeRegistry
from src.core.event_collector import EventCollector
from src.core.stop_controller import StopController
from src.models.data_models import RiskDecision, TradeIntent, IntentRiskDecision
from src.models.risk_decision import (
    BROKER_READONLY_BLOCK,
    DATA_QUALITY_BLOCK,
    DUPLICATE_INTENT_ID,
    EXECUTION_DISABLED,
    INTENT_MISSING_FIELDS,
    LIVE_MICRO_SYMBOL_CAP,
    LIVE_READ_ONLY_BLOCK,
    STRATEGY_LIMIT_REACHED,
)
from src.strategies.ross_momentum.ross_momentum_risk_overlay import (
    RiskContext,
    RossMomentumRiskOverlay,
)
from src.strategies.strategy_contracts import StrategyRiskPayload, TradeIntent as StrategyTradeIntent


class RiskEngine:
    """Minimal risk engine placeholder with teaching-style log messages."""

    def __init__(
        self,
        trade_registry: Optional[ActiveTradeRegistry] = None,
        event_collector: Optional[EventCollector] = None,
        stop_controller: Optional[StopController] = None,
    ) -> None:
        print("[BOOT] RiskEngine instantiated — phase 4 teaching rules active")
        self.trade_registry = trade_registry or ActiveTradeRegistry()
        self.event_collector = event_collector or EventCollector()
        self.stop_controller = stop_controller or StopController()
        self.ross_overlay = RossMomentumRiskOverlay(event_collector=self.event_collector)
        self._ross_strategy_names = {
            "MomentumContinuationStrategy",
            "RossMomentumStrategy",
            "RossMomentumStrategyV1",
        }
        self.strategy_limits = dict(get_config("RISK_STRATEGY_LIMITS"))

    def evaluate_strategy_payload(self, payload: StrategyRiskPayload) -> RiskDecision:
        """
        Canonical RiskEngine path for Epoch 3 strategy payloads.

        Produces per-intent decisions with explicit reason tags and sizing outputs.
        """

        run_mode = RunMode(get_config("RUN_MODE_EFFECTIVE"))
        execution_enabled = bool(get_config("EXECUTION_ENABLED_EFFECTIVE"))
        risk_reasons: List[str] = []
        per_intent: List[IntentRiskDecision] = []
        sizing: dict = {}

        if payload.decision_type.name == "NO_ACTION" or not payload.intents:
            return RiskDecision(
                symbol=payload.symbol,
                allowed=False,
                max_position_size=0,
                risk_level="NO_ACTION",
                rationale="No intents supplied; risk engine has nothing to evaluate.",
                trader_type="UNKNOWN",
                strategy_name=payload.strategy_id,
                direction="UNKNOWN",
                overall_action="NO_ACTION",
                per_intent=[],
                risk_reasons=["NO_INTENTS"],
                sizing={},
                circuit_breaker_tripped=self.stop_controller.is_breaker_tripped(),
                execution_blocked=not execution_enabled,
            )

        if run_mode == RunMode.LIVE_READ_ONLY:
            risk_reasons.append(LIVE_READ_ONLY_BLOCK)
        if run_mode in {RunMode.PAPER, RunMode.LIVE_MICRO}:
            daily_pnl = self.event_collector.daily_realised_pnl()
            hard_limit = abs(get_daily_loss_hard_limit())
            if hard_limit > 0 and daily_pnl <= -hard_limit:
                risk_reasons.append("DAILY_MAX_LOSS_HARD_STOP")
        if not execution_enabled:
            risk_reasons.append(EXECUTION_DISABLED)
        if get_ibkr_readonly_enabled() and run_mode in {RunMode.LIVE, RunMode.LIVE_MICRO}:
            risk_reasons.append(BROKER_READONLY_BLOCK)

        normalized_risk_flags = {flag.lower() for flag in payload.risk_flags}
        if "data_quality" in normalized_risk_flags:
            risk_reasons.append(DATA_QUALITY_BLOCK)

        intent_ids: set[str] = set()
        live_micro_symbols: set[str] = set()
        max_symbols = int(get_config("LIVE_MICRO_MAX_SYMBOLS_PER_CYCLE"))

        for intent in payload.intents:
            decision = self._evaluate_intent(
                intent=intent,
                payload=payload,
                run_mode=run_mode,
                risk_reasons=risk_reasons,
                intent_ids=intent_ids,
                live_micro_symbols=live_micro_symbols,
                max_symbols=max_symbols,
                execution_enabled=execution_enabled,
            )
            per_intent.append(decision)
            sizing[decision.intent_id] = decision.max_position_size

        any_allowed = any(intent.allowed for intent in per_intent)
        overall_action = "ALLOW" if any_allowed else "BLOCK"
        rationale = (
            "Risk decision generated from StrategyRiskPayload with "
            f"{len(per_intent)} intents."
        )
        return RiskDecision(
            symbol=payload.symbol,
            allowed=any_allowed,
            max_position_size=max((intent.max_position_size for intent in per_intent), default=0),
            risk_level="LOW" if any_allowed else "BLOCKED",
            rationale=rationale,
            trader_type="UNKNOWN",
            strategy_name=payload.strategy_id,
            direction="UNKNOWN",
            overall_action=overall_action,
            per_intent=per_intent,
            risk_reasons=risk_reasons,
            sizing=sizing,
            circuit_breaker_tripped=self.stop_controller.is_breaker_tripped(),
            execution_blocked=not execution_enabled or bool(risk_reasons),
        )

    def _evaluate_intent(
        self,
        intent: StrategyTradeIntent,
        payload: StrategyRiskPayload,
        run_mode: RunMode,
        risk_reasons: List[str],
        intent_ids: set[str],
        live_micro_symbols: set[str],
        max_symbols: int,
        execution_enabled: bool,
    ) -> IntentRiskDecision:
        reason_tags: List[str] = []
        if not intent.intent_id or not intent.symbol:
            reason_tags.append(INTENT_MISSING_FIELDS)
        if intent.intent_id in intent_ids:
            reason_tags.append(DUPLICATE_INTENT_ID)
        if intent.symbol != payload.symbol:
            reason_tags.append(INTENT_MISSING_FIELDS)

        intent_ids.add(intent.intent_id)
        if run_mode == RunMode.LIVE_MICRO:
            live_micro_symbols.add(intent.symbol)
            if len(live_micro_symbols) > max_symbols:
                reason_tags.append(LIVE_MICRO_SYMBOL_CAP)

        intent_flags = {flag.lower() for flag in intent.risk_flags}
        if "data_quality" in intent_flags and run_mode in {RunMode.LIVE, RunMode.LIVE_MICRO}:
            reason_tags.append(DATA_QUALITY_BLOCK)

        if risk_reasons:
            reason_tags.extend(risk_reasons)

        allowed = not reason_tags and execution_enabled
        if run_mode in {RunMode.LIVE_MICRO, RunMode.PAPER}:
            size = 1
        else:
            size = int(get_config("RISK_MAX_POSITION_SIZE"))
        if not allowed:
            size = 0

        return IntentRiskDecision(
            intent_id=intent.intent_id,
            symbol=intent.symbol,
            allowed=allowed,
            max_position_size=size,
            reason_tags=sorted(set(reason_tags)),
            rationale="Intent approved by RiskEngine." if allowed else "Intent blocked by RiskEngine.",
        )

    def evaluate_trade_intent(
        self,
        trade_intent: TradeIntent,
        *,
        risk_multiplier: float | None = None,
    ) -> RiskDecision:
        """
        Evaluate a TradeIntent using deterministic, conservative rules.

        Always returns a RiskDecision to keep the classroom flow moving without
        performing portfolio math, order routing, or broker interactions.
        """

        print(f"[RISK] Evaluating TradeIntent for symbol={trade_intent.symbol}")
        run_mode = RunMode(get_config("RUN_MODE_EFFECTIVE"))
        execution_enabled = bool(get_config("EXECUTION_ENABLED_EFFECTIVE"))
        if self.stop_controller.is_breaker_tripped():
            rationale = "Circuit breaker active — blocking intent."
            return RiskDecision(
                symbol=trade_intent.symbol,
                allowed=False,
                max_position_size=0,
                risk_level="BLOCKED",
                rationale=rationale,
                trader_type=trade_intent.trader_type,
                strategy_name=trade_intent.strategy_name,
                direction=trade_intent.direction,
                reason_code="CIRCUIT_BREAKER_TRIPPED",
                overall_action="BLOCK",
                risk_reasons=["CIRCUIT_BREAKER_TRIPPED"],
                circuit_breaker_tripped=True,
                execution_blocked=True,
            )
        if run_mode == RunMode.LIVE_READ_ONLY:
            rationale = "LIVE_READ_ONLY: execution blocked by risk gate."
            return RiskDecision(
                symbol=trade_intent.symbol,
                allowed=False,
                max_position_size=0,
                risk_level="BLOCKED",
                rationale=rationale,
                trader_type=trade_intent.trader_type,
                strategy_name=trade_intent.strategy_name,
                direction=trade_intent.direction,
                reason_code=LIVE_READ_ONLY_BLOCK,
                overall_action="BLOCK",
                risk_reasons=[LIVE_READ_ONLY_BLOCK],
                execution_blocked=True,
            )
        if not execution_enabled:
            rationale = "Execution disabled by configuration."
            return RiskDecision(
                symbol=trade_intent.symbol,
                allowed=False,
                max_position_size=0,
                risk_level="BLOCKED",
                rationale=rationale,
                trader_type=trade_intent.trader_type,
                strategy_name=trade_intent.strategy_name,
                direction=trade_intent.direction,
                reason_code=EXECUTION_DISABLED,
                overall_action="BLOCK",
                risk_reasons=[EXECUTION_DISABLED],
                execution_blocked=True,
            )
        if run_mode in {RunMode.PAPER, RunMode.LIVE_MICRO}:
            daily_pnl = self.event_collector.daily_realised_pnl()
            hard_limit = abs(get_daily_loss_hard_limit())
            if hard_limit > 0 and daily_pnl <= -hard_limit:
                rationale = (
                    "Daily loss hard stop reached — blocking new executions "
                    f"(daily_pnl={daily_pnl:.2f}, limit=-{hard_limit:.2f})."
                )
                return RiskDecision(
                    symbol=trade_intent.symbol,
                    allowed=False,
                    max_position_size=0,
                    risk_level="BLOCKED",
                    rationale=rationale,
                    trader_type=trade_intent.trader_type,
                    strategy_name=trade_intent.strategy_name,
                    direction=trade_intent.direction,
                    reason_code="DAILY_MAX_LOSS_HARD_STOP",
                    overall_action="BLOCK",
                    risk_reasons=["DAILY_MAX_LOSS_HARD_STOP"],
                    execution_blocked=True,
                )

        data_quality_flags = getattr(trade_intent, "data_quality_flags", [])
        if data_quality_flags:
            rationale = (
                "Trade intent blocked due to data quality flags: "
                + ", ".join(data_quality_flags)
            )
            self.event_collector.emit(
                event_type="TRADE_BLOCKED",
                source="RiskEngine",
                payload={
                    "symbol": trade_intent.symbol,
                    "trader_type": trade_intent.trader_type,
                    "strategy_name": trade_intent.strategy_name,
                    "reason": DATA_QUALITY_BLOCK,
                    "reason_code": DATA_QUALITY_BLOCK,
                    "human_readable_rationale": rationale,
                },
            )
            print(
                "[RISK] Data quality block — "
                f"symbol={trade_intent.symbol} flags={data_quality_flags}"
            )
            return RiskDecision(
                symbol=trade_intent.symbol,
                allowed=False,
                max_position_size=0,
                risk_level="BLOCKED",
                rationale=rationale,
                trader_type=trade_intent.trader_type,
                strategy_name=trade_intent.strategy_name,
                direction=trade_intent.direction,
                reason_code=DATA_QUALITY_BLOCK,
            )

        if trade_intent.strategy_name in self._ross_strategy_names:
            overlay_context = RiskContext(
                current_tick=getattr(trade_intent, "tick", 0) or 0
            )
            overlay_decision = self.ross_overlay.evaluate(trade_intent, overlay_context)
            if overlay_decision is not None:
                return overlay_decision

        trader_type = getattr(trade_intent, "trader_type", "MANUAL").upper()
        current_active = self.trade_registry.count_active_by_trader(trader_type)
        print(
            f"[RISK:REGISTRY] Active trades for {trader_type} currently {current_active} "
            "(registry single source of truth)"
        )
        strategy_limit = self.strategy_limits.get(trader_type)
        if strategy_limit:
            max_trades = strategy_limit.get("max_trades", 0)
            if current_active >= max_trades:
                print(
                    f"[RISK:STRATEGY] {trader_type} active={current_active} max={max_trades} "
                    "→ BLOCKED (limit reached)"
                )
                self.event_collector.emit(
                    event_type="TRADE_BLOCKED",
                    source="RiskEngine",
                    payload={
                        "symbol": trade_intent.symbol,
                        "trader_type": trade_intent.trader_type,
                        "strategy_name": trade_intent.strategy_name,
                        "reason": STRATEGY_LIMIT_REACHED,
                        "reason_code": STRATEGY_LIMIT_REACHED,
                        "human_readable_rationale": (
                            f"Strategy {trader_type} reached its max active trades "
                            f"({current_active}/{max_trades}); blocking this intent."
                        ),
                    },
                )
                print(
                    f"[EVENT] TRADE_BLOCKED emitted for "
                    f"{trade_intent.symbol} ({trade_intent.trader_type})"
                )
                rationale = (
                    f"Strategy {trader_type} reached its max active trades "
                    f"({current_active}/{max_trades}); blocking this intent."
                )
                return RiskDecision(
                    symbol=trade_intent.symbol,
                    allowed=False,
                    max_position_size=0,
                    risk_level="BLOCKED",
                    rationale=rationale,
                    trader_type=trader_type,
                    strategy_name=trade_intent.strategy_name,
                    direction=trade_intent.direction,
                    reason_code=STRATEGY_LIMIT_REACHED,
                )

            print(
                f"[RISK:STRATEGY] {trader_type} active={current_active} max={max_trades} "
                "→ ALLOW (within limit)"
            )
        else:
            print(
                f"[RISK:STRATEGY] {trader_type} has no configured limit — defaulting to ALLOW"
            )

        allowed = True
        if trade_intent.direction.upper() == "LONG":
            print("[RISK] Trade direction is LONG — teaching rule allows the idea to proceed")
            allowed = True
        else:
            print(
                "[RISK] Trade direction is not LONG — still allowed for teaching; "
                "no blocking logic implemented"
            )

        if run_mode in {RunMode.LIVE_MICRO, RunMode.PAPER}:
            max_position_size = 1
        else:
            max_position_size = int(get_config("RISK_MAX_POSITION_SIZE"))
        print(
            "[RISK] Max position size capped at "
            f"{max_position_size} share(s) for safety and simplicity"
        )
        applied_multiplier = None
        if risk_multiplier is not None:
            applied_multiplier = max(0.0, float(risk_multiplier))
            max_position_size = int(round(max_position_size * applied_multiplier))
            if applied_multiplier <= 0 or max_position_size <= 0:
                rationale = "Regime risk multiplier reduced size to zero."
                return RiskDecision(
                    symbol=trade_intent.symbol,
                    allowed=False,
                    max_position_size=0,
                    risk_level="BLOCKED",
                    rationale=rationale,
                    trader_type=trader_type,
                    strategy_name=trade_intent.strategy_name,
                    direction=trade_intent.direction,
                    reason_code="REGIME_RISK_MULTIPLIER",
                )

        confidence = trade_intent.confidence
        low_threshold = float(get_config("RISK_CONFIDENCE_LOW_THRESHOLD"))
        medium_threshold = float(get_config("RISK_CONFIDENCE_MEDIUM_THRESHOLD"))
        if confidence >= low_threshold:
            risk_level = "LOW"
            print(
                f"[RISK] Confidence >= {low_threshold:.2f} — assigning risk level LOW for teaching clarity"
            )
        elif confidence >= medium_threshold:
            risk_level = "MEDIUM"
            print(
                f"[RISK] Confidence between {medium_threshold:.2f} and {low_threshold:.2f} — "
                "assigning risk level MEDIUM"
            )
        else:
            risk_level = "HIGH"
            print(
                f"[RISK] Confidence < {medium_threshold:.2f} — assigning risk level HIGH to emphasize caution"
            )

        rationale = (
            "Teaching-only decision: allow intent, cap size at 1 share, "
            f"and set risk level to {risk_level} based on confidence for {trader_type} "
            "within strategy limits."
        )

        decision = RiskDecision(
            symbol=trade_intent.symbol,
            allowed=allowed,
            max_position_size=max_position_size,
            risk_level=risk_level,
            rationale=rationale,
            trader_type=trader_type,
            strategy_name=trade_intent.strategy_name,
            direction=trade_intent.direction,
            stop_loss_price=getattr(trade_intent, "stop_loss_price", None),
            take_profit_price=getattr(trade_intent, "take_profit_price", None),
            pattern_name=getattr(trade_intent, "pattern_name", None),
            invalidation_level=getattr(trade_intent, "invalidation_level", None),
        )
        if applied_multiplier is not None:
            decision.risk_reasons.append(
                f"REGIME_RISK_MULTIPLIER:{applied_multiplier:.2f}"
            )
        return decision


def evaluate_trade_intents(
    intents: List[TradeIntentRecord],
    mode: Epoch5Mode,
    health_status: HealthStatus | None,
) -> List[RiskDecisionRecord]:
    """Epoch 5 risk gate for TradeIntentRecords."""
    decisions: List[RiskDecisionRecord] = []
    for intent in intents:
        triggered_rules: List[str] = []
        constraints: List[str] = []
        decision = "ALLOW"
        max_size = 1

        if health_status == HealthStatus.CRITICAL:
            decision = "BLOCK"
            max_size = 0
            triggered_rules.append("HEALTH_CRITICAL")

        if "DATA_QUALITY" in intent.tags:
            decision = "BLOCK"
            max_size = 0
            triggered_rules.append("DATA_QUALITY")

        if mode == Epoch5Mode.SIM:
            decision = "ALLOW_WITH_CONSTRAINTS"
            max_size = 0
            constraints.append("SIMULATED_NO_EXECUTION")
            triggered_rules.append("MODE_SIM")

        if mode == Epoch5Mode.READONLY:
            decision = "ALLOW_WITH_CONSTRAINTS"
            max_size = 0
            constraints.append("READONLY_NO_EXECUTION")
            triggered_rules.append("MODE_READONLY")

        if mode == Epoch5Mode.LIVE_1SHARE and decision != "BLOCK":
            decision = "ALLOW"
            max_size = 1

        rationale = "Risk evaluation complete."
        if triggered_rules:
            rationale = f"Triggered rules: {', '.join(triggered_rules)}."

        decisions.append(
            RiskDecisionRecord(
                symbol=intent.symbol,
                intent_id=intent.intent_id,
                decision=decision,
                max_position_size=max_size,
                constraints=constraints,
                triggered_rules=triggered_rules,
                rationale=rationale,
            )
        )
    return decisions
