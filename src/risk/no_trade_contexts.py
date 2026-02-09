"""Explicit no-trade contexts and deterministic evaluation helpers."""

from __future__ import annotations

from dataclasses import dataclass

from src.config.runtime_config import RunMode
from src.models.risk_decision import (
    BROKER_READONLY_BLOCK,
    CIRCUIT_BREAKER_TRIPPED,
    DATA_QUALITY_BLOCK,
    EXECUTION_DISABLED,
    LIVE_READ_ONLY_BLOCK,
    RISK_SESSION_BLOCK,
)


@dataclass(frozen=True)
class NoTradeContext:
    code: str
    rationale: str


def evaluate_no_trade_contexts(
    *,
    run_mode: RunMode,
    execution_enabled: bool,
    session_blocked: bool,
    broker_readonly: bool,
    circuit_breaker_tripped: bool,
    data_quality_block: bool,
) -> list[NoTradeContext]:
    """Return ordered no-trade contexts for hard enforcement."""

    contexts: list[NoTradeContext] = []

    if circuit_breaker_tripped:
        contexts.append(
            NoTradeContext(
                code=CIRCUIT_BREAKER_TRIPPED,
                rationale="Circuit breaker active — no new trades allowed.",
            )
        )
    if run_mode == RunMode.READ_ONLY:
        contexts.append(
            NoTradeContext(
                code=LIVE_READ_ONLY_BLOCK,
                rationale="READ_ONLY mode forbids new executions.",
            )
        )
    if not execution_enabled:
        contexts.append(
            NoTradeContext(
                code=EXECUTION_DISABLED,
                rationale="Execution disabled by configuration.",
            )
        )
    if broker_readonly and run_mode == RunMode.LIVE:
        contexts.append(
            NoTradeContext(
                code=BROKER_READONLY_BLOCK,
                rationale="Broker marked READ_ONLY; execution forbidden in LIVE mode.",
            )
        )
    if session_blocked:
        contexts.append(
            NoTradeContext(
                code=RISK_SESSION_BLOCK,
                rationale="Market session is not approved for trading.",
            )
        )
    if data_quality_block:
        contexts.append(
            NoTradeContext(
                code=DATA_QUALITY_BLOCK,
                rationale="Data quality flags require a no-trade block.",
            )
        )

    return contexts
