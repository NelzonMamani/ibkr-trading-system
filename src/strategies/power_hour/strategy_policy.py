"""Authoritative policy for Power Hour strategy."""

from __future__ import annotations

from dataclasses import dataclass

from src.config.runtime_config import RunMode


@dataclass(frozen=True)
class StrategyPolicy:
    name: str = "power_hour"
    display_name: str = "POWER_HOUR"
    version: str = "v1"
    trader_type: str = "MOMENTUM"
    allowed_sessions: tuple[str, ...] = ('REG', 'AH', 'NA')
    allowed_modes_for_intents: tuple[RunMode, ...] = (RunMode.SIM, RunMode.PAPER)
    min_price: float = 1.0
    min_volume: float = 1000.0
    max_intents_per_cycle: int = 1


POLICY = StrategyPolicy()
