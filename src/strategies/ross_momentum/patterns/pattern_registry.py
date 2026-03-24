"""Registry of enabled Ross Momentum setup families."""

from __future__ import annotations

from typing import Any, Callable, List

from src.config.config_resolver import get_config
from src.setup_engine.registry import build_tradeable_patterns
from src.setup_engine.setup_families import (
    ClimaxTopPattern,
    EngulfingPattern,
    LongUpperWickPattern,
    MarubozuPattern,
    ThreeSoldiersCrowsPattern,
    VolumeClimaxPattern,
)
from src.strategies.ross_momentum.patterns.pattern_base import PatternBase
from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_trace import RossPatternTrace
from src.strategies.ross_momentum.patterns.pattern_types import PatternResult


def build_additional_heuristic_patterns() -> List[PatternBase]:
    """Optional experimental families; kept empty for deterministic runtime behavior."""
    return []


class RossPatternRegistry:
    def __init__(self) -> None:
        self._patterns: List[PatternBase] = build_tradeable_patterns()
        self._patterns.extend(
            [
                EngulfingPattern(),
                LongUpperWickPattern(),
                MarubozuPattern(),
                ThreeSoldiersCrowsPattern(),
                ClimaxTopPattern(),
                VolumeClimaxPattern(),
            ]
        )

        if get_config("ROSS_ENABLE_ADDITIONAL_HEURISTIC_PATTERNS"):
            print(
                "[ROSS][WARN] Enabling additional heuristic placeholder patterns. "
                "These are experimental and may false-positive."
            )
            self._patterns.extend(build_additional_heuristic_patterns())

    @property
    def patterns(self) -> List[PatternBase]:
        return list(self._patterns)

    @property
    def inactive_pattern_ids(self) -> set[str]:
        return {
            (getattr(pattern, "pattern_id", "") or pattern.name)
            for pattern in self._patterns
            if bool(getattr(pattern, "is_placeholder", False))
        }

    def run(
        self,
        inputs: PatternInputs,
        *,
        trace_context: dict[str, Any] | None = None,
        trace_collector: Callable[[RossPatternTrace], None] | None = None,
    ) -> List[PatternResult]:
        input_summary = dict((trace_context or {}).get("input_summary") or {})
        results: List[PatternResult] = []
        for pattern in self._patterns:
            pattern_id = getattr(pattern, "pattern_id", "") or pattern.name
            pattern_trace = RossPatternTrace(
                symbol=inputs.symbol,
                cycle_id=(trace_context or {}).get("cycle_id"),
                strategy_key=(trace_context or {}).get("strategy_key", "ross_momentum"),
                session_label=(trace_context or {}).get("session_label"),
                session_phase=(trace_context or {}).get("session_phase"),
                runtime_mode=(trace_context or {}).get("runtime_mode"),
                symbol_source=(trace_context or {}).get("symbol_source"),
                pattern_id=pattern_id,
                pattern_name=pattern.name,
                setup_family_id=pattern_id,
                invoked=True,
                input_summary=input_summary,
                input_quality_flags=list(inputs.data_quality_flags),
            )
            print(
                "[PATTERN_TRACE][CALL] "
                f"symbol={inputs.symbol} pattern={pattern.name} pattern_id={pattern_id} "
                f"registry=RossPatternRegistry strategy={(trace_context or {}).get('strategy_key', 'ross_momentum')}"
            )
            print(
                "[PATTERN_TRACE][INPUT] "
                f"symbol={inputs.symbol} pattern_id={pattern_id} input_summary={input_summary}"
            )
            try:
                result = pattern.evaluate(inputs)
                pattern_trace.detected = bool(result.detected)
                pattern_trace.rejection_reason = result.rejection_reason
                pattern_trace.final_outcome = "DETECTED" if result.detected else "REJECTED"
                print(
                    "[PATTERN_TRACE][RESULT] "
                    f"symbol={inputs.symbol} pattern={pattern.name} pattern_id={pattern_id} "
                    f"detected={bool(result.detected)} reason={result.rejection_reason or 'detected'} "
                    f"pattern_name={result.pattern_name}"
                )
                results.append(result)
            except Exception as exc:
                pattern_trace.detected = False
                pattern_trace.final_outcome = "ERROR"
                pattern_trace.rejection_reason = f"exception:{exc}"
                pattern_trace.exception = repr(exc)
                print(
                    "[PATTERN_TRACE][ERROR] "
                    f"symbol={inputs.symbol} pattern_id={pattern_id} pattern={pattern.name} error={exc!r}"
                )
                print(
                    "[PATTERN_TRACE][RESULT] "
                    f"symbol={inputs.symbol} pattern={pattern.name} pattern_id={pattern_id} "
                    "detected=False reason=exception"
                )
            finally:
                if trace_collector is not None:
                    trace_collector(pattern_trace)
        return results

    @property
    def pattern_ids(self) -> List[str]:
        return [getattr(pattern, "pattern_id", "") or pattern.name for pattern in self._patterns]
