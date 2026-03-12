"""Epoch 5 risk audit and gating helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from src.config.config_resolver import get_config
from src.core_engine.events import RiskDecisionRecord, TradeIntentRecord
from src.core_engine.health import HealthStatus
from src.core_engine.state import RunMode
from src.risk.data_quality_contract import data_quality_blocking_causes


@dataclass(frozen=True)
class AccountSnapshot:
    available_funds: float
    source: str = "UNKNOWN"
    canonical: bool = False
    broker_connection_state: str = "UNKNOWN"


def compute_capital_per_symbol(available_capital: float, focus_count: int) -> float:
    if focus_count <= 0:
        return 0.0
    return float(available_capital) / float(focus_count)


def evaluate_trade_intents(
    intents: List[TradeIntentRecord],
    mode: RunMode,
    health_status: HealthStatus | None,
    account: AccountSnapshot | None = None,
) -> List[RiskDecisionRecord]:
    decisions: List[RiskDecisionRecord] = []
    resolved_account = account or AccountSnapshot(available_funds=0.0, source="UNAVAILABLE", canonical=False, broker_connection_state="MISSING")
    focus_symbols = {str(intent.symbol).upper() for intent in intents if str(intent.symbol).strip()}
    focus_count = len(focus_symbols)
    if focus_count == 0:
        print("[CAPITAL] available_capital=0 focus_count=0 capital_per_symbol=0")
        return decisions

    available_capital = float(resolved_account.available_funds)
    capital_per_symbol = compute_capital_per_symbol(available_capital, focus_count)

    live_capital_invalid = (
        mode == RunMode.LIVE
        and (not resolved_account.canonical or resolved_account.source != "IBKR_CANONICAL" or available_capital <= 0)
    )
    print(
        "[CAPITAL] "
        f"source={resolved_account.source} canonical={resolved_account.canonical} "
        f"available_capital={available_capital} focus_count={focus_count} "
        f"capital_per_symbol={capital_per_symbol} broker_connection_state={resolved_account.broker_connection_state}"
    )

    for intent in intents:
        triggered_rules: List[str] = []
        constraints: List[str] = []
        decision = "ALLOW"
        max_size = 0
        block_reason = ""

        if health_status == HealthStatus.CRITICAL:
            decision = "BLOCK"
            max_size = 0
            triggered_rules.append("HEALTH_CRITICAL")

        data_quality_causes = data_quality_blocking_causes(intent.tags)
        if data_quality_causes:
            decision = "BLOCK"
            max_size = 0
            triggered_rules.append("DATA_QUALITY")
            print(f"[RISK][AUDIT] symbol={intent.symbol} data_quality_causes={data_quality_causes}")

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

        available_funds = available_capital
        entry_price = max(float(getattr(intent, "entry_price", 1.0) or 1.0), 0.01)
        requested_shares = int(capital_per_symbol / entry_price)
        if requested_shares <= 0:
            decision = "BLOCK"
            max_size = 0
            triggered_rules.append("INSUFFICIENT_CAPITAL_PER_SYMBOL")
            requested_shares = 0
            print(
                f"[ROSS][POSITION] symbol={intent.symbol} capital_per_symbol={capital_per_symbol} "
                f"entry_price={entry_price} shares=0"
            )
        else:
            print(
                f"[ROSS][POSITION] symbol={intent.symbol} capital_mode=DYNAMIC_FOCUS "
                f"shares={requested_shares} capital_per_symbol={capital_per_symbol}"
            )
        position_value = float(requested_shares) * entry_price
        risk_allowed = position_value <= capital_per_symbol + 1e-9

        if mode == RunMode.LIVE and live_capital_invalid:
            decision = "BLOCK"
            max_size = 0
            block_reason = "CANONICAL_CAPITAL_UNAVAILABLE"
            triggered_rules.append("CANONICAL_CAPITAL_UNAVAILABLE")
        elif mode == RunMode.LIVE and decision != "BLOCK":
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
                capital_source=resolved_account.source,
                block_reason=block_reason,
                approved_quantity=max_size,
            )
        )
    return decisions
