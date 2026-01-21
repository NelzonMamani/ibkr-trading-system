from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from src.scanner.contracts import StockSelectionPolicy
from src.strategies.ross_momentum.strategy_policy import UniverseSource, UniverseSpec


@dataclass(frozen=True)
class ScannerRequest:
    universe_source: UniverseSource
    ibkr_scan_code: str
    requested_top_n: int
    optional_symbols_override: Optional[Sequence[str]] = None
    region: Optional[str] = None
    instrument: Optional[str] = None
    exchanges: Optional[Sequence[str]] = None


def scanner_request_from_policy(
    policy: StockSelectionPolicy,
    *,
    optional_symbols_override: Optional[Sequence[str]] = None,
) -> ScannerRequest:
    universe: UniverseSpec = getattr(policy, "universe", UniverseSpec())
    requested_top_n = universe.top_n or policy.top_gainers_n
    exchanges = list(universe.exchanges) if universe.exchanges else None
    return ScannerRequest(
        universe_source=universe.source,
        ibkr_scan_code=universe.ibkr_scan_code,
        requested_top_n=int(requested_top_n),
        optional_symbols_override=optional_symbols_override,
        region=universe.region,
        instrument=universe.instrument,
        exchanges=exchanges,
    )
