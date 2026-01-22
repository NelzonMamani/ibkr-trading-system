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


def arbitrate_symbol(
    inputs_for_symbol: Iterable[ArbitrationInput],
    loser_position_map: dict[str, bool] | None = None,
) -> ArbitrationResult:
    inputs = [entry for entry in inputs_for_symbol if entry.proposed_intent != SignalIntent.NO_TRADE]
    loser_position_map = loser_position_map or {}

    if not inputs:
        return ArbitrationResult(
            symbol="",
            winner_strategy_id=None,
            winner_intent=SignalIntent.NO_TRADE,
            denied=[],
            exit_only=[],
        )

    sorted_inputs = sorted(
        inputs,
        key=lambda entry: (-entry.priority, entry.strategy_id),
    )
    winner = sorted_inputs[0]
    denied: list[tuple[str, str]] = []
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
            )
        )
    return results
