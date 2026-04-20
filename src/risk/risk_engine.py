"""
Teaching-first risk engine that deterministically converts intents to risk decisions.

Phase 4: Minimal live-capable scaffolding with highly constrained, conservative defaults.
"""

import os
from dataclasses import dataclass
from typing import Optional, List, Tuple

from src.core.engines.trade_lifecycle_engine import TradeLifecycleEngine
from src.core_engine.events import RiskDecisionRecord, TradeIntentRecord
from src.core_engine.health import HealthStatus
from src.core_engine.state import RunMode as Epoch5Mode

from src.config.config_resolver import get_config
from src.config.system_config import get_current_market_session
from src.config.runtime_config import (
    RunMode,
    get_config_max_position_pct,
    get_default_capital,
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
    CIRCUIT_BREAKER_TRIPPED,
    DECISION_ARTIFACT_MISSING,
    BROKER_READONLY_BLOCK,
    DATA_QUALITY_BLOCK,
    DUPLICATE_INTENT_ID,
    EXECUTION_DISABLED,
    INTENT_MISSING_FIELDS,
    LIVE_READ_ONLY_BLOCK,
    RISK_MAX_OPEN_POSITIONS,
    RISK_MAX_TOTAL_EXPOSURE,
    RISK_PROFILE_MAX_POSITION_VALUE,
    RISK_PROFILE_MAX_RISK_PER_TRADE,
    RISK_SESSION_BLOCK,
    STRATEGY_READ_ONLY_EXECUTION_LOCK,
    STRATEGY_LIMIT_REACHED,
    CAPITAL_MAX_POSITIONS,
    CAPITAL_PORTFOLIO_LIMIT,
    CAPITAL_POSITION_LIMIT,
    LIFECYCLE_CRITICAL_DRIFT,
    LIFECYCLE_DRAWDOWN_BREACHED,
    LIFECYCLE_KILL_SWITCH_ACTIVE,
    LIFECYCLE_TOO_MANY_OPEN_POSITIONS,
)
from src.risk.global_kill_switch import GlobalKillSwitch
from src.risk.data_quality_contract import data_quality_blocking_causes
from src.risk.no_trade_contexts import evaluate_no_trade_contexts
from src.strategies.ross_momentum.ross_momentum_risk_overlay import (
    RiskContext,
    RossMomentumRiskOverlay,
)
from src.strategies.strategy_contracts import StrategyRiskPayload, TradeIntent as StrategyTradeIntent
from src.utils.time_utils import utc_now


class PortfolioStateDesyncError(RuntimeError):
    """Raised when authoritative portfolio state is internally contradictory."""




@dataclass(frozen=True)
class ValidationResult:
    accepted: bool
    reason: str | None = None


def Accept() -> ValidationResult:
    return ValidationResult(accepted=True, reason=None)


def Reject(reason: str) -> ValidationResult:
    return ValidationResult(accepted=False, reason=reason)


