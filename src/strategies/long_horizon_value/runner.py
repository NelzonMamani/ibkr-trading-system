"""
Strategy Runner for Long Horizon Value.
Orchestrator calls this runner; it emits TradeIntents only.
"""

from __future__ import annotations

from typing import Iterable

from src.config.runtime_config import RunMode
from src.models.data_models import TradeIntent
from src.strategies.long_horizon_value.strategy_policy_v2 import POLICY_V2


class LongHorizonValueRunner:
    def run(self, context):
        """Deterministic watchlist-to-intent adapter for Wave 2 validation."""
        watchlist = self._coerce_watchlist(context)
        mode = self._resolve_mode(context)
        session_label = self._resolve_session_label(context)
        reports = [
            {
                "status": "READY",
                "reason": "LongHorizonValue deterministic fallback pipeline active.",
                "watchlist_k": len(watchlist),
            }
        ]

        underwriting_report = self._evaluate_underwriting_session_gate(
            session_label=session_label,
            watchlist=watchlist,
            context=context,
        )
        reports.append(underwriting_report)

        intents: list[TradeIntent] = []
        fallback_allowed = mode in {RunMode.SIM, RunMode.PAPER}
        if not fallback_allowed:
            reports.append(
                {
                    "status": "FALLBACK_DISABLED",
                    "reason": "Deterministic fallback is only allowed in SIM/PAPER.",
                    "mode": mode.value,
                }
            )

        for row in watchlist:
            if not fallback_allowed:
                break
            symbol = self._symbol_of(row)
            if not symbol:
                continue
            intent = TradeIntent(
                symbol=symbol,
                direction="LONG",
                strategy_name="LongHorizonValue",
                confidence=0.55,
                rationale="Deterministic long-horizon value fallback: watchlist candidate accepted.",
                trader_type="LONG_HORIZON_VALUE",
                pattern_name="LHV_DETERMINISTIC_FALLBACK",
                data_quality_flags=list(getattr(row, "data_quality_flags", []) or []),
            )
            intents.append(intent)
            # Keep deterministic issuance conservative: single intent per cycle.
            break

        if not intents and watchlist:
            reports.append(
                {
                    "status": "NO_SYMBOLS",
                    "reason": "Watchlist rows missing symbol field.",
                }
            )

        intents, approval_reports = self._enforce_manual_approval_gate(intents=intents, context=context, mode=mode)
        reports.extend(approval_reports)
        intents, allocation_reports = self._apply_capital_allocation_layer(intents=intents, context=context)
        reports.extend(allocation_reports)

        reports.append(
            {
                "status": "SUMMARY",
                "mode": mode.value,
                "session_label": session_label,
                "trade_intents": len(intents),
            }
        )
        return {"trade_intents": intents, "reports": reports, "metrics": {"watchlist_k": len(watchlist)}}

    def _enforce_manual_approval_gate(
        self,
        *,
        intents: list[TradeIntent],
        context,
        mode: RunMode,
    ) -> tuple[list[TradeIntent], list[dict]]:
        if not intents:
            return intents, []

        reports: list[dict] = []
        mode_label = str(getattr(mode, "value", mode) or "").upper()
        manual_approval = bool(context.get("manual_approval")) if isinstance(context, dict) else bool(getattr(context, "manual_approval", False))
        gated_actions = {str(action).upper() for action in POLICY_V2.long_horizon_underwriting_batch.manual_approval_required_for}

        for intent in intents:
            action = self._resolve_intent_action(intent)

            if mode_label == RunMode.READ_ONLY.value:
                setattr(intent, "executable", False)
                reports.append({"status": "READ_ONLY_BLOCK"})

            if action not in gated_actions:
                continue

            if mode_label == RunMode.READ_ONLY.value or not manual_approval:
                setattr(intent, "executable", False)
                setattr(intent, "approval_status", "PENDING_MANUAL_APPROVAL")
                reports.append(
                    {
                        "status": "MANUAL_APPROVAL_REQUIRED",
                        "action": action,
                        "reason": "Manual approval required by long-horizon underwriting doctrine.",
                    }
                )

        return intents, reports

    def _apply_capital_allocation_layer(self, *, intents: list[TradeIntent], context) -> tuple[list[TradeIntent], list[dict]]:
        if not intents:
            return intents, []

        policy_model = POLICY_V2.long_horizon_capital_allocation
        risk_model = POLICY_V2.risk_model
        max_position_pct = float(risk_model.max_position_pct)
        tier_order = tuple(str(tier).upper() for tier in policy_model.conviction_tiers)
        tier_target_weights = {str(tier).upper(): float(weight) for tier, weight in policy_model.tier_target_weights.items()}
        default_tier = tier_order[-1] if tier_order else ""

        reports: list[dict] = []
        for intent in intents:
            action = self._resolve_intent_action(intent)
            if action not in {"BUY", "ADD"}:
                continue

            tier = self._resolve_conviction_tier(context=context, symbol=getattr(intent, "symbol", None), default_tier=default_tier)
            target_weight = tier_target_weights.get(tier, tier_target_weights.get(default_tier, 0.0))
            target_weight = min(float(target_weight), max_position_pct)
            existing_position_weight = self._resolve_existing_position_weight(context=context, symbol=getattr(intent, "symbol", None))

            if action == "BUY" or existing_position_weight <= 0.0:
                tranche_weight = 0.5 * target_weight
            else:
                remaining_weight = max(target_weight - existing_position_weight, 0.0)
                tranche_weight = remaining_weight / 3.0

            setattr(intent, "target_weight", float(target_weight))
            setattr(intent, "proposed_tranche_weight", float(tranche_weight))
            setattr(intent, "conviction_tier", tier)

            reports.append(
                {
                    "status": "CAPITAL_ALLOCATION_SNAPSHOT",
                    "symbol": getattr(intent, "symbol", None),
                    "conviction_tier": tier,
                    "target_weight": float(target_weight),
                    "proposed_tranche_weight": float(tranche_weight),
                    "max_position_pct": max_position_pct,
                }
            )

        return intents, reports

    def _evaluate_underwriting_session_gate(self, *, session_label: str, watchlist: list[object], context) -> dict:
        policy_model = POLICY_V2.long_horizon_underwriting_batch
        normalized_session = str(session_label or "UNKNOWN").upper()
        allowed_sessions = tuple(str(label).upper() for label in policy_model.allowed_sessions)
        forbid_sessions = tuple(str(label).upper() for label in policy_model.forbid_sessions)

        should_run_underwriting = normalized_session in allowed_sessions and normalized_session not in forbid_sessions
        if not should_run_underwriting:
            return {
                "status": "UNDERWRITING_SKIPPED_SESSION_GUARD",
                "reason": "Long-horizon underwriting batch is restricted to CLOSED/OVN runtime windows.",
                "session_label": normalized_session,
                "allowed_sessions": allowed_sessions,
                "forbid_sessions": forbid_sessions,
            }

        return self._run_underwriting_batch(
            session_label=normalized_session,
            watchlist=watchlist,
            context=context,
        )

    def _run_underwriting_batch(self, *, session_label: str, watchlist: list[object], context) -> dict:
        del context
        return {
            "status": "UNDERWRITING_BATCH_EXECUTED",
            "session_label": session_label,
            "artifact": "underwriting_dossier",
            "candidate_count": len(watchlist),
        }

    @staticmethod
    def _coerce_watchlist(context) -> list[object]:
        if isinstance(context, dict):
            payload = context.get("watchlist")
        else:
            payload = getattr(context, "watchlist", None)
        if isinstance(payload, list):
            return payload
        if isinstance(payload, Iterable):
            return list(payload)
        return []

    @staticmethod
    def _resolve_mode(context) -> RunMode:
        raw = None
        if isinstance(context, dict):
            raw = context.get("mode")
        else:
            raw = getattr(context, "mode", None)
        label = str(raw or RunMode.SIM.value).upper()
        return RunMode.__members__.get(label, RunMode.SIM)

    @staticmethod
    def _resolve_session_label(context) -> str:
        raw = None
        if isinstance(context, dict):
            raw = context.get("session_label")
        else:
            raw = getattr(context, "session_label", None)
        return str(raw or "UNKNOWN").upper()

    @staticmethod
    def _resolve_conviction_tier(*, context, symbol: str | None, default_tier: str) -> str:
        if isinstance(context, dict):
            payload = context.get("conviction_tier")
        else:
            payload = getattr(context, "conviction_tier", None)

        if isinstance(payload, dict):
            if symbol and symbol in payload:
                return str(payload[symbol]).upper()
            return str(payload.get("default", default_tier)).upper()
        return str(payload or default_tier).upper()

    @staticmethod
    def _resolve_existing_position_weight(*, context, symbol: str | None) -> float:
        if isinstance(context, dict):
            payload = context.get("existing_position_weight", 0.0)
        else:
            payload = getattr(context, "existing_position_weight", 0.0)

        if isinstance(payload, dict):
            if symbol and symbol in payload:
                payload = payload[symbol]
            else:
                payload = payload.get("default", 0.0)

        try:
            return float(payload)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _symbol_of(row: object) -> str | None:
        if isinstance(row, dict):
            return row.get("symbol")
        return getattr(row, "symbol", None)

    @staticmethod
    def _resolve_intent_action(intent: TradeIntent) -> str:
        action = getattr(intent, "action", None)
        if action:
            return str(action).upper()
        direction = str(getattr(intent, "direction", "") or "").upper()
        if direction == "LONG":
            return "BUY"
        if direction == "SHORT":
            return "SELL"
        return direction
