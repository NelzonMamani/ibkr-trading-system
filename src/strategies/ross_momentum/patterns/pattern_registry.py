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
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternResult
from src.strategies.strategy_contracts import SessionContext


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
        self._session_allowlist_by_pattern: dict[str, set[SessionContext]] = {
            "P_ORB": {SessionContext.REGULAR},
            "P_OPENING_DRIVE": {SessionContext.REGULAR},
            "P_FAILED_ORB_FAKEOUT": {SessionContext.REGULAR},
        }
        self._setup_name_by_pattern_id: dict[str, str] = {
            "P_GAP_GO": "GAP_GO",
            "P_ORB": "OPENING_RANGE_BREAKOUT",
            "P_FIRST_PULLBACK": "FIRST_PULLBACK",
            "P_PREMKT_BREAK": "PREMARKET_HIGH_BREAK",
            "P_PREMARKET_HIGH_BREAK": "PREMARKET_HIGH_BREAK",
            "P_KEY_LEVEL_BREAK": "KEY_LEVEL_BREAK",
            "P_HOD_BREAK": "HOD_BREAK",
            "P_ABCD": "ABCD",
            "P_CUP_HANDLE": "CUP_HANDLE",
            "P_EMA_PULLBACK": "EMA_PULLBACK",
            "P_TREND_CONTINUATION_STAIR_STEP": "TREND_CONTINUATION_STAIR_STEP",
            "P_VWAP_PULLBACK": "VWAP_PULLBACK",
        }

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
            setup_name = self._setup_name_by_pattern_id.get(pattern_id)
            if setup_name is not None:
                print(f"[SETUP][INVOKE] name={setup_name}")
            print(f"[PATTERN_TRACE][INVOKE] symbol={inputs.symbol} pattern={pattern.name}")
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
            missing_inputs = list(input_summary.get("missing_fields") or [])
            if missing_inputs:
                print(
                    "[PATTERN_TRACE][INPUT_MISSING] "
                    f"symbol={inputs.symbol} pattern_id={pattern_id} missing={missing_inputs}"
                )
            session_allowlist = self._session_allowlist_by_pattern.get(pattern_id)
            if session_allowlist and inputs.session_context not in session_allowlist:
                pattern_trace.skipped = True
                pattern_trace.skip_reason = "session_incompatible"
                pattern_trace.final_outcome = "SKIPPED"
                print(
                    f"[PATTERN_TRACE][RESULT] symbol={inputs.symbol} pattern={pattern.name} detected=False"
                )
                print(
                    f"[PATTERN_TRACE][REJECT] symbol={inputs.symbol} pattern={pattern.name} reason=session_incompatible"
                )
                print(
                    "[PATTERN_TRACE][SKIP] "
                    f"symbol={inputs.symbol} pattern_id={pattern_id} reason=session_incompatible"
                )
                results.append(
                    PatternResult(
                        setup_id=pattern_id,
                        pattern_name=pattern.name,
                        pattern_family=pattern.family,
                        detected=False,
                        direction=getattr(pattern, "direction_bias", Direction.NEUTRAL),
                        confidence=0.0,
                        setup_quality_tags=[],
                        rationale_text="Skipped: session incompatible",
                    )
                )
                if trace_collector is not None:
                    trace_collector(pattern_trace)
                continue
            if bool(getattr(pattern, "is_placeholder", False)):
                pattern_trace.skipped = True
                pattern_trace.skip_reason = "inactive_placeholder"
                pattern_trace.final_outcome = "SKIPPED"
                print(
                    f"[PATTERN_TRACE][RESULT] symbol={inputs.symbol} pattern={pattern.name} detected=False"
                )
                print(
                    f"[PATTERN_TRACE][REJECT] symbol={inputs.symbol} pattern={pattern.name} reason=inactive_placeholder"
                )
                print(
                    "[PATTERN_TRACE][SKIP] "
                    f"symbol={inputs.symbol} pattern_id={pattern_id} reason=inactive_placeholder"
                )
                results.append(
                    PatternResult(
                        setup_id=pattern_id,
                        pattern_name=pattern.name,
                        pattern_family=pattern.family,
                        detected=False,
                        direction=getattr(pattern, "direction_bias", Direction.NEUTRAL),
                        confidence=0.0,
                        setup_quality_tags=[],
                        rationale_text="Skipped: inactive placeholder",
                    )
                )
                if trace_collector is not None:
                    trace_collector(pattern_trace)
                continue
            try:
                result = pattern.evaluate(inputs)
                pattern_trace.detected = bool(result.detected)
                pattern_trace.rejection_reason = result.rejection_reason
                pattern_trace.final_outcome = "DETECTED" if result.detected else "REJECTED"
                if setup_name is not None:
                    print(
                        "[SETUP][RESULT] "
                        f"name={setup_name} detected={bool(result.detected)} "
                        f"reason={result.rejection_reason or 'detected'}"
                    )
                print(
                    f"[PATTERN_TRACE][RESULT] symbol={inputs.symbol} pattern={pattern.name} detected={bool(result.detected)}"
                )
                if pattern_id == "P_ABCD":
                    print(f"[PATTERN_TRACE][RESULT] pattern=ABCD detected={bool(result.detected)}")
                if not result.detected and result.rejection_reason:
                    print(
                        f"[PATTERN_TRACE][REJECT] symbol={inputs.symbol} pattern={pattern.name} reason={result.rejection_reason}"
                    )
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
                    f"[PATTERN_TRACE][RESULT] symbol={inputs.symbol} pattern={pattern.name} detected=False"
                )
                print(
                    f"[PATTERN_TRACE][REJECT] symbol={inputs.symbol} pattern={pattern.name} reason=exception:{exc}"
                )
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
