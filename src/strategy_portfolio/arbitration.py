"""Arbitration layer for resolving competing strategy intents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .contracts import SignalIntent
from .reason_codes import ReasonCode


@dataclass(frozen=True)
class ArbitrationInput:
    symbol: str
    strategy_id: str
    priority: int
    proposed_intent: SignalIntent


@dataclass(frozen=True)
class ArbitrationResult:
    symbol: str
    winner_strategy_id: str | None
    winner_intent: SignalIntent
    denied: list[tuple[str, str]]
    exit_only: list[tuple[str, str]]


_SIGNAL_INTENT_RANK = {
    SignalIntent.ENTER_LONG: 0,
    SignalIntent.ENTER_SHORT: 1,
    SignalIntent.EXIT_ONLY: 2,
    SignalIntent.HOLD: 3,
    SignalIntent.NO_TRADE: 4,
}


def _dedupe_inputs(
    inputs: Iterable[ArbitrationInput],
) -> tuple[list[ArbitrationInput], list[tuple[str, str]]]:
    """Ensure one intent per strategy per symbol, deterministically."""

    by_strategy: dict[str, ArbitrationInput] = {}
    denied: list[tuple[str, str]] = []
    for entry in inputs:
        current = by_strategy.get(entry.strategy_id)
        if current is None:
            by_strategy[entry.strategy_id] = entry
            continue

        candidate_rank = (-entry.priority, _SIGNAL_INTENT_RANK[entry.proposed_intent])
        current_rank = (-current.priority, _SIGNAL_INTENT_RANK[current.proposed_intent])
        if candidate_rank < current_rank:
            denied.append((current.strategy_id, ReasonCode.ARBITRATION_DENY.value))
            by_strategy[entry.strategy_id] = entry
        else:
            denied.append((entry.strategy_id, ReasonCode.ARBITRATION_DENY.value))

    return list(by_strategy.values()), denied


def arbitrate_symbol(
    inputs_for_symbol: Iterable[ArbitrationInput],
    loser_position_map: dict[str, bool] | None = None,
    strategy_budget_map: dict[str, float] | None = None,
) -> ArbitrationResult:
    inputs = [entry for entry in inputs_for_symbol if entry.proposed_intent != SignalIntent.NO_TRADE]
    loser_position_map = loser_position_map or {}
    strategy_budget_map = strategy_budget_map or {}
    symbol = next((entry.symbol for entry in inputs_for_symbol), "")

    inputs, denied = _dedupe_inputs(inputs)
    budget_denied: list[tuple[str, str]] = []
    if strategy_budget_map:
        budgeted_inputs: list[ArbitrationInput] = []
        for entry in inputs:
            budget = strategy_budget_map.get(entry.strategy_id)
            if budget is not None and budget <= 0:
                budget_denied.append(
                    (entry.strategy_id, ReasonCode.ALLOCATION_EXHAUSTED.value)
                )
            else:
                budgeted_inputs.append(entry)
        inputs = budgeted_inputs

    if not inputs:
        return ArbitrationResult(
            symbol=symbol,
            winner_strategy_id=None,
            winner_intent=SignalIntent.NO_TRADE,
            denied=denied + budget_denied,
            exit_only=[],
        )

    sorted_inputs = sorted(
        inputs,
        key=lambda entry: (-entry.priority, entry.strategy_id),
    )
    winner = sorted_inputs[0]
    denied = denied + budget_denied
    exit_only: list[tuple[str, str]] = []

    for loser in sorted_inputs[1:]:
        reason = ReasonCode.ARBITRATION_DENY_LOWER_PRIORITY.value
        if loser_position_map.get(loser.strategy_id, False):
            exit_only.append((loser.strategy_id, reason))
        else:
            denied.append((loser.strategy_id, reason))

    return ArbitrationResult(
        symbol=winner.symbol,
        winner_strategy_id=winner.strategy_id,
        winner_intent=winner.proposed_intent,
        denied=denied,
        exit_only=exit_only,
    )


def arbitrate_all(
    inputs: Iterable[ArbitrationInput],
    loser_position_map: dict[str, bool] | None = None,
    strategy_budget_map: dict[str, float] | None = None,
) -> list[ArbitrationResult]:
    grouped: dict[str, list[ArbitrationInput]] = {}
    for entry in inputs:
        grouped.setdefault(entry.symbol, []).append(entry)

    results = []
    for symbol in sorted(grouped.keys()):
        results.append(
            arbitrate_symbol(
                grouped[symbol],
                loser_position_map=loser_position_map,
                strategy_budget_map=strategy_budget_map,
            )
        )
    return results
