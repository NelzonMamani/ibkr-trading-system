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
    get_ibkr_readonly_enabled,
    get_risk_account_equity,
    get_risk_profile_name,
)
from src.config.risk_profiles import RISK_PROFILES, RiskProfile
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

    @staticmethod
    def _resolve_profile_size(profile: RiskProfile) -> int:
        base_size = int(get_config("RISK_MAX_POSITION_SIZE"))
        if profile.max_shares is not None:
            base_size = min(base_size, int(profile.max_shares))
        return max(0, base_size)

    @staticmethod
    def _resolve_daily_loss_limit(profile: RiskProfile) -> float | None:
        if profile.daily_max_loss_pct is None:
            return None
        equity = float(get_risk_account_equity())
        return round(equity * (float(profile.daily_max_loss_pct) / 100.0), 2)

    def _resolve_risk_profile(self) -> RiskProfile:
        profile_name = str(get_risk_profile_name() or "NORMAL").upper()
        profile = RISK_PROFILES.get(profile_name)
        if profile is None:
            print(f"[RISK][WARN] Unknown risk profile '{profile_name}', defaulting to NORMAL.")
            return RISK_PROFILES["NORMAL"]
        return profile

    def _profile_risk_reasons(self, profile: RiskProfile) -> List[str]:
        reasons: List[str] = []
        daily_loss_limit = self._resolve_daily_loss_limit(profile)
        if daily_loss_limit is not None:
            daily_pnl = self.event_collector.daily_realised_pnl()
            if daily_pnl <= -daily_loss_limit:
                reasons.append("RISK_PROFILE_DAILY_MAX_LOSS")
        daily_trade_limit = profile.daily_max_trades
        if daily_trade_limit is not None:
            daily_trades = self.event_collector.daily_trade_count()
            if daily_trades >= int(daily_trade_limit):
                reasons.append("RISK_PROFILE_DAILY_MAX_TRADES")
        return reasons

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
        risk_profile = self._resolve_risk_profile()

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
        risk_reasons.extend(self._profile_risk_reasons(risk_profile))
        if not execution_enabled:
            risk_reasons.append(EXECUTION_DISABLED)
        if get_ibkr_readonly_enabled() and run_mode == RunMode.LIVE:
            risk_reasons.append(BROKER_READONLY_BLOCK)

        normalized_risk_flags = {flag.lower() for flag in payload.risk_flags}
        if "data_quality" in normalized_risk_flags:
            risk_reasons.append(DATA_QUALITY_BLOCK)

        intent_ids: set[str] = set()

        for intent in payload.intents:
            decision = self._evaluate_intent(
                intent=intent,
                payload=payload,
                run_mode=run_mode,
                risk_reasons=risk_reasons,
                intent_ids=intent_ids,
                execution_enabled=execution_enabled,
                risk_profile=risk_profile,
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
        execution_enabled: bool,
        risk_profile: RiskProfile,
    ) -> IntentRiskDecision:
        reason_tags: List[str] = []
        if not intent.intent_id or not intent.symbol:
            reason_tags.append(INTENT_MISSING_FIELDS)
        if intent.intent_id in intent_ids:
            reason_tags.append(DUPLICATE_INTENT_ID)
        if intent.symbol != payload.symbol:
            reason_tags.append(INTENT_MISSING_FIELDS)

        intent_ids.add(intent.intent_id)

        intent_flags = {flag.lower() for flag in intent.risk_flags}
        if "data_quality" in intent_flags and run_mode == RunMode.LIVE:
            reason_tags.append(DATA_QUALITY_BLOCK)

        if risk_reasons:
            reason_tags.extend(risk_reasons)

        allowed = not reason_tags and execution_enabled
        size = self._resolve_profile_size(risk_profile)
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
        risk_profile = self._resolve_risk_profile()
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
        profile_reasons = self._profile_risk_reasons(risk_profile)
        if profile_reasons:
            rationale = "Risk profile blocked intent: " + ", ".join(profile_reasons)
            return RiskDecision(
                symbol=trade_intent.symbol,
                allowed=False,
                max_position_size=0,
                risk_level="BLOCKED",
                rationale=rationale,
                trader_type=trade_intent.trader_type,
                strategy_name=trade_intent.strategy_name,
                direction=trade_intent.direction,
                reason_code=profile_reasons[0],
                overall_action="BLOCK",
                risk_reasons=profile_reasons,
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

        resolved_stop_loss = trade_intent.stop_loss_price or trade_intent.invalidation_level
        if risk_profile.enforce_hard_stops and resolved_stop_loss is None:
            rationale = "Risk profile requires hard stop; intent missing stop_loss_price."
            return RiskDecision(
                symbol=trade_intent.symbol,
                allowed=False,
                max_position_size=0,
                risk_level="BLOCKED",
                rationale=rationale,
                trader_type=trade_intent.trader_type,
                strategy_name=trade_intent.strategy_name,
                direction=trade_intent.direction,
                reason_code="RISK_PROFILE_HARD_STOP_REQUIRED",
                overall_action="BLOCK",
                risk_reasons=["RISK_PROFILE_HARD_STOP_REQUIRED"],
                execution_blocked=True,
            )

        active_trade = self.trade_registry.get_trade(
            trade_intent.symbol,
            trade_intent.trader_type,
        )
        if active_trade is not None and not risk_profile.allow_scaling:
            rationale = "Risk profile blocks scaling into existing positions."
            return RiskDecision(
                symbol=trade_intent.symbol,
                allowed=False,
                max_position_size=0,
                risk_level="BLOCKED",
                rationale=rationale,
                trader_type=trade_intent.trader_type,
                strategy_name=trade_intent.strategy_name,
                direction=trade_intent.direction,
                reason_code="RISK_PROFILE_SCALING_DISABLED",
                overall_action="BLOCK",
                risk_reasons=["RISK_PROFILE_SCALING_DISABLED"],
                execution_blocked=True,
            )
        if active_trade is not None and risk_profile.max_adds is not None:
            if int(risk_profile.max_adds) <= 0:
                rationale = "Risk profile blocks adds; max_adds reached."
                return RiskDecision(
                    symbol=trade_intent.symbol,
                    allowed=False,
                    max_position_size=0,
                    risk_level="BLOCKED",
                    rationale=rationale,
                    trader_type=trade_intent.trader_type,
                    strategy_name=trade_intent.strategy_name,
                    direction=trade_intent.direction,
                    reason_code="RISK_PROFILE_MAX_ADDS_REACHED",
                    overall_action="BLOCK",
                    risk_reasons=["RISK_PROFILE_MAX_ADDS_REACHED"],
                    execution_blocked=True,
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

        max_position_size = self._resolve_profile_size(risk_profile)
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
            stop_loss_price=resolved_stop_loss,
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

        if mode == Epoch5Mode.LIVE_READ_ONLY:
            decision = "ALLOW_WITH_CONSTRAINTS"
            max_size = 0
            constraints.append("READONLY_NO_EXECUTION")
            triggered_rules.append("MODE_LIVE_READ_ONLY")

        if mode == Epoch5Mode.PAPER and decision != "BLOCK":
            decision = "ALLOW"
            max_size = 1
            triggered_rules.append("MODE_PAPER")

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
