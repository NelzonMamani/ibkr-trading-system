"""Epoch 5 risk audit and gating helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from src.core_engine.events import RiskDecisionRecord, TradeIntentRecord
from src.core_engine.health import HealthStatus
from src.core_engine.state import RunMode
from src.risk.data_quality_contract import data_quality_blocking_causes


DEFAULT_PAPER_CAPITAL = 10000.0


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

    raw_available_capital = float(resolved_account.available_funds)
    available_capital = raw_available_capital

    live_capital_invalid = (
        mode == RunMode.LIVE
        and (
            raw_available_capital <= 0
            or not resolved_account.canonical
            or resolved_account.source != "IBKR_CANONICAL"
        )
    )
    if live_capital_invalid:
        print("[RISK][BLOCK] live mode requires valid broker capital")

    if mode in {RunMode.PAPER, RunMode.SIM} and raw_available_capital <= 0:
        available_capital = DEFAULT_PAPER_CAPITAL
        print("[RISK][CAPITAL_OVERRIDE] using default capital=10000")

    capital_per_symbol = compute_capital_per_symbol(available_capital, focus_count)
    print(
        "[CAPITAL] "
        f"source={resolved_account.source} canonical={resolved_account.canonical} "
        f"raw_available_capital={raw_available_capital} available_capital={available_capital} "
        f"focus_count={focus_count} "
        f"capital_per_symbol={capital_per_symbol} broker_connection_state={resolved_account.broker_connection_state}"
    )

    for intent in intents:
        triggered_rules: List[str] = []
        constraints: List[str] = []
        decision = "ALLOW"
        max_size = 0
        block_reason = ""

        if mode == RunMode.LIVE and live_capital_invalid:
            decisions.append(
                RiskDecisionRecord(
                    symbol=intent.symbol,
                    intent_id=intent.intent_id,
                    decision="BLOCK",
                    max_position_size=0,
                    constraints=constraints,
                    triggered_rules=["CANONICAL_CAPITAL_UNAVAILABLE"],
                    rationale="Triggered rules: CANONICAL_CAPITAL_UNAVAILABLE.",
                    available_funds=available_capital,
                    order_value=0.0,
                    risk_allowed=False,
                    capital_source=resolved_account.source,
                    block_reason="CANONICAL_CAPITAL_UNAVAILABLE",
                    approved_quantity=0,
                )
            )
            continue

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
        raw_entry_price = getattr(intent, "entry_price", None)
        stop_price = getattr(intent, "stop_price", None)
        try:
            entry_price = float(raw_entry_price) if raw_entry_price is not None else None
        except (TypeError, ValueError):
            entry_price = None
        sizing_mode = "STOP_BASED" if stop_price is not None else "CAPITAL_BASED"
        print(
            "[RISK][SIZE_INPUT] "
            f"symbol={intent.symbol} capital_per_symbol={capital_per_symbol} "
            f"entry_price={entry_price} stop_price={stop_price} sizing_mode={sizing_mode}"
        )
        if entry_price is None or entry_price <= 0:
            decision = "BLOCK"
            max_size = 0
            triggered_rules.append("INVALID_ENTRY_PRICE")
            requested_shares = 0
            print(
                f"[RISK][SIZE_BLOCK] symbol={intent.symbol} reason=INVALID_ENTRY_PRICE"
            )
        else:
            requested_shares = int(capital_per_symbol // entry_price)
        if requested_shares <= 0:
            decision = "BLOCK"
            max_size = 0
            if "INSUFFICIENT_CAPITAL_PER_SYMBOL" not in triggered_rules:
                triggered_rules.append("INSUFFICIENT_CAPITAL_PER_SYMBOL")
            print(
                f"[RISK][SIZE_BLOCK] symbol={intent.symbol} reason=INSUFFICIENT_CAPITAL_PER_SYMBOL"
            )
        else:
            print(
                f"[ROSS][POSITION] symbol={intent.symbol} capital_mode=DYNAMIC_FOCUS "
                f"shares={requested_shares} capital_per_symbol={capital_per_symbol}"
            )
        position_value = float(requested_shares) * float(entry_price or 0.0)
        risk_allowed = position_value <= capital_per_symbol + 1e-9

        if mode == RunMode.LIVE and decision != "BLOCK":
            decision = "ALLOW"
            max_size = requested_shares

        if not risk_allowed:
            decision = "BLOCK"
            max_size = 0
            triggered_rules.append("INSUFFICIENT_AVAILABLE_FUNDS")

        sizing_basis = sizing_mode
        approved_quantity = 0
        if decision in {"ALLOW", "ALLOW_WITH_CONSTRAINTS"}:
            approved_quantity = max(1, requested_shares)
            max_size = approved_quantity
            assert approved_quantity > 0

        print(f"[RISK][FINAL] symbol={intent.symbol} approved_quantity={approved_quantity}")
        print(
            "[RISK][SIZE_RESULT] "
            f"symbol={intent.symbol} approved_quantity={approved_quantity} "
            f"notional_estimate={round(position_value, 2)} rationale={decision}"
        )

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
                approved_quantity=approved_quantity,
                sizing_basis=sizing_basis,
            )
        )
    return decisions
