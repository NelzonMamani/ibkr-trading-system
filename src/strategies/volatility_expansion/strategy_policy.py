"""Authoritative policy for Volatility Expansion strategy."""

from __future__ import annotations

from dataclasses import dataclass

from src.config.runtime_config import RunMode


@dataclass(frozen=True)
class StrategyPolicy:
    name: str = "volatility_expansion"
    display_name: str = "VOLATILITY_EXPANSION"
    version: str = "v1"
    trader_type: str = "QUANT"
    allowed_sessions: tuple[str, ...] = ('REG', 'NA')
    allowed_modes_for_intents: tuple[RunMode, ...] = (RunMode.SIM, RunMode.PAPER)
    min_price: float = 1.0
    min_volume: float = 1000.0
    max_intents_per_cycle: int = 1


POLICY = StrategyPolicy()
