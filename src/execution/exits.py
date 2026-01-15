"""Exit plan helpers for Epoch 5 (placeholder)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExitPlan:
    stop: str
    target: str | None = None


def build_exit_plan(stop_model: str, target_model: str | None = None) -> ExitPlan:
    return ExitPlan(stop=stop_model, target=target_model)