def validate_order(order, portfolio) -> ValidationResult:
    if getattr(portfolio, "total_exposure", 0) > getattr(portfolio, "max_exposure", float("inf")):
        return Reject("EXPOSURE_LIMIT")

    size = getattr(order, "size", getattr(order, "quantity", 0))
    if size > getattr(portfolio, "max_position_size", float("inf")):
        return Reject("POSITION_LIMIT")

    if getattr(portfolio, "daily_loss", 0) > getattr(portfolio, "max_daily_loss", float("inf")):
        return Reject("DAILY_LOSS_LIMIT")

    return Accept()


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
        self.trade_lifecycle_engine: TradeLifecycleEngine | None = None
        self.kill_switch = GlobalKillSwitch()

    def set_trade_lifecycle_engine(self, trade_lifecycle_engine: TradeLifecycleEngine) -> None:
        self.trade_lifecycle_engine = trade_lifecycle_engine

    @staticmethod
    def _assert_portfolio_state_invariant(*, open_positions: int, total_exposure: float) -> None:
        if abs(float(total_exposure)) <= 1e-9 and int(open_positions) > 0:
            raise PortfolioStateDesyncError(
                f"portfolio_exposure={float(total_exposure):.2f} with open_positions={int(open_positions)}"
            )

    @staticmethod
    def _resolve_trade_value(trade_intent: TradeIntent, fallback_quantity: int) -> float:
        entry_price = getattr(trade_intent, "entry_price", None)
        if entry_price is None:
            entry_price = getattr(trade_intent, "entry", None)
        if entry_price is None or float(entry_price) <= 0:
            return 0.0
        quantity = int(getattr(trade_intent, "quantity", 0) or 0)
        if quantity <= 0:
            quantity = max(1, int(fallback_quantity))
        return round(float(quantity) * float(entry_price), 2)

    def _block_for_lifecycle(
        self,
        *,
        trade_intent: TradeIntent,
        run_mode: RunMode,
        evaluated_limits: dict,
        timestamp: str,
        decision_id: str | None,
        reason_code: str,
        rationale: str,
    ) -> RiskDecision:
        decision = RiskDecision(
            symbol=trade_intent.symbol,
            allowed=False,
            max_position_size=0,
            risk_level="BLOCKED",
            rationale=rationale,
            trader_type=trade_intent.trader_type,
            strategy_name=trade_intent.strategy_name,
            direction=trade_intent.direction,
            reason_code=reason_code,
            overall_action="BLOCK",
            decision_code="HALT" if self.kill_switch.active else "REJECT",
            risk_reasons=[reason_code],
            execution_blocked=True,
            blocked_by_lifecycle=True,
            lifecycle_block_reason=reason_code,
            run_mode=run_mode.value,
            evaluated_limits=evaluated_limits,
            timestamp=timestamp,
        )
        return self._finalize_decision(decision, decision_id)

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

    @staticmethod
    def _resolve_position_value_limit(profile: RiskProfile) -> float | None:
        if profile.max_position_value_pct is None:
            return None
        equity = float(get_risk_account_equity())
        return round(equity * (float(profile.max_position_value_pct) / 100.0), 2)

    @staticmethod
    def _resolve_risk_per_trade_limit(profile: RiskProfile) -> float | None:
        if profile.max_risk_per_trade_pct is None:
            return None
        equity = float(get_risk_account_equity())
        return round(equity * (float(profile.max_risk_per_trade_pct) / 100.0), 2)

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

    def _session_gate(self, run_mode: RunMode) -> Tuple[str, List[str], bool]:
        session = get_current_market_session()
        active_sessions = [str(value).upper() for value in get_config("ACTIVE_SESSIONS")]
        # THA is authoritative for time eligibility; risk no longer blocks by session.
        should_gate = False
        return session, active_sessions, should_gate

    def _total_exposure(self) -> float:
        total = 0.0
        for trade in self.trade_registry.snapshot():
            total += float(trade.entry_price) * int(trade.quantity)
        return round(total, 2)

    def _total_exposure_limit(self) -> float:
        equity = float(get_risk_account_equity())
        pct = float(get_config("RISK_MAX_TOTAL_EXPOSURE_PCT"))
        return round(equity * (pct / 100.0), 2)

    def _emit_risk_decision_event(self, decision: RiskDecision) -> None:
        self.event_collector.emit(
            event_type="RISK_DECISION",
            source="RiskEngine",
            payload={
                "symbol": decision.symbol,
                "strategy_name": decision.strategy_name,
                "trader_type": decision.trader_type,
                "decision_code": decision.decision_code,
                "overall_action": decision.overall_action,
                "run_mode": decision.run_mode,
                "reason_codes": decision.risk_reasons,
                "timestamp": decision.timestamp,
                "evaluated_limits": decision.evaluated_limits,
                "intent_id": decision.intent_id,
                "decision_id": decision.decision_id,
            },
        )

    def _finalize_decision(
        self, decision: RiskDecision, decision_id: str | None
    ) -> RiskDecision:
        decision.decision_id = decision_id
        self._emit_risk_decision_event(decision)
        return decision

    def evaluate_strategy_payload(self, payload: StrategyRiskPayload) -> RiskDecision:
        """
        Canonical RiskEngine path for Epoch 3 strategy payloads.

        Produces per-intent decisions with explicit reason tags and sizing outputs.
        """

        run_mode = RunMode(get_config("RUN_MODE_EFFECTIVE"))
        timestamp = utc_now().isoformat()
        execution_enabled = bool(get_config("EXECUTION_ENABLED_EFFECTIVE"))
        risk_reasons: List[str] = []
        per_intent: List[IntentRiskDecision] = []
        sizing: dict = {}
        risk_profile = self._resolve_risk_profile()
        session_label, active_sessions, session_blocked = self._session_gate(run_mode)
        open_positions = self.trade_registry.count_active()
        max_open_positions = int(get_config("RISK_MAX_OPEN_POSITIONS"))
        total_exposure = self._total_exposure()
        total_exposure_limit = self._total_exposure_limit()
        if self.trade_lifecycle_engine is not None:
            try:
                lifecycle_state = self.trade_lifecycle_engine.build_portfolio_state()
                open_positions = int(lifecycle_state.total_open_positions)
                total_exposure = float(lifecycle_state.total_exposure)
                self._assert_portfolio_state_invariant(
                    open_positions=open_positions,
                    total_exposure=total_exposure,
                )
            except PortfolioStateDesyncError:
                raise
            except Exception as exc:
                print(f"[LIFECYCLE][DEGRADED] stage=strategy_payload_portfolio_state reason={exc}")
        available_capital = float(get_default_capital())
        print(f"[RISK][CAPITAL] source=CONFIG default_available_capital={available_capital}")
        evaluated_limits = {
            "profile": risk_profile.name,
            "available_capital": available_capital,
            "max_position_size": self._resolve_profile_size(risk_profile),
            "max_open_positions": max_open_positions,
            "open_positions": open_positions,
            "max_total_exposure": total_exposure_limit,
            "total_exposure": total_exposure,
            "daily_loss_limit": self._resolve_daily_loss_limit(risk_profile),
            "daily_trade_limit": risk_profile.daily_max_trades,
            "session": session_label,
            "active_sessions": active_sessions,
            "execution_allowed": not session_blocked,
            "execution_ready": session_label in {"PRE", "RTH", "RTH_OPEN", "RTH_MID", "RTH_LATE"},
            "prep_only": session_label in {"AH", "OVN", "CLOSED", "WEEKEND"},
            "execution_enabled": execution_enabled,
            "run_mode": run_mode.value,
        }

        if self.stop_controller.is_breaker_tripped():
            decision = RiskDecision(
                symbol=payload.symbol,
                allowed=False,
                max_position_size=0,
                risk_level="BLOCKED",
                rationale="Circuit breaker active — blocking risk evaluation.",
                trader_type="UNKNOWN",
                strategy_name=payload.strategy_id,
                direction="UNKNOWN",
                overall_action="HALT",
                decision_code="HALT",
                risk_reasons=[CIRCUIT_BREAKER_TRIPPED],
                circuit_breaker_tripped=True,
                execution_blocked=True,
                run_mode=run_mode.value,
                evaluated_limits=evaluated_limits,
                timestamp=timestamp,
            )
            self._emit_risk_decision_event(decision)
            return decision

        if payload.decision_type.name == "NO_ACTION" or not payload.intents:
            decision = RiskDecision(
                symbol=payload.symbol,
                allowed=False,
                max_position_size=0,
                risk_level="NO_ACTION",
                rationale="No intents supplied; risk engine has nothing to evaluate.",
                trader_type="UNKNOWN",
                strategy_name=payload.strategy_id,
                direction="UNKNOWN",
                overall_action="NO_ACTION",
                decision_code="REJECT",
                per_intent=[],
                risk_reasons=["NO_INTENTS"],
                sizing={},
                circuit_breaker_tripped=self.stop_controller.is_breaker_tripped(),
                execution_blocked=not execution_enabled,
                run_mode=run_mode.value,
                evaluated_limits=evaluated_limits,
                timestamp=timestamp,
            )
            self._emit_risk_decision_event(decision)
            return decision

        payload_data_quality_causes = data_quality_blocking_causes(payload.risk_flags)
        no_trade_contexts = evaluate_no_trade_contexts(
            run_mode=run_mode,
            execution_enabled=execution_enabled,
            session_blocked=session_blocked,
            broker_readonly=get_ibkr_readonly_enabled(),
            circuit_breaker_tripped=self.stop_controller.is_breaker_tripped(),
            data_quality_block=bool(payload_data_quality_causes),
        )
        risk_reasons.extend(context.code for context in no_trade_contexts)
        if open_positions >= max_open_positions:
            risk_reasons.append(RISK_MAX_OPEN_POSITIONS)
        if total_exposure >= total_exposure_limit:
            risk_reasons.append(RISK_MAX_TOTAL_EXPOSURE)
        if payload.strategy_id == "LongHorizonValue" and run_mode == RunMode.LIVE:
            risk_reasons.append(STRATEGY_READ_ONLY_EXECUTION_LOCK)
            print(
                "[RISK] Strategy execution lock active for LongHorizonValue in LIVE mode."
            )
            for intent in payload.intents:
                self.event_collector.emit(
                    event_type="TRADE_BLOCKED",
                    source="RiskEngine",
                    payload={
                        "symbol": payload.symbol,
                        "trader_type": payload.trader_type,
                        "strategy_name": payload.strategy_id,
                        "reason": STRATEGY_READ_ONLY_EXECUTION_LOCK,
                        "reason_code": STRATEGY_READ_ONLY_EXECUTION_LOCK,
                        "human_readable_rationale": (
                            "LongHorizonValue is READ_ONLY by policy in LIVE mode."
                        ),
                        "intent_id": intent.intent_id,
                    },
                )
        risk_reasons.extend(self._profile_risk_reasons(risk_profile))

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
        decision_code = "APPROVE" if any_allowed else "REJECT"
        rationale = (
            "Risk decision generated from StrategyRiskPayload with "
            f"{len(per_intent)} intents."
        )
        decision = RiskDecision(
            symbol=payload.symbol,
            allowed=any_allowed,
            max_position_size=max((intent.max_position_size for intent in per_intent), default=0),
            risk_level="LOW" if any_allowed else "BLOCKED",
            rationale=rationale,
            trader_type="UNKNOWN",
            strategy_name=payload.strategy_id,
            direction="UNKNOWN",
            overall_action=overall_action,
            decision_code=decision_code,
            per_intent=per_intent,
            risk_reasons=risk_reasons,
            sizing=sizing,
            circuit_breaker_tripped=self.stop_controller.is_breaker_tripped(),
            execution_blocked=not execution_enabled or bool(risk_reasons),
            run_mode=run_mode.value,
            evaluated_limits=evaluated_limits,
            timestamp=timestamp,
        )
        self._emit_risk_decision_event(decision)
        return decision

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

        intent_data_quality_causes = data_quality_blocking_causes(intent.risk_flags)
        if intent_data_quality_causes and run_mode == RunMode.LIVE:
            reason_tags.append(DATA_QUALITY_BLOCK)
            print(
                "[RISK][DATA_QUALITY] decision=BLOCK "
                f"symbol={intent.symbol} causes={intent_data_quality_causes} flags={list(intent.risk_flags)}"
            )

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
        timestamp = utc_now().isoformat()
        execution_enabled = bool(get_config("EXECUTION_ENABLED_EFFECTIVE"))
        decision_id = getattr(trade_intent, "decision_id", None)
        risk_profile = self._resolve_risk_profile()
        session_label, active_sessions, session_blocked = self._session_gate(run_mode)
        open_positions = self.trade_registry.count_active()
        max_open_positions = int(get_config("RISK_MAX_OPEN_POSITIONS"))
        total_exposure = self._total_exposure()
        total_exposure_limit = self._total_exposure_limit()
        available_capital = float(get_default_capital())
        print(f"[RISK][CAPITAL] source=CONFIG default_available_capital={available_capital}")
        evaluated_limits = {
            "profile": risk_profile.name,
            "available_capital": available_capital,
            "max_position_size": self._resolve_profile_size(risk_profile),
            "max_open_positions": max_open_positions,
            "open_positions": open_positions,
            "max_total_exposure": total_exposure_limit,
            "total_exposure": total_exposure,
            "daily_loss_limit": self._resolve_daily_loss_limit(risk_profile),
            "daily_trade_limit": risk_profile.daily_max_trades,
            "session": session_label,
            "active_sessions": active_sessions,
            "execution_allowed": not session_blocked,
            "execution_ready": session_label in {"PRE", "RTH", "RTH_OPEN", "RTH_MID", "RTH_LATE"},
            "prep_only": session_label in {"AH", "OVN", "CLOSED", "WEEKEND"},
            "execution_enabled": execution_enabled,
            "run_mode": run_mode.value,
        }
        trade_value = self._resolve_trade_value(
            trade_intent=trade_intent,
            fallback_quantity=self._resolve_profile_size(risk_profile),
        )
        evaluated_limits["trade_value"] = trade_value
        evaluated_limits["kill_switch_active"] = self.kill_switch.active

        try:
            if bool(get_config("LIFECYCLE_MANUAL_KILL_SWITCH")) or os.getenv(
                "LIFECYCLE_MANUAL_KILL_SWITCH", "0"
            ).lower() in {"1", "true", "yes", "on"}:
                self.kill_switch.activate("manual")
        except Exception:
            # config read should not crash risk evaluation paths
            pass

        lifecycle_signals = None
        portfolio_state = None
        lifecycle_critical_drift = False
        if self.trade_lifecycle_engine is not None:
            try:
                lifecycle_signals = self.trade_lifecycle_engine.compute_lifecycle_risk_signals()
                portfolio_state = self.trade_lifecycle_engine.build_portfolio_state()
                open_positions = int(portfolio_state.total_open_positions)
                total_exposure = float(portfolio_state.total_exposure)
                self._assert_portfolio_state_invariant(
                    open_positions=open_positions,
                    total_exposure=total_exposure,
                )
                evaluated_limits["open_positions"] = open_positions
                evaluated_limits["total_exposure"] = total_exposure
                findings = self.trade_lifecycle_engine.get_drift_report()
                lifecycle_critical_drift = any(
                    str(event.get("severity", "")).upper() == "CRITICAL"
                    or str(event.get("status", "")).upper() == "ORPHANED"
                    for event in findings
                )
            except PortfolioStateDesyncError:
                raise
            except Exception as exc:
                print(f"[LIFECYCLE][DEGRADED] stage=risk_bridge reason={exc}")
        if lifecycle_critical_drift:
            self.kill_switch.activate("critical_broker_mismatch")

        evaluated_limits["kill_switch_active"] = self.kill_switch.active
        evaluated_limits["kill_switch_reason"] = self.kill_switch.reason
        if portfolio_state is not None:
            evaluated_limits["lifecycle_total_exposure"] = float(portfolio_state.total_exposure)
            evaluated_limits["lifecycle_open_positions"] = int(portfolio_state.total_open_positions)
        if lifecycle_signals is not None:
            if lifecycle_signals.max_drawdown_breached:
                self.kill_switch.activate("drawdown")
            if self.kill_switch.active:
                print(f"[RISK][BLOCKED][KILL_SWITCH] reason={self.kill_switch.reason}")
                return self._block_for_lifecycle(
                    trade_intent=trade_intent,
                    run_mode=run_mode,
                    evaluated_limits=evaluated_limits,
                    timestamp=timestamp,
                    decision_id=decision_id,
                    reason_code=LIFECYCLE_KILL_SWITCH_ACTIVE,
                    rationale=f"Lifecycle kill switch active: {self.kill_switch.reason}",
                )
            if lifecycle_signals.max_drawdown_breached:
                print("[RISK][BLOCKED][LIFECYCLE] reason=drawdown")
                return self._block_for_lifecycle(
                    trade_intent=trade_intent,
                    run_mode=run_mode,
                    evaluated_limits=evaluated_limits,
                    timestamp=timestamp,
                    decision_id=decision_id,
                    reason_code=LIFECYCLE_DRAWDOWN_BREACHED,
                    rationale="Lifecycle max drawdown breached.",
                )
            if lifecycle_signals.drift_detected and lifecycle_critical_drift:
                print("[RISK][BLOCKED][LIFECYCLE] reason=critical_drift")
                return self._block_for_lifecycle(
                    trade_intent=trade_intent,
                    run_mode=run_mode,
                    evaluated_limits=evaluated_limits,
                    timestamp=timestamp,
                    decision_id=decision_id,
                    reason_code=LIFECYCLE_CRITICAL_DRIFT,
                    rationale="Lifecycle drift detected with CRITICAL severity.",
                )
            if lifecycle_signals.too_many_open_positions:
                print("[RISK][BLOCKED][LIFECYCLE] reason=too_many_open_positions")
                return self._block_for_lifecycle(
                    trade_intent=trade_intent,
                    run_mode=run_mode,
                    evaluated_limits=evaluated_limits,
                    timestamp=timestamp,
                    decision_id=decision_id,
                    reason_code=LIFECYCLE_TOO_MANY_OPEN_POSITIONS,
                    rationale="Lifecycle too_many_open_positions signal active.",
                )

        if portfolio_state is not None:
            max_portfolio_exposure = float(get_config("LIFECYCLE_MAX_PORTFOLIO_EXPOSURE"))
            max_position_exposure = float(get_config("LIFECYCLE_MAX_POSITION_EXPOSURE"))
            max_positions = int(get_config("LIFECYCLE_MAX_POSITIONS"))
            if float(portfolio_state.total_exposure) + float(trade_value) > max_portfolio_exposure:
                print("[RISK][BLOCKED][CAPITAL] reason=portfolio_limit")
                return self._block_for_lifecycle(
                    trade_intent=trade_intent,
                    run_mode=run_mode,
                    evaluated_limits=evaluated_limits,
                    timestamp=timestamp,
                    decision_id=decision_id,
                    reason_code=CAPITAL_PORTFOLIO_LIMIT,
                    rationale="Portfolio exposure limit exceeded by proposed trade.",
                )
            if float(trade_value) > max_position_exposure:
                print("[RISK][BLOCKED][CAPITAL] reason=position_limit")
                return self._block_for_lifecycle(
                    trade_intent=trade_intent,
                    run_mode=run_mode,
                    evaluated_limits=evaluated_limits,
                    timestamp=timestamp,
                    decision_id=decision_id,
                    reason_code=CAPITAL_POSITION_LIMIT,
                    rationale="Position exposure limit exceeded by proposed trade.",
                )
            if int(portfolio_state.total_open_positions) >= max_positions:
                print("[RISK][BLOCKED][CAPITAL] reason=max_positions")
                return self._block_for_lifecycle(
                    trade_intent=trade_intent,
                    run_mode=run_mode,
                    evaluated_limits=evaluated_limits,
                    timestamp=timestamp,
                    decision_id=decision_id,
                    reason_code=CAPITAL_MAX_POSITIONS,
                    rationale="Maximum lifecycle position count reached.",
                )

        setup_family_id = str(getattr(trade_intent, "setup_family_id", "") or "").upper()
        if setup_family_id == "PARABOLIC_EXHAUSTION":
            print(f"[RISK][EXHAUSTION_SUPPRESSION] symbol={trade_intent.symbol} action=BLOCK_NEW_LONGS_PYRAMID")
            decision = RiskDecision(
                symbol=trade_intent.symbol,
                allowed=False,
                max_position_size=0,
                risk_level="BLOCKED",
                rationale="Parabolic exhaustion active: block new longs and pyramiding.",
                trader_type=trade_intent.trader_type,
                strategy_name=trade_intent.strategy_name,
                direction=trade_intent.direction,
                reason_code="PARABOLIC_EXHAUSTION_SUPPRESSION",
                overall_action="BLOCK",
                decision_code="REJECT",
                risk_reasons=["PARABOLIC_EXHAUSTION_SUPPRESSION"],
                execution_blocked=True,
                run_mode=run_mode.value,
                evaluated_limits=evaluated_limits,
                timestamp=timestamp,
            )
            return self._finalize_decision(decision, decision_id)

        if getattr(trade_intent, "force_execute", False):
            print(f"[RISK][BYPASS] symbol={trade_intent.symbol}")
            decision = RiskDecision(
                symbol=trade_intent.symbol,
                allowed=True,
                max_position_size=max(1, self._resolve_profile_size(risk_profile)),
                risk_level="LOW",
                rationale="FORCED_EXECUTION_WINDOW_BYPASS",
                trader_type=trade_intent.trader_type,
                strategy_name=trade_intent.strategy_name,
                direction=trade_intent.direction,
                stop_loss_price=trade_intent.stop_loss_price,
                take_profit_price=trade_intent.take_profit_price,
                pattern_name=getattr(trade_intent, "pattern_name", None),
                invalidation_level=getattr(trade_intent, "invalidation_level", None),
                overall_action="ALLOW",
                decision_code="APPROVE",
                execution_blocked=False,
                run_mode=run_mode.value,
                evaluated_limits=evaluated_limits,
                timestamp=timestamp,
            )
            setattr(decision, "force_execute", True)
            return self._finalize_decision(decision, decision_id)
        if not decision_id:
            rationale = "Decision artifact missing; blocking intent."
            decision = RiskDecision(
                symbol=trade_intent.symbol,
                allowed=False,
                max_position_size=0,
                risk_level="BLOCKED",
                rationale=rationale,
                trader_type=trade_intent.trader_type,
                strategy_name=trade_intent.strategy_name,
                direction=trade_intent.direction,
                reason_code=DECISION_ARTIFACT_MISSING,
                overall_action="BLOCK",
                decision_code="REJECT",
                risk_reasons=[DECISION_ARTIFACT_MISSING],
                execution_blocked=True,
                run_mode=run_mode.value,
                evaluated_limits=evaluated_limits,
                timestamp=timestamp,
            )
            return self._finalize_decision(decision, decision_id)
        data_quality_flags = getattr(trade_intent, "data_quality_flags", [])
        data_quality_causes = data_quality_blocking_causes(data_quality_flags)
        no_trade_contexts = evaluate_no_trade_contexts(
            run_mode=run_mode,
            execution_enabled=execution_enabled,
            session_blocked=session_blocked,
            broker_readonly=get_ibkr_readonly_enabled(),
            circuit_breaker_tripped=self.stop_controller.is_breaker_tripped(),
            data_quality_block=bool(data_quality_causes),
        )
        if no_trade_contexts:
            rationale = "; ".join(context.rationale for context in no_trade_contexts)
            decision = RiskDecision(
                symbol=trade_intent.symbol,
                allowed=False,
                max_position_size=0,
                risk_level="BLOCKED",
                rationale=rationale,
                trader_type=trade_intent.trader_type,
                strategy_name=trade_intent.strategy_name,
                direction=trade_intent.direction,
                reason_code=no_trade_contexts[0].code,
                overall_action="BLOCK",
                decision_code="HALT" if self.stop_controller.is_breaker_tripped() else "REJECT",
                risk_reasons=[context.code for context in no_trade_contexts],
                circuit_breaker_tripped=self.stop_controller.is_breaker_tripped(),
                execution_blocked=True,
                run_mode=run_mode.value,
                evaluated_limits=evaluated_limits,
                timestamp=timestamp,
            )
            return self._finalize_decision(decision, decision_id)
        if trade_intent.strategy_name == "LongHorizonValue" and run_mode == RunMode.LIVE:
            rationale = "LongHorizonValue is READ_ONLY by policy in LIVE mode."
            self.event_collector.emit(
                event_type="TRADE_BLOCKED",
                source="RiskEngine",
                payload={
                    "symbol": trade_intent.symbol,
                    "trader_type": trade_intent.trader_type,
                    "strategy_name": trade_intent.strategy_name,
                    "reason": STRATEGY_READ_ONLY_EXECUTION_LOCK,
                    "reason_code": STRATEGY_READ_ONLY_EXECUTION_LOCK,
                    "human_readable_rationale": rationale,
                },
            )
            print(
                "[RISK] Strategy execution lock active for LongHorizonValue in LIVE mode."
            )
            decision = RiskDecision(
                symbol=trade_intent.symbol,
                allowed=False,
                max_position_size=0,
                risk_level="BLOCKED",
                rationale=rationale,
                trader_type=trade_intent.trader_type,
                strategy_name=trade_intent.strategy_name,
                direction=trade_intent.direction,
                reason_code=STRATEGY_READ_ONLY_EXECUTION_LOCK,
                overall_action="BLOCK",
                decision_code="REJECT",
                risk_reasons=[STRATEGY_READ_ONLY_EXECUTION_LOCK],
                execution_blocked=True,
                run_mode=run_mode.value,
                evaluated_limits=evaluated_limits,
                timestamp=timestamp,
            )
            return self._finalize_decision(decision, decision_id)
        if open_positions >= max_open_positions:
            rationale = "Max open positions reached; blocking intent."
            decision = RiskDecision(
                symbol=trade_intent.symbol,
                allowed=False,
                max_position_size=0,
                risk_level="BLOCKED",
                rationale=rationale,
                trader_type=trade_intent.trader_type,
                strategy_name=trade_intent.strategy_name,
                direction=trade_intent.direction,
                reason_code=RISK_MAX_OPEN_POSITIONS,
                overall_action="BLOCK",
                decision_code="REJECT",
                risk_reasons=[RISK_MAX_OPEN_POSITIONS],
                execution_blocked=True,
                run_mode=run_mode.value,
                evaluated_limits=evaluated_limits,
                timestamp=timestamp,
            )
            return self._finalize_decision(decision, decision_id)
        if total_exposure >= total_exposure_limit:
            rationale = "Max total exposure reached; blocking intent."
            decision = RiskDecision(
                symbol=trade_intent.symbol,
                allowed=False,
                max_position_size=0,
                risk_level="BLOCKED",
                rationale=rationale,
                trader_type=trade_intent.trader_type,
                strategy_name=trade_intent.strategy_name,
                direction=trade_intent.direction,
                reason_code=RISK_MAX_TOTAL_EXPOSURE,
                overall_action="BLOCK",
                decision_code="REJECT",
                risk_reasons=[RISK_MAX_TOTAL_EXPOSURE],
                execution_blocked=True,
                run_mode=run_mode.value,
                evaluated_limits=evaluated_limits,
                timestamp=timestamp,
            )
            return self._finalize_decision(decision, decision_id)
        profile_reasons = self._profile_risk_reasons(risk_profile)
        if profile_reasons:
            rationale = "Risk profile blocked intent: " + ", ".join(profile_reasons)
            decision = RiskDecision(
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
                decision_code="REJECT",
                risk_reasons=profile_reasons,
                execution_blocked=True,
                run_mode=run_mode.value,
                evaluated_limits=evaluated_limits,
                timestamp=timestamp,
            )
            return self._finalize_decision(decision, decision_id)

        if data_quality_flags and data_quality_causes:
            rationale = (
                "Trade intent blocked due to data quality causes: "
                + ", ".join(data_quality_causes)
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
                    "data_quality_causes": data_quality_causes,
                    "data_quality_flags": list(data_quality_flags),
                },
            )
            print(
                "[RISK][DATA_QUALITY] decision=BLOCK "
                f"symbol={trade_intent.symbol} causes={data_quality_causes} flags={list(data_quality_flags)}"
            )
            decision = RiskDecision(
                symbol=trade_intent.symbol,
                allowed=False,
                max_position_size=0,
                risk_level="BLOCKED",
                rationale=rationale,
                trader_type=trade_intent.trader_type,
                strategy_name=trade_intent.strategy_name,
                direction=trade_intent.direction,
                reason_code=DATA_QUALITY_BLOCK,
                overall_action="BLOCK",
                decision_code="REJECT",
                risk_reasons=[DATA_QUALITY_BLOCK],
                execution_blocked=True,
                run_mode=run_mode.value,
                evaluated_limits=evaluated_limits,
                timestamp=timestamp,
            )
            return self._finalize_decision(decision, decision_id)
        if data_quality_flags and not data_quality_causes:
            print(
                "[RISK][DATA_QUALITY] decision=ALLOW "
                f"symbol={trade_intent.symbol} causes=[] flags={list(data_quality_flags)}"
            )

        resolved_stop_loss = trade_intent.stop_loss_price or trade_intent.invalidation_level
        if risk_profile.enforce_hard_stops and resolved_stop_loss is None:
            rationale = "Risk profile requires hard stop; intent missing stop_loss_price."
            decision = RiskDecision(
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
                decision_code="REJECT",
                risk_reasons=["RISK_PROFILE_HARD_STOP_REQUIRED"],
                execution_blocked=True,
                run_mode=run_mode.value,
                evaluated_limits=evaluated_limits,
                timestamp=timestamp,
            )
            return self._finalize_decision(decision, decision_id)

        entry_price = getattr(trade_intent, "entry_price", None)
        if entry_price is None:
            entry_price = getattr(trade_intent, "entry", None)
        max_position_value = self._resolve_position_value_limit(risk_profile)
        if entry_price is not None and max_position_value is not None:
            position_value = float(entry_price) * float(self._resolve_profile_size(risk_profile))
            if position_value > max_position_value:
                rationale = "Risk profile max position value breached."
                decision = RiskDecision(
                    symbol=trade_intent.symbol,
                    allowed=False,
                    max_position_size=0,
                    risk_level="BLOCKED",
                    rationale=rationale,
                    trader_type=trade_intent.trader_type,
                    strategy_name=trade_intent.strategy_name,
                    direction=trade_intent.direction,
                    reason_code=RISK_PROFILE_MAX_POSITION_VALUE,
                    overall_action="BLOCK",
                    decision_code="REJECT",
                    risk_reasons=[RISK_PROFILE_MAX_POSITION_VALUE],
                    execution_blocked=True,
                    run_mode=run_mode.value,
                    evaluated_limits=evaluated_limits,
                    timestamp=timestamp,
                )
                return self._finalize_decision(decision, decision_id)
        max_risk_per_trade = self._resolve_risk_per_trade_limit(risk_profile)
        if (
            entry_price is not None
            and resolved_stop_loss is not None
            and max_risk_per_trade is not None
        ):
            risk_per_share = abs(float(entry_price) - float(resolved_stop_loss))
            risk_total = risk_per_share * float(self._resolve_profile_size(risk_profile))
            if risk_total > max_risk_per_trade:
                rationale = "Risk profile max risk per trade breached."
                decision = RiskDecision(
                    symbol=trade_intent.symbol,
                    allowed=False,
                    max_position_size=0,
                    risk_level="BLOCKED",
                    rationale=rationale,
                    trader_type=trade_intent.trader_type,
                    strategy_name=trade_intent.strategy_name,
                    direction=trade_intent.direction,
                    reason_code=RISK_PROFILE_MAX_RISK_PER_TRADE,
                    overall_action="BLOCK",
                    decision_code="REJECT",
                    risk_reasons=[RISK_PROFILE_MAX_RISK_PER_TRADE],
                    execution_blocked=True,
                    run_mode=run_mode.value,
                    evaluated_limits=evaluated_limits,
                    timestamp=timestamp,
                )
                return self._finalize_decision(decision, decision_id)

        active_trade = self.trade_registry.get_trade(
            trade_intent.symbol,
            trade_intent.trader_type,
        )
        if active_trade is not None and not risk_profile.allow_scaling:
            rationale = "Risk profile blocks scaling into existing positions."
            decision = RiskDecision(
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
                decision_code="REJECT",
                risk_reasons=["RISK_PROFILE_SCALING_DISABLED"],
                execution_blocked=True,
                run_mode=run_mode.value,
                evaluated_limits=evaluated_limits,
                timestamp=timestamp,
            )
            return self._finalize_decision(decision, decision_id)
        if active_trade is not None and risk_profile.max_adds is not None:
            if int(risk_profile.max_adds) <= 0:
                rationale = "Risk profile blocks adds; max_adds reached."
                decision = RiskDecision(
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
                    decision_code="REJECT",
                    risk_reasons=["RISK_PROFILE_MAX_ADDS_REACHED"],
                    execution_blocked=True,
                    run_mode=run_mode.value,
                    evaluated_limits=evaluated_limits,
                    timestamp=timestamp,
                )
                return self._finalize_decision(decision, decision_id)

        if trade_intent.strategy_name in self._ross_strategy_names:
            overlay_context = RiskContext(
                current_tick=getattr(trade_intent, "tick", 0) or 0
            )
            overlay_decision = self.ross_overlay.evaluate(trade_intent, overlay_context)
            if overlay_decision is not None:
                overlay_decision.run_mode = run_mode.value
                overlay_decision.evaluated_limits = evaluated_limits
                overlay_decision.timestamp = timestamp
                overlay_decision.decision_code = "REJECT"
                overlay_decision.overall_action = "BLOCK"
                return self._finalize_decision(overlay_decision, decision_id)

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
                decision = RiskDecision(
                    symbol=trade_intent.symbol,
                    allowed=False,
                    max_position_size=0,
                    risk_level="BLOCKED",
                    rationale=rationale,
                    trader_type=trader_type,
                    strategy_name=trade_intent.strategy_name,
                    direction=trade_intent.direction,
                    reason_code=STRATEGY_LIMIT_REACHED,
                    overall_action="BLOCK",
                    decision_code="REJECT",
                    risk_reasons=[STRATEGY_LIMIT_REACHED],
                    execution_blocked=True,
                    run_mode=run_mode.value,
                    evaluated_limits=evaluated_limits,
                    timestamp=timestamp,
                )
                return self._finalize_decision(decision, decision_id)

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
        print(
            f"[RISK_CHECK] symbol={trade_intent.symbol} size={max_position_size} allowed={allowed}"
        )
        applied_multiplier = None
        if risk_multiplier is not None:
            applied_multiplier = max(0.0, float(risk_multiplier))
            max_position_size = int(round(max_position_size * applied_multiplier))
            if applied_multiplier <= 0 or max_position_size <= 0:
                rationale = "Regime risk multiplier reduced size to zero."
                decision = RiskDecision(
                    symbol=trade_intent.symbol,
                    allowed=False,
                    max_position_size=0,
                    risk_level="BLOCKED",
                    rationale=rationale,
                    trader_type=trader_type,
                    strategy_name=trade_intent.strategy_name,
                    direction=trade_intent.direction,
                    reason_code="REGIME_RISK_MULTIPLIER",
                    overall_action="BLOCK",
                    decision_code="REJECT",
                    risk_reasons=["REGIME_RISK_MULTIPLIER"],
                    execution_blocked=True,
                    run_mode=run_mode.value,
                    evaluated_limits=evaluated_limits,
                    timestamp=timestamp,
                )
                return self._finalize_decision(decision, decision_id)

        max_position_pct = max(0.0, min(float(get_config_max_position_pct()), 1.0))
        max_position_value = min(
            float(available_capital),
            float(available_capital) * max_position_pct,
        )
        print(
            "[RISK][SIZING] "
            f"symbol={trade_intent.symbol} mode={run_mode.value} "
            f"entry_price={entry_price} available_capital={available_capital} "
            f"max_position_value={round(max_position_value, 2)} "
            f"requested_quantity={max_position_size}"
        )
        if entry_price is not None and float(entry_price) > 0:
            max_capital_constrained_shares = int(max_position_value // float(entry_price))
            if max_capital_constrained_shares < max_position_size:
                print(
                    "[RISK][CAPITAL_CLAMP] "
                    f"symbol={trade_intent.symbol} requested_shares={max_position_size} "
                    f"clamped_shares={max_capital_constrained_shares} entry_price={entry_price} "
                    f"available_capital={available_capital} max_position_pct={max_position_pct}"
                )
            max_position_size = min(max_position_size, max_capital_constrained_shares)
            if max_position_size <= 0:
                rationale = "Insufficient capital under max position policy."
                decision = RiskDecision(
                    symbol=trade_intent.symbol,
                    allowed=False,
                    max_position_size=0,
                    risk_level="BLOCKED",
                    rationale=rationale,
                    trader_type=trader_type,
                    strategy_name=trade_intent.strategy_name,
                    direction=trade_intent.direction,
                    reason_code="INSUFFICIENT_CAPITAL",
                    overall_action="BLOCK",
                    decision_code="REJECT",
                    risk_reasons=["INSUFFICIENT_CAPITAL"],
                    execution_blocked=True,
                    run_mode=run_mode.value,
                    evaluated_limits=evaluated_limits,
                    timestamp=timestamp,
                )
                return self._finalize_decision(decision, decision_id)

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
            overall_action="ALLOW" if allowed else "BLOCK",
            decision_code="APPROVE" if allowed else "REJECT",
            risk_reasons=[],
            execution_blocked=not allowed,
            run_mode=run_mode.value,
            evaluated_limits=evaluated_limits,
            timestamp=timestamp,
        )
        print(
            "[RISK][SIZING] "
            f"symbol={trade_intent.symbol} mode={run_mode.value} "
            f"entry_price={entry_price} available_capital={available_capital} "
            f"max_position_value={round(max_position_value, 2)} approved_quantity={max_position_size}"
        )
        if applied_multiplier is not None:
            decision.risk_reasons.append(
                f"REGIME_RISK_MULTIPLIER:{applied_multiplier:.2f}"
            )
        return self._finalize_decision(decision, decision_id)


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

        if mode == Epoch5Mode.READ_ONLY:
            decision = "ALLOW_WITH_CONSTRAINTS"
            max_size = 0
            constraints.append("READONLY_NO_EXECUTION")
            triggered_rules.append("MODE_READ_ONLY")

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
