"""Epoch 5 risk audit and gating helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from src.config.config_resolver import get_config
from src.core_engine.events import RiskDecisionRecord, TradeIntentRecord
from src.core_engine.health import HealthStatus
from src.core_engine.state import RunMode


@dataclass(frozen=True)
class AccountSnapshot:
    available_funds: float


def evaluate_trade_intents(
    intents: List[TradeIntentRecord],
    mode: RunMode,
    health_status: HealthStatus | None,
    account: AccountSnapshot | None = None,
) -> List[RiskDecisionRecord]:
    decisions: List[RiskDecisionRecord] = []
    resolved_account = account or AccountSnapshot(available_funds=float(get_config("RISK_ACCOUNT_EQUITY")))
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

        if mode == RunMode.SIM:
            decision = "ALLOW_WITH_CONSTRAINTS"
            max_size = 0
            constraints.append("SIMULATED_NO_EXECUTION")
            triggered_rules.append("MODE_SIM")

        if mode == RunMode.READ_ONLY:
            decision = "ALLOW_WITH_CONSTRAINTS"
            max_size = 0
            constraints.append("READONLY_NO_EXECUTION")
            triggered_rules.append("MODE_READONLY")

        available_funds = float(resolved_account.available_funds)
        account_equity = available_funds
        entry_price = max(float(getattr(intent, "entry_price", 1.0) or 1.0), 0.01)
        requested_shares = 1
        if account_equity < 5_000:
            requested_shares = max(1, int(available_funds / entry_price))
            print(
                f"[ROSS][POSITION] capital_mode=SMALL_ACCOUNT shares={requested_shares} bp={int(available_funds)}"
            )
        position_value = float(requested_shares) * entry_price
        risk_allowed = position_value <= available_funds + 1e-9

        if mode == RunMode.LIVE and decision != "BLOCK":
            decision = "ALLOW"
            max_size = requested_shares

        if not risk_allowed:
            decision = "BLOCK"
            max_size = 0
            triggered_rules.append("INSUFFICIENT_AVAILABLE_FUNDS")

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
                available_funds=available_funds,
                order_value=position_value,
                risk_allowed=risk_allowed,
            )
        )
    return decisions
