"""Deterministic Ross-style SignalEngineV1 for teaching-first signals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List

from src.models.data_models import PatternResult, ScannerCandidate
from src.signals.signal_event import SignalEvent
from src.signals.signal_types import SignalType


@dataclass(frozen=True)
class SignalEngineConfig:
    enabled: bool = True
    min_strength: float = 0.55
    max_signals_per_symbol: int = 2
    max_signals_per_cycle: int = 8


class SignalEngineV1:
    name = "SignalEngineV1"

    def __init__(self, config: SignalEngineConfig | None = None) -> None:
        self.config = config or SignalEngineConfig()

    def generate(
        self,
        scanner_output: List[ScannerCandidate],
        pattern_output: List[PatternResult],
        tick: int,
    ) -> List[SignalEvent]:
        if not self.config.enabled:
            return []

        candidates_by_symbol = {candidate.symbol: candidate for candidate in scanner_output}
        patterns_by_symbol = self._group_patterns(pattern_output)
        signals: List[SignalEvent] = []

        for symbol in sorted(candidates_by_symbol.keys()):
            candidate = candidates_by_symbol[symbol]
            if getattr(candidate, "data_quality_flags", []):
                print(
                    "[SIGNALS] Skipping symbol due to data quality flags "
                    f"symbol={symbol} flags={candidate.data_quality_flags}"
                )
                continue
            gap_percent = float(getattr(candidate, "gap_percent", 0.0) or 0.0)
            rvol = float(getattr(candidate, "rvol", 0.0) or 0.0)
            float_millions = float(getattr(candidate, "float_millions", 0.0) or 0.0)
            base_strength = self._base_strength(gap_percent, rvol, float_millions)
            symbol_signals: List[SignalEvent] = []

            if gap_percent >= 8.0 and float_millions <= 50.0 and rvol >= 2.0:
                symbol_signals.append(
                    self._build_signal(
                        symbol,
                        SignalType.HOD_BREAK,
                        min(base_strength + 0.05, 0.90),
                        tick,
                        gap_percent,
                        rvol,
                        float_millions,
                        "gap>=8 & float<=50 & rvol>=2",
                    )
                )

            if 4.0 <= gap_percent < 8.0 and rvol >= 2.0:
                symbol_signals.append(
                    self._build_signal(
                        symbol,
                        SignalType.MOMO_BREAKOUT,
                        base_strength,
                        tick,
                        gap_percent,
                        rvol,
                        float_millions,
                        "gap 4-8 & rvol>=2",
                    )
                )

            if rvol >= 3.5 and gap_percent >= 6.0:
                symbol_signals.append(
                    self._build_signal(
                        symbol,
                        SignalType.ORB_BREAK,
                        min(base_strength + 0.03, 0.90),
                        tick,
                        gap_percent,
                        rvol,
                        float_millions,
                        "rvol>=3.5 & gap>=6",
                    )
                )

            if self._has_pattern(patterns_by_symbol.get(symbol, []), {"GAP_AND_GO"}):
                symbol_signals.append(
                    self._build_signal(
                        symbol,
                        SignalType.FIRST_PULLBACK_LONG,
                        min(base_strength + 0.02, 0.90),
                        tick,
                        gap_percent,
                        rvol,
                        float_millions,
                        "pattern contains 'GAP_AND_GO'",
                    )
                )

            if self._has_pattern(
                patterns_by_symbol.get(symbol, []),
                {"ORB_BREAKOUT", "FIRST_PULLBACK", "VWAP_RECLAIM", "HOD_BREAK"},
            ):
                symbol_signals.append(
                    self._build_signal(
                        symbol,
                        SignalType.VWAP_RECLAIM,
                        min(base_strength + 0.01, 0.90),
                        tick,
                        gap_percent,
                        rvol,
                        float_millions,
                        "pattern contains Ross momentum pattern",
                    )
                )

            filtered = [
                signal
                for signal in symbol_signals
                if signal.strength >= self.config.min_strength
            ]
            filtered.sort(
                key=lambda signal: (-signal.strength, signal.signal_type.value)
            )
            signals.extend(filtered[: self.config.max_signals_per_symbol])

        signals.sort(key=lambda signal: (-signal.strength, signal.symbol))
        return signals[: self.config.max_signals_per_cycle]

    def _group_patterns(
        self, patterns: Iterable[PatternResult]
    ) -> Dict[str, List[PatternResult]]:
        grouped: Dict[str, List[PatternResult]] = {}
        for pattern in patterns:
            grouped.setdefault(pattern.symbol, []).append(pattern)
        return grouped

    def _has_pattern(
        self, patterns: Iterable[PatternResult], needles: set[str]
    ) -> bool:
        return any(pattern.pattern_name in needles for pattern in patterns)

    def _base_strength(
        self, gap_percent: float, rvol: float, float_millions: float
    ) -> float:
        base = 0.50
        if gap_percent >= 8.0:
            base += 0.10
        elif gap_percent >= 4.0:
            base += 0.06
        if rvol >= 3.0:
            base += 0.10
        elif rvol >= 2.0:
            base += 0.06
        if float_millions <= 50.0:
            base += 0.08
        elif float_millions <= 100.0:
            base += 0.04
        return max(0.30, min(base, 0.90))

    def _build_signal(
        self,
        symbol: str,
        signal_type: SignalType,
        strength: float,
        tick: int,
        gap_percent: float,
        rvol: float,
        float_millions: float,
        rule_label: str,
    ) -> SignalEvent:
        rationale = (
            f"symbol={symbol} tick={tick} gap%={gap_percent:.2f} "
            f"rvol={rvol:.2f} float={float_millions:.2f} "
            f"rule={rule_label} strength={strength:.2f}"
        )
        return SignalEvent(
            symbol=symbol,
            signal_type=signal_type,
            strength=strength,
            tick=tick,
            source=self.name,
            rationale=rationale,
            gap_percent=gap_percent,
            rvol=rvol,
            float_millions=float_millions,
        )
